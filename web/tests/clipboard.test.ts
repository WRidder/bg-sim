/**
 * Copy and paste through the system clipboard (src/clipboard/): the envelope round trip
 * and its schema checks, dependency collection through nested subsystems (library
 * blocks, the global closure, CSV files, note images), conflict resolution and its
 * rewrites, one undo step per paste, the paste position, and ids that stay unique.
 */

import { readFileSync, readdirSync } from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

import { beforeEach, describe, expect, it } from "vitest";

import { collectDependencies, catalogLibrary, globalClosure } from "../src/clipboard/dependencies";
import {
  buildEnvelope,
  CLIPBOARD_FORMAT,
  MAX_CLIPBOARD_CHARS,
  readEnvelopeText,
  serializeEnvelope,
  type ClipboardEnvelope,
} from "../src/clipboard/envelope";
import { analyse, pasteEnvelope, reportLines, resetPasteCascade, type PasteIo } from "../src/clipboard/pasteFlow";
import { clipCentre, preparePaste } from "../src/clipboard/pastePlan";
import { usePasteUiStore } from "../src/clipboard/pasteUi";
import { freeDataName, freeGlobalName, resolve } from "../src/clipboard/resolve";
import { validateEnvelope } from "../src/clipboard/validate";
import type { Model, ModelDiagram, ModelNode } from "../src/contracts/model";
import { allConnectionIds, allNodeIds } from "../src/editor/subsystemPath";
import { resetDocumentStore, useDocumentStore } from "../src/state/documentStore";
import { createEmptyModel } from "../src/state/modelFactory";

const here = path.dirname(fileURLToPath(import.meta.url));
const fixtures = path.resolve(here, "..", "..", "contracts", "fixtures", "clipboard");

const MOTOR = `@block MyMotor begin
    @ports a::Power{Rotation}
    @parameters k::Real = 1.0
    @components begin
        g = MyGear(n = 3)
    end
end
`;
const GEAR = `@block MyGear begin
    @parameters n::Real = 2.0
end
`;

function ref(id: string, name: string, blockRef: string, x: number, y: number, extra: Partial<ModelNode> = {}): ModelNode {
  return { id, name, block: { ref: blockRef }, position: { x, y }, ...extra };
}

function diagram(nodes: ModelNode[], extra: Partial<ModelDiagram> = {}): ModelDiagram {
  return { nodes, connections: [], ...extra };
}

/** A model with a subsystem Drive (a project block, a CsvSource, a note image) and a load. */
function sourceModel(): Model {
  const model = createEmptyModel("rig");
  model.parameters = [
    { name: "J0", value: "0.002" },
    { name: "k_motor", value: "0.1*J0 + 1" },
    { name: "unused", value: "42" },
    { name: "scale", value: "3" },
  ];
  model.diagram = diagram(
    [
      {
        id: "n1",
        name: "Drive",
        position: { x: 100, y: 100 },
        block: {
          subsystem: {
            ports: [{ name: "shaft", kind: "power", domain: "Rotation", size: [1], node: "n2", port: "a" }],
            diagram: diagram(
              [
                ref("n2", "Motor", "project:MyMotor", 0, 0, { params: { k: "k_motor" } }),
                ref("n3", "Profile", "stdlib:sources/CsvSource", -160, 0, { constants: { file: "data/profile.csv" } }),
              ],
              {
                connections: [
                  { id: "c9", kind: "signal", from: { node: "n3", port: "y" }, to: { node: "n2", port: "u" } },
                ],
                annotations: [{ id: "a1", kind: "text", text: "![w](assets/0123456789ab.png)", x: 0, y: 100, w: 100, h: 60 }],
                probes: [{ id: "p1", name: "Scope", kind: "window", position: { x: 0, y: 0 }, links: [] }],
              },
            ),
          },
        },
      },
      ref("n4", "Load", "stdlib:rotation/Inertia", 300, 100, { params: { J: "2*J0" } }),
      ref("n5", "Other", "stdlib:continuous/Gain", 500, 500, { params: { k: "scale" } }),
    ],
    {
      connections: [
        { id: "c1", kind: "bond", from: { node: "n1", port: "shaft" }, to: { node: "n4", port: "a" }, route: [{ x: 200, y: 100 }] },
        { id: "c2", kind: "signal", from: { node: "n4", port: "w" }, to: { node: "n5", port: "u" } },
      ],
      annotations: [{ id: "a1", kind: "text", text: "Drive train", x: 80, y: 20, w: 160, h: 60 }],
      shapes: [{ id: "s1", kind: "rectangle", x: 60, y: 60, w: 300, h: 120, locked: true }],
    },
  );
  model.bindings = [];
  model.plots = [{ id: "pl1", title: "Speed", signals: ["Load/w"] }];
  return model;
}

