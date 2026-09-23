import functools
import weakref

import sqlalchemy as sa
from pydantic import BaseModel, ConfigDict, Field
from skyportal_py_models.annotations import AnnotationPostBody
from skyportal_py_models.photometry import PhotometryPostBody
from skyportal_py_models.sources import SourcePatchBody
from skyportal_py_models.thumbnails import ThumbnailPostBody
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from baselayer.app.access import permissions
from baselayer.app.models import async_bulk_verify, pending_rows, public
from baselayer.log import make_log

from ...models import Annotation, Filter, Obj, User
from ...utils.data_access import any_group_auto_publishes
from ..base import BaseHandler, RequestError
from .annotation import annotation_groups, obj_annotation, update_annotation
from .candidate.candidate import post_candidate
from .photometry import (
    MAX_NUMBER_ROWS,
    get_group_ids,
    get_stream_ids,
    insert_new_photometry_data,
    standardize_photometry_data,
)
from .source import patch_source, publish_saved_source, save_source
from .thumbnail import post_thumbnail

log = make_log("api/turbo_frame")


class FrameSave(BaseModel):
    model_config = ConfigDict(extra="forbid")

    group_ids: list[int] | None = Field(
        None,
        description="Groups to save the source to. Defaults to all of the "
        "user's groups.",
    )
    score: float | None = Field(None, description="Machine learning score.")


class FrameThumbnail(BaseModel):
    model_config = ConfigDict(extra="forbid")

    ttype: str = Field(description="Thumbnail type, e.g. 'new', 'ref' or 'sub'.")
    data: str = Field(description="base64-encoded PNG file contents.")


class FramePosition(BaseModel):
    model_config = ConfigDict(extra="forbid")

    ra: float = Field(description="ICRS Right Ascension [deg].")
    dec: float = Field(description="ICRS Declination [deg].")


class FrameObject(BaseModel):
    model_config = ConfigDict(extra="forbid", coerce_numbers_to_str=True)

    id: str = Field(description="Name of the object.")
    ra: float | None = Field(None, description="ICRS Right Ascension [deg].")
    dec: float | None = Field(None, description="ICRS Declination [deg].")
    passed_at: str = Field(
        description="Arrow-parseable datetime string indicating when passed filter."
    )
    save: FrameSave | None = Field(
        None, description="Save the object as a source, as POST /api/sources."
    )
    thumbnails: list[FrameThumbnail] | None = Field(
        None, description="Thumbnails to post, as POST /api/thumbnail."
    )
    annotation: AnnotationPostBody | None = Field(
        None,
        description="Annotation to post, or to put if the object already has "
        "one from this origin.",
    )
    patch: SourcePatchBody | None = Field(
        None, description="Source update, as PATCH /api/sources/{obj_id}."
    )
    position: FramePosition | None = Field(
        None,
        description="Position update, as PATCH /api/sources/{obj_id} with "
        "allow_candidate_position_update.",
    )


class TurboFramePostBody(BaseModel):
    """Request body for posting a frame's detections."""

    model_config = ConfigDict(extra="forbid")

    filter_ids: list[int] = Field(
        default_factory=list,
        description="Filters each object passed, as in POST /api/candidates.",
    )
    objects: list[FrameObject] = Field(default_factory=list)
    photometry: list[PhotometryPostBody] = Field(
        default_factory=list,
        description="POST /api/photometry payloads, posted after the objects.",
    )


def gated(mode, rows):
    # a public policy grants every row, so checking it is a wasted query
    return [row for row in rows if getattr(type(row), mode) is not public]


async def verify_unchecked(session, checked):
    """``session.verify()``, minus the read check of rows already in ``checked``,
    for the rows loaded or written since the last call."""
    read_rows, updated_rows, deleted_rows, new_rows = pending_rows(session)
    read_rows = [row for row in read_rows if row not in checked]
    for mode, rows in (
        ("read", read_rows),
        ("update", updated_rows),
        ("delete", deleted_rows),
    ):
        await async_bulk_verify(session, mode, gated(mode, rows), session.user_or_token)
    await session.flush()
    await async_bulk_verify(
        session, "create", gated("create", new_rows), session.user_or_token
    )
    checked.update(session.identity_map.values())


