from typing import Annotated, Literal

import sqlalchemy as sa
from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    StringConstraints,
    model_validator,
)
from sqlalchemy.orm import selectinload

from baselayer.app.access import auth_or_token, permissions

from ...models import Allocation, Instrument, TurboSourceRequest
from ..base import BaseHandler

MAX_RADIUS_ARCSEC = 60.0
DEFAULT_RADIUS_ARCSEC = 3.0
MAX_LIST = 1000


class TurboSourceRequestBody(BaseModel):
    """Request body for bringing a star from TURBO's database into SkyPortal."""

    model_config = ConfigDict(extra="forbid")

    star: (
        Annotated[
            str, StringConstraints(strip_whitespace=True, min_length=1, max_length=64)
        ]
        | None
    ) = Field(
        None,
        description="TURBO star ID, e.g. STELLAR26aaabcde. Alternative to ra and dec.",
    )
    ra: float | None = Field(
        None, ge=0, lt=360, description="ICRS Right Ascension [deg]."
    )
    dec: float | None = Field(
        None, ge=-90, le=90, description="ICRS Declination [deg]."
    )
    radius: float = Field(
        DEFAULT_RADIUS_ARCSEC,
        gt=0,
        le=MAX_RADIUS_ARCSEC,
        description="Search radius around the position [arcsec]; the nearest "
        "TURBO star inside it is used.",
    )
    group_ids: list[int] | None = Field(
        None,
        min_length=1,
        description="Groups to share the source with. Defaults to the "
        "allocation's group and its default share groups.",
    )
    allocation_id: int | None = Field(
        None,
        description="TURBO allocation to serve the request. Defaults to the first.",
    )

    @model_validator(mode="after")
    def position_xor_star(self):
        if self.star is not None:
            if self.ra is not None or self.dec is not None:
                raise ValueError("give either star or ra and dec, not both")
        elif self.ra is None or self.dec is None:
            raise ValueError("give either star or both ra and dec")
        return self


class TurboSourceRequestResultBody(BaseModel):
    """Request body for recording the outcome of a request."""

    model_config = ConfigDict(extra="forbid")

    status: Literal["completed", "failed"]
    message: str | None = Field(None, max_length=1000)
    obj_id: str | None = None
    n_points: int | None = Field(None, ge=0)


def serialize(request):
    return {
        "id": request.id,
        "created_at": request.created_at,
        "modified": request.modified,
        "requester": request.requester.username if request.requester else None,
        "allocation_id": request.allocation_id,
        "star": request.star,
        "ra": request.ra,
        "dec": request.dec,
        "radius": request.radius,
        "group_ids": request.group_ids,
        "status": request.status,
        "message": request.message,
        "obj_id": request.obj_id,
        "n_points": request.n_points,
    }


