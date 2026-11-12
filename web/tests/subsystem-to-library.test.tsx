/**
 * "Save to project library" of a subsystem: the plan (the composite source,
 * the blocks it needs, the instance values, what it refuses), the store
 * action, the save with its checks and roll-back, and the inspector dialog.
 */

import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import catalogJson from "../../contracts/fixtures/catalog/valid/catalog.min.json";
import type { Catalog, CatalogBlock } from "../src/contracts/catalog";
import type { Diagnostic } from "../src/contracts/diagnostic";
import type { Model, ModelNode, ModelSubsystemPort } from "../src/contracts/model";
import { resetCodeSession } from "../src/code/codeSession";
import { resetDiagnosticsStore } from "../src/diagnostics/store";
import { Inspector } from "../src/inspector/Inspector";
import { buildCatalogIndex } from "../src/library/catalogIndex";
import { resetCatalogStore, useCatalogStore } from "../src/library/catalogStore";
import { addedErrors, saveSubsystemToProjectLibrary } from "../src/library/saveSubsystem";
import {
  applySubsystemReplacement,
  parameterRetargets,
  planSubsystemBlock,
  subsystemBlockNameProblem,
  subsystemParameters,
  suggestedSubsystemBlockName,
} from "../src/library/subsystemToBlock";
import { resetRunStore } from "../src/plot/runStore";
import { resetDocumentStore, useDocumentStore } from "../src/state/documentStore";
import { createEmptyModel } from "../src/state/modelFactory";

const catalog = catalogJson as unknown as Catalog;
const index = buildCatalogIndex(catalog);

const LAG_SOURCE = `@block Equation begin
    @inputs u::Real
    @outputs y::Real
    @parameters tau::Real = 0.5
    @variables x::Real = 0.0
    @equations begin
        ddt(x) ~ (u - x) / tau
        y ~ x
    end
end
`;

function node(id: string, name: string, block: ModelNode["block"], extra: Partial<ModelNode> = {}): ModelNode {
  return {
    id,
    name,
    block,
    position: { x: 0, y: 0 },
    params: {},
    constants: {},
    starts: {},
    ui: { showLabel: true, color: null },
    ...extra,
  };
}

const ref = (value: string): ModelNode["block"] => ({ ref: value });

function signalPort(
  name: string,
  direction: "input" | "output",
  nodeId: string,
  port: string,
  size: number[] = [],
): ModelSubsystemPort {
  return { name, kind: "signal", direction, type: "Real", size, unit: null, node: nodeId, port };
}

/** An actuator: a torque source on an inertia, a filter on its command and a nested sensor. */
function actuator(): ModelNode {
  const sense = node("s0", "sense", {
    subsystem: {
      ports: [
        { name: "a", kind: "power", domain: "Rotation", size: [1], node: "s1", port: "a" },
        signalPort("y", "output", "s1", "y"),
      ],
      diagram: {
        nodes: [node("s1", "sensor", ref("stdlib:converters/SpeedSensor"))],
        connections: [],
      },
    },
  });
  return node("a0", "Actuator1", {
    subsystem: {
      ports: [
        signalPort("u", "input", "a1", "u"),
        signalPort("speed", "output", "s0", "y"),
        { name: "shaft", kind: "power", domain: "Rotation", size: [1], node: "a3", port: "b", frame: "base" },
        { name: "tap", kind: "power", domain: "Rotation", size: [1], node: "a5", port: "junction" },
      ],
      diagram: {
        nodes: [
          node("a1", "lag", { inline: { source: LAG_SOURCE } }, { params: { tau: "0.25" } }),
          node("a2", "drive", ref("stdlib:rotation/TorqueSource"), { params: { T: "= 2*gain" } }),
          node("a3", "rotor", ref("stdlib:rotation/Inertia"), {
            params: { J: "0.02" },
            starts: { w: "1.5" },
          }),
          node("a4", "damper", ref("stdlib:rotation/RotationalDamper")),
          node("a5", "hub", { junction: "1" }),
          node("a6", "split", { junction: "0" }),
          sense,
        ],
        connections: [
          { id: "c1", kind: "signal", from: { node: "a1", port: "y" }, to: { node: "a2", port: "u" } },
          { id: "c2", kind: "wire", from: { node: "a2", port: "b" }, to: { node: "a3", port: "a" } },
          { id: "c3", kind: "bond", from: { node: "a3", port: "a" }, to: { node: "a4", port: "a" } },
          { id: "c4", kind: "bond", from: { node: "a5" }, to: { node: "a4", port: "b" } },
          { id: "c6", kind: "bond", from: { node: "a5" }, to: { node: "a6" } },
          { id: "c5", kind: "wire", from: { node: "a3", port: "b" }, to: { node: "s0", port: "a" } },
        ],
        annotations: [{ id: "note1", kind: "text", text: "Motor side", x: 0, y: 0, w: 100, h: 40 }],
      },
    },
  });
}

