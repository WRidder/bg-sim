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
      "src-stop",
      "src-assertion",
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

  it("draws an explicit, distinct glyph for every motion and drive-electronics block", () => {
    // The icon ids of stdlib/motion (src/library/catalog.jl); none shares a drawing with
    // another motion block or with a signal source.
    const motionIcons = [
      "mot-adc",
      "mot-cycloidal-profile",
      "mot-dac",
      "mot-encoder",
      "mot-h-bridge",
      "mot-harmonic-profile",
      "mot-polynomial-profile",
      "mot-power-amplifier",
      "mot-pwm",
      "mot-pwm-average",
      "mot-s-curve-profile",
      "mot-trapezoidal-profile",
    ];
    const ids = new Set(svgIconIds());
    const strip = (icon: string) =>
      renderToStaticMarkup(<BlockIcon icon={icon} name={icon} />).replace(/(aria-label|data-icon)="[^"]*"/g, "");
    const glyphs = new Set<string>();
    for (const icon of motionIcons) {
      expect(ids.has(icon), icon).toBe(true);
      glyphs.add(strip(icon));
    }
    expect(glyphs.size).toBe(motionIcons.length);
    for (const icon of ["src-trapezoid", "src-pulse", "cont-gain", "conv-angle-sensor"]) {
      expect(glyphs.has(strip(icon)), icon).toBe(false);
    }
  });

  it("draws an explicit, distinct glyph for every contact block", () => {
    // The icon ids of stdlib/contact (src/library/catalog.jl); no two share a drawing.
    const contactIcons = [
      "ct-contact-point",
      "ct-contact-surface",
      "ct-impact-body-3d",
      "ct-impact-inertia-3d",
      "ct-moving-plane-contact",
      "ct-switched-pivot-3d",
    ];
    const ids = new Set(svgIconIds());
    const glyphs = new Set<string>();
    for (const icon of contactIcons) {
      expect(ids.has(icon), icon).toBe(true);
      glyphs.add(renderToStaticMarkup(<BlockIcon icon={icon} name={icon} />).replace(/(aria-label|data-icon)="[^"]*"/g, ""));
    }
    expect(glyphs.size).toBe(contactIcons.length);
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

  it("draws an explicit, distinct glyph for every hydraulic block", () => {
    // The icon ids of stdlib/hydraulic and of the hydraulic converters and sensors
    // (src/library/catalog.jl): ISO 1219-like symbols, no two alike.
    const hydraulicIcons = [
      "hyd-accumulator",
      "hyd-check-valve",
      "hyd-directional-valve",
      "hyd-flow-control",
      "hyd-flow-source",
      "hyd-orifice",
      "hyd-pipe",
      "hyd-pressure-source",
      "hyd-relief-valve",
      "hyd-tank",
      "hyd-variable-orifice",
      "hyd-volume",
      "conv-fixed-pump",
      "conv-variable-pump",
      "conv-ls-pump",
      "conv-hydraulic-motor",
      "conv-hydraulic-cylinder",
      "conv-pressure-sensor",
      "conv-flow-sensor",
    ];
    const ids = new Set(svgIconIds());
    const glyphs = new Set<string>();
    for (const icon of hydraulicIcons) {
      expect(ids.has(icon), icon).toBe(true);
      const html = renderToStaticMarkup(<BlockIcon icon={icon} name={icon} />);
      glyphs.add(html.replace(/(aria-label|data-icon)="[^"]*"/g, ""));
    }
    expect(glyphs.size).toBe(hydraulicIcons.length);
  });

  it("draws an explicit glyph for the electromagnet", () => {
    // stdlib:converters/Electromagnet (src/library/catalog.jl): a cored coil above its armature,
    // not the generic converter glyph and not the EM converter's.
    const ids = new Set(svgIconIds());
    expect(ids.has("conv-electromagnet")).toBe(true);
    const strip = (icon: string) =>
      renderToStaticMarkup(<BlockIcon icon={icon} name={icon} />).replace(/(aria-label|data-icon)="[^"]*"/g, "");
    const html = strip("conv-electromagnet");
    expect(html).toContain("<svg");
    for (const other of ["conv-em-converter", "conv-dc-motor", "conv-position-sensor", "elec-mutual-inductance"]) {
      expect(html, other).not.toBe(strip(other));
    }
  });

  it("draws a distinct glyph for every signal and control block", () => {
    // The icon ids of the signal and control blocks (src/library/catalog.jl): linear
    // systems, filters, routing, nonlinearities, simulation control and observers.
    const controlIcons = [
      "cont-transfer-function",
      "cont-zero-pole",
      "cont-notch",
      "cont-butterworth",
      "cont-bessel",
      "cont-band-pass",
      "cont-mux2",
      "cont-mux3",
      "cont-mux4",
      "cont-demux2",
      "cont-demux3",
      "cont-demux4",
      "cont-multiport-switch",
      "cont-backlash",
      "cont-variable-delay",
      "cont-wrap-to-pi",
      "cont-polynomial",
      "cont-rounding",
      "cont-hit-crossing",
      "cont-luenberger",
      "disc-memory",
      "disc-derivative",
      "disc-kalman",
      "src-stop",
      "src-assertion",
    ];
    const ids = new Set(svgIconIds());
    const glyphs = new Set<string>();
    for (const icon of controlIcons) {
      expect(ids.has(icon), icon).toBe(true);
      const html = renderToStaticMarkup(<BlockIcon icon={icon} name={icon} />);
      glyphs.add(html.replace(/(aria-label|data-icon)="[^"]*"/g, ""));
    }
    expect(glyphs.size).toBe(controlIcons.length);
  });

  it("draws four distinct flexible-beam glyphs", () => {
    // The assumed-modes beams of stdlib/planar and stdlib/spatial (src/library/catalog.jl).
    const beamIcons = [
      "pl-flexible-beam-2d",
      "pl-modal-beam-2d",
      "sp-flexible-beam-3d",
      "sp-modal-beam-3d",
    ];
    const ids = new Set(svgIconIds());
    const glyphs = new Set<string>();
    for (const icon of beamIcons) {
      expect(ids.has(icon), icon).toBe(true);
      const html = renderToStaticMarkup(<BlockIcon icon={icon} name={icon} />);
      glyphs.add(html.replace(/(aria-label|data-icon)="[^"]*"/g, ""));
    }
    expect(glyphs.size).toBe(beamIcons.length);
  });

  it("draws seven distinct truss glyphs", () => {
    // The truss blocks of stdlib/planar (src/library/catalog.jl), used by the bridge example.
    const trussIcons = [
      "pl-point-mass-2d",
      "pl-pin-node-2d",
      "pl-axial-bar-2d",
      "pl-bar-2d",
      "pl-truss-2d",
      "pl-moving-load-2d",
      "pl-deck-contact-2d",
    ];
    const ids = new Set(svgIconIds());
    const glyphs = new Set<string>();
    for (const icon of trussIcons) {
      expect(ids.has(icon), icon).toBe(true);
      const html = renderToStaticMarkup(<BlockIcon icon={icon} name={icon} />);
      glyphs.add(html.replace(/(aria-label|data-icon)="[^"]*"/g, ""));
    }
    expect(glyphs.size).toBe(trussIcons.length);
  });

  it("draws distinct glyphs for the vacuum gripping blocks", () => {
    // stdlib/contact SuctionCup and VacuumGenerator (src/library/catalog.jl).
    const vacuumIcons = ["ct-suction-cup", "ct-vacuum-generator", "hyd-pressure-source", "hyd-orifice"];
    const ids = new Set(svgIconIds());
    const glyphs = new Set<string>();
    for (const icon of vacuumIcons) {
      expect(ids.has(icon), icon).toBe(true);
      const html = renderToStaticMarkup(<BlockIcon icon={icon} name={icon} />);
      glyphs.add(html.replace(/(aria-label|data-icon)="[^"]*"/g, ""));
    }
    expect(glyphs.size).toBe(vacuumIcons.length);
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
