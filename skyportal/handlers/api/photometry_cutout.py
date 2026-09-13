from datetime import timedelta

import sqlalchemy as sa
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.orm import selectinload

from baselayer.app.access import auth_or_token, permissions

from ...models import Photometry, PhotometryCutoutRequest, Thumbnail
from ...utils.naive_datetime import utcnow_naive
from ..base import BaseHandler

CUTOUT_TYPE = "dif"
MAX_REQUEST_POINTS = 5000
STALE_AFTER = timedelta(minutes=15)


class PhotometryCutoutRequestBody(BaseModel):
    """Request body for requesting photometry cutouts."""

    model_config = ConfigDict(extra="forbid")

    photometry_ids: list[int] = Field(
        min_length=1,
        max_length=MAX_REQUEST_POINTS,
        description="Photometry points of this source whose cutouts to make.",
    )


class PhotometryCutoutFailureBody(BaseModel):
    """Request body for marking a photometry cutout request failed."""

    model_config = ConfigDict(extra="forbid")

    error: str = Field(description="Why the cutout could not be made.")


def image_id_of(point):
    try:
        return int((point.altdata or {})["image_id"])
    except (KeyError, TypeError, ValueError):
        return None


class SourcePhotometryCutoutsHandler(BaseHandler):
    @auth_or_token
    async def get(self, obj_id: str):
        """
        ---
        summary: Get a source's photometry cutouts
        description: |
          Every requested difference-image cutout behind a source's photometry
          points: ready ones with their URL, and pending or failed requests.
        tags:
          - thumbnails
        parameters:
          - in: path
            name: obj_id
            required: true
            schema:
              type: string
        responses:
          200:
            content:
              application/json:
                schema: Success
        """
        async with self.AsyncSession() as session:
            thumbnails = (
                (
                    await session.scalars(
                        Thumbnail.select(session.user_or_token).where(
                            Thumbnail.obj_id == obj_id,
                            Thumbnail.type == CUTOUT_TYPE,
                            Thumbnail.photometry_id.isnot(None),
                        )
                    )
                )
                .unique()
                .all()
            )
            requests = (
                (
                    await session.scalars(
                        PhotometryCutoutRequest.select(session.user_or_token).where(
                            PhotometryCutoutRequest.photometry_id.in_(
                                sa.select(Photometry.id).where(
                                    Photometry.obj_id == obj_id
                                )
                            )
                        )
                    )
                )
                .unique()
                .all()
            )
            stale_before = utcnow_naive() - STALE_AFTER
            ready = {t.photometry_id: t.public_url for t in thumbnails}
            data = [
                {
                    "photometry_id": photometry_id,
                    "status": "ready",
                    "public_url": public_url,
                    "error": None,
                    "stale": False,
                }
                for photometry_id, public_url in ready.items()
            ]
            data.extend(
                {
                    "photometry_id": r.photometry_id,
                    "status": r.status,
                    "public_url": None,
                    "error": r.error,
                    "stale": r.status == "pending" and r.created_at < stale_before,
                }
                for r in requests
                if r.photometry_id not in ready
            )
        return self.success(data=data)

    @auth_or_token
    async def post(self, obj_id: str, *, body: PhotometryCutoutRequestBody = None):
        """
        ---
        summary: Request photometry cutouts
        description: |
          Queue the difference-image cutout behind each given photometry point
          of a source. Points already cut out or already queued are left alone;
          a failed or stale request is queued again. Points without a recorded
          archive frame are reported as unavailable.
        tags:
          - thumbnails
        parameters:
          - in: path
            name: obj_id
            required: true
            schema:
              type: string
        responses:
          200:
            content:
              application/json:
                schema: Success
        """
        body = self.parse_body(PhotometryCutoutRequestBody)
        ids = set(body.photometry_ids)
        statuses = dict.fromkeys(ids, "unavailable")
        async with self.AsyncSession() as session:
            points = (
                (
                    await session.scalars(
                        Photometry.select(session.user_or_token).where(
                            Photometry.id.in_(ids), Photometry.obj_id == obj_id
                        )
                    )
                )
                .unique()
                .all()
            )
            ready = set(
                (
                    await session.scalars(
                        sa.select(Thumbnail.photometry_id).where(
                            Thumbnail.photometry_id.in_(ids),
                            Thumbnail.type == CUTOUT_TYPE,
                        )
                    )
                ).all()
            )
            existing = {
                r.photometry_id: r
                for r in (
                    await session.scalars(
                        sa.select(PhotometryCutoutRequest).where(
                            PhotometryCutoutRequest.photometry_id.in_(ids)
                        )
                    )
                ).all()
            }
            stale_before = utcnow_naive() - STALE_AFTER
            for point in points:
                if point.id in ready:
                    statuses[point.id] = "ready"
                    continue
                if image_id_of(point) is None:
                    continue
                statuses[point.id] = "pending"
                previous = existing.get(point.id)
                if previous is not None:
                    if (
                        previous.status == "pending"
                        and previous.created_at >= stale_before
                    ):
                        continue
                    await session.delete(previous)
                    await session.flush()
                session.add(
                    PhotometryCutoutRequest(
                        photometry_id=point.id,
                        requester_id=self.associated_user_object.id,
                    )
                )
            await session.commit()
        return self.success(data={"statuses": {str(k): v for k, v in statuses.items()}})