function model(nodes: ModelNode[]): Model {
  const doc = createEmptyModel("Robot");
  doc.diagram.nodes = nodes;
  doc.parameters = [{ name: "gain", value: "3.0" }];
  return doc;
}

function plan(doc: Model, target: ModelNode, expose: string[] = [], taken: string[] = []) {
  return planSubsystemBlock({
    doc,
    node: target,
    path: target.name,
    name: "Actuator",
    index,
    taken,
    expose: new Set(expose),
  });
}

describe("the plan of a subsystem block", () => {
  it("writes the composite source, the blocks it needs and the instance values", () => {
    const target = actuator();
    const result = plan(model([target]), target, ["rotor/J"]);
    expect(result.problems).toEqual([]);

    // Dependencies first: the inline block, the nested subsystem, then the block itself.
    expect(result.blocks.map((block) => [block.name, block.origin, block.path])).toEqual([
      ["Equation", "inline", "Actuator1/lag"],
      ["Actuator_sense", "subsystem", "Actuator1/sense"],
      ["Actuator", "subsystem", "Actuator1"],
    ]);
    expect(result.blocks[0]?.source).toBe(LAG_SOURCE);
    expect(result.blocks[1]?.source).toBe(`@block Actuator_sense begin
    # Saved from the subsystem Actuator1/sense.
    @ports begin
        a::Power{Rotation}
    end
    @outputs begin
        y::Real
    end
    @components begin
        sensor = SpeedSensor()
    end
    @connections begin
        connect(a, sensor.a)
        connect(y, sensor.y)
    end
end
`);
    expect(result.blocks[2]?.source).toBe(`@block Actuator begin
    # Saved from the subsystem Actuator1.
    @ports begin
        shaft::Power{Rotation}, [frame = "base"]
        tap::Power{Rotation}
    end
    @inputs begin
        u::Real
    end
    @outputs begin
        speed::Real
    end
    @parameters begin
        T::Real = 1.0, [unit = "N*m", description = "Torque gain on the control input"]
        J::Real = 0.02, [unit = "kg*m^2", min = 0, description = "Moment of inertia"]
    end
    @components begin
        lag = Equation(tau = 0.25)
        drive = TorqueSource(T = T)
        rotor = Inertia(J = J)
        damper = RotationalDamper()
        hub = Junction(1)
        split = Junction(0)
        sense = Actuator_sense()
    end
    @connections begin
        connect(u, lag.u)
        connect(speed, sense.y)
        connect(shaft, rotor.b)
        connect(tap, hub)
        connect(lag.y, drive.u)
        connect(drive.b, rotor.a)
        bond(rotor.a, damper.a)
        bond(hub, damper.b)
        bond(hub, split)
        connect(rotor.b, sense.a)
    end
end
`);

    // The global stays on the instance; the plain number became the block's default.
    expect(result.instance.params).toEqual({ T: "2*gain" });
    expect(result.instance.starts).toEqual({ "rotor/w": "1.5" });
    expect(result.exposed).toEqual([
      { name: "T", key: "drive/T" },
      { name: "J", key: "rotor/J" },
    ]);
    expect([...parameterRetargets("Arm/Actuator1", result)]).toEqual([
      ["Arm/Actuator1/drive/T", "Arm/Actuator1/T"],
      ["Arm/Actuator1/rotor/J", "Arm/Actuator1/J"],
    ]);
    // Every bond, by its place among the block's `connect`/`bond` lines; `c6` joins two
    // junctions, so it is the one with signals of its own.
    expect(result.bondRenames).toEqual([
      { from: "c3", to: "Actuator/c7" },
      { from: "c4", to: "Actuator/c8" },
      { from: "c6", to: "Actuator/c9" },
    ]);
    expect(result.notes.join(" ")).toContain("1 note");
    expect(result.notes.join(" ")).toContain("1 start value stays with this instance");
  });

  it("lists the parameters inside, marking the ones a global forces out", () => {
    const target = actuator();
    const entries = subsystemParameters(model([target]), target, index);
    expect(entries.map((entry) => entry.key)).toEqual(["drive/T", "rotor/J", "damper/d"]);
    expect(entries[0]).toMatchObject({ value: "2*gain", forced: true, blocked: null });
    expect(entries[1]).toMatchObject({ value: "0.02", forced: false });
    expect(entries[2]).toMatchObject({ value: null, default: "1e-3", forced: false });
  });

  it("passes an exposed parameter of a nested subsystem up through both blocks", () => {
    const inner = node("i0", "inner", {
      subsystem: {
        ports: [],
        diagram: {
          nodes: [node("i1", "R1", ref("stdlib:electrical/Resistor"), { params: { R: "gain" } })],
          connections: [],
        },
      },
    });
    const outer = node("o0", "Outer1", { subsystem: { ports: [], diagram: { nodes: [inner], connections: [] } } });
    const result = plan(model([outer]), outer);
    expect(result.problems).toEqual([]);
    expect(result.blocks[0]?.source).toContain("R::Real = 1000.0");
    expect(result.blocks[0]?.source).toContain("R1 = Resistor(R = R)");
    expect(result.blocks[1]?.source).toContain("R::Real = 1000.0");
    expect(result.blocks[1]?.source).toContain("inner = Actuator_inner(R = R)");
    expect(result.instance.params).toEqual({ R: "gain" });
    expect(result.exposed).toEqual([{ name: "R", key: "inner/R1/R" }]);
  });

  it("names two exposed parameters apart and writes vectors and constants", () => {
    const sub = node("o0", "Mix1", {
      subsystem: {
        ports: [signalPort("y", "output", "m3", "y", [2])],
        diagram: {
          nodes: [
            node("m1", "R1", ref("stdlib:electrical/Resistor")),
            node("m2", "R2", ref("stdlib:electrical/Resistor")),
            node("m3", "add", ref("stdlib:continuous/Sum"), {
              params: { signs: "[1.0, -1.0, 1.0]" },
              constants: { N: 3 },
            }),
          ],
          connections: [],
        },
      },
    });
    const result = plan(model([sub]), sub, ["R1/R", "R2/R", "add/signs"]);
    expect(result.problems).toEqual([]);
    const source = result.blocks[0]?.source ?? "";
    expect(source).toContain("y::Vec{2}");
    expect(source).toContain("R1 = Resistor(R = R)");
    expect(source).toContain("R2 = Resistor(R = R2_R)");
    // The vector's length is the node's own N (the block declares `signs::Vec{N}`), so its value
    // fits and becomes the default.
    expect(source).toContain("signs::Vec{3} = [1.0, -1.0, 1.0]");
    expect(source).toContain("add = Sum(N = 3, signs = signs)");
    expect(result.instance.params).toEqual({});

    // Without a value of that length the block's two-element default does not fit.
    const bare = structuredClone(sub);
    if ("subsystem" in bare.block) {
      const add = bare.block.subsystem.diagram.nodes[2];
      if (add !== undefined) {
        add.params = {};
      }
    }
    expect(subsystemParameters(model([bare]), bare, index).find((entry) => entry.key === "add/signs")?.blocked)
      .toContain("is not a plain vector of its size");
  });

  it("says what it cannot translate", () => {
    const sub = node("o0", "Bad1", {
      subsystem: {
        ports: [signalPort("gain", "output", "b1", "y")],
        diagram: {
          nodes: [
            node("b1", "gain", ref("stdlib:continuous/Gain")),
            node("b2", "end", ref("stdlib:continuous/Gain")),
            node("b3", "ghost", ref("stdlib:nowhere/Missing")),
            node("b4", "table", ref("stdlib:continuous/Sum"), {
              constants: { N: "gain", file: "data.csv" },
            }),
            node("b5", "anon", { inline: { source: "@equations y ~ u" } }, { params: { k: "gain" } }),
            node("b6", "col", ref("stdlib:continuous/Sum"), { constants: { N: [[1], [2]] } }),
          ],
          connections: [{ id: "c1", kind: "signal", from: { node: "b1", port: "y" }, to: { node: "gone", port: "u" } }],
        },
      },
    });
    const problems = plan(model([sub]), sub).problems.join("\n");
    expect(problems).toContain("has both a port and a block called gain");
    expect(problems).toContain("“end” is a reserved word");
    expect(problems).toContain("stdlib:nowhere/Missing, which is not in the catalog");
    expect(problems).toContain("Constant N of Bad1/table uses the global parameter gain");
    expect(problems).toContain("keeps the setting “file”");
    expect(problems).toContain("inline block without a @block <Name> declaration");
    expect(problems).toContain("one-column or ragged matrix");
    expect(problems).toContain("refers to a block that is no longer there");
  });

  it("refuses a stdlib block that a project block of the same name would replace", () => {
    const shadow = { ...catalog.blocks[0], ref: "project:Gain", name: "Gain" } as CatalogBlock;
    const sub = node("o0", "S1", {
      subsystem: {
        ports: [],
        diagram: { nodes: [node("g1", "g", ref("stdlib:continuous/Gain"))], connections: [] },
      },
    });
    const result = planSubsystemBlock({
      doc: model([sub]),
      node: sub,
      path: "S1",
      name: "Scaled",
      index: buildCatalogIndex({ ...catalog, blocks: [...catalog.blocks, shadow] }),
      taken: ["Gain"],
    });
    expect(result.problems.join("\n")).toContain("the project library has its own Gain");
  });

  it("proposes and validates the block name", () => {
    expect(suggestedSubsystemBlockName(actuator(), [], index)).toBe("Actuator");
    expect(suggestedSubsystemBlockName(actuator(), ["actuator"], index)).toBe("Actuator2");
    expect(suggestedSubsystemBlockName(node("x", "Gain1", ref("x")), [], index)).toBe("Gain2");
    expect(subsystemBlockNameProblem("Actuator", [], index)).toBeNull();
    expect(subsystemBlockNameProblem("Actuator", ["Actuator"], index)).toContain("already has a block");
    expect(subsystemBlockNameProblem("DCMotor", [], index)).toContain("The standard library already has DCMotor");
  });
});

