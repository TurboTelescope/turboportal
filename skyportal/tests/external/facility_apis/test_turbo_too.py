import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from skyportal.enum_types import ALLOWED_API_CLASSNAMES
from skyportal.facility_apis import TURBOMMAAPI, TURBOTOOAPI


class _FakeSessionCM:
    def __init__(self, session):
        self._session = session

    async def __aenter__(self):
        return self._session

    async def __aexit__(self, *exc):
        return False


def _obj_request(status):
    return SimpleNamespace(
        id=1,
        status=status,
        obj=SimpleNamespace(internal_key="k"),
        last_modified_by_id=2,
    )


def test_registered_and_implements():
    assert "TURBOTOOAPI" in ALLOWED_API_CLASSNAMES
    assert "TURBOMMAAPI" in ALLOWED_API_CLASSNAMES
    too_implements = TURBOTOOAPI.implements()
    assert too_implements["submit"]
    assert too_implements["update"]
    assert too_implements["delete"]
    mma_implements = TURBOMMAAPI.implements()
    assert mma_implements["send"]
    assert mma_implements["remove"]
    assert mma_implements["queued"]


def test_too_submit_marks_submitted():
    fake = _obj_request("pending submission")
    session = AsyncMock()
    session.scalar = AsyncMock(return_value=fake)
    asyncio.run(TURBOTOOAPI.submit(fake, session))
    assert fake.status == "submitted"
    session.commit.assert_awaited()


def test_too_update_allowed_while_submitted():
    fake = _obj_request("submitted")
    session = AsyncMock()
    session.scalar = AsyncMock(return_value=fake)
    asyncio.run(TURBOTOOAPI.update(fake, session))
    session.commit.assert_awaited()


def test_too_update_rejects_when_not_submitted():
    fake = _obj_request("deleted")
    session = AsyncMock()
    session.scalar = AsyncMock(return_value=fake)
    with pytest.raises(ValueError):
        asyncio.run(TURBOTOOAPI.update(fake, session))


def test_too_delete_marks_deleted():
    fake = _obj_request("submitted")
    session = AsyncMock()
    session.scalar = AsyncMock(return_value=fake)
    asyncio.run(TURBOTOOAPI.delete(fake, session))
    assert fake.status == "deleted"


def test_mma_send_marks_submitted_to_turbo_queue():
    fake = SimpleNamespace(id=5, status="pending submission")
    session = AsyncMock()
    session.scalar = AsyncMock(return_value=fake)
    asyncio.run(TURBOMMAAPI.send(fake, session))
    assert fake.status == "submitted to TURBO queue"


def test_mma_remove_marks_removed():
    fake = SimpleNamespace(id=5, status="submitted to TURBO queue")
    session = AsyncMock()
    session.scalar = AsyncMock(return_value=fake)
    with patch("skyportal.facility_apis.turbo_too.baselayer_models") as mock_models:
        mock_models.async_plain_session_factory.return_value = _FakeSessionCM(session)
        asyncio.run(TURBOMMAAPI.remove(fake))
    assert fake.status == "removed"


def test_mma_queued_returns_sorted_unique_plan_names():
    session = AsyncMock()
    session.scalars = AsyncMock(
        return_value=SimpleNamespace(all=lambda: ["b", "a", "a"])
    )
    allocation = SimpleNamespace(id=7)
    with patch("skyportal.facility_apis.turbo_too.baselayer_models") as mock_models:
        mock_models.async_plain_session_factory.return_value = _FakeSessionCM(session)
        result = asyncio.run(TURBOMMAAPI.queued(allocation))
    assert result == ["a", "b"]
