/**
 * Bond-graph letters (plan 7.3). The 1D elements (`bg-*` icon ids) render as
 * their block name. The multibond primitives render the same serif letter plus
 * a small superscript dimension mark (2 = Planar, 3 = Spatial), keyed on the
 * catalog icon id so the catalog and the block titles stay untouched.
 *
 * The digit equals the bond stroke count (Planar bonds draw 2 strokes, Spatial
 * 3), not the component count.
 */

export type BondDim = 2 | 3;

export interface BondLetter {
  letter: string;
  dim: BondDim | null;
}

function entry(letter: string, dim: BondDim): BondLetter {
  return { letter, dim };
}

/** Multibond primitive icon id -> letter and bond dimension. */
export const MULTIBOND_LETTERS: Readonly<Record<string, BondLetter>> = {
  "mb-i-planar": entry("I", 2),
  "mb-i-spatial": entry("I", 3),
  "mb-c-planar": entry("C", 2),
  "mb-c-spatial": entry("C", 3),
  "mb-r-planar": entry("R", 2),
  "mb-r-spatial": entry("R", 3),
  "mb-se-planar": entry("Se", 2),
  "mb-se-spatial": entry("Se", 3),
  "mb-sf-planar": entry("Sf", 2),
  "mb-sf-spatial": entry("Sf", 3),
  "mb-de-planar": entry("De", 2),
  "mb-de-spatial": entry("De", 3),
  "mb-df-planar": entry("Df", 2),
  "mb-df-spatial": entry("Df", 3),
  "mb-tf-planar": entry("TF", 2),
  "mb-tf-planar-mat": entry("TF", 2),
  "mb-tf-spatial": entry("TF", 3),
  "mb-tf-spatial-mat": entry("TF", 3),
  "mb-screw-tf": entry("TF", 2),
  "mb-fixed-transform-2d": entry("TF", 2),
  "mb-fixed-transform-3d": entry("TF", 3),
  "mb-fixed-transform-3d-neutral": entry("TF", 3),
  "mb-mtf-planar": entry("MTF", 2),
  "mb-mtf-planar-mat": entry("MTF", 2),
  "mb-mtf-spatial": entry("MTF", 3),
  "mb-tf-ad": entry("MTF", 2),
  "mb-tf-ad-neutral": entry("MTF", 2),
  "mb-joint-transform-2d": entry("MTF", 2),
  "mb-joint-transform-3d": entry("MTF", 3),
  "mb-gy-planar": entry("GY", 2),
  "mb-gy-spatial": entry("GY", 3),
  "mb-mgy-planar": entry("MGY", 2),
  "mb-mgy-spatial": entry("MGY", 3),
  "mb-coriolis-planar": entry("MGY", 2),
  "mb-coriolis-spatial": entry("MGY", 3),
  "mb-mse-planar": entry("MSe", 2),
  "mb-gravity-planar": entry("MSe", 2),
  "mb-gravity-spatial": entry("MSe", 3),
  "mb-external-wrench-planar": entry("MSe", 2),
  "mb-external-wrench-spatial": entry("MSe", 3),
  "mb-msf-planar": entry("MSf", 2),
  "mb-ground-planar": entry("Sf", 2),
  "mb-ground-spatial": entry("Sf", 3),
};

/**
 * The letter an icon id renders as, or null when the icon is not a bond-graph
 * letter. `name` is the block name, which is the letter for 1D `bg-*` ids.
 */
export function bondLetterFor(icon: string, name: string): BondLetter | null {
  if (icon.startsWith("bg-")) {
    return { letter: name, dim: null };
  }
  return MULTIBOND_LETTERS[icon] ?? null;
}

/** True for the 1D letters and the multibond primitives (the 2x2 footprint). */
export function isLetterIcon(icon: string): boolean {
  return icon.startsWith("bg-") || Object.hasOwn(MULTIBOND_LETTERS, icon);
}

export function dimDescription(dim: BondDim): string {
  return dim === 2 ? "2D planar multibond" : "3D spatial multibond";
}
