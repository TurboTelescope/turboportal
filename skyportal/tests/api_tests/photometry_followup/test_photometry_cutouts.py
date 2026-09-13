import base64
import io

from PIL import Image

from skyportal.tests import api, assert_api


def _png_b64():
    buffer = io.BytesIO()
    Image.new("L", (32, 32)).save(buffer, format="PNG")
    return base64.b64encode(buffer.getvalue()).decode()


def _post_point(token, source, group, camera, mjd, altdata):
    status, data = api(
        "POST",
        "photometry",
        data={
            "obj_id": str(source.id),
            "mjd": mjd,
            "instrument_id": camera.id,
            "flux": 12.24,
            "fluxerr": 0.031,
            "zp": 25.0,
            "magsys": "ab",
            "filter": "ztfg",
            "group_ids": [group.id],
            "altdata": altdata,
        },
        token=token,
    )
    assert_api(status, data)
    return data["data"]["ids"][0]


def _cutout_states(source, token):
    status, data = api("GET", f"sources/{source.id}/photometry_cutouts", token=token)
    assert_api(status, data)
    return {c["photometry_id"]: c for c in data["data"]}


def _pending_requests(token, photometry_id):
    status, data = api(
        "GET", "photometry_cutout_requests?afterID=0&limit=1000", token=token
    )
    assert_api(status, data)
    return [r for r in data["data"] if r["photometry_id"] == photometry_id]


def _request(source, token, ids):
    status, data = api(
        "POST",
        f"sources/{source.id}/photometry_cutouts",
        data={"photometry_ids": ids},
        token=token,
    )
    assert_api(status, data)
    return data["data"]["statuses"]


def test_photometry_cutout_request_lifecycle(
    upload_data_token, public_source, public_group, ztf_camera
):
    with_frame = _post_point(
        upload_data_token,
        public_source,
        public_group,
        ztf_camera,
        58001.0,
        {"image_id": 1234},
    )
    without_frame = _post_point(
        upload_data_token,
        public_source,
        public_group,
        ztf_camera,
        58002.0,
        {"exposure": 30},
    )

    assert _request(public_source, upload_data_token, [with_frame, without_frame]) == {
        str(with_frame): "pending",
        str(without_frame): "unavailable",
    }
    assert _request(public_source, upload_data_token, [with_frame]) == {
        str(with_frame): "pending"
    }
    assert _cutout_states(public_source, upload_data_token)[with_frame]["status"] == (
        "pending"
    )

    pending = _pending_requests(upload_data_token, with_frame)
    assert len(pending) == 1
    assert pending[0]["image_id"] == 1234
    assert pending[0]["obj_id"] == public_source.id
    assert pending[0]["filter"] == "ztfg"
    first_request_id = pending[0]["id"]

    status, data = api(
        "PUT",
        f"photometry_cutout_requests/{first_request_id}",
        data={"error": "frame missing"},
        token=upload_data_token,
    )
    assert_api(status, data)
    failed = _cutout_states(public_source, upload_data_token)[with_frame]
    assert failed["status"] == "failed"
    assert failed["error"] == "frame missing"
    assert _pending_requests(upload_data_token, with_frame) == []

    assert _request(public_source, upload_data_token, [with_frame]) == {
        str(with_frame): "pending"
    }
    retried = _pending_requests(upload_data_token, with_frame)
    assert len(retried) == 1
    assert retried[0]["id"] != first_request_id

    thumbnail = {
        "obj_id": public_source.id,
        "data": _png_b64(),
        "ttype": "dif",
        "photometry_id": with_frame,
    }
    status, data = api("POST", "thumbnail", data=thumbnail, token=upload_data_token)
    assert_api(status, data)
    thumbnail_id = data["data"]["id"]

    ready = _cutout_states(public_source, upload_data_token)[with_frame]
    assert ready["status"] == "ready"
    assert ready["public_url"]
    assert _pending_requests(upload_data_token, with_frame) == []

    status, data = api("POST", "thumbnail", data=thumbnail, token=upload_data_token)
    assert_api(status, data)
    assert data["data"]["id"] == thumbnail_id
    assert _request(public_source, upload_data_token, [with_frame]) == {
        str(with_frame): "ready"
    }
