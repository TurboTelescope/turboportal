"""Statuses that mean an observation plan is sitting in a facility's queue.

Each facility API writes its own status string, so a literal comparison only
ever recognises the instrument that happens to use that wording. Keep the set
here and in static/js/components/observation_plan/observationPlanStatus.ts in
step.
"""

QUEUED_AT_FACILITY = (
    "submitted to telescope queue",
    "submitted to TURBO queue",
    "queued at TURBO",
)


def is_queued_at_facility(status) -> bool:
    return bool(status) and status in QUEUED_AT_FACILITY
