from types import SimpleNamespace

import pytest

from skyportal.utils import tns_submission


def _service(publish_existing=False):
    return SimpleNamespace(
        tns_altdata={"api_key": "k"},
        tns_bot_id=1,
        tns_bot_name="bot",
        testing=False,
        publish_existing_tns_objects=publish_existing,
    )


def _request():
    return SimpleNamespace(
        obj_id="TURBO26aaorslo",
        obj=SimpleNamespace(ra=13.961454, dec=-9.258226),
    )


@pytest.fixture
def tns(monkeypatch):
    calls = []

    def get_IAUname(api_key, headers, obj_id=None, ra=None, dec=None, **kw):
        calls.append("name" if obj_id is not None else "position")
        # another survey reported it under its own internal name
        return ("AT", "2026ahaf") if ra is not None else (None, None)

    monkeypatch.setattr(tns_submission, "get_IAUname", get_IAUname)
    monkeypatch.setattr(tns_submission, "get_tns_headers", lambda *a: {})
    return calls


def test_an_object_reported_by_another_survey_is_not_reported_again(tns):
    with pytest.raises(tns_submission.TNSWarning, match="2026ahaf"):
        tns_submission.apply_existing_tns_report_rules(_service(), _request())
    assert tns == ["name", "position"]


def test_the_position_is_not_searched_when_existing_objects_may_be_reported(
    tns, monkeypatch
):
    monkeypatch.setattr(tns_submission, "get_internal_names", lambda *a, **k: [])
    tns_submission.apply_existing_tns_report_rules(
        _service(publish_existing=True), _request()
    )
    assert tns == ["name"]
