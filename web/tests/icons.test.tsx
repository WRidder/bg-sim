/**
 * Every catalog `icon` id must have a renderer (plan 7.3): the bond-graph
 * letters for `bg-*`, an SVG schematic for everything else.
 */

import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";

import catalogJson from "../../contracts/fixtures/catalog/valid/catalog.min.json";
import type { Catalog } from "../src/contracts/catalog";
import { BlockIcon, hasIcon, isLetterIcon, JunctionGlyph, svgIconIds } from "../src/editor/icons";

const catalog = catalogJson as unknown as Catalog;

describe("block icons", () => {
  it("has a renderer for every catalog icon id", () => {
    for (const block of catalog.blocks) {
      expect(hasIcon(block.icon), `${block.name} (${block.icon})`).toBe(true);
    }
  });

  it("renders a non-empty glyph for every block", () => {
    for (const block of catalog.blocks) {
      const html = renderToStaticMarkup(<BlockIcon icon={block.icon} name={block.name} />);
      expect(html.length, block.icon).toBeGreaterThan(20);
      if (block.icon.startsWith("bg-")) {
        expect(html, block.icon).toContain(block.name);
        expect(html, block.icon).toContain("bond-letter");
      } else {
        expect(html, block.icon).toContain("<svg");
      }
    }
  });

  it("covers every non-bond-graph icon with an explicit SVG glyph", () => {
    const ids = new Set(svgIconIds());
    for (const block of catalog.blocks) {
      if (!isLetterIcon(block.icon)) {
        expect(ids.has(block.icon), block.icon).toBe(true);
      }
    }
  });

  it("draws an explicit glyph for every signal source and sink", () => {
    // The catalog fixture holds only the M1 blocks; these are the icon ids of every block
    // in stdlib/sources (src/library/catalog.jl), each of which must have its own glyph.
    const sourceIcons = [
      "src-chirp",
      "src-constant",
      "src-csv",
      "src-csv-sampled",
      "src-exp-sine",
      "src-exponentials",
      "src-multi-sine",
      "src-noise",
      "src-prbs",
      "src-random-walk",
      "src-pulse",
      "src-ramp",
      "src-recorder",
      "src-repeating-table",
      "src-sawtooth",
      "src-scope",
      "src-sine",
      "src-step",
      "src-time",
      "src-time-table",
      "src-trapezoid",
      "src-triangle",
      "src-uniform-noise",
      "src-white-noise",
    ];
    const ids = new Set(svgIconIds());
    const glyphs = new Set<string>();
    for (const icon of sourceIcons) {
      expect(ids.has(icon), icon).toBe(true);
      const html = renderToStaticMarkup(<BlockIcon icon={icon} name={icon} />);
      expect(html, icon).toContain("<svg");
      glyphs.add(html.replace(/(aria-label|data-icon)="[^"]*"/g, ""));
    }
    // No two sources share a drawing.
    expect(glyphs.size).toBe(sourceIcons.length);
  });

  it("draws an explicit glyph for every common mechanical and electrical component", () => {
    // The icon ids of the rotation and electrical components on top of the M1/M2 rows
    // (src/library/catalog.jl); each has its own drawing.
    const componentIcons = [
      "rot-hard-stop",
      "rot-clutch",
      "rot-brake",
      "rot-planetary-gear",
      "rot-belt-drive",
      "rot-worm-gear",
      "elec-opamp",
      "elec-vcvs",
      "elec-vccs",
      "elec-ccvs",
      "elec-cccs",
      "elec-mutual-inductance",
      "elec-battery",
      "elec-mosfet",
      "elec-igbt",
    ];
    const ids = new Set(svgIconIds());
    const glyphs = new Set<string>();
    for (const icon of componentIcons) {
      expect(ids.has(icon), icon).toBe(true);
      const html = renderToStaticMarkup(<BlockIcon icon={icon} name={icon} />);
      expect(html, icon).toContain("<svg");
      glyphs.add(html.replace(/(aria-label|data-icon)="[^"]*"/g, ""));
    }
    expect(glyphs.size).toBe(componentIcons.length);
  });

  it("falls back to a placeholder for an unknown icon id", () => {
    expect(hasIcon("no-such-icon")).toBe(false);
    const html = renderToStaticMarkup(<BlockIcon icon="no-such-icon" name="Mystery" />);
    expect(html).toContain("<svg");
    expect(html).toContain('aria-label="Mystery"');
  });

  it("draws the junction glyph with its kind", () => {
    expect(renderToStaticMarkup(<JunctionGlyph kind="0" />)).toContain(">0<");
    expect(renderToStaticMarkup(<JunctionGlyph kind="1" />)).toContain(">1<");
  });
});
