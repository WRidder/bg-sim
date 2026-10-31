import { existsSync, readFileSync } from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { describe, expect, it } from "vitest";
import {
  bendingShape, bendingSigma, LAMBDA, MAX_MODES, modeShape, torsionShape,
  type DeformationBasis, type DeformationFamily,
} from "../src/viewer/beamModes";

const BASES: readonly DeformationBasis[] = ["clamped-free", "free-free"];
const MODES = [1, 2, 3] as const;

/** Composite Simpson over 0..1. */
function integrate(f: (xi: number) => number, n = 4000): number {
  const h = 1 / n;
  let sum = f(0) + f(1);
  for (let i = 1; i < n; i++) sum += (i % 2 === 1 ? 4 : 2) * f(i * h);
  return (sum * h) / 3;
}

/** The textbook form, cancellation and all: only trusted where lambda * xi is small. */
function naiveBending(basis: DeformationBasis, n: number, xi: number): number {
  const l = LAMBDA[basis][n - 1] ?? NaN;
  const x = l * xi;
  if (basis === "clamped-free") {
    const sigma = (Math.sinh(l) - Math.sin(l)) / (Math.cosh(l) + Math.cos(l));
    return Math.cosh(x) - Math.cos(x) - sigma * (Math.sinh(x) - Math.sin(x));
  }
  const sigma = (Math.cosh(l) - Math.cos(l)) / (Math.sinh(l) - Math.sin(l));
  return Math.cosh(x) + Math.cos(x) - sigma * (Math.sinh(x) + Math.sin(x));
}

/** Third derivative with respect to xi: a second-order one-sided difference of the second, inwards. */
function third(basis: DeformationBasis, n: number, xi: number): number {
  const h = xi < 0.5 ? 1e-4 : -1e-4;
  const d2 = (x: number): number => bendingShape(basis, n, x)[2];
  return (-3 * d2(xi) + 4 * d2(xi + h) - d2(xi + 2 * h)) / (2 * h);
}

describe("mode constants", () => {
  it("lambda solves the frequency equation of the basis", () => {
    for (const l of LAMBDA["clamped-free"]) expect(Math.abs(Math.cos(l) * Math.cosh(l) + 1)).toBeLessThan(1e-5);
    for (const l of LAMBDA["free-free"]) expect(Math.abs(Math.cos(l) * Math.cosh(l) - 1)).toBeLessThan(1e-4);
  });

  it("sigma matches the closed form", () => {
    expect(bendingSigma("clamped-free", 1)).toBeCloseTo(0.734095514, 8);
    expect(bendingSigma("free-free", 1)).toBeCloseTo(0.982502215, 8);
  });

  it("refuses a fourth mode", () => {
    expect(MAX_MODES).toBe(3);
    expect(() => bendingShape("clamped-free", 4, 0.5)).toThrow(RangeError);
    expect(() => torsionShape("free-free", 0, 0.5)).toThrow(RangeError);
  });
});