const library = catalogLibrary([
  { ref: "project:MyMotor", source: MOTOR },
  { ref: "project:MyGear", source: GEAR },
  { ref: "project:Unrelated", source: "@block Unrelated begin\nend\n" },
]);

function copyDrive(): ClipboardEnvelope {
  const envelope = buildEnvelope({
    doc: sourceModel(),
    path: [],
    selection: ["n1", "n4", "note:a1", "shape:s1"],
    project: "lab",
    model: "rig",
    library,
  });
  if (envelope === null) {
    throw new Error("nothing copied");
  }
  return envelope;
}

/** A fake backend: a target project with a library, data files, and a log of writes. */
function fakeIo(options: {
  targetLibrary?: Record<string, string>;
  sourceLibrary?: Record<string, string>;
  data?: Record<string, Record<string, string>>;
  choices?: Record<string, "existing" | "rename" | "inline"> | null;
  publish?: boolean;
} = {}): PasteIo & { log: string[]; asked: string[] } {
  const log: string[] = [];
  const asked: string[] = [];
  const libraries: Record<string, Record<string, string>> = {
    lab: { MyMotor: MOTOR, MyGear: GEAR, ...(options.sourceLibrary ?? {}) },
    other: { ...(options.targetLibrary ?? {}) },
  };
  const data = options.data ?? { lab: { "profile.csv": "t,y\n0,1\n" }, other: {} };
  return {
    log,
    asked,
    libraryNames: async (project) => Object.keys(libraries[project] ?? {}),
    librarySource: async (project, name) => libraries[project]?.[name] ?? null,
    writeLibrary: async (project, name, source) => {
      log.push(`library ${project}/${name}`);
      libraries[project] = { ...(libraries[project] ?? {}), [name]: source };
    },
    refreshCatalog: async (project) =>
      options.publish === false
        ? null
        : ({
            blocks: Object.keys(libraries[project] ?? {}).map((name) => ({ ref: `project:${name}` })),
          } as never),
    dataFileNames: async (project) => Object.keys(data[project] ?? {}),
    dataText: async (project, file) => data[project]?.[file] ?? null,
    writeData: async (project, file, text) => {
      log.push(`data ${project}/${file}`);
      data[project] = { ...(data[project] ?? {}), [file]: text };
    },
    copyAssets: async (target, from, files) => {
      log.push(`assets ${from.project}/${from.model} -> ${target.project}/${target.model}: ${files.join(",")}`);
      return { copied: [...files], existing: [], missing: [] };
    },
    ask: async (conflicts) => {
      asked.push(...conflicts.map((conflict) => conflict.key));
      return options.choices === undefined ? {} : options.choices;
    },
  };
}

beforeEach(() => {
  resetDocumentStore();
  resetPasteCascade();
  usePasteUiStore.setState({ dialog: null, notice: null, busy: false });
});

