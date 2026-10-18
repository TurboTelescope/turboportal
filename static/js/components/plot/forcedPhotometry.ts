// forced photometry origins: SkyPortal's own, and TURBO's per-image
// difference and science forced points (TURBO_forced_dif, TURBO_forced_sci)
export const isForcedPhotometry = (origin: string | null | undefined) =>
  origin === "fp" ||
  origin === "alert_fp" ||
  /^turbo_forced/i.test(origin ?? "");
