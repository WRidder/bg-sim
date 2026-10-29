/**
 * Multibond icons: the primitives render as the 1D bond-graph letters plus a
 * superscript dimension mark; the composite blocks have schematic SVG glyphs.
 */

import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";

import catalogJson from "../../contracts/fixtures/catalog/valid/catalog.min.json";
import type { Catalog } from "../src/contracts/catalog";
import { BOND_NODE_SIZE, isBondGraph, isCompactBlock, layoutNode } from "../src/editor/geometry";
import {
  BlockIcon,
  MULTIBOND_LETTERS,
  bondLetterFor,
  hasIcon,
  svgIconIds,
} from "../src/editor/icons";
import { interfaceForBlock } from "../src/editor/nodeInterface";
import { buildCatalogIndex } from "../src/library/catalogIndex";

const index = buildCatalogIndex(catalogJson as unknown as Catalog);

/** Every composite multibond icon id of the Julia catalog (catalog.jl). */
const COMPOSITE_IDS = [
  "mb-compose-pose-2d",
  "mb-compose-pose-3d",
  "mb-pose-integrator-3d",
  "mb-revolute-2d",
  "pl-fixed-joint-2d",
  "pl-free-2d",
  "pl-joint-pose-2d",
  "pl-local-pose-2d",
  "pl-pose-integrator-2d",
  "pl-prismatic-2d",
  "pl-revolute-2d-compliant",
  "pl-revolute-2d-friction",
  "pl-revolute-2d-limit",
  "pl-revolute-2d-rigid",
  "pl-rigid-body-2d",
  "drv-current-drive",
  "drv-electric-drive",
  "drv-gearbox",
  "drv-reaction-wheel",
  "sp-cylindrical-3d",
  "sp-free-3d",
  "sp-helical-3d",
  "sp-local-pose-3d",
  "sp-planar-3d",
  "sp-prismatic-3d",
  "sp-prismatic-3d-compliant",
  "sp-prismatic-3d-friction",
  "sp-prismatic-3d-limit",
  "sp-revolute-3d",
  "sp-revolute-3d-compliant",
  "sp-revolute-3d-friction",
  "sp-revolute-3d-limit",
  "sp-rigid-body-3d",
  "sp-spherical-3d",
  "sp-universal-3d",
  "ct-contact-point",
  "ct-contact-surface",
  "ct-impact-body-3d",
  "ct-impact-inertia-3d",
  "ct-switched-pivot-3d",
];

describe("multibond letters", () => {
  it("covers exactly the intended primitives", () => {
    expect(Object.keys(MULTIBOND_LETTERS)).toHaveLength(43);
    const letters = new Set(Object.values(MULTIBOND_LETTERS).map((entry) => entry.letter));
    expect([...letters].sort()).toEqual(
      ["C", "De", "Df", "GY", "I", "MGY", "MSe", "MSf", "MTF", "R", "Se", "Sf", "TF"].sort(),
    );
    for (const [icon, entry] of Object.entries(MULTIBOND_LETTERS)) {
      expect([2, 3], icon).toContain(entry.dim);
      // Planar-named ids are 2D, Spatial-named ids are 3D.
      if (/planar|-2d/.test(icon)) {
        expect(entry.dim, icon).toBe(2);
      }
      if (/spatial|-3d/.test(icon)) {
        expect(entry.dim, icon).toBe(3);
      }
    }
    expect(MULTIBOND_LETTERS["mb-screw-tf"]).toEqual({ letter: "TF", dim: 2 });
    expect(MULTIBOND_LETTERS["mb-gravity-spatial"]).toEqual({ letter: "MSe", dim: 3 });
  });

  it("never overlaps the composite glyph ids", () => {
    const svg = new Set(svgIconIds());
    for (const icon of Object.keys(MULTIBOND_LETTERS)) {
      expect(svg.has(icon), icon).toBe(false);
      expect(hasIcon(icon), icon).toBe(true);
    }
  });

  it("gives every composite multibond catalog id a renderer", () => {
    for (const icon of COMPOSITE_IDS) {
      expect(hasIcon(icon), icon).toBe(true);
      expect(Object.hasOwn(MULTIBOND_LETTERS, icon), icon).toBe(false);
      const html = renderToStaticMarkup(<BlockIcon icon={icon} name="X" />);
      expect(html, icon).toContain("<svg");
      expect(html, icon).toContain(`data-icon="${icon}"`);
    }
  });

  it("keeps the 1D letter for bg-* ids with no dimension mark", () => {
    expect(bondLetterFor("bg-mse", "MSe")).toEqual({ letter: "MSe", dim: null });
    const html = renderToStaticMarkup(<BlockIcon icon="bg-mse" name="MSe" />);
    expect(html).not.toContain("data-dim");
  });

  it("renders the superscript with data-dim 2 / 3 in the library icon", () => {
    const planar = renderToStaticMarkup(<BlockIcon icon="mb-tf-planar" name="TFPlanar" />);
    expect(planar).toContain('data-dim="2"');
    expect(planar).toContain("²");
    expect(planar).toContain("bond-letter");
    expect(planar).toContain("TF");
    expect(planar).not.toContain("TFPlanar</");
    const spatial = renderToStaticMarkup(<BlockIcon icon="mb-i-spatial" name="ISpatial" />);
    expect(spatial).toContain('data-dim="3"');
    expect(spatial).toContain("³");
    expect(spatial).toContain("3D spatial multibond");
    expect(spatial).toContain('aria-hidden="true"');
  });
});

describe("multibond primitive footprint", () => {
  const se = interfaceForBlock(index.blocksByName.get("Se")!);

  it("is a bond-graph letter with the 1D footprint, not a compact card", () => {
    const planar = { ...se, icon: "mb-mse-planar", title: "MSePlanar" };
    const oneD = layoutNode(se);
    const layout = layoutNode(planar);
    expect(isBondGraph(planar)).toBe(true);
    expect(isCompactBlock(planar)).toBe(false);
    expect(layout.width).toBe(BOND_NODE_SIZE);
    expect(layout.height).toBe(BOND_NODE_SIZE);
    expect(layout.ports).toEqual(oneD.ports);
  });

  it("keeps composite blocks as compact cards", () => {
    const body = { ...se, icon: "pl-rigid-body-2d", title: "RigidBody2D" };
    expect(isBondGraph(body)).toBe(false);
    expect(isCompactBlock(body)).toBe(true);
  });

  it("sizes the glyph by the letter length, not the block name", () => {
    expect(bondLetterFor("mb-mse-spatial-x", "MSe")).toBeNull();
    expect(bondLetterFor("mb-gravity-spatial", "GravitySpatial")?.letter.length).toBe(3);
    expect(bondLetterFor("mb-mgy-planar", "MGYPlanar")?.letter.length).toBe(3);
    expect(bondLetterFor("mb-tf-planar", "TFPlanar")?.letter.length).toBe(2);
    expect(bondLetterFor("mb-i-planar", "IPlanar")?.letter.length).toBe(1);
  });
});
