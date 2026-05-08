export function clamp01(v: number): number {
  if (!Number.isFinite(v)) return 0;
  if (v < 0) return 0;
  if (v > 1) return 1;
  return v;
}

/**
 * Count significant decimals in a raw display string: `0.7` -> 1,
 * `0.70` -> 2, `70` -> 0, `70.5%` -> 1. The calibrated number must
 * not exceed this.
 */
export function decimalsInDisplay(rawDisplay: string): number {
  const m = rawDisplay.match(/\.(\d+)/);
  return m ? m[1].length : 0;
}

export function formatPercent(probability: number, decimals: number): string {
  const pct = clamp01(probability) * 100;
  return `${pct.toFixed(Math.max(0, decimals))}%`;
}

/**
 * Format the "calibrated estimate: X%" affordance, capping the
 * calibrated decimals at the raw display's decimals so the calibrated
 * number is never pseudo-precise relative to the firm's stated belief.
 */
export function formatCalibratedDisplay(
  rawDisplay: string,
  calibrated: number,
): string {
  const decimals = decimalsInDisplay(rawDisplay);
  return `calibrated estimate: ${formatPercent(calibrated, decimals)}`;
}