describe("replacing the subsystem by an instance", () => {
  it("keeps the node, sets the instance values and moves dashboard inputs", () => {
    const target = actuator();
    const arm = node("arm", "Arm", { subsystem: { ports: [], diagram: { nodes: [target], connections: [] } } });
    const doc = model([arm]);
    doc.plots = [{ id: "p1", title: "Hub", signals: ["Arm/Actuator1/c6.e", "Arm/Actuator1/rotor/w"] }] as Model["plots"];
    doc.dashboard = {
      cards: [
        { id: "k1", kind: "slider", size: "1x1", parameter: "Arm/Actuator1/rotor/J" },
        { id: "k2", kind: "slider", size: "1x1", parameter: "Arm/Actuator1/damper/d" },
      ],
    } as Model["dashboard"];
    const result = planSubsystemBlock({
      doc,
      node: target,
      path: "Arm/Actuator1",
      name: "Actuator",
      index,
      taken: [],
      expose: new Set(["rotor/J"]),
    });
    useDocumentStore.getState().openDocument("demo", "Robot", doc);
    // The node is replaced in the open diagram: ids are unique per diagram only.
    useDocumentStore.getState().enterSubsystem("arm");
    const store = useDocumentStore.getState();
    expect(store.replaceSubsystemWithRef("missing", "project:Actuator", "Arm/x", result).ok).toBe(false);
    expect(store.replaceSubsystemWithRef("a0", "project:Actuator", "Arm/Actuator1", result).ok).toBe(true);

    const after = useDocumentStore.getState().doc;
    const armNode = after?.diagram.nodes[0];
    const replaced = armNode !== undefined && "subsystem" in armNode.block ? armNode.block.subsystem.diagram.nodes[0] : undefined;
    expect(replaced).toMatchObject({
      id: "a0",
      name: "Actuator1",
      block: { ref: "project:Actuator" },
      params: { T: "2*gain" },
      starts: { "rotor/w": "1.5" },
    });
    expect(after?.dashboard?.cards.map((card) => card.parameter)).toEqual([
      "Arm/Actuator1/J",
      "Arm/Actuator1/damper/d",
    ]);
    // A plotted bond between two junctions follows the compiler's new name for it.
    expect(after?.plots?.[0]?.signals).toEqual(["Arm/Actuator1/Actuator/c9.e", "Arm/Actuator1/rotor/w"]);

    // One undo step brings the drawn subsystem back.
    useDocumentStore.getState().undo();
    const undone = useDocumentStore.getState().doc?.diagram.nodes[0];
    const back = undone !== undefined && "subsystem" in undone.block ? undone.block.subsystem.diagram.nodes[0] : undefined;
    expect(back !== undefined && "subsystem" in back.block).toBe(true);
    expect(useDocumentStore.getState().doc?.dashboard?.cards[0]?.parameter).toBe("Arm/Actuator1/rotor/J");
  });

  it("does nothing for a node that is not a subsystem", () => {
    const doc = model([node("n1", "G1", ref("stdlib:continuous/Gain"))]);
    const target = actuator();
    expect(applySubsystemReplacement(doc, "n1", "project:X", "G1", plan(model([target]), target))).toBe(false);
  });
});

