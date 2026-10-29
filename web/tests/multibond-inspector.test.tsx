/**
 * W-MB3: the frame inspector, per-component multibond units, and the 2D/3D
 * robotics library categories with multibond port glyphs.
 *
 * The catalogs come from the C-MB1 plan fixture (live catalog shape: domains
 * with authoritative `components`, blocks with `dimension` and `frame`); the
 * test never hard-codes a block list that the library would need to know.
 */

import { act, fireEvent, render, screen, within } from "@testing-library/react";
import { beforeEach, describe, expect, it } from "vitest";

import catalogJson from "../../contracts/fixtures/catalog/valid/catalog.min.json";
import planarJson from "../../contracts/fixtures/catalog/valid/catalog.planar.json";
import type { Catalog, CatalogBlock } from "../src/contracts/catalog";
import { resetDiagnosticsStore, useDiagnosticsStore } from "../src/diagnostics/store";
import {
  explainBondFrames,
  qualifiedFrame,
} from "../src/inspector/frames";
import { Inspector } from "../src/inspector/Inspector";
import { resetCatalogStore, useCatalogStore } from "../src/library/catalogStore";
import { LibraryBrowser } from "../src/library/LibraryBrowser";
import {
  resetDocumentStore,
  useDocumentStore,
} from "../src/state/documentStore";
import {
  createConnection,
  createEmptyModel,
  createNodeFromBlock,
} from "../src/state/modelFactory";
import type { Model, ModelNode } from "../src/contracts/model";

const scalarCatalog = catalogJson as unknown as Catalog;

function cloneCatalog(source: Catalog): Catalog {
  return JSON.parse(JSON.stringify(source)) as Catalog;
}

function planarCatalog(): Catalog {
  return cloneCatalog(planarJson as unknown as Catalog);
}

function planarBlock(catalog: Catalog): CatalogBlock {
  const block = catalog.blocks.find((entry) => entry.name === "RigidBody2D");
  if (block === undefined) {
    throw new Error("the planar fixture has no RigidBody2D block");
  }
  return block;
}

/** A spatial copy of the planar body block, so one catalog has both dimensions. */
function spatialCatalog(): Catalog {
  const catalog = planarCatalog();
  const source = planarBlock(catalog);
  const spatial: CatalogBlock = {
    ...(JSON.parse(JSON.stringify(source)) as CatalogBlock),
    ref: "stdlib:spatial/ISpatial",
    name: "ISpatial",
    group: "Multibond",
    dimension: 3,
    ports: [{ name: "p", domain: "Spatial", size: [6], frame: "body" }],
    variables: [
      { name: "P", type: "Real", size: [6], unit: null, start: "[0, 0, 0, 0, 0, 0]", state: "prefer" },
    ],
    source: "@block ISpatial begin\nend\n",
    path: "stdlib/multibond/ISpatial.jl",
  };
  catalog.blocks.push(spatial);
  return catalog;
}

function nodeFrom(block: CatalogBlock, id: string, name: string): ModelNode {
  return createNodeFromBlock(block, { x: 0, y: 0 }, id, name);
}

function open(nodes: readonly ModelNode[], connections: Model["diagram"]["connections"] = []): Model {
  const doc = createEmptyModel("MultibondInspector");
  doc.diagram.nodes = [...nodes];
  doc.diagram.connections = [...connections];
  useDocumentStore.getState().openDocument("demo", "MultibondInspector", doc);
  return doc;
}

beforeEach(() => {
  resetDocumentStore();
  resetCatalogStore();
  resetDiagnosticsStore();
});