class TurboSourceRequestHandler(BaseHandler):
    @auth_or_token
    async def get(self, request_id: int | None = None):
        """
        ---
        single:
          summary: Get a TURBO source request
          description: Retrieve one request to bring a star from TURBO's database into SkyPortal.
          tags:
            - turbo
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
        multiple:
          summary: List TURBO source requests
          description: |
            Requests to bring stars from TURBO's database into SkyPortal that
            the user can read, newest first.
          tags:
            - turbo
          parameters:
            - in: query
              name: status
              nullable: true
              schema:
                type: string
              description: Only requests with this status (pending, completed or failed).
            - in: query
              name: allocationID
              nullable: true
              schema:
                type: integer
              description: Only requests served by this allocation.
            - in: query
              name: mine
              nullable: true
              schema:
                type: boolean
              description: Only the user's own requests.
            - in: query
              name: limit
              nullable: true
              schema:
                type: integer
              description: Maximum number of requests. Defaults to 100, at most 1000.
          responses:
            200:
              content:
                application/json:
                  schema: Success
        """
        async with self.AsyncSession() as session:
            stmt = TurboSourceRequest.select(session.user_or_token).options(
                selectinload(TurboSourceRequest.requester)
            )
            if request_id is not None:
                request = await session.scalar(
                    stmt.where(TurboSourceRequest.id == request_id)
                )
                if request is None:
                    return self.error(
                        f"Cannot find TURBO source request with ID: {request_id}"
                    )
                return self.success(data=serialize(request))

            status = self.get_query_argument("status", None)
            allocation_id = self.get_query_argument("allocationID", None)
            limit = self.get_query_argument("limit", 100)
            try:
                limit = max(1, min(int(limit), MAX_LIST))
                if allocation_id is not None:
                    allocation_id = int(allocation_id)
            except ValueError:
                return self.error("limit and allocationID must be integers")
            if status is not None:
                stmt = stmt.where(TurboSourceRequest.status == status)
            if allocation_id is not None:
                stmt = stmt.where(TurboSourceRequest.allocation_id == allocation_id)
            if self.get_query_argument("mine", "false").lower() == "true":
                stmt = stmt.where(
                    TurboSourceRequest.requester_id == self.associated_user_object.id
                )
            requests = (
                (
                    await session.scalars(
                        stmt.order_by(TurboSourceRequest.id.desc()).limit(limit)
                    )
                )
                .unique()
                .all()
            )
            data = [serialize(r) for r in requests]
        return self.success(data=data)

    @auth_or_token
    async def post(self, *, body: TurboSourceRequestBody = None):
        """
        ---
        summary: Bring a star from TURBO's database into SkyPortal
        description: |
          Queue a request for the TURBO poster to look up a star, by TURBO ID or
          by position, in TURBO's own database and post it as a source with its
          full light curve. The poster picks the request up from SkyPortal and
          records the outcome on it. An identical request that is still pending
          is returned instead of a new one.
        tags:
          - turbo
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
        body = self.parse_body(TurboSourceRequestBody)
        async with self.AsyncSession() as session:
            stmt = (
                Allocation.select(session.user_or_token)
                .join(Instrument, Allocation.instrument_id == Instrument.id)
                .where(Instrument.api_classname == "TURBOAPI")
                .order_by(Allocation.id)
            )
            if body.allocation_id is not None:
                stmt = stmt.where(Allocation.id == body.allocation_id)
            allocation = await session.scalar(stmt)
            if allocation is None:
                return self.error("No TURBO allocation is accessible to you.")

            if body.group_ids is None:
                group_ids = {
                    allocation.group_id,
                    *(allocation.default_share_group_ids or []),
                }
            else:
                group_ids = set(body.group_ids)
                accessible = {g.id for g in self.current_user.accessible_groups}
                if not group_ids <= accessible:
                    return self.error(
                        f"Groups not accessible: {sorted(group_ids - accessible)}"
                    )
            group_ids = sorted(group_ids)

            ra = None if body.ra is None else round(body.ra, 6)
            dec = None if body.dec is None else round(body.dec, 6)
            star = body.star

            existing = await session.scalar(
                TurboSourceRequest.select(session.user_or_token)
                .where(
                    TurboSourceRequest.status == "pending",
                    TurboSourceRequest.allocation_id == allocation.id,
                    TurboSourceRequest.star.is_not_distinct_from(star),
                    TurboSourceRequest.ra.is_not_distinct_from(ra),
                    TurboSourceRequest.dec.is_not_distinct_from(dec),
                    TurboSourceRequest.radius == body.radius,
                    TurboSourceRequest.group_ids == group_ids,
                )
                .order_by(TurboSourceRequest.id)
            )
            if existing is not None:
                return self.success(data={"id": existing.id, "existing": True})

            request = TurboSourceRequest(
                allocation_id=allocation.id,
                requester_id=self.associated_user_object.id,
                star=star,
                ra=ra,
                dec=dec,
                radius=body.radius,
                group_ids=group_ids,
                status="pending",
            )
            session.add(request)
            await session.commit()
            request_id = request.id
        return self.success(data={"id": request_id, "existing": False})

    @permissions(["Upload data"])
    async def put(self, request_id: int, *, body: TurboSourceRequestResultBody = None):
        """
        ---
        summary: Record the outcome of a TURBO source request
        description: |
          Mark a request completed or failed, with a message and the source it
          brought in.
        tags:
          - turbo
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
        body = self.parse_body(TurboSourceRequestResultBody)
        async with self.AsyncSession() as session:
            request = await session.scalar(
                TurboSourceRequest.select(session.user_or_token, mode="update").where(
                    TurboSourceRequest.id == request_id
                )
            )
            if request is None:
                return self.error(
                    f"Cannot find TURBO source request with ID: {request_id}"
                )
            request.status = body.status
            request.message = body.message
            request.obj_id = body.obj_id
            request.n_points = body.n_points
            await session.commit()
        return self.success()

    @auth_or_token
    async def delete(self, request_id: int):
        """
        ---
        summary: Delete a TURBO source request
        description: Remove a request from the list; the source it brought in stays.
        tags:
          - turbo
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
        async with self.AsyncSession() as session:
            request = await session.scalar(
                TurboSourceRequest.select(session.user_or_token, mode="delete").where(
                    TurboSourceRequest.id == request_id
                )
            )
            if request is None:
                return self.error(
                    f"Cannot find TURBO source request with ID: {request_id}"
                )
            await session.delete(request)
            await session.commit()
        return self.success()