describe("the envelope", () => {
  it("round-trips through the clipboard text and validates against the schema", () => {
    const envelope = copyDrive();
    expect(envelope.format).toBe(CLIPBOARD_FORMAT);
    expect(envelope.nodes.map((node) => node.name)).toEqual(["Drive", "Load"]);
    // Only the connection between two copied nodes travels.
    expect(envelope.connections.map((connection) => connection.id)).toEqual(["c1"]);
    expect(envelope.annotations).toHaveLength(1);
    expect(envelope.shapes).toHaveLength(1);
    // Probes inside a copied subsystem stay behind and are counted.
    const drive = envelope.nodes[0];
    expect(drive !== undefined && "subsystem" in drive.block ? drive.block.subsystem.diagram.probes : "x").toBeUndefined();
    expect(envelope.omitted).toEqual({ bindings: 0, probes: 1, dashboardCards: 0, plots: 1 });

    const read = readEnvelopeText(serializeEnvelope(envelope));
    expect(read.kind).toBe("envelope");
    const checked = validateEnvelope(read.kind === "envelope" ? read.value : null);
    expect(checked.ok).toBe(true);
    expect(checked.ok ? checked.envelope : null).toEqual(envelope);
  });

  it("refuses unknown versions, foreign text, oversize text and schema violations", () => {
    expect(readEnvelopeText("hello world").kind).toBe("foreign");
    expect(readEnvelopeText('{"format":"bgsim.model"}').kind).toBe("foreign");
    expect(readEnvelopeText(null).kind).toBe("foreign");
    const future = readEnvelopeText(JSON.stringify({ ...copyDrive(), version: 2 }));
    expect(future.kind).toBe("invalid");
    expect(future.kind === "invalid" ? future.message : "").toMatch(/version 2/);
    const huge = `{"format":"${CLIPBOARD_FORMAT}","pad":"${"x".repeat(MAX_CLIPBOARD_CHARS)}"}`;
    expect(readEnvelopeText(huge).kind).toBe("invalid");

    const bad = { ...copyDrive(), nodes: [ref("n1", "2 Gain", "stdlib:continuous/Gain", 0, 0)] };
    const checked = validateEnvelope(bad);
    expect(checked.ok).toBe(false);
    expect(checked.ok ? "" : checked.message).toMatch(/\/nodes\/0\/name/);
  });

  it("agrees with the contract fixtures", () => {
    for (const kind of ["valid", "invalid"] as const) {
      for (const file of readdirSync(path.join(fixtures, kind))) {
        const value = JSON.parse(readFileSync(path.join(fixtures, kind, file), "utf8")) as unknown;
        expect(validateEnvelope(value).ok, `${kind}/${file}`).toBe(kind === "valid");
      }
    }
  });
});

describe("dependency collection", () => {
  it("follows nested subsystems, library sources and the global closure", () => {
    const deps = copyDrive().dependencies;
    // MyMotor is used inside the subsystem; its source instantiates MyGear.
    expect(deps.libraryBlocks).toEqual([
      { name: "MyMotor", source: MOTOR },
      { name: "MyGear", source: GEAR },
    ]);
    // k_motor (nested) and J0 (Load, and k_motor's value); not `unused` or `scale`.
    expect(deps.globals.map((entry) => entry.name)).toEqual(["J0", "k_motor"]);
    expect(deps.dataFiles).toEqual(["profile.csv"]);
    expect(deps.assets).toEqual(["0123456789ab.png"]);
  });

  it("lists a project block without a source when the catalog lacks it, and scans inline code", () => {
    const deps = collectDependencies({
      nodes: [
        ref("n1", "A", "project:Missing", 0, 0),
        { id: "n2", name: "B", position: { x: 0, y: 0 }, block: { inline: { source: "@block B begin\n  @components g = MyGear(n = 2)\nend" } } },
      ],
      annotations: [],
      globals: [],
      library,
    });
    expect(deps.libraryBlocks).toEqual([{ name: "Missing" }, { name: "MyGear", source: GEAR }]);
  });

  it("closes globals over chains and ignores cycles", () => {
    const globals = [
      { name: "a", value: "b + 1" },
      { name: "b", value: "c * 2" },
      { name: "c", value: "a" },
      { name: "d", value: "1" },
    ];
    expect(globalClosure(globals, ["a"]).map((entry) => entry.name)).toEqual(["a", "b", "c"]);
  });
});