describe("frame display helpers", () => {
  it("qualifies a declared frame with the instance path", () => {
    expect(qualifiedFrame(["Arm1"], "body")).toBe("Arm1/body");
    expect(qualifiedFrame(["Sub1", "Arm1"], "body")).toBe("Sub1/Arm1/body");
    expect(qualifiedFrame([], "world")).toBe("world");
    expect(qualifiedFrame(["Arm1"], null)).toBeNull();
    expect(qualifiedFrame(["Arm1"], "  ")).toBeNull();
    expect(qualifiedFrame([" "], "body")).toBe("body");
  });

  it("explains equal frames, a bridge and frame-neutral ends", () => {
    const arm = { endpoint: "Arm1.p", declared: "arm", qualified: "Arm1/arm" };
    const arm2 = { endpoint: "Arm2.p", declared: "arm", qualified: "Arm2/arm" };
    const world = { endpoint: "Ground.p", declared: "world", qualified: "Ground/world" };
    const neutral = { endpoint: "Link.p", declared: null, qualified: null };

    // FIX-MB-6: identity is face-scoped and decided by the worker. Without an
    // E007 the check accepted the bond; the sentence must not claim a rule.
    const same = explainBondFrames({ from: arm, to: arm2, reported: "Arm1/arm" });
    expect(same).toContain("Arm1/arm");
    expect(same).toContain("Arm2/arm");
    expect(same).toContain("The model check accepts this bond (no E007)");
    expect(same).not.toContain("unqualified");
    expect(same).not.toContain("DEC-MB-1");
    expect(same).not.toContain("unchanged");

    // With the worker's E007 for the connection, the mismatch and hint show.
    const mismatch = explainBondFrames({
      from: arm,
      to: arm2,
      reported: null,
      e007: {
        code: "E007",
        severity: "error",
        message: "frames of different instances are distinct (Arm1/arm vs Arm2/arm)",
        hint: "route the bond through a joint or a frame-neutral transform",
        connection: "c1",
      },
    });
    expect(mismatch).toContain("Frame mismatch (E007)");
    expect(mismatch).toContain("frames of different instances are distinct (Arm1/arm vs Arm2/arm)");
    expect(mismatch).toContain("Hint: route the bond through a joint or a frame-neutral transform");
    expect(mismatch).not.toContain("accepts");

    const bridged = explainBondFrames({ from: arm, to: world, reported: null });
    expect(bridged).toContain("Arm1/arm");
    expect(bridged).toContain("Ground/world");
    expect(bridged).toContain("E007");
    expect(bridged).toContain("FixedTransform or JointTransform");
    expect(bridged).toContain("bridge");

    const adopted = explainBondFrames({ from: neutral, to: world, reported: null });
    expect(adopted).toContain("Ground/world");
    expect(adopted).toContain("frame-neutral");

    const reported = explainBondFrames({ from: neutral, to: neutral, reported: "Body/body" });
    expect(reported).toContain("Body/body");

    const none = explainBondFrames({ from: neutral, to: neutral, reported: null });
    expect(none).toContain("frame-neutral");
  });
});

