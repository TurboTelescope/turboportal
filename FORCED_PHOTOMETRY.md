# SkyPortal Forced Photometry from External Surveys — Handoff Doc

This doc describes how to enable user-triggered forced photometry from ATLAS,
ZTF, PS1, ASAS-SN, and LSST on a TURBO source page in SkyPortal. It was
produced from a reading of the upstream SkyPortal source and is intended to be
handed to a Claude session running on the **tayamni** host
(`https://tayamni.spa.umn.edu`) where SkyPortal lives.

## Goal

When a user opens a TURBO transient on the SkyPortal source page, they should
be able to click a button (in the existing **Forced Photometry** accordion) to
request forced photometry from an external survey for that source. Results
should land back in the source's photometry table automatically.

## TL;DR

- **ATLAS, ZTF, PS1**: zero new code needed — SkyPortal already ships
  FollowUpAPI plugins. Pure SkyPortal *admin/config* task: register a
  Telescope, an Instrument with the right `api_classname`, and an Allocation
  whose `types` includes `"forced_photometry"`, with API credentials in
  `altdata`.
- **ASAS-SN, LSST**: not built in. Need new plugin files added to the
  `skyportal/facility_apis/` directory, modeled after
  `skyportal/facility_apis/atlas.py`. Each is ~300–500 lines.

## How SkyPortal's forced-photometry plugin pattern works

(All file references below are relative to the SkyPortal repository root.)

### Plugin definition

Each external facility is a class subclassing `FollowUpAPI` in
`skyportal/facility_apis/`. The base class is in
`skyportal/facility_apis/_base.py`. Notable methods/fields a plugin can
implement:

- `submit(request, session, **kwargs)` — required. Posts the request to the
  external service. Receives a `FollowupRequest` model containing
  `request.obj.ra`, `request.obj.dec`, `request.payload` (form values),
  `request.allocation.altdata` (credentials).
- `delete(request, session, **kwargs)` — optional. Removes the request.
- `form_json_schema_forced_photometry` — JSONSchema dict describing the form
  fields shown to the user when they click the FP accordion. Typically just
  `start_date` + `end_date`.
- `form_json_schema_altdata` — JSONSchema dict describing the credentials
  fields a SkyPortal admin fills when creating an allocation (e.g. an
  `api_token` field).
- `commit_photometry(...)` — module-level helper that converts an external
  survey's response into SkyPortal `Photometry` rows, tagged with
  `origin = "fp"` so the frontend filter
  (`showForcedPhotometry` in `static/js/components/plot/PhotometryPlot.jsx`)
  treats them as forced points.

### Registration

The new plugin class must be imported and listed in
`skyportal/facility_apis/__init__.py`. Look at how `ATLASAPI` and `ZTFAPI` are
imported there — the new plugin needs an analogous entry.

### Request lifecycle

1. User opens a source page in the browser. SkyPortal's
   `static/js/components/source/Source.jsx` renders a "Forced Photometry"
   accordion (around line 1417) containing
   `<FollowupRequestForm requestType="forced_photometry" />`.
2. The form (`static/js/components/followup_request/FollowupRequestForm.jsx`,
   around line 151) filters available Allocations to those whose
   `instrumentFormParams[id].formSchemaForcedPhotometry` is non-null AND
   whose `types` array includes `"forced_photometry"`. So an allocation only
   shows up in the dropdown if *both* the plugin defines that schema and the
   admin marked the allocation as supporting FP.
3. User picks an allocation, fills the form, hits Submit.
4. Frontend POSTs to `/api/followup_request`. The handler is in
   `skyportal/handlers/api/followup_request.py` — at line ~709 it calls
   `instrument.api_class.submit(followup_request, session, ...)`. The
   validation that picks the FP schema vs the triggered schema is at line
   ~668.
5. The plugin's `submit()` hits the external survey, stores a
   `FacilityTransactionRequest` row for polling, and sets
   `request.status = "submitted"`.
6. A background watcher (each plugin handles this differently — ATLAS uses
   `FacilityTransactionRequest`-based polling, ZTF has its own retrieval
   path) fetches results and calls `commit_photometry()` which writes
   `Photometry` rows.
