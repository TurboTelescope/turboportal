from astropy import units as u
from regions import Regions
from turbo_load_fields import build_field_region, load_fields, read_tess


def test_read_tess(tmp_path):
    tess = tmp_path / "RASA11.tess"
    tess.write_text("0 0.00000 -90.00000\n1 0.00000 -88.00000\n2 60.00000 -88.00000\n")
    field_data = read_tess(str(tess))
    assert field_data == {
        "ID": [0, 1, 2],
        "RA": [0.0, 0.0, 60.0],
        "Dec": [-90.0, -88.0, -88.0],
    }


def test_build_field_region_matches_requested_size():
    region_str = build_field_region(3.325, 2.218)
    region = Regions.parse(region_str, format="ds9")[0]
    assert region.center.ra.deg == 0.0
    assert region.center.dec.deg == 0.0
    assert region.width.to_value(u.deg) == 3.325
    assert region.height.to_value(u.deg) == 2.218


def test_load_fields_dry_run_makes_no_network_call(tmp_path, monkeypatch, capsys):
    tess = tmp_path / "RASA11.tess"
    tess.write_text("0 0.00000 -90.00000\n1 0.00000 -88.00000\n")

    def _fail(*a, **k):
        raise AssertionError("dry-run must not touch the network")

    monkeypatch.setattr("turbo_load_fields.requests.get", _fail)
    monkeypatch.setattr("turbo_load_fields.requests.put", _fail)

    rc = load_fields(
        "https://example.invalid/api",
        None,
        16,
        str(tess),
        3.325,
        2.218,
        dry_run=True,
        force=False,
    )
    assert rc == 0
    out = capsys.readouterr().out
    assert "would load 2 fields" in out
    assert "instrument 16" in out