describe("component units in the inspector", () => {
  it("shows the Planar effort/flow arrays and one signal per component", () => {
    const catalog = planarCatalog();
    useCatalogStore.getState().setCatalog(catalog);
    const body = planarBlock(catalog);
    open([nodeFrom(body, "n1", "Arm1")]);
    useDocumentStore.getState().setSelection(["n1"], []);
    render(<Inspector />);

    const units = screen.getByTestId("inspector-port-p-units");
    expect(units.textContent).toContain("[N*m, N, N]");
    expect(units.textContent).toContain("[rad/s, m/s, m/s]");
    expect(units.getAttribute("aria-label")).toBe("Planar component units");

    const effort = [
      screen.getByTestId("inspector-signal-Arm1/p.e[1]"),
      screen.getByTestId("inspector-signal-Arm1/p.e[2]"),
      screen.getByTestId("inspector-signal-Arm1/p.e[3]"),
    ].map((line) => line.textContent);
    expect(effort[0]).toContain("N*m");
    expect(effort[1]).toContain("N");
    expect(effort[2]).toContain("N");
    const flow = [
      screen.getByTestId("inspector-signal-Arm1/p.f[1]"),
      screen.getByTestId("inspector-signal-Arm1/p.f[2]"),
      screen.getByTestId("inspector-signal-Arm1/p.f[3]"),
    ].map((line) => line.textContent);
    expect(flow[0]).toContain("rad/s");
    expect(flow[1]).toContain("m/s");
    expect(flow[2]).toContain("m/s");
    expect(screen.getByTestId("inspector-signal-Arm1/p.P").textContent).toContain("W");

    // There is no single port-level e/f unit for a multibond port.
    expect(screen.queryByTestId("inspector-signal-Arm1/p.e")).toBeNull();
    expect(screen.queryByTestId("inspector-signal-Arm1/p.f")).toBeNull();

    // The port frame is the declared name plus its instance-qualified form.
    const frame = screen.getByTestId("inspector-port-p-frame");
    expect(frame.textContent).toContain("body");
    expect(frame.textContent).toContain("Arm1/body");
    expect(screen.getByTestId("inspector-port-p").getAttribute("data-multibond")).toBe("3");
  });

  it("shows the six Spatial components and keeps scalar ports unchanged", () => {
    const catalog = spatialCatalog();
    useCatalogStore.getState().setCatalog(catalog);
    const spatial = catalog.blocks.find((entry) => entry.name === "ISpatial");
    if (spatial === undefined) {
      throw new Error("the spatial catalog has no ISpatial block");
    }
    open([nodeFrom(spatial, "n1", "Body")]);
    useDocumentStore.getState().setSelection(["n1"], []);
    const { unmount } = render(<Inspector />);

    const units = screen.getByTestId("inspector-port-p-units");
    expect(units.textContent).toContain("[N*m, N*m, N*m, N, N, N]");
    expect(units.textContent).toContain("[rad/s, rad/s, rad/s, m/s, m/s, m/s]");
    expect(screen.getByTestId("inspector-signal-Body/p.e[6]").textContent).toContain("N");
    expect(screen.getByTestId("inspector-signal-Body/p.f[6]").textContent).toContain("m/s");
    unmount();

    // A scalar port keeps its single e/f pair and its single-unit domain.
    useCatalogStore.getState().setCatalog(scalarCatalog);
    const motor = scalarCatalog.blocks.find((entry) => entry.name === "DCMotor");
    if (motor === undefined) {
      throw new Error("the scalar catalog has no DCMotor block");
    }
    open([nodeFrom(motor, "n2", "Motor1")]);
    useDocumentStore.getState().setSelection(["n2"], []);
    render(<Inspector />);
    expect(screen.queryByTestId("inspector-port-shaft-units")).toBeNull();
    expect(screen.getByTestId("inspector-signal-Motor1/shaft.f").textContent).toContain("rad/s");
    expect(screen.getByTestId("inspector-port-shaft-frame").textContent).toContain(
      "frame-neutral",
    );
  });

  it("shows a frame line only for power ports, never for signal ports", () => {
    useCatalogStore.getState().setCatalog(scalarCatalog);
    const mse = scalarCatalog.blocks.find((entry) => entry.name === "MSe");
    if (mse === undefined) {
      throw new Error("the scalar catalog has no MSe block");
    }
    open([nodeFrom(mse, "n3", "MSe1")]);
    useDocumentStore.getState().setSelection(["n3"], []);
    render(<Inspector />);

    // The Generic power port has no declared frame, so it is frame-neutral.
    expect(screen.getByTestId("inspector-port-p-frame").textContent).toBe("frame-neutral");
    expect(screen.getByTestId("inspector-signal-MSe1/p.e")).toBeTruthy();

    // A signal input is frame-less, not frame-neutral: no frame line at all.
    expect(screen.getByTestId("inspector-port-u")).toBeTruthy();
    expect(screen.getByTestId("inspector-signal-MSe1/u")).toBeTruthy();
    expect(screen.queryByTestId("inspector-port-u-frame")).toBeNull();
  });
});