describe("bending shapes", () => {
  for (const basis of BASES) {
    for (const n of MODES) {
      it(`${basis} mode ${String(n)}: (1/L) integral phi^2 = 1`, () => {
        expect(integrate((xi) => bendingShape(basis, n, xi)[0] ** 2)).toBeCloseTo(1, 6);
      });

      it(`${basis} mode ${String(n)}: derivatives agree with finite differences`, () => {
        const h = 1e-6;
        for (const xi of [0.1, 0.37, 0.5, 0.81]) {
          const [f, df, d2f] = bendingShape(basis, n, xi);
          const [fp, dfp] = bendingShape(basis, n, xi + h);
          const [fm, dfm] = bendingShape(basis, n, xi - h);
          expect((fp - fm) / (2 * h)).toBeCloseTo(df, 4);
          expect((dfp - dfm) / (2 * h)).toBeCloseTo(d2f, 3);
          expect(Number.isFinite(f)).toBe(true);
        }
      });

      it(`${basis} mode ${String(n)}: the stable form equals the textbook form`, () => {
        for (const xi of [0, 0.25, 0.5, 0.75, 1]) {
          expect(bendingShape(basis, n, xi)[0]).toBeCloseTo(naiveBending(basis, n, xi), 9);
        }
      });
    }

    it(`${basis}: modes are orthogonal`, () => {
      for (const m of MODES) {
        for (const n of MODES) {
          if (m >= n) continue;
          expect(Math.abs(integrate((xi) => bendingShape(basis, m, xi)[0] * bendingShape(basis, n, xi)[0]))).toBeLessThan(1e-6);
        }
      }
    });
  }

  it("clamped-free: clamped at A (phi = phi' = 0), free at B (phi'' = phi''' = 0)", () => {
    for (const n of MODES) {
      const [f0, df0] = bendingShape("clamped-free", n, 0);
      const [, , d2f1] = bendingShape("clamped-free", n, 1);
      const scale = LAMBDA["clamped-free"][n - 1] ?? 1;
      expect(Math.abs(f0)).toBeLessThan(1e-12);
      expect(Math.abs(df0)).toBeLessThan(1e-12);
      expect(Math.abs(d2f1) / scale ** 2).toBeLessThan(1e-7);
      expect(Math.abs(third("clamped-free", n, 1)) / scale ** 3).toBeLessThan(1e-4);
    }
  });

  it("clamped-free: the tip deflects by 2 (alternating sign)", () => {
    expect(bendingShape("clamped-free", 1, 1)[0]).toBeCloseTo(2, 6);
    expect(bendingShape("clamped-free", 2, 1)[0]).toBeCloseTo(-2, 6);
    expect(bendingShape("clamped-free", 3, 1)[0]).toBeCloseTo(2, 6);
  });

  it("free-free: no moment and no shear at either end", () => {
    for (const n of MODES) {
      const scale = LAMBDA["free-free"][n - 1] ?? 1;
      for (const xi of [0, 1]) {
        expect(Math.abs(bendingShape("free-free", n, xi)[2]) / scale ** 2).toBeLessThan(1e-7);
        expect(Math.abs(third("free-free", n, xi)) / scale ** 3).toBeLessThan(1e-4);
      }
      // the ends deflect by +-2
      expect(Math.abs(bendingShape("free-free", n, 0)[0])).toBeCloseTo(2, 6);
    }
  });

  it("free-free: orthogonal to the rigid motions (integral phi = integral xi phi = 0)", () => {
    for (const n of MODES) {
      expect(Math.abs(integrate((xi) => bendingShape("free-free", n, xi)[0]))).toBeLessThan(1e-6);
      expect(Math.abs(integrate((xi) => xi * bendingShape("free-free", n, xi)[0]))).toBeLessThan(1e-6);
    }
  });
});

describe("torsion shapes", () => {
  for (const basis of BASES) {
    for (const n of MODES) {
      it(`${basis} mode ${String(n)}: normalised, with the right derivatives`, () => {
        expect(integrate((xi) => torsionShape(basis, n, xi)[0] ** 2)).toBeCloseTo(1, 8);
        const h = 1e-6;
        const [, df] = torsionShape(basis, n, 0.3);
        expect((torsionShape(basis, n, 0.3 + h)[0] - torsionShape(basis, n, 0.3 - h)[0]) / (2 * h)).toBeCloseTo(df, 5);
      });
    }
    it(`${basis}: orthogonal`, () => {
      expect(Math.abs(integrate((xi) => torsionShape(basis, 1, xi)[0] * torsionShape(basis, 2, xi)[0]))).toBeLessThan(1e-9);
      expect(Math.abs(integrate((xi) => torsionShape(basis, 2, xi)[0] * torsionShape(basis, 3, xi)[0]))).toBeLessThan(1e-9);
    });
  }

  it("clamped-free: no twist at A, no torque (psi' = 0) at B", () => {
    for (const n of MODES) {
      expect(torsionShape("clamped-free", n, 0)[0]).toBe(0);
      expect(Math.abs(torsionShape("clamped-free", n, 1)[1])).toBeLessThan(1e-12);
    }
  });

  it("free-free: no torque at either end", () => {
    for (const n of MODES) {
      expect(Math.abs(torsionShape("free-free", n, 0)[1])).toBeLessThan(1e-12);
      expect(Math.abs(torsionShape("free-free", n, 1)[1])).toBeLessThan(1e-12);
    }
  });

  it("modeShape picks the family", () => {
    expect(modeShape("torsion", "free-free", 2, 0.3)).toEqual(torsionShape("free-free", 2, 0.3));
    expect(modeShape("bending-z", "free-free", 2, 0.3)).toEqual(bendingShape("free-free", 2, 0.3));
  });
});

