import { describe, it, expect } from "bun:test";

import { isQueuedAtFacility, isQueuedOrComplete } from "./observationPlanStatus";

describe("isQueuedAtFacility", () => {
  it("matches the default MMAAPI/ZTF status", () => {
    expect(isQueuedAtFacility("submitted to telescope queue")).toBe(true);
  });

  it("matches TURBOMMAAPI's send() and post-send statuses", () => {
    expect(isQueuedAtFacility("submitted to TURBO queue")).toBe(true);
    expect(isQueuedAtFacility("queued at TURBO")).toBe(true);
  });

  it("rejects other statuses", () => {
    expect(isQueuedAtFacility("complete")).toBe(false);
    expect(isQueuedAtFacility("pending submission")).toBe(false);
    expect(isQueuedAtFacility(undefined)).toBe(false);
    expect(isQueuedAtFacility(null)).toBe(false);
  });
});

describe("isQueuedOrComplete", () => {
  it("treats complete and any queued status as done", () => {
    expect(isQueuedOrComplete("complete")).toBe(true);
    expect(isQueuedOrComplete("submitted to TURBO queue")).toBe(true);
    expect(isQueuedOrComplete("running")).toBe(false);
  });
});
