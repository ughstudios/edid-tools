/**
 * Approximate maximum *line* bit rates for common HDMI / DisplayPort generations.
 * Real sinks/sources vary; use for planning only (see UI disclaimer).
 *
 * HDMI: TMDS / FRL ceiling figures commonly quoted for the spec generation.
 * DP: typical 4-lane maximum raw link rate (HBR2 / HBR3 / UHBR20).
 */
export const DISPLAY_INTERFACE_IDS = [
  "hdmi-1-4",
  "hdmi-2-0",
  "hdmi-2-1",
  "dp-1-2",
  "dp-1-4",
  "dp-2-0",
] as const;

export type DisplayInterfaceId = (typeof DISPLAY_INTERFACE_IDS)[number];

/** Published-style max aggregate Gbit/s for the generation (rounded where standard uses exact fraction). */
export const DISPLAY_INTERFACE_MAX_GBPS: Record<DisplayInterfaceId, number> = {
  "hdmi-1-4": 10.2,
  "hdmi-2-0": 18,
  "hdmi-2-1": 48,
  "dp-1-2": 21.6,
  "dp-1-4": 32.4,
  "dp-2-0": 80,
};

/**
 * Multiplier on top of active-area bits/sec to approximate horizontal/vertical blanking,
 * encoding, and controller margins (not a CVT solver — a rule of thumb).
 */
export const DEFAULT_DISPLAY_TIMING_OVERHEAD = 1.2;

/** Active-area only (no blanking multiplier), Gbit/s. */
export function activeVideoGbps(width: number, height: number, hz: number, bitsPerPixel: number): number {
  if (width <= 0 || height <= 0 || hz <= 0 || bitsPerPixel <= 0) return 0;
  return (width * height * hz * bitsPerPixel) / 1e9;
}

export function requiredVideoGbps(
  width: number,
  height: number,
  hz: number,
  bitsPerPixel: number,
  timingOverhead: number = DEFAULT_DISPLAY_TIMING_OVERHEAD,
): number {
  const activeGbps = activeVideoGbps(width, height, hz, bitsPerPixel);
  return activeGbps * Math.max(1, timingOverhead);
}