function answer(status: number, body: unknown): Response {
  const text = typeof body === "string" ? body : JSON.stringify(body);
  return {
    status,
    ok: status >= 200 && status < 300,
    text: async () => text,
    json: async () => JSON.parse(text) as unknown,
  } as unknown as Response;
}

interface Backend {
  /** The catalog lists what was written; false plays the fake worker. */
  publish: boolean;
  /** Errors of the model check when the model holds a `project:` instance. */
  instanceErrors?: Diagnostic[];
  blockErrors?: Diagnostic[];
  files: Map<string, string>;
  deleted: string[];
}

function stubBackend(backend: Backend) {
  const mock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
    const url = String(input);
    const method = init?.method ?? "GET";
    const name = decodeURIComponent(url.split("/library/")[1] ?? "");
    if (method === "PUT" && url.includes("/library/")) {
      backend.files.set(name, String(init?.body));
      return answer(200, { project: "demo", name });
    }
    if (method === "DELETE" && url.includes("/library/")) {
      backend.files.delete(name);
      backend.deleted.push(name);
      return answer(204, "");
    }
    if (url.includes("/api/catalog")) {
      const extra = backend.publish
        ? [...backend.files.keys()].map(
            (file) => ({ ...catalog.blocks[0], ref: `project:${file}`, name: file, group: "Project" }) as CatalogBlock,
          )
        : [];
      return answer(200, { ...catalog, blocks: [...catalog.blocks, ...extra] });
    }
    if (url.includes("/api/check/block")) {
      return answer(200, { diagnostics: backend.blockErrors ?? [], interface: null });
    }
    if (url.includes("/api/check/model")) {
      const body = String(init?.body);
      const instance = body.includes('"project:Actuator"');
      return answer(200, { diagnostics: instance ? (backend.instanceErrors ?? []) : [], domains: {} });
    }
    if (url.includes("/api/projects/demo")) {
      return answer(200, {
        name: "demo",
        project: { libraryDir: "library" },
        models: [],
        library: [...backend.files.keys()].map((file) => ({ name: file, modified: 0 })),
      });
    }
    return answer(404, { detail: `unexpected ${method} ${url}` });
  });
  vi.stubGlobal("fetch", mock);
  return mock;
}