describe("the frame inspector for a bond", () => {
  it("shows the model-check frame, both port frames and what the bond does", () => {
    const catalog = planarCatalog();
    useCatalogStore.getState().setCatalog(catalog);
    const body = planarBlock(catalog);
    open(
      [nodeFrom(body, "n1", "Arm1"), nodeFrom(body, "n2", "Arm2")],
      [createConnection("c1", "bond", { node: "n1", port: "p" }, { node: "n2", port: "p" })],
    );
    useDocumentStore.getState().setSelection([], ["c1"]);
    const revision = useDocumentStore.getState().revision;
    act(() => {
      useDiagnosticsStore.getState().applyResult(
        {
          diagnostics: [],
          domains: { c1: "Planar" },
          causality: { c1: { strokeAt: "to" } },
          frames: { c1: "Arm1/body" },
          multibond: { c1: 2 },
          unitFactors: {},
          signals: [],
          stats: { states: 3, equations: 3 },
        },
        revision,
      );
    });
    render(<Inspector />);

    const frame = screen.getByTestId("inspector-connection-frame-c1");
    expect(frame.getAttribute("data-frame")).toBe("Arm1/body");
    expect(frame.textContent).toContain("Arm1/body");

    expect(screen.getByTestId("inspector-connection-end-c1-from").textContent).toContain(
      "Arm1/body",
    );
    expect(screen.getByTestId("inspector-connection-end-c1-to").textContent).toContain(
      "Arm2/body",
    );

    const explanation = screen.getByTestId("inspector-frame-explanation-c1").textContent ?? "";
    // Same declared name at two instances and no E007: the check accepted it.
    expect(explanation).toContain("displayed as Arm1/body and Arm2/body");
    expect(explanation).toContain("The model check accepts this bond (no E007)");
    expect(explanation).not.toContain("unqualified");
    expect(explanation).not.toContain("Frame mismatch");

    expect(screen.getByTestId("inspector-connection-domain-c1").textContent).toBe(
      "Planar · 3 components · 2 strokes",
    );
  });

  it("shows the worker's E007 message and hint when the check rejects the bond", () => {
    const catalog = planarCatalog();
    useCatalogStore.getState().setCatalog(catalog);
    const body = planarBlock(catalog);
    open(
      [nodeFrom(body, "n1", "Arm1"), nodeFrom(body, "n2", "Arm2")],
      [
        createConnection("c1", "bond", { node: "n1", port: "p" }, { node: "n2", port: "p" }),
        createConnection("c9", "bond", { node: "n2", port: "p" }, { node: "n1", port: "p" }),
      ],
    );
    useDocumentStore.getState().setSelection([], ["c1"]);
    const revision = useDocumentStore.getState().revision;
    act(() => {
      useDiagnosticsStore.getState().applyResult(
        {
          diagnostics: [
            {
              code: "E007",
              severity: "error",
              message: "frames of different instances are distinct (Arm1/body vs Arm2/body)",
              hint: "route the bond through a joint or a frame-neutral transform",
              connection: "c1",
            },
            {
              code: "E007",
              severity: "error",
              message: "other connection mismatch",
              connection: "c9",
            },
          ],
          domains: {},
          causality: {},
          frames: {},
          multibond: {},
          unitFactors: {},
          signals: [],
          stats: { states: 0, equations: 0 },
        },
        revision,
      );
    });
    render(<Inspector />);

    const explanation = screen.getByTestId("inspector-frame-explanation-c1").textContent ?? "";
    expect(explanation).toContain("Frame mismatch (E007)");
    expect(explanation).toContain(
      "frames of different instances are distinct (Arm1/body vs Arm2/body)",
    );
    expect(explanation).toContain("Hint: route the bond through a joint or a frame-neutral transform");
    expect(explanation).not.toContain("other connection mismatch");
    expect(explanation).not.toContain("accepts");
  });

  it("names the transform as the bridge when a bond joins two frames", () => {
    const catalog = planarCatalog();
    const body = planarBlock(catalog);
    const ground: CatalogBlock = {
      ...(JSON.parse(JSON.stringify(body)) as CatalogBlock),
      ref: "stdlib:planar/GroundPlanar",
      name: "GroundPlanar",
      ports: [{ name: "p", domain: "Planar", size: [3], frame: "world" }],
      source: "@block GroundPlanar begin\nend\n",
      path: "stdlib/planar/GroundPlanar.jl",
    };
    catalog.blocks.push(ground);
    useCatalogStore.getState().setCatalog(catalog);

    open(
      [nodeFrom(ground, "n1", "Ground"), nodeFrom(body, "n2", "Arm1")],
      [createConnection("c2", "bond", { node: "n1", port: "p" }, { node: "n2", port: "p" })],
    );
    useDocumentStore.getState().setSelection([], ["c2"]);
    render(<Inspector />);

    const explanation = screen.getByTestId("inspector-frame-explanation-c2").textContent ?? "";
    expect(explanation).toContain("Ground/world");
    expect(explanation).toContain("Arm1/body");
    expect(explanation).toContain("E007");
    expect(explanation).toContain("FixedTransform or JointTransform");
    expect(screen.getByTestId("inspector-connection-frame-c2").textContent).toContain(
      "no frame reported",
    );
  });
});

