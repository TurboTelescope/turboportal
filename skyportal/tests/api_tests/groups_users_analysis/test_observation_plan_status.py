import uuid

from astropy import units as u
from astropy.coordinates import SkyCoord
from regions import RectangleSkyRegion, Regions

from skyportal.model_util import create_token
from skyportal.tests import api, retry_until
from skyportal.tests.external.test_moving_objects import remove_telescope_and_instrument
from skyportal.tests.fixtures import UserFactory


def _add_turbo_instrument(super_admin_token, field_ids):
    telescope_name = f"turbo_{uuid.uuid4()}"
    instrument_name = f"turbo_instr_{uuid.uuid4()}"

    status, data = api(
        "POST",
        "telescope",
        data={
            "name": telescope_name,
            "nickname": telescope_name,
            "lat": 33.979,
            "lon": -107.188,
            "elevation": 3190.0,
            "diameter": 0.28,
            "robotic": True,
            "fixed_location": True,
        },
        token=super_admin_token,
    )
    assert status == 200
    assert data["status"] == "success"
    telescope_id = data["data"]["id"]

    region = RectangleSkyRegion(
        center=SkyCoord(0 * u.deg, 0 * u.deg), width=3.325 * u.deg, height=2.218 * u.deg
    )
    field_data = {
        "ID": field_ids,
        "RA": [10.0 + i for i in range(len(field_ids))],
        "Dec": [5.0 + i for i in range(len(field_ids))],
    }
    status, data = api(
        "POST",
        "instrument",
        data={
            "name": instrument_name,
            "type": "imager",
            "band": "Optical",
            "filters": ["sdssg", "sdssr"],
            "telescope_id": telescope_id,
            "api_classname": "TURBOTOOAPI",
            "api_classname_obsplan": "TURBOMMAAPI",
            "field_data": field_data,
            "field_region": Regions([region]).serialize(format="ds9"),
        },
        token=super_admin_token,
    )
    assert status == 200
    assert data["status"] == "success"
    instrument_id = data["data"]["id"]

    def fields_loaded():
        status, data = api(
            "GET",
            f"instrument/{instrument_id}",
            token=super_admin_token,
            params={"ignoreCache": True},
        )
        assert status == 200
        assert len(data["data"]["fields"]) == len(field_ids)

    retry_until(fields_loaded, timeout=30)

    return telescope_id, instrument_id


def _add_turbo_allocation(super_admin_token, group_id, instrument_id):
    status, data = api(
        "POST",
        "allocation",
        data={
            "group_id": group_id,
            "instrument_id": instrument_id,
            "pi": "TURBO",
            "hours_allocated": 100,
            "_altdata": {"configured": True},
        },
        token=super_admin_token,
    )
    assert status == 200
    assert data["status"] == "success"
    return data["data"]["id"]


def _post_manual_plan(
    super_admin_token, allocation_id, gcnevent_id, localization_id, field_id
):
    status, data = api(
        "POST",
        "observation_plan/manual",
        data={
            "gcnevent_id": gcnevent_id,
            "localization_id": localization_id,
            "allocation_id": allocation_id,
            "status": "pending submission",
            "payload": {"queue_name": str(uuid.uuid4())},
            "plan_name": f"TURBO-auto-{gcnevent_id}-r0",
            "observation_plans": [
                {
                    "validity_window_start": "2020-07-16T01:01:01",
                    "validity_window_end": "2020-07-17T01:01:01",
                    "status": "pending submission",
                    "planned_observations": [
                        {
                            "dateobs": "2020-07-16T01:01:01",
                            "field_id": field_id,
                            "exposure_time": 30.0,
                            "weight": 1.0,
                            "filt": "sdssg",
                            "planned_observation_id": 1,
                            "overhead_per_exposure": 10.0,
                        }
                    ],
                }
            ],
        },
        token=super_admin_token,
    )
    assert status == 200
    assert data["status"] == "success"
    return data["data"]["id"]


def test_status_only_put_updates_status_without_touching_facility_api(
    super_admin_token, public_group, gcn_GW190814
):
    telescope_id, instrument_id = _add_turbo_instrument(super_admin_token, [1])
    allocation_id = _add_turbo_allocation(
        super_admin_token, public_group.id, instrument_id
    )
    request_id = _post_manual_plan(
        super_admin_token,
        allocation_id,
        gcn_GW190814.id,
        gcn_GW190814.localizations[0].id,
        1,
    )

    status, data = api(
        "PUT",
        f"observation_plan/{request_id}",
        data={"status": "queued at TURBO"},
        token=super_admin_token,
    )
    assert status == 200
    assert data["status"] == "success"

    status, data = api("GET", f"observation_plan/{request_id}", token=super_admin_token)
    assert status == 200
    assert data["data"]["status"] == "queued at TURBO"

    remove_telescope_and_instrument(telescope_id, instrument_id, super_admin_token)


def test_status_only_put_rejects_other_fields(
    super_admin_token, public_group, gcn_GW190814
):
    telescope_id, instrument_id = _add_turbo_instrument(super_admin_token, [2])
    allocation_id = _add_turbo_allocation(
        super_admin_token, public_group.id, instrument_id
    )
    request_id = _post_manual_plan(
        super_admin_token,
        allocation_id,
        gcn_GW190814.id,
        gcn_GW190814.localizations[0].id,
        2,
    )

    status, data = api(
        "PUT",
        f"observation_plan/{request_id}",
        data={"status": "queued at TURBO", "payload": {"queue_name": "hijacked"}},
        token=super_admin_token,
    )
    assert status == 400

    remove_telescope_and_instrument(telescope_id, instrument_id, super_admin_token)


def test_status_only_put_denied_for_unrelated_user(
    super_admin_token, public_group, public_group2, gcn_GW190814
):
    telescope_id, instrument_id = _add_turbo_instrument(super_admin_token, [3])
    allocation_id = _add_turbo_allocation(
        super_admin_token, public_group.id, instrument_id
    )
    request_id = _post_manual_plan(
        super_admin_token,
        allocation_id,
        gcn_GW190814.id,
        gcn_GW190814.localizations[0].id,
        3,
    )

    outsider = UserFactory(groups=[public_group2])
    outsider_token = create_token(["Manage observation plans"], outsider.id, "outsider")

    status, data = api(
        "PUT",
        f"observation_plan/{request_id}",
        data={"status": "queued at TURBO"},
        token=outsider_token,
    )
    assert status == 400

    UserFactory.teardown(outsider.id)
    remove_telescope_and_instrument(telescope_id, instrument_id, super_admin_token)