const E102: Diagnostic = {
  code: "E102",
  severity: "error",
  message: "`Inertia` has no port `c`",
  path: "Actuator1/rotor",
};

function openActuator(): { target: ModelNode } {
  const target = actuator();
  useDocumentStore.getState().openDocument("demo", "Robot", model([target]));
  return { target };
}

function topNode(): ModelNode | undefined {
  return useDocumentStore.getState().doc?.diagram.nodes[0];
}

beforeEach(() => {
  resetDocumentStore();
  resetCatalogStore();
  resetDiagnosticsStore();
  resetRunStore();
  resetCodeSession();
  useCatalogStore.getState().setCatalog(catalog);
});

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("saving a subsystem to the project library", () => {
  function save(target: ModelNode) {
    const doc = useDocumentStore.getState().doc as Model;
    return saveSubsystemToProjectLibrary("demo", {
      nodeId: target.id,
      path: target.name,
      name: "Actuator",
      plan: plan(doc, target),
    });
  }

  it("writes the blocks, checks the model and replaces the node", async () => {
    const backend: Backend = { publish: true, files: new Map(), deleted: [] };
    stubBackend(backend);
    const { target } = openActuator();
    const outcome = await save(target);
    expect(outcome.ref).toBe("project:Actuator");
    expect([...backend.files.keys()]).toEqual(["Equation", "Actuator_sense", "Actuator"]);
    expect(backend.deleted).toEqual([]);
    expect(topNode()?.block).toEqual({ ref: "project:Actuator" });
    expect(useCatalogStore.getState().index?.blocksByRef.has("project:Actuator")).toBe(true);
  });

  it("writes nothing when a planned source does not check", async () => {
    const backend: Backend = {
      publish: true,
      files: new Map(),
      deleted: [],
      blockErrors: [{ code: "E001", severity: "error", message: "unexpected token" }],
    };
    stubBackend(backend);
    const { target } = openActuator();
    await expect(save(target)).rejects.toThrow("would not compile, so nothing was saved: E001: unexpected token");
    expect(backend.files.size).toBe(0);
    expect("subsystem" in (topNode()?.block ?? {})).toBe(true);
  });

  it("removes the files again when the instance adds an error to the model", async () => {
    const backend: Backend = { publish: true, files: new Map(), deleted: [], instanceErrors: [E102] };
    stubBackend(backend);
    const { target } = openActuator();
    await expect(save(target)).rejects.toThrow(
      "would not stand in for the subsystem, so nothing was saved: E102: `Inertia` has no port `c` (Actuator1/rotor)",
    );
    expect(backend.files.size).toBe(0);
    expect(backend.deleted).toEqual(["Equation", "Actuator_sense", "Actuator"]);
    expect("subsystem" in (topNode()?.block ?? {})).toBe(true);
    expect(useCatalogStore.getState().index?.blocksByRef.has("project:Actuator")).toBe(false);
  });

  it("keeps the subsystem when the catalog does not list the block (fake worker)", async () => {
    const backend: Backend = { publish: false, files: new Map(), deleted: [] };
    stubBackend(backend);
    const { target } = openActuator();
    const outcome = await save(target);
    expect(outcome.ref).toBeNull();
    expect(outcome.pending).toContain("does not list project:Actuator");
    expect(backend.files.size).toBe(3);
    expect("subsystem" in (topNode()?.block ?? {})).toBe(true);
  });

  it("only counts errors the model did not have before", () => {
    const warning: Diagnostic = { code: "W201", severity: "warning", message: "derivative causality" };
    expect(addedErrors([E102], [E102, warning])).toEqual([]);
    expect(addedErrors([], [E102, E102])).toEqual(["E102: `Inertia` has no port `c` (Actuator1/rotor)"]);
  });
});