def discard_unchecked(session, checked):
    # rows a failed savepoint loaded but never verified would fail the next check
    for row in [row for row in session.identity_map.values() if row not in checked]:
        session.expunge(row)


def drop_points(data, failed):
    """Drop, in place, the points of ``data`` whose object is in ``failed``, one
    of them at least, and return the positions of the points kept."""
    obj_ids = data["obj_id"]
    if not isinstance(obj_ids, list):
        return []
    keep = [i for i, obj_id in enumerate(obj_ids) if str(obj_id) not in failed]

    def pick(value):
        if isinstance(value, list) and len(value) == len(obj_ids):
            return [value[i] for i in keep]
        return value

    for key, value in data.items():
        if key in ("group_ids", "stream_ids"):
            continue
        if isinstance(value, dict):
            data[key] = {k: pick(v) for k, v in value.items()}
        else:
            data[key] = pick(value)
    return keep


class TurboFrameHandler(BaseHandler):
    @permissions(["Upload data"])
    async def post(self, *, body: TurboFramePostBody = None):
        """
        ---
        summary: Post a frame's detections
        description: |
          The TURBO poster's per-detection requests for a frame, applied in one
          transaction. For each object, in order: POST /api/candidates, then
          optionally POST /api/sources, POST /api/thumbnail per thumbnail, the
          annotation (PUT /api/sources/{obj_id}/annotations/{id} if one from
          that origin exists, else POST), PATCH /api/sources/{obj_id} and the
          position PATCH. Then each photometry batch as POST /api/photometry,
          except that points already posted are kept and their ids returned,
          and points of objects that failed are left out and listed in the
          batch's `skipped`. Each object and each batch runs in its own
          savepoint: a failure rolls back only that object or batch and is
          reported in its result. Objects with an annotation also need the
          Annotate permission.
        tags:
          - candidates
          - sources
          - photometry
        responses:
          200:
            content:
              application/json:
                schema: Success
        """
        body = self.parse_body(TurboFramePostBody)
        ids = [item.id for item in body.objects]
        if len(set(ids)) != len(ids):
            return self.error("An object may appear only once per frame.")
        if any(item.annotation is not None for item in body.objects) and not (
            {"Annotate", "System admin"} & set(self.current_user.permissions)
        ):
            return self.error("Annotations need the Annotate permission.", status=403)

        async with self.AsyncSession() as session:
            user_or_token = session.user_or_token
            # weak, so a row nothing holds any more leaves it with the identity map
            frame = {"groups": {}, "checked": weakref.WeakSet()}
            if body.objects:
                frame["filters"] = (
                    (
                        await session.scalars(
                            Filter.select(user_or_token).where(
                                Filter.id.in_(body.filter_ids)
                            )
                        )
                    )
                    .unique()
                    .all()
                )
                if not frame["filters"]:
                    return self.error("At least one valid filter ID must be provided.")
                frame["objs"] = {
                    obj.id: obj
                    for obj in (
                        await session.scalars(
                            Obj.select(user_or_token).where(Obj.id.in_(ids))
                        )
                    ).all()
                }
                # What the annotation POST-then-PUT upsert finds: an existing
                # annotation the user may both read (GET) and update (PUT).
                origins = {i.annotation.origin for i in body.objects if i.annotation}
                frame["annotations"] = {}
                if origins:
                    readable = Annotation.select(user_or_token, columns=[Annotation.id])
                    annotations = await session.scalars(
                        Annotation.select(user_or_token, mode="update")
                        .options(selectinload(Annotation.groups))
                        .where(
                            Annotation.obj_id.in_(ids),
                            Annotation.origin.in_(origins),
                            Annotation.id.in_(readable),
                        )
                    )
                    frame["annotations"] = {
                        (a.obj_id, a.origin): a for a in annotations.unique().all()
                    }
            checked = frame["checked"]
            await verify_unchecked(session, checked)

            results, done = {}, []
            for item in body.objects:
                try:
                    async with session.begin_nested():
                        done.append(await self._post_object(session, item, body, frame))
                except Exception as e:
                    discard_unchecked(session, checked)
                    # cached groups may have been among the discarded rows
                    frame["groups"].clear()
                    results[item.id] = {"ok": False, "error": str(e)}
                    continue
                results[item.id] = {"ok": True, "error": None}

            failed = {obj_id for obj_id, r in results.items() if not r["ok"]}
            photometry = []
            for batch in body.photometry:
                obj_ids = (
                    batch.obj_id if isinstance(batch.obj_id, list) else [batch.obj_id]
                )
                skipped = sorted({str(obj_id) for obj_id in obj_ids} & failed)
                data = batch.model_dump(exclude_unset=True)
                keep = drop_points(data, failed) if skipped else None
                if keep == []:
                    photometry.append(
                        {
                            "ok": False,
                            "error": f"Objects that failed in this request: {skipped}",
                            "ids": [],
                        }
                    )
                    continue
                try:
                    async with session.begin_nested():
                        phot_ids = await self._post_photometry(session, data, checked)
                except Exception as e:
                    discard_unchecked(session, checked)
                    photometry.append({"ok": False, "error": str(e), "ids": []})
                    continue
                result = {"ok": True, "error": None, "ids": phot_ids}
                if skipped:
                    # ids stay aligned with the posted points
                    placed = dict(zip(keep, phot_ids))
                    result["ids"] = [placed.get(i) for i in range(len(obj_ids))]
                    result["skipped"] = skipped
                photometry.append(result)

            # Every row was verified at its endpoint's commit point above; the
            # session's own commit would also read-check rows that those
            # endpoints only create-check.
            await verify_unchecked(session, checked)
            await AsyncSession.commit(session)

        log(
            f"Frame from {self.associated_user_object.username}: "
            f"{len(results) - len(failed)}/{len(results)} objects, "
            f"{sum(p['ok'] for p in photometry)}/{len(photometry)} photometry batches"
        )
        await self._publish([d for d in done if d["saved"] is not None])
        for d in done:
            if d["saved"] is not None:
                self.push_all("skyportal/REFRESH_SOURCE", {"obj_key": d["key"]})
                self.push_all("skyportal/REFRESH_CANDIDATE", {"id": d["key"]})
            elif d["refresh"]:
                self.push_all("skyportal/REFRESH_SOURCE", {"obj_key": d["key"]})
            if d["moved"]:
                self.push_all(
                    "skyportal/REFRESH_SOURCE_POSITION", {"obj_key": d["key"]}
                )

        return self.success(data={"objects": results, "photometry": photometry})

    async def _post_object(self, session, item, body, frame):
        user = self.associated_user_object
        # awaited where each endpoint commits, so it checks the same rows
        verify = functools.partial(verify_unchecked, session, frame["checked"])
        step = "candidate"
        try:
            obj, _ = await post_candidate(
                {
                    **item.model_dump(
                        include={"id", "ra", "dec", "passed_at"}, exclude_unset=True
                    ),
                    "filter_ids": body.filter_ids,
                },
                user,
                session,
                commit=verify,
                obj=frame["objs"].get(item.id),
                filters=frame["filters"],
            )

            saved = None
            if item.save is not None:
                step = "save"
                _, groups, savers, _, _ = await save_source(
                    {
                        **item.model_dump(
                            include={"id", "ra", "dec"}, exclude_unset=True
                        ),
                        **item.save.model_dump(exclude_unset=True),
                    },
                    user.id,
                    session,
                    commit=verify,
                )
                saved = groups, savers

            for thumbnail in item.thumbnails or []:
                step = f"thumbnail {thumbnail.ttype}"
                await post_thumbnail(
                    ThumbnailPostBody(
                        obj_id=item.id, **thumbnail.model_dump()
                    ).model_dump(),
                    user.id,
                    session,
                    commit=verify,
                )

            if item.annotation is not None:
                step = "annotation"
                await self._upsert_annotation(session, item.id, item.annotation, frame)
                await verify()

            moved = False
            if item.patch is not None:
                step = "patch"
                _, moved = await patch_source(
                    {**item.patch.model_dump(exclude_unset=True), "id": item.id},
                    user,
                    session,
                    commit=verify,
                )

            if item.position is not None:
                step = "position"
                position = SourcePatchBody(
                    ra=item.position.ra,
                    dec=item.position.dec,
                    allow_candidate_position_update=True,
                )
                _, position_moved = await patch_source(
                    {**position.model_dump(exclude_unset=True), "id": item.id},
                    user,
                    session,
                    commit=verify,
                )
                moved = moved or position_moved
        except Exception as e:
            raise RequestError(f"{step}: {e}") from e

        return {
            "id": obj.id,
            "key": obj.internal_key,
            "saved": saved,
            "moved": moved,
            "refresh": any(
                x is not None for x in (item.annotation, item.patch, item.position)
            ),
        }

    async def _upsert_annotation(self, session, obj_id, body, frame):
        existing = frame["annotations"].get((obj_id, body.origin))
        if existing is not None:
            # PUT {data, group_ids}: groups are left alone when not given
            groups = None
            if body.group_ids is not None:
                groups = await self._annotation_groups(session, body.group_ids, frame)
            update_annotation(existing, body.data, None, groups)
            return
        group_ids = body.group_ids or [
            g.id for g in self.current_user.accessible_groups
        ]
        groups = await self._annotation_groups(session, group_ids, frame)
        session.add(
            obj_annotation(
                obj_id, body.origin, body.data, self.associated_user_object.id, groups
            )
        )

    async def _annotation_groups(self, session, group_ids, frame):
        key = tuple(group_ids)
        if key not in frame["groups"]:
            frame["groups"][key] = await annotation_groups(
                session, self.current_user, group_ids
            )
        return frame["groups"][key]

    async def _post_photometry(self, session, data, checked):
        # PhotometryHandler.post's steps, leaving the commit to the frame and
        # keeping rows already posted, since the poster re-sends whole frames
        user = self.associated_user_object
        group_ids = await get_group_ids(dict(data), user, session)
        stream_ids = await get_stream_ids(dict(data), user, session)
        df, instrument_cache = await standardize_photometry_data(data, session)
        if len(df.index) > MAX_NUMBER_ROWS:
            raise RequestError(
                f"Maximum number of photometry rows to post exceeded: {len(df.index)} > {MAX_NUMBER_ROWS}. "
                "Please break up the data into smaller sets and try again"
            )
        obj_id = df["obj_id"].unique()[0]
        log(
            f"Pending request from {user.username} for object {obj_id} with {len(df.index)} rows"
        )
        ids, upload_id = await insert_new_photometry_data(
            df,
            instrument_cache,
            group_ids,
            stream_ids,
            user,
            session,
            duplicates="ignore",
            commit=functools.partial(verify_unchecked, session, checked),
        )
        log(
            f"Request from {user.username} for object {obj_id} with {len(df.index)} rows complete with upload_id {upload_id}"
        )
        return ids

    async def _publish(self, saved):
        # post_source_async's auto-publishing, run after the commit as it is
        # there, in a session of its own so its commits verify only its rows
        if not saved:
            return
        async with self.AsyncSession() as session:
            publishes = {}
            for d in saved:
                groups, savers = d["saved"]
                key = frozenset(group.id for group in groups)
                if key not in publishes:
                    publishes[key] = await any_group_auto_publishes(session, list(key))
                if not publishes[key]:
                    continue
                try:
                    obj = await session.scalar(sa.select(Obj).where(Obj.id == d["id"]))
                    users = {
                        u.id: u
                        for u in (
                            await session.scalars(
                                sa.select(User).where(
                                    User.id.in_({s.id for s in savers.values()})
                                )
                            )
                        ).all()
                    }
                    await publish_saved_source(
                        session,
                        obj,
                        groups,
                        {gid: users[s.id] for gid, s in savers.items()},
                    )
                except Exception as e:
                    log(f"Auto-publishing source {d['id']} failed: {e}")
