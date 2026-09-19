export const QUEUED_STATUSES = [
  "submitted to telescope queue",
  "submitted to TURBO queue",
  "queued at TURBO",
];

export const isQueuedAtFacility = (status?: string | null): boolean =>
  !!status && QUEUED_STATUSES.includes(status);

export const isQueuedOrComplete = (status?: string | null): boolean =>
  status === "complete" || isQueuedAtFacility(status);