class PhotometryCutoutRequestHandler(BaseHandler):
    @permissions(["Upload data"])
    async def get(self):
        """
        ---
        summary: List pending photometry cutout requests
        description: |
          Pending cutout requests, oldest first, with the position, filter and
          archive image of the photometry point each one is for.
        tags:
          - thumbnails
        parameters:
          - in: query
            name: afterID
            nullable: true
            schema:
              type: integer
            description: Only return requests with a larger ID. Defaults to 0.
          - in: query
            name: limit
            nullable: true
            schema:
              type: integer
            description: Maximum number of requests. Defaults to 500, at most 1000.
        responses:
          200:
            content:
              application/json:
                schema: Success
        """
        after_id = self.get_query_argument("afterID", 0, type=int)
        limit = self.get_query_argument("limit", 500, type=int)
        if after_id is None or limit is None:
            return self.error("afterID and limit must be integers")
        limit = max(1, min(limit, 1000))

        async with self.AsyncSession() as session:
            requests = (
                (
                    await session.scalars(
                        PhotometryCutoutRequest.select(session.user_or_token)
                        .where(
                            PhotometryCutoutRequest.status == "pending",
                            PhotometryCutoutRequest.id > after_id,
                        )
                        .order_by(PhotometryCutoutRequest.id)
                        .limit(limit)
                    )
                )
                .unique()
                .all()
            )
            points = {
                p.id: p
                for p in (
                    await session.scalars(
                        sa.select(Photometry)
                        .where(Photometry.id.in_([r.photometry_id for r in requests]))
                        .options(selectinload(Photometry.obj))
                    )
                )
                .unique()
                .all()
            }
            data = []
            for r in requests:
                point = points.get(r.photometry_id)
                image_id = image_id_of(point) if point is not None else None
                if image_id is None:
                    continue
                data.append(
                    {
                        "id": r.id,
                        "photometry_id": point.id,
                        "obj_id": point.obj_id,
                        "ra": point.obj.ra,
                        "dec": point.obj.dec,
                        "filter": point.filter,
                        "image_id": image_id,
                    }
                )
        return self.success(data=data)

    @permissions(["Upload data"])
    async def put(self, request_id: int, *, body: PhotometryCutoutFailureBody = None):
        """
        ---
        summary: Mark a photometry cutout request failed
        description: Record why the cutout for a request could not be made.
        tags:
          - thumbnails
        parameters:
          - in: path
            name: request_id
            required: true
            schema:
              type: integer
        responses:
          200:
            content:
              application/json:
                schema: Success
          400:
            content:
              application/json:
                schema: Error
        """
        body = self.parse_body(PhotometryCutoutFailureBody)
        async with self.AsyncSession() as session:
            request = await session.scalar(
                PhotometryCutoutRequest.select(
                    session.user_or_token, mode="update"
                ).where(PhotometryCutoutRequest.id == int(request_id))
            )
            if request is None:
                return self.error(
                    f"Cannot find photometry cutout request with ID: {request_id}"
                )
            request.status = "failed"
            request.error = body.error[:1000]
            await session.commit()
        return self.success()