describe("conflict resolution", () => {
  const target = (globals: Model["parameters"] = []) => ({ project: "other", model: "bench", path: [], globals: globals ?? [] });

  it("creates what the target lacks and asks nothing", async () => {
    const envelope = copyDrive();
    const io = fakeIo();
    const analysis = await analyse(envelope, target(), io);
    expect(analysis.conflicts).toEqual([]);
    expect(analysis.library.map((entry) => [entry.name, entry.status])).toEqual([
      ["MyMotor", "create"],
      ["MyGear", "create"],
    ]);
    expect(analysis.data.map((entry) => entry.status)).toEqual(["copy"]);
    expect(analysis.assets?.files).toEqual(["0123456789ab.png"]);
    const resolution = resolve(envelope, analysis, {});
    expect(resolution.libraryWrites.map((write) => write.name)).toEqual(["MyMotor", "MyGear"]);
    expect(resolution.addGlobals.map((entry) => entry.name)).toEqual(["J0", "k_motor"]);
    expect(resolution.dataWrites.map((write) => write.file)).toEqual(["profile.csv"]);
  });

  it("keeps the target's definitions by default", async () => {
    const envelope = copyDrive();
    const io = fakeIo({
      targetLibrary: { MyMotor: "@block MyMotor begin\nend\n" },
      data: { lab: { "profile.csv": "t,y\n0,1\n" }, other: { "profile.csv": "t,y\n0,5\n" } },
    });
    const analysis = await analyse(envelope, target([{ name: "J0", value: "7" }]), io);
    expect(analysis.conflicts.map((conflict) => conflict.key)).toEqual([
      "library:MyMotor",
      "global:J0",
      "dataFile:profile.csv",
    ]);
    const resolution = resolve(envelope, analysis, {});
    // MyMotor stays the target's, so MyGear (only its dependency) is not imported either.
    expect(resolution.libraryWrites).toEqual([]);
    expect(resolution.dataWrites).toEqual([]);
    expect(resolution.addGlobals.map((entry) => entry.name)).toEqual(["k_motor"]);
    expect(resolution.rewrites.refs).toEqual({});
    expect(resolution.kept).toEqual(["library block MyMotor", "global J0 = 7", "data file profile.csv"]);
  });

  it("imports under new names and rewrites references, expressions and files", async () => {
    const envelope = copyDrive();
    const io = fakeIo({
      targetLibrary: { MyMotor: "@block MyMotor begin\nend\n", MyGear: "@block MyGear begin\nend\n" },
      data: { lab: { "profile.csv": "t,y\n0,1\n" }, other: { "profile.csv": "t,y\n0,5\n" } },
    });
    const analysis = await analyse(envelope, target([{ name: "J0", value: "7" }]), io);
    const resolution = resolve(envelope, analysis, {
      "library:MyMotor": "rename",
      "library:MyGear": "rename",
      "global:J0": "rename",
      "dataFile:profile.csv": "rename",
    });
    expect(resolution.libraryWrites.map((write) => write.name)).toEqual(["MyMotor2", "MyGear2"]);
    const motor = resolution.libraryWrites[0]?.source ?? "";
    expect(motor).toMatch(/@block MyMotor2 begin/);
    // The renamed motor instantiates the renamed gear.
    expect(motor).toMatch(/g = MyGear2\(n = 3\)/);
    expect(resolution.rewrites.refs).toEqual({ "project:MyMotor": "project:MyMotor2", "project:MyGear": "project:MyGear2" });
    expect(resolution.addGlobals).toEqual([
      { name: "J0_2", value: "0.002" },
      { name: "k_motor", value: "0.1*J0_2 + 1" },
    ]);
    expect(resolution.rewrites.dataFiles).toEqual({ "data/profile.csv": "data/profile2.csv" });

    useDocumentStore.getState().openDocument("other", "bench", { ...createEmptyModel("bench"), parameters: [{ name: "J0", value: "7" }] });
    useDocumentStore.getState().pasteClip(envelope, { at: { x: 0, y: 0 }, rewrites: resolution.rewrites, addGlobals: resolution.addGlobals });
    const doc = useDocumentStore.getState().doc as Model;
    const drive = doc.diagram.nodes.find((node) => node.name === "Drive");
    const inner = drive !== undefined && "subsystem" in drive.block ? drive.block.subsystem.diagram.nodes : [];
    expect(inner.map((node) => ("ref" in node.block ? node.block.ref : ""))).toEqual(["project:MyMotor2", "stdlib:sources/CsvSource"]);
    expect(inner[1]?.constants?.file).toBe("data/profile2.csv");
    expect(doc.diagram.nodes.find((node) => node.name === "Load")?.params?.J).toBe("2*J0_2");
    expect(doc.parameters?.map((entry) => `${entry.name}=${entry.value}`)).toEqual(["J0=7", "J0_2=0.002", "k_motor=0.1*J0_2 + 1"]);
  });

  it("converts conflicting library blocks to inline blocks", async () => {
    const envelope = copyDrive();
    const io = fakeIo({ targetLibrary: { mymotor: "@block mymotor begin\nend\n" } });
    const analysis = await analyse(envelope, target(), io);
    expect(analysis.conflicts[0]?.existing).toBe("mymotor");
    const resolution = resolve(envelope, analysis, { "library:MyMotor": "inline" });
    expect(resolution.inlined).toEqual(["MyMotor"]);
    expect(resolution.rewrites.inline?.["project:MyMotor"]).toBe(MOTOR);
    // The inline source still instantiates MyGear, which is imported.
    expect(resolution.libraryWrites.map((write) => write.name)).toEqual(["MyGear"]);
  });

  it("reads library sources the copy lacked from the source project", async () => {
    const envelope = copyDrive();
    envelope.dependencies.libraryBlocks = [{ name: "MyMotor" }];
    const analysis = await analyse(envelope, target(), fakeIo());
    expect(analysis.library.map((entry) => [entry.name, entry.source !== null])).toEqual([
      ["MyMotor", true],
      ["MyGear", true],
    ]);
  });

  it("proposes free names", () => {
    expect(freeGlobalName("m", [{ name: "m", value: "1" }, { name: "m_2", value: "1" }], [])).toBe("m_3");
    expect(freeGlobalName("x", [], ["x"])).toBe("x_2");
    expect(freeGlobalName("t", [], [])).toBe("t_2");
    expect(freeDataName("profile.csv", ["Profile.CSV", "profile2.csv"])).toBe("profile3.csv");
  });
});

