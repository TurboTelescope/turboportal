import argparse
import os
import sys

import requests
from astropy import units as u
from astropy.coordinates import SkyCoord
from regions import RectangleSkyRegion, Regions

FIELD_WIDTH_DEG = 3.325
FIELD_HEIGHT_DEG = 2.218
DEFAULT_BASE_URL = "https://cse-skyportal-prd-web-01.oit.umn.edu/api"


def read_tess(path):
    ids, ras, decs = [], [], []
    with open(path) as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            tid, ra, dec = line.split()
            ids.append(int(tid))
            ras.append(float(ra))
            decs.append(float(dec))
    return {"ID": ids, "RA": ras, "Dec": decs}


def build_field_region(width_deg=FIELD_WIDTH_DEG, height_deg=FIELD_HEIGHT_DEG):
    region = RectangleSkyRegion(
        center=SkyCoord(0 * u.deg, 0 * u.deg),
        width=width_deg * u.deg,
        height=height_deg * u.deg,
    )
    return Regions([region]).serialize(format="ds9")


def existing_field_count(base_url, token, instrument_id):
    resp = requests.get(
        f"{base_url}/instrument/{instrument_id}",
        headers={"Authorization": f"token {token}"},
        params={"includeGeoJSON": "false"},
        timeout=30,
    )
    resp.raise_for_status()
    return len(resp.json()["data"].get("fields") or [])


def load_fields(
    base_url,
    token,
    instrument_id,
    tess_path,
    width_deg,
    height_deg,
    dry_run,
    force,
):
    field_data = read_tess(tess_path)
    n = len(field_data["ID"])
    region = build_field_region(width_deg, height_deg)

    if not dry_run:
        n_existing = existing_field_count(base_url, token, instrument_id)
        if n_existing and not force:
            print(
                f"Instrument {instrument_id} already has {n_existing} fields; "
                "pass --force to load anyway (this WILL create duplicate "
                "field_ids -- InstrumentField has no unique constraint on "
                "(instrument_id, field_id))."
            )
            return 1

    print(
        f"{'[dry-run] would load' if dry_run else 'Loading'} {n} fields "
        f"onto instrument {instrument_id} from {tess_path}"
    )
    print(f"field_region: {region.strip()}")
    if dry_run:
        return 0

    resp = requests.put(
        f"{base_url}/instrument/{instrument_id}",
        headers={"Authorization": f"token {token}"},
        json={"field_data": field_data, "field_region": region},
        timeout=60,
    )
    resp.raise_for_status()
    print(
        f"PUT accepted; SkyPortal builds the {n} fields in the background "
        "(one commit per field). Check progress with:\n"
        f"  curl -s -H 'Authorization: token $SKYPORTAL_POSTER_TOKEN' "
        f"'{base_url}/instrument/{instrument_id}' "
        "| python3 -c 'import json,sys; "
        'print(len(json.load(sys.stdin)["data"]["fields"] or []))\''
    )
    return 0


def main():
    parser = argparse.ArgumentParser(
        description="Load the RASA11 tessellation as SkyPortal InstrumentFields "
        "via PUT /api/instrument/{id}."
    )
    parser.add_argument("--instrument-id", type=int, required=True)
    parser.add_argument(
        "--tess-path",
        required=True,
        help="Path to turbo_utils/turbo_utils/tiling/RASA11.tess",
    )
    parser.add_argument(
        "--base-url", default=os.environ.get("SKYPORTAL_BASE_URL", DEFAULT_BASE_URL)
    )
    parser.add_argument("--token", default=os.environ.get("SKYPORTAL_POSTER_TOKEN"))
    parser.add_argument("--width-deg", type=float, default=FIELD_WIDTH_DEG)
    parser.add_argument("--height-deg", type=float, default=FIELD_HEIGHT_DEG)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument(
        "--force", action="store_true", help="Load even if fields already exist"
    )
    args = parser.parse_args()

    if not args.dry_run and not args.token:
        parser.error("--token or SKYPORTAL_POSTER_TOKEN is required unless --dry-run")

    sys.exit(
        load_fields(
            args.base_url.rstrip("/"),
            args.token,
            args.instrument_id,
            args.tess_path,
            args.width_deg,
            args.height_deg,
            args.dry_run,
            args.force,
        )
    )


if __name__ == "__main__":
    main()
