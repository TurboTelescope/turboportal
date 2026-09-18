import sqlalchemy as sa
from sqlalchemy.orm import selectinload

from baselayer.app import models as baselayer_models
from baselayer.app.flow import Flow

from . import MMAAPI, FollowUpAPI


class TURBOTOOAPI(FollowUpAPI):
    @staticmethod
    async def submit(request, session, **kwargs):
        from ..models import FollowupRequest

        request = await session.scalar(
            sa.select(FollowupRequest)
            .where(FollowupRequest.id == request.id)
            .options(selectinload(FollowupRequest.obj))
        )
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
    async def update(request, session, **kwargs):
        from ..models import FollowupRequest

        request = await session.scalar(
            sa.select(FollowupRequest)
            .where(FollowupRequest.id == request.id)
            .options(selectinload(FollowupRequest.obj))
        )
        if request.status != "submitted":
            raise ValueError(f"Cannot update a request with status {request.status}")
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
        request.status = "deleted"
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

    form_json_schema = {
        "type": "object",
        "properties": {
            "filters": {
                "type": "array",
                "title": "Filters",
                "items": {"type": "string", "enum": ["sdssg", "sdssr"]},
                "uniqueItems": True,
                "minItems": 1,
                "default": ["sdssg", "sdssr"],
            },
            "exposure_time": {
                "type": "number",
                "title": "Exposure Time [s]",
                "default": 30.0,
            },
            "n_frames": {
                "type": "integer",
                "title": "Frames per visit",
                "default": 10,
            },
            "urgency": {
                "type": "string",
                "title": "Urgency",
                "enum": ["urgent", "normal", "low"],
                "default": "normal",
            },
            "hours_valid": {
                "type": "number",
                "title": "Valid for (hours)",
                "default": 24.0,
            },
        },
        "required": ["filters", "urgency"],
    }

    ui_json_schema = {"filters": {"ui:widget": "checkboxes"}}


class TURBOMMAAPI(MMAAPI):
    @staticmethod
    async def send(request, session):
        from ..models import ObservationPlanRequest

        request = await session.scalar(
            sa.select(ObservationPlanRequest).where(
                ObservationPlanRequest.id == request.id
            )
        )
        request.status = "submitted to TURBO queue"

    @staticmethod
    async def remove(request):
        from ..models import ObservationPlanRequest

        async with baselayer_models.async_plain_session_factory() as session:
            request = await session.scalar(
                sa.select(ObservationPlanRequest).where(
                    ObservationPlanRequest.id == request.id
                )
            )
            request.status = "removed"
            await session.commit()

    @staticmethod
    async def queued(allocation, start_date=None, end_date=None, queues_only=False):
        from ..models import EventObservationPlan, ObservationPlanRequest

        async with baselayer_models.async_plain_session_factory() as session:
            result = await session.scalars(
                sa.select(EventObservationPlan.plan_name)
                .join(
                    ObservationPlanRequest,
                    EventObservationPlan.observation_plan_request_id
                    == ObservationPlanRequest.id,
                )
                .where(
                    ObservationPlanRequest.allocation_id == allocation.id,
                    ObservationPlanRequest.status.in_(
                        ["submitted to TURBO queue", "queued at TURBO"]
                    ),
                )
            )
            return sorted(set(result.all()))

    form_json_schema_altdata = {}