describe("pasting", () => {
  it("pastes into another project as one undo step and reports what was carried", async () => {
    const envelope = copyDrive();
    useDocumentStore.getState().openDocument("other", "bench", createEmptyModel("bench"));
    const io = fakeIo();
    const status = await pasteEnvelope(envelope, { at: { x: 400, y: 300 } }, io);
    expect(status).toBe("pasted");
    expect(io.log).toEqual([
      "library other/MyMotor",
      "library other/MyGear",
      "data other/profile.csv",
      "assets lab/rig -> other/bench: 0123456789ab.png",
    ]);
    let doc = useDocumentStore.getState().doc as Model;
    expect(doc.diagram.nodes.map((node) => node.name)).toEqual(["Drive", "Load"]);
    expect(doc.parameters?.map((entry) => entry.name)).toEqual(["J0", "k_motor"]);
    expect(useDocumentStore.getState().past).toHaveLength(1);
    const notice = usePasteUiStore.getState().notice;
    expect(notice?.title).toBe("Pasted 2 blocks, 1 connection, 1 note, 1 shape from lab/rig");
    expect(notice?.lines.join("\n")).toMatch(/Library blocks added: MyMotor, MyGear/);
    expect(notice?.lines.join("\n")).toMatch(/Global parameters added: J0, k_motor/);
    expect(notice?.lines.join("\n")).toMatch(/Not carried along: 1 plot probe, 1 saved plot, docs pages/);
    expect(notice?.lines.join("\n")).toMatch(/files written to the project stay/);

    useDocumentStore.getState().undo();
    doc = useDocumentStore.getState().doc as Model;
    expect(doc.diagram.nodes).toEqual([]);
    expect(doc.parameters ?? []).toEqual([]);
  });

  it("does nothing when the conflict dialog is cancelled", async () => {
    useDocumentStore.getState().openDocument("other", "bench", { ...createEmptyModel("bench"), parameters: [{ name: "J0", value: "9" }] });
    const io = fakeIo({ choices: null });
    expect(await pasteEnvelope(copyDrive(), { at: null }, io)).toBe("cancelled");
    expect(io.asked).toEqual(["global:J0"]);
    expect(io.log).toEqual([]);
    expect(useDocumentStore.getState().doc?.diagram.nodes).toEqual([]);
  });

  it("reports blocks the catalog does not publish (the fake worker)", async () => {
    useDocumentStore.getState().openDocument("other", "bench", createEmptyModel("bench"));
    await pasteEnvelope(copyDrive(), { at: null }, fakeIo({ publish: false }));
    expect(usePasteUiStore.getState().notice?.lines.join("\n")).toMatch(/catalog could not be re-read/);
  });

  it("pastes back into the same diagram without dependency work", async () => {
    useDocumentStore.getState().openDocument("lab", "rig", sourceModel());
    const io = fakeIo();
    await pasteEnvelope(copyDrive(), { at: null }, io);
    expect(io.log).toEqual([]);
    expect(usePasteUiStore.getState().notice).not.toBeNull(); // probes and plots stay behind
    const names = (useDocumentStore.getState().doc as Model).diagram.nodes.map((node) => node.name);
    expect(names).toEqual(["Drive", "Load", "Other", "Drive2", "Load2"]);
    expect((useDocumentStore.getState().doc as Model).parameters).toHaveLength(4);
  });

  it("keeps ids unique across the document when a subsystem is pasted twice", async () => {
    useDocumentStore.getState().openDocument("lab", "rig", sourceModel());
    const envelope = copyDrive();
    await pasteEnvelope(envelope, { at: null }, fakeIo());
    await pasteEnvelope(envelope, { at: null }, fakeIo());
    const doc = useDocumentStore.getState().doc as Model;
    const nodeIds = allNodeIds(doc);
    const connectionIds = allConnectionIds(doc);
    expect(new Set(nodeIds).size).toBe(nodeIds.length);
    expect(new Set(connectionIds).size).toBe(connectionIds.length);
    expect(doc.diagram.nodes.map((node) => node.name)).toEqual(["Drive", "Load", "Other", "Drive2", "Load2", "Drive3", "Load3"]);
    // Each copy's exposed port points at its own motor, and the inner connection follows.
    for (const node of doc.diagram.nodes.filter((entry) => "subsystem" in entry.block)) {
      if (!("subsystem" in node.block)) continue;
      const inner = node.block.subsystem.diagram;
      const motor = inner.nodes.find((entry) => entry.name === "Motor");
      expect(node.block.subsystem.ports[0]?.node).toBe(motor?.id);
      expect(inner.connections[0]?.to.node).toBe(motor?.id);
    }
    // The second paste of the same copy cascades by the paste offset.
    const drives = doc.diagram.nodes.filter((node) => node.name.startsWith("Drive"));
    expect(drives.map((node) => node.position)).toEqual([
      { x: 100, y: 100 },
      { x: 124, y: 124 },
      { x: 148, y: 148 },
    ]);
  });

  it("pastes into the open subsystem level", async () => {
    useDocumentStore.getState().openDocument("lab", "rig", sourceModel());
    useDocumentStore.getState().navigateToPath(["n1"]);
    await pasteEnvelope(copyDrive(), { at: { x: 0, y: 0 } }, fakeIo());
    const doc = useDocumentStore.getState().doc as Model;
    const drive = doc.diagram.nodes[0];
    const inner = drive !== undefined && "subsystem" in drive.block ? drive.block.subsystem.diagram : null;
    expect(inner?.nodes.map((node) => node.name)).toEqual(["Motor", "Profile", "Drive", "Load"]);
    expect(doc.diagram.nodes).toHaveLength(3);
  });
});