7. The frontend's photometry plot re-fetches and the FP points show up
   immediately.

## Current built-in coverage

Verified by reading `skyportal/facility_apis/`:

| Survey | Class | File | Notes |
|---|---|---|---|
| ATLAS | `ATLASAPI` | `skyportal/facility_apis/atlas.py` | Cleanest reference implementation. Form takes `start_date`/`end_date`. Auth via `api_token` in altdata. |
| ZTF (IPAC FP) | `ZTFAPI` | `skyportal/facility_apis/ztf.py` | Same plugin handles both triggered scheduling and forced photometry; the `payload.request_type` field switches between them. Needs `ipac_email`, `ipac_userpass`, `ipac_http_user`, `ipac_http_password` in altdata. |
| PS1 | `PS1API` | `skyportal/facility_apis/ps1.py` | Forced photometry against PS1 archive. |
| **ASAS-SN** | — | — | **Not present.** |
| **LSST/Rubin** | — | — | **Not present.** |

`skyportal/facility_apis/__init__.py` is the registry.

## Part 1 — Enabling ATLAS / ZTF / PS1 (SkyPortal admin work only)

For each of ATLAS, ZTF, PS1, do this in SkyPortal's admin UI (or via the API):

1. **Telescope** — create one if it doesn't already exist (e.g. "ATLAS",
   "ZTF", "PS1"). Coords are nominal.
2. **Instrument** — create one under that telescope with
   `api_classname = "ATLASAPI"` (or `"ZTFAPI"` / `"PS1API"`). The
   `api_classname` field is the *class name string*; this is how
   `instrument.api_class` is resolved server-side.