describe("the robotics library categories", () => {
  it("groups the live multibond blocks by dimension into 2D and 3D multibond", () => {
    const catalog = spatialCatalog();
    // The live stdlib catalog names the directory "Multibond", and the planar
    // mechanics directory is another group; the authoritative dimension decides
    // the robotics category, without a block list.
    for (const block of catalog.blocks) {
      block.group = "Multibond";
    }
    const planar = catalog.blocks.find((entry) => entry.name === "RigidBody2D");
    if (planar === undefined) {
      throw new Error("the catalog has no RigidBody2D block");
    }
    planar.group = "Planar mechanics";

    useCatalogStore.getState().setCatalog(catalog);
    const { container } = render(<LibraryBrowser />);

    const groupIds = [...container.querySelectorAll(".library-group")].map((group) =>
      group.getAttribute("data-testid"),
    );
    expect(groupIds).toContain("library-group-2D multibond");
    expect(groupIds).toContain("library-group-3D multibond");
    expect(groupIds).not.toContain("library-group-Multibond");

    const planarGroup = screen.getByTestId("library-group-2D multibond");
    const spatialGroup = screen.getByTestId("library-group-3D multibond");
    expect(within(planarGroup).getByTestId("library-item-RigidBody2D")).toBeTruthy();
    expect(within(spatialGroup).getByTestId("library-item-ISpatial")).toBeTruthy();

    // No block is dropped or duplicated by the split.
    expect(screen.getAllByTestId(/^library-item-/)).toHaveLength(catalog.blocks.length + 2);
  });

  it("draws 2-stroke, 3-stroke and 1-stroke port glyphs with accessible labels", () => {
    const catalog = spatialCatalog();
    useCatalogStore.getState().setCatalog(catalog);
    const { container } = render(<LibraryBrowser />);

    const planarRow = screen.getByTestId("library-item-RigidBody2D");
    fireEvent.click(within(planarRow).getByRole("button"));
    const planarGlyph = within(planarRow).getByRole("img", {
      name: "Planar multibond port p, 3 components, 2 strokes, frame body",
    });
    expect(planarGlyph.getAttribute("data-strokes")).toBe("2");
    expect(planarGlyph.getAttribute("data-glyph")).toBe("multibond");
    expect(planarGlyph.querySelectorAll("line")).toHaveLength(2);

    const spatialRow = screen.getByTestId("library-item-ISpatial");
    fireEvent.click(within(spatialRow).getByRole("button"));
    const spatialGlyph = within(spatialRow).getByRole("img", {
      name: "Spatial multibond port p, 6 components, 3 strokes, frame body",
    });
    expect(spatialGlyph.getAttribute("data-strokes")).toBe("3");
    expect(spatialGlyph.querySelectorAll("line")).toHaveLength(3);

    // A scalar domain keeps one stroke, and it is still one accessible port.
    useCatalogStore.getState().setCatalog(scalarCatalog);
    fireEvent.change(screen.getByTestId("library-search"), { target: { value: "DCMotor" } });
    const motorRow = screen.getByTestId("library-item-DCMotor");
    fireEvent.click(within(motorRow).getByRole("button"));
    const shaftRow = within(motorRow).getByTestId("library-port-DCMotor-p-shaft");
    const scalarGlyph = within(shaftRow).getByRole("img", {
      name: "Rotation scalar port shaft, 1 component, 1 stroke",
    });
    expect(scalarGlyph.getAttribute("data-strokes")).toBe("1");
    expect(scalarGlyph.querySelectorAll("line")).toHaveLength(1);
    expect(container.querySelectorAll(".library-port-glyph").length).toBeGreaterThan(0);
  });

  it("keeps an unknown group such as Drives as its own group and a scalar block ungrouped by dimension", () => {
    const catalog = planarCatalog();
    const scalar = scalarCatalog.blocks[0];
    if (scalar === undefined) {
      throw new Error("the scalar catalog has no block");
    }
    const drive: CatalogBlock = {
      ...(JSON.parse(JSON.stringify(scalar)) as CatalogBlock),
      name: "DriveX",
      ref: "stdlib:drives/DriveX",
      group: "Drives",
    };
    delete drive.dimension;
    catalog.blocks.push(drive);
    useCatalogStore.getState().setCatalog(catalog);
    render(<LibraryBrowser />);
    expect(within(screen.getByTestId("library-group-Drives")).getByTestId("library-item-DriveX")).toBeTruthy();
    expect(screen.getByTestId("library-group-2D multibond")).toBeTruthy();
  });

  it("keeps a catalog that already names the categories as it is", () => {
    const catalog = planarCatalog();
    useCatalogStore.getState().setCatalog(catalog);
    render(<LibraryBrowser />);
    expect(screen.getByTestId("library-group-2D multibond")).toBeTruthy();
  });
});
