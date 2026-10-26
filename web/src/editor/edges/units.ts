/**
 * Unit-factor badges for signal connections (plan 5.3 and 7.3).
 *
 * `model.check` reports the factor the compiler inserts when the units differ
 * (`mm -> m` is 0.001). A factor of exactly 1 needs no badge: the wire is
 * already in the target unit, and `×1` would only add noise. Non-finite and
 * missing factors render nothing too; the check is the source of truth.
 */

/** `0.001` -> `×0.001`; 1.0 (and invalid factors) -> no badge. */
export function unitFactorLabel(factor: number | null | undefined): string | null {
  if (typeof factor !== "number" || !Number.isFinite(factor) || factor === 1) {
    return null;
  }
  const magnitude = Math.abs(factor);
  if (magnitude !== 0 && (magnitude < 1e-4 || magnitude >= 1e6)) {
    return `×${factor.toExponential(3).replace(/\.?0+e/, "e")}`;
  }
  return `×${String(factor)}`;
}