3. **Allocation** — create an allocation for whichever Group(s) own TURBO
   sources, pointing at the new instrument. Critical fields:
   - `types`: must include the string `"forced_photometry"`. Without this,
     the allocation will not appear in the FP dropdown on source pages.
   - `altdata`: JSON object with credentials. Required keys per survey:

     | Survey | Required altdata keys |
     |---|---|
     | ATLAS | `api_token` (request one at https://fallingstar-data.com/forcedphot/) |
     | ZTF | `ipac_email`, `ipac_userpass`, `ipac_http_user`, `ipac_http_password` (IPAC ZTF FP account) |
     | PS1 | check `skyportal/facility_apis/ps1.py` for the exact altdata schema (likely a token or service URL) |

4. **Verify**: open any source page → "Forced Photometry" accordion →
   confirm the new allocation appears in the dropdown → submit a test
   request with a recent date range → watch the photometry plot for new
   points tagged with origin `fp`.

If the allocation doesn't appear in the dropdown, the two usual causes are:

- `types` doesn't contain `"forced_photometry"` (back-end filter).
- The user doesn't have submit permissions on the allocation group
  (front-end filter).

No changes to TURBO's pipeline are required for this part. The existing
`turbo_data_analysis/steps/alerts/skyportal.py` already posts sources to
SkyPortal; once those sources exist, any user can click to request FP.

## Part 2 — Adding ASAS-SN and LSST (new plugins)

Both need new files added to `skyportal/facility_apis/` in your SkyPortal
fork. Model both on `skyportal/facility_apis/atlas.py` — it is the smallest
working reference and is much simpler than `ztf.py`.

### Shared template

```
skyportal/facility_apis/<survey>.py
├─ class <Survey>Request        — builds the outgoing payload from request.payload
├─ def commit_photometry(...)   — converts JSON response → SkyPortal Photometry rows
└─ class <Survey>API(FollowUpAPI)
   ├─ submit(request, session, **kwargs)
   ├─ delete(request, session, **kwargs)        # optional
   ├─ form_json_schema_forced_photometry        # form fields shown to the user
   ├─ form_json_schema_altdata                  # credential fields for the allocation
   └─ ui_json_schema = {}
```

Then add to `skyportal/facility_apis/__init__.py`:

```python
from .<survey> import <Survey>API
# ...
__all__ = (
    ...,
    <Survey>API,
    ...,
)
```

### ASAS-SN specifics

ASAS-SN's Sky Patrol v2 photometry service is at
`https://asas-sn.osu.edu/` (the public web form lives at
`https://asas-sn.osu.edu/photometry`). There is a programmatic interface; the
exact endpoint and auth mechanism need to be confirmed from current ASAS-SN
docs — pick this up as the first step before writing the plugin. The form is
RA/Dec + optional date range, so the `form_json_schema_forced_photometry`
will look very similar to ATLAS's.

Auth: typically an email-based queue (results emailed). If polling is
required, model the polling on ATLAS's `FacilityTransactionRequest` pattern.

### LSST/Rubin specifics

The forced source data is queryable via the Rubin Science Platform TAP
service at `https://data.lsst.cloud/api/tap`. Auth is a per-user bearer
token from the RSP. Queries are ADQL against the
`dp02_dc2_catalogs.ForcedSource` (or equivalent DP1) table joined to
`Object`. For real-time forced photometry on a new transient you'd want the
`ForcedSourceOnDiaObject` table when it's available — confirm with current
Rubin docs before coding.

This one is more complex than ATLAS because:

- Results are returned synchronously by the TAP query (no polling needed),
  but
- The query has to be constructed in ADQL, and
- You'll likely want to do a small radius cone search rather than an exact
  position match.

The `altdata` schema should hold a single `rubin_token` field.

## What lives where (cheat sheet)

In the SkyPortal repo (whichever path on tayamni):

```
skyportal/
├─ facility_apis/
│  ├─ __init__.py                 ← register new plugin classes here
│  ├─ _base.py                    ← FollowUpAPI base
│  ├─ atlas.py                    ← REFERENCE for new plugins
│  ├─ ztf.py
│  └─ ps1.py
├─ handlers/api/
│  └─ followup_request.py         ← server-side submit handler (line ~709 calls plugin.submit)
└─ models/
   ├─ followup_request.py         ← FollowupRequest model
   ├─ facility_transaction.py     ← FacilityTransaction/FacilityTransactionRequest
   └─ instrument.py               ← Instrument.api_classname resolution

static/js/components/
├─ source/Source.jsx              ← line ~1417: Forced Photometry accordion
└─ followup_request/
   └─ FollowupRequestForm.jsx     ← line ~151: filters allocations by formSchemaForcedPhotometry + types
```

The TURBO side that posts sources is in a different repo, under
`turbo_data_analysis/steps/alerts/skyportal.py`. **No changes there are
needed** for any of this work; the post-sources flow already runs and the
"click to request FP" wiring is independent of how sources got created.

## Suggested order of attack

1. **Day 1**: Get ATLAS working end-to-end. It's the smallest config task and
   exercises the full pipeline (admin UI → form schema → submit handler →
   transaction polling → `commit_photometry` → frontend display). Once
   ATLAS works, ZTF and PS1 are minor variations of the same recipe.
2. **Day 2**: Get ZTF + PS1 set up (same recipe, different credentials).
   This wraps up everything that doesn't require new code.
3. **Day 3+**: Write the ASAS-SN plugin. Confirm the API/auth from current
   ASAS-SN docs first, then copy `atlas.py` and adapt. Test against a known
   bright transient before wiring it to TURBO sources.
4. **Day 4+**: Write the LSST/Rubin plugin. This is the largest scope —
   budget time for figuring out the RSP token, ADQL query, and result
   parsing.

## Open questions / things to verify on tayamni

- Confirm which SkyPortal version is deployed at `tayamni.spa.umn.edu`. The
  plugin pattern has been stable for years but field names in the
  `Allocation.altdata` schema may have drifted. If the deployed version
  predates the FP accordion in `Source.jsx`, that needs upgrading first.
- Confirm which user groups should own these allocations (TURBO group? a
  broader group?). The visibility of the FP button on a source page is
  gated by group membership.
- Confirm whether IPAC ZTF / ATLAS accounts exist for the TURBO team
  already, or whether new ones need to be requested.
- Check the deployed SkyPortal config for `app.atlas.host`/`app.atlas.port`
  — `atlas.py` reads these at import time from `config.yaml`. ZTF and PS1
  similarly read host/URL config from `config.yaml`.