/*
 * Cross-check against the Julia FlexibleBeam implementation: `contracts/fixtures/modes/mode_shapes.json`,
 * written by the Julia side, holds the shapes at s/L = 0, 0.25, 0.5, 0.75, 1. It is read loosely (any
 * nesting) and every entry that names a basis, a family (bending or torsion), a mode number and five
 * values is compared. The test is skipped while the file does not exist; once it exists it must contain
 * comparable entries.
 */
const here = path.dirname(fileURLToPath(import.meta.url));
const MODE_FIXTURE = path.resolve(here, "..", "..", "contracts", "fixtures", "modes", "mode_shapes.json");

interface FixtureEntry {
  readonly basis: DeformationBasis;
  readonly family: DeformationFamily;
  readonly n: number;
  readonly values: readonly number[];
}

function isBasis(v: unknown): v is DeformationBasis {
  return v === "clamped-free" || v === "free-free";
}

function familyOf(text: string): DeformationFamily | null {
  const t = text.toLowerCase();
  return t.includes("torsion") || t === "psi" || t.includes("twist") ? "torsion" : t.includes("bend") || t === "phi" ? "bending-y" : null;
}

function numbers(v: unknown): number[] | null {
  return Array.isArray(v) && v.length > 0 && v.every((x) => typeof x === "number") ? (v as number[]) : null;
}

/** Entries from any reasonable layout: records with basis/family/mode/values, or basis -> family -> [mode][values]. */
function fixtureEntries(doc: unknown): { xi: number[]; entries: FixtureEntry[] } {
  const entries: FixtureEntry[] = [];
  let xi: number[] = [0, 0.25, 0.5, 0.75, 1];
  const walk = (node: unknown, ctx: { basis?: DeformationBasis; family?: DeformationFamily }): void => {
    if (Array.isArray(node)) {
      // basis and family known from the path: an array of mode value arrays
      if (ctx.basis !== undefined && ctx.family !== undefined && node.every((m) => numbers(m) !== null)) {
        node.forEach((m, i) => entries.push({ basis: ctx.basis as DeformationBasis, family: ctx.family as DeformationFamily, n: i + 1, values: numbers(m) ?? [] }));
        return;
      }
      for (const item of node) walk(item, ctx);
      return;
    }
    if (typeof node !== "object" || node === null) return;
    const o = node as Record<string, unknown>;
    const ownXi = numbers(o["xi"] ?? o["s_over_L"] ?? o["s/L"]);
    if (ownXi !== null && ctx.basis === undefined) xi = ownXi;
    const basis = isBasis(o["basis"]) ? o["basis"] : ctx.basis;
    const famText = typeof o["family"] === "string" ? o["family"] : typeof o["kind"] === "string" ? o["kind"] : null;
    const family = (famText !== null ? familyOf(famText) : null) ?? ctx.family;
    const n = typeof o["n"] === "number" ? o["n"] : typeof o["mode"] === "number" ? o["mode"] : null;
    const values = numbers(o["values"] ?? o["phi"] ?? o["psi"] ?? o["shape"]);
    if (basis !== undefined && family !== undefined && n !== null && values !== null) {
      entries.push({ basis, family, n, values });
      return;
    }
    for (const [key, value] of Object.entries(o)) {
      const next = { ...ctx };
      if (basis !== undefined) next.basis = basis;
      if (family !== undefined) next.family = family;
      if (isBasis(key)) next.basis = key;
      const keyFamily = familyOf(key);
      if (keyFamily !== null) next.family = keyFamily;
      walk(value, next);
    }
  };
  walk(doc, {});
  return { xi, entries };
}

describe.skipIf(!existsSync(MODE_FIXTURE))("cross-check with the Julia mode shapes fixture", () => {
  it("matches every shape value the fixture lists", () => {
    const doc: unknown = JSON.parse(readFileSync(MODE_FIXTURE, "utf8"));
    const { xi, entries } = fixtureEntries(doc);
    expect(entries.length, "no comparable entries (basis, family, mode, values) in mode_shapes.json").toBeGreaterThan(0);
    for (const e of entries) {
      expect(e.values.length, `${e.basis} ${e.family} mode ${String(e.n)}: one value per s/L point`).toBe(xi.length);
      e.values.forEach((v, i) => {
        const at = xi[i] ?? NaN;
        expect(modeShape(e.family, e.basis, e.n, at)[0], `${e.basis} ${e.family} mode ${String(e.n)} at s/L = ${String(at)}`).toBeCloseTo(v, 6);
      });
    }
  });
});