describe("the inspector dialog", () => {
  it("offers the save for a subsystem, lists its parameters and reports the result", async () => {
    const backend: Backend = { publish: true, files: new Map(), deleted: [] };
    stubBackend(backend);
    openActuator();
    useDocumentStore.getState().setSelection(["a0"], []);
    render(<Inspector />);
    expect(screen.queryByTestId("inspector-copy-library")).toBeNull();
    fireEvent.click(screen.getByTestId("inspector-save-library"));

    const name = screen.getByTestId("subsystem-block-name") as HTMLInputElement;
    await waitFor(() => expect(name.disabled).toBe(false));
    expect(name.value).toBe("Actuator");

    // The global-driven torque is ticked and locked; the inertia is the user's choice.
    const forced = screen.getByTestId("subsystem-block-expose-drive/T") as HTMLInputElement;
    expect(forced.checked).toBe(true);
    expect(forced.disabled).toBe(true);
    const inertia = screen.getByTestId("subsystem-block-expose-rotor/J") as HTMLInputElement;
    expect(inertia.checked).toBe(false);
    fireEvent.click(inertia);
    expect(screen.getByTestId("subsystem-block-others").textContent).toContain("Actuator_sense");

    // A stdlib name is refused as it is typed.
    fireEvent.change(name, { target: { value: "DCMotor" } });
    expect((screen.getByTestId("subsystem-block-submit") as HTMLButtonElement).disabled).toBe(true);
    fireEvent.change(name, { target: { value: "Actuator" } });

    fireEvent.click(screen.getByTestId("subsystem-block-submit"));
    await waitFor(() => expect(screen.queryByTestId("subsystem-block-dialog")).toBeNull());
    expect(backend.files.get("Actuator")).toContain("rotor = Inertia(J = J)");
    expect(topNode()?.block).toEqual({ ref: "project:Actuator" });
  });

  it("shows why a subsystem cannot be saved and keeps the button disabled", async () => {
    stubBackend({ publish: true, files: new Map(), deleted: [] });
    const empty = node("e0", "Empty1", { subsystem: { ports: [], diagram: { nodes: [], connections: [] } } });
    useDocumentStore.getState().openDocument("demo", "Robot", model([empty]));
    useDocumentStore.getState().setSelection(["e0"], []);
    render(<Inspector />);
    fireEvent.click(screen.getByTestId("inspector-save-library"));
    await waitFor(() => expect(screen.getByTestId("subsystem-block-problems").textContent).toContain("is empty"));
    expect((screen.getByTestId("subsystem-block-submit") as HTMLButtonElement).disabled).toBe(true);
  });
});

