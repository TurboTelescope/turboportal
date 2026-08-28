import json
from datetime import timedelta

import aiohttp
import sqlalchemy as sa
from astropy.time import Time
from baselayer.app.env import load_env
from baselayer.app.flow import Flow
from baselayer.log import make_log
from sqlalchemy.orm import selectinload

from ..utils import http
from ..utils.naive_datetime import utcnow_naive
from . import FollowUpAPI

env, cfg = load_env()

if cfg.get("app.turbo.port") is None:
    TURBO_URL = f"{cfg['app.turbo.protocol']}://{cfg['app.turbo.host']}"
else:
    TURBO_URL = (
        f"{cfg['app.turbo.protocol']}://{cfg['app.turbo.host']}:{cfg['app.turbo.port']}"
    )

log = make_log("facility_apis/turbo")


class TURBOAPI(FollowUpAPI):
    """On-demand TURBO forced photometry.

    Posts a request to the internal migizi forced-photometry service, which
    runs tier-aware forced photometry over the TURBO archive (default 5-min
    stacks; raw 30s frames only within a short window) and commits the points
    back to SkyPortal itself (origin=fp), so no result polling is needed here.
    """

    @staticmethod
    async def submit(request, session, **kwargs):
        from ..models import FacilityTransaction, FollowupRequest

        # async sessions raise on implicit lazy loads; eager-load what we walk
        request = await session.scalar(
            sa.select(FollowupRequest)
            .where(FollowupRequest.id == request.id)
            .options(
                selectinload(FollowupRequest.allocation),
                selectinload(FollowupRequest.obj),
            )
        )

        altdata = request.allocation.altdata
        if not altdata or "api_token" not in altdata:
            raise ValueError("Missing allocation api_token.")

        payload = request.payload
        for key in ("start_date", "end_date"):
            if key not in payload:
                raise ValueError(f"{key} is a required parameter")
        mjd_min = Time(payload["start_date"], format="iso").mjd
        mjd_max = Time(payload["end_date"], format="iso").mjd
        if mjd_max < mjd_min:
            raise ValueError("start_date must be before end_date")

        share_groups = request.allocation.default_share_group_ids or []
        body = {
            "obj_id": request.obj_id,
            "ra": request.obj.ra,
            "dec": request.obj.dec,
            "mjd_min": mjd_min,
            "mjd_max": mjd_max,
            "tier_minutes": payload.get("tier_minutes", 5),
            "raw": payload.get("raw", False),
            "group_ids": list({request.allocation.group_id, *share_groups}),
        }

        url = f"{TURBO_URL}/forcedphot/queue/"
        headers = {
            "Authorization": f"token {altdata['api_token']}",
            "Content-Type": "application/json",
        }

        async with aiohttp.ClientSession() as http_session:
            async with http_session.post(url, headers=headers, json=body) as r:
                content = await r.text()
                status = r.status

        # the service enqueues (202) or completes (200/201) and posts points
        # itself; anything else is a rejection surfaced on the request.
        if status in (200, 201, 202):
            request.status = "submitted"
        elif status == 429:
            request.status = f"throttled: {content}"
        else:
            request.status = f"rejected: {content}"

        transaction = FacilityTransaction(
            request=http.serialize_aiohttp_request(
                "POST", url, headers, json.dumps(body)
            ),
            response=await http.serialize_aiohttp_response(r, content),
            followup_request=request,
            initiator_id=request.last_modified_by_id,
        )
        session.add(transaction)

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
