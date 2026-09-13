from datetime import timedelta

import sqlalchemy as sa
from astropy.time import Time
from baselayer.app.flow import Flow
from sqlalchemy.orm import selectinload

from ..utils.naive_datetime import utcnow_naive
from . import FollowUpAPI


class TURBOAPI(FollowUpAPI):
    """On-demand TURBO forced photometry.

    Record-only: submit just marks the request `submitted`. The migizi
    forced-photometry worker polls SkyPortal for submitted TURBO requests
    (outbound HTTPS, like the poster -- no inbound port on migizi), runs
    tier-aware forced photometry over the archive (default 5-min stacks; raw
    30s frames only within a short window), posts the points (origin=fp), and
    marks the request complete. An oversized request is parked with a
    size-warning status until re-submitted with `confirm_large`.
    """

    @staticmethod
    async def submit(request, session, **kwargs):
        from ..models import FollowupRequest

        # async sessions raise on implicit lazy loads; eager-load what we walk
        request = await session.scalar(
            sa.select(FollowupRequest)
            .where(FollowupRequest.id == request.id)
            .options(selectinload(FollowupRequest.obj))
        )

        payload = request.payload
        for key in ("start_date", "end_date"):
            if key not in payload:
                raise ValueError(f"{key} is a required parameter")
        mjd_min = Time(payload["start_date"], format="iso").mjd
        mjd_max = Time(payload["end_date"], format="iso").mjd
        if mjd_max < mjd_min:
            raise ValueError("start_date must be before end_date")

        request.status = "submitted"
        await session.commit()

        if kwargs.get("refresh_source", False):
            flow = Flow()
            flow.push(
                "*",
                "skyportal/REFRESH_SOURCE",
                payload={"obj_key": request.obj.internal_key},
            )
        if kwargs.get("refresh_requests", False):
            flow = Flow()
            flow.push(
                request.last_modified_by_id,
                "skyportal/REFRESH_FOLLOWUP_REQUESTS",
            )

    @staticmethod
    async def delete(request, session, **kwargs):
        from ..models import FollowupRequest

        request = await session.scalar(
            sa.select(FollowupRequest)
            .where(FollowupRequest.id == request.id)
            .options(selectinload(FollowupRequest.obj))
        )
        last_modified_by_id = request.last_modified_by_id
        obj_internal_key = request.obj.internal_key

        await session.delete(request)
        await session.commit()

        if kwargs.get("refresh_source", False):
            flow = Flow()
            flow.push(
                "*",
                "skyportal/REFRESH_SOURCE",
                payload={"obj_key": obj_internal_key},
            )
        if kwargs.get("refresh_requests", False):
            flow = Flow()
            flow.push(
                last_modified_by_id,
                "skyportal/REFRESH_FOLLOWUP_REQUESTS",
            )

    form_json_schema_forced_photometry = {
        "type": "object",
        "properties": {
            "start_date": {
                "type": "string",
                "default": str(utcnow_naive() - timedelta(days=30)).replace("T", ""),
                "title": "Start Date (UT)",
            },
            "end_date": {
                "type": "string",
                "default": str(utcnow_naive()).replace("T", ""),
                "title": "End Date (UT)",
            },
            "tier_minutes": {
                "type": "integer",
                "enum": [15, 5, 1],
                "default": 5,
                "title": "Stack cadence (minutes)",
            },
            "raw": {
                "type": "boolean",
                "default": False,
                "title": "Raw 30s frames (window must be <= 24h)",
            },
            "confirm_large": {
                "type": "boolean",
                "default": False,
                "title": "Confirm large request (skip the size warning)",
            },
        },
        "required": [
            "start_date",
            "end_date",
        ],
    }

    ui_json_schema = {}

    form_json_schema_altdata = {
        "type": "object",
        "properties": {
            "api_token": {
                "type": "string",
                "title": "API Token",
            },
        },
        "required": [
            "api_token",
        ],
    }