describe("a node id that another diagram also uses", () => {
  it("replaces the subsystem of the open diagram, not the first node with that id", () => {
    // `Other` holds a block with the id of the subsystem that is exported.
    const twin = node("a0", "Twin", { ref: "stdlib:rotation/Inertia" });
    const other = node("o1", "Other", { subsystem: { ports: [], diagram: { nodes: [twin], connections: [] } } });
    const target = actuator();
    const doc = model([other, target]);
    const result = planSubsystemBlock({
      doc,
      node: target,
      path: target.name,
      name: "Actuator",
      index,
      taken: [],
    });
    const candidate = structuredClone(doc) as Model;
    expect(applySubsystemReplacement(candidate, "a0", "project:Actuator", target.name, result, [])).toBe(true);
    expect(candidate.diagram.nodes[1]?.block).toEqual({ ref: "project:Actuator" });
    const untouched = candidate.diagram.nodes[0];
    expect(untouched !== undefined && "subsystem" in untouched.block && untouched.block.subsystem.diagram.nodes[0]?.block).toEqual({
      ref: "stdlib:rotation/Inertia",
    });
    // Looked up in a diagram that does not hold it: nothing is replaced.
    expect(applySubsystemReplacement(structuredClone(doc) as Model, "a0", "project:Actuator", "x", result, ["o1"])).toBe(false);
  });

  it("refuses names the block language reserves", () => {
    const target = actuator();
    const inner = "subsystem" in target.block ? target.block.subsystem.diagram.nodes[0] : undefined;
    if (inner !== undefined) {
      inner.name = "t";
    }
    const result = planSubsystemBlock({ doc: model([target]), node: target, path: target.name, name: "Actuator", index, taken: [] });
    expect(result.problems.join(" ")).toContain("reserved word");
  });
});