describe("placement", () => {
  it("centres the group on the anchor in whole grid steps and moves the waypoints", () => {
    const envelope = copyDrive();
    const centre = clipCentre(envelope);
    expect(centre).toEqual({ x: 210, y: 100 });
    const prepared = preparePaste({
      clip: envelope,
      diagram: diagram([]),
      nodeIds: [],
      connectionIds: [],
      at: { x: 1000, y: 500 },
      offset: 0,
    });
    // The shift (790, 400) rounds to whole 20-unit grid steps: (800, 400).
    expect(prepared.nodes.map((node) => node.position)).toEqual([
      { x: 900, y: 500 },
      { x: 1100, y: 500 },
    ]);
    expect(prepared.connections[0]?.route).toEqual([{ x: 1000, y: 500 }]);
    expect(prepared.annotations[0]).toMatchObject({ x: 880, y: 420 });
    // A pasted shape is unlocked.
    expect(prepared.shapes[0]?.locked).toBeUndefined();
  });

  it("drops connections whose ends were not copied", () => {
    const envelope = copyDrive();
    envelope.connections.push({ id: "c7", kind: "signal", from: { node: "n4", port: "w" }, to: { node: "n5", port: "u" } });
    useDocumentStore.getState().openDocument("other", "bench", createEmptyModel("bench"));
    const result = useDocumentStore.getState().pasteClip(envelope);
    expect(result?.connections).toBe(1);
    expect(result?.droppedConnections).toBe(1);
  });

  it("writes report lines for renamed imports", () => {
    const lines = reportLines(
      copyDrive(),
      {
        pasted: { nodes: 1, connections: 0, annotations: 0, shapes: 0, droppedConnections: 0 },
        resolution: {
          rewrites: {},
          addGlobals: [{ name: "J0_2", value: "1" }],
          renamedGlobals: { J0: "J0_2" },
          libraryWrites: [{ name: "MyMotor2", source: "", renamedFrom: "MyMotor" }],
          dataWrites: [],
          inlined: [],
          kept: [],
          unavailable: [],
        },
        unpublished: ["MyMotor2"],
        catalogError: false,
        assetsCopied: 0,
        problems: [],
      },
      true,
    );
    expect(lines).toContain("Library blocks added: MyMotor as MyMotor2.");
    expect(lines).toContain("Global parameters added: J0 as J0_2.");
    expect(lines.join("\n")).toMatch(/does not list project:MyMotor2 yet/);
  });
});
