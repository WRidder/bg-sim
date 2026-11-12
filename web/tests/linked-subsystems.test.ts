/**
 * Library subsystems: a drawn definition and its instances
 * (src/library/linkedSubsystems.ts), through the document store.
 *
 * An open model holds each instance as a working copy. The tests cover: making a
 * subsystem reusable, an edit inside one instance reaching the others, pinned
 * values staying with their instance, resetting, unpinning, ports, nested
 * definitions, a definition that would contain itself, undo, and the saved form.
 */

import { beforeEach, describe, expect, it } from "vitest";

import type { CatalogBlock } from "../src/contracts/catalog";
import type { Model, ModelDiagram, ModelNode, SubsystemDefinition } from "../src/contracts/model";
import {
  changedValueCount,
  dehydrateModel,
  enclosingInstance,
  hydrateModel,
  instanceCount,
  instanceValues,
  linkedDefinition,
  readPin,
  syncLinked,
} from "../src/library/linkedSubsystems";
import { resetDocumentStore, useDocumentStore } from "../src/state/documentStore";
import { createEmptyModel } from "../src/state/modelFactory";

function node(id: string, name: string, block: ModelNode["block"], extra: Partial<ModelNode> = {}): ModelNode {
  return { id, name, block, position: { x: 0, y: 0 }, ...extra };
}

/** A rotor on a 1-junction behind one power port. */
function actuatorDiagram(): ModelDiagram {
  return {
    nodes: [
      node("a1", "hub", { junction: "1" }),
      node("a2", "rotor", { ref: "stdlib:bondgraph/I" }, { params: { i: "0.02" }, starts: { p: "0" } }),
      node("a3", "damper", { ref: "stdlib:bondgraph/R" }, { params: { r: "0.1" } }),
    ],
    connections: [
      { id: "b1", kind: "bond", from: { node: "a1" }, to: { node: "a2", port: "p" } },
      { id: "b2", kind: "bond", from: { node: "a1" }, to: { node: "a3", port: "p" } },
    ],
  };
}

function actuatorNode(id: string, name: string): ModelNode {
  return node(id, name, {
    subsystem: {
      ports: [{ name: "shaft", kind: "power", domain: "Generic", size: [1], node: "a1", port: "junction" }],
      diagram: actuatorDiagram(),
    },
  });
}

function robot(): Model {
  const doc = createEmptyModel("Robot", "0.1.0");
  doc.diagram.nodes = [
    actuatorNode("n1", "Act1"),
    node("n2", "Load", { ref: "stdlib:bondgraph/R" }, { params: { r: "1.0" } }),
  ];
  doc.diagram.connections = [
    { id: "c1", kind: "bond", from: { node: "n1", port: "shaft" }, to: { node: "n2", port: "p" } },
  ];
  return doc;
}

const ACTUATOR_BLOCK = {
  ref: "project:Actuator",
  name: "Actuator",
  subsystem: true,
  parameters: [],
} as unknown as CatalogBlock;

const store = () => useDocumentStore.getState();
const doc = (): Model => store().doc as Model;
const top = (name: string): ModelNode => {
  const found = doc().diagram.nodes.find((entry) => entry.name === name);
  if (found === undefined) {
    throw new Error(`no node ${name}`);
  }
  return found;
};
const inner = (name: string): ModelDiagram => {
  const found = top(name);
  if (!("subsystem" in found.block)) {
    throw new Error(`${name} is not a subsystem`);
  }
  return found.block.subsystem.diagram;
};

/** A robot with `Act1` made reusable and a second instance `Act2` from the library. */
function twoActuators(): void {
  store().openDocument("demo", "Robot", robot());
  expect(store().makeSubsystemReusable("n1", "Actuator", [])).toEqual({ ok: true });
  store().addBlock(ACTUATOR_BLOCK, { x: 300, y: 0 });
  const added = doc().diagram.nodes[doc().diagram.nodes.length - 1];
  expect(added?.name).toBe("Actuator");
  store().renameNode(added?.id ?? "", "Act2");
}

beforeEach(() => {
  resetDocumentStore();
});

describe("making a subsystem reusable", () => {
  it("adds the definition and makes the node its first instance", () => {
    store().openDocument("demo", "Robot", robot());
    expect(store().makeSubsystemReusable("n1", "1bad", []).ok).toBe(false);
    expect(store().makeSubsystemReusable("n1", "Gear", ["gear"]).ok).toBe(false);
    expect(store().makeSubsystemReusable("n1", "Actuator", [])).toEqual({ ok: true });

    expect(linkedDefinition(top("Act1"))).toBe("Actuator");
    expect(doc().definitions?.Actuator?.diagram.nodes.map((entry) => entry.name)).toEqual([
      "hub",
      "rotor",
      "damper",
    ]);
    expect(instanceCount(doc(), "Actuator")).toBe(1);
    expect(store().makeSubsystemReusable("n1", "Other", []).ok).toBe(false);

    store().undo();
    expect(linkedDefinition(top("Act1"))).toBeNull();
    expect(doc().definitions?.Actuator).toBeUndefined();
  });

  it("a new instance from the library is a copy of the definition", () => {
    twoActuators();
    expect(linkedDefinition(top("Act2"))).toBe("Actuator");
    expect(inner("Act2")).toEqual(inner("Act1"));
    expect(instanceCount(doc(), "Actuator")).toBe(2);
  });
});

describe("an edit inside one instance", () => {
  it("reaches the definition and every other instance", () => {
    twoActuators();
    store().enterSubsystem("n1");
    expect(store().setNodeParam("a3", "r", "0.5").ok).toBe(true);
    store().setNodePositions({ a2: { x: 40, y: 80 } });

    expect(readPin(inner("Act2"), "params", "damper/r")).toBe("0.5");
    expect(readPin(doc().definitions?.Actuator?.diagram as ModelDiagram, "params", "damper/r")).toBe("0.5");
    expect(inner("Act2").nodes.find((entry) => entry.id === "a2")?.position).toEqual({ x: 40, y: 80 });

    // The other way round: an edit in the second instance reaches the first.
    store().navigateToPath([top("Act2").id]);
    store().setNodeParam("a3", "r", "0.7");
    expect(readPin(inner("Act1"), "params", "damper/r")).toBe("0.7");

    store().undo();
    expect(readPin(inner("Act1"), "params", "damper/r")).toBe("0.5");
    expect(readPin(inner("Act2"), "params", "damper/r")).toBe("0.5");
    store().redo();
    expect(readPin(inner("Act1"), "params", "damper/r")).toBe("0.7");
  });

  it("adds and removes blocks everywhere", () => {
    twoActuators();
    store().enterSubsystem("n1");
    store().setSelection(["a3"], []);
    store().deleteSelection();
    expect(inner("Act2").nodes.map((entry) => entry.name)).toEqual(["hub", "rotor"]);
    expect(inner("Act2").connections.map((entry) => entry.id)).toEqual(["b1"]);
    expect(doc().definitions?.Actuator?.diagram.nodes).toHaveLength(2);
  });
});

describe("pinned values", () => {
  it("stay with the instance they are set in", () => {
    twoActuators();
    expect(store().setDefinitionPin("Actuator", "params", "rotor/i", true)).toEqual({ ok: true });
    expect(doc().definitions?.Actuator?.pins).toEqual({ params: ["rotor/i"] });

    // Typed inside the second instance: only that instance has it.
    store().navigateToPath([top("Act2").id]);
    store().setNodeParam("a2", "i", "0.05");
    expect(readPin(inner("Act2"), "params", "rotor/i")).toBe("0.05");
    expect(readPin(inner("Act1"), "params", "rotor/i")).toBe("0.02");
    expect(readPin(doc().definitions?.Actuator?.diagram as ModelDiagram, "params", "rotor/i")).toBe("0.02");
    expect(changedValueCount(top("Act2"), doc().definitions)).toBe(1);
    expect(changedValueCount(top("Act1"), doc().definitions)).toBe(0);

    // A shared value edited in the same instance still reaches the other one.
    store().setNodeParam("a3", "r", "0.9");
    expect(readPin(inner("Act1"), "params", "damper/r")).toBe("0.9");
    expect(readPin(inner("Act1"), "params", "rotor/i")).toBe("0.02");
    expect(readPin(inner("Act2"), "params", "rotor/i")).toBe("0.05");
  });

  it("are listed, set and reset from the instance", () => {
    twoActuators();
    store().setDefinitionPin("Actuator", "params", "rotor/i", true);
    store().setDefinitionPin("Actuator", "starts", "rotor/p", true);
    const act2 = top("Act2").id;
    expect(store().setInstanceValue(act2, "params", "rotor/i", "0.08")).toEqual({ ok: true });
    expect(store().setInstanceValue(act2, "starts", "rotor/p", "1.5")).toEqual({ ok: true });

    const node2 = top("Act2");
    if (!("subsystem" in node2.block)) {
      throw new Error("Act2 is not a subsystem");
    }
    expect(instanceValues(node2.block.subsystem, doc().definitions?.Actuator as SubsystemDefinition)).toEqual([
      { kind: "params", path: "rotor/i", value: "0.08", default: "0.02", changed: true, resolves: true },
      { kind: "starts", path: "rotor/p", value: "1.5", default: "0", changed: true, resolves: true },
    ]);
    expect(readPin(inner("Act1"), "params", "rotor/i")).toBe("0.02");

    store().resetInstanceValues(act2, { kind: "params", path: "rotor/i" });
    expect(readPin(inner("Act2"), "params", "rotor/i")).toBe("0.02");
    expect(changedValueCount(top("Act2"), doc().definitions)).toBe(1);
    store().resetInstanceValues(act2);
    expect(changedValueCount(top("Act2"), doc().definitions)).toBe(0);
  });

  it("return to the definition's value when unpinned", () => {
    twoActuators();
    store().setDefinitionPin("Actuator", "params", "rotor/i", true);
    store().setInstanceValue(top("Act2").id, "params", "rotor/i", "0.08");
    store().setDefinitionPin("Actuator", "params", "rotor/i", false);
    expect(doc().definitions?.Actuator?.pins).toBeUndefined();
    expect(readPin(inner("Act2"), "params", "rotor/i")).toBe("0.02");
  });
});

describe("ports of a library subsystem", () => {
  it("a removed port loses its connections at every instance", () => {
    twoActuators();
    const act2 = top("Act2").id;
    const current = doc();
    store().openDocument("demo", "Robot", {
      ...current,
      diagram: {
        ...current.diagram,
        connections: [
          ...current.diagram.connections,
          { id: "c2", kind: "bond", from: { node: act2, port: "shaft" }, to: { node: "n2", port: "p" } },
        ],
      },
    });
    const before = doc().diagram.connections.length;
    store().enterSubsystem("n1");
    store().deleteSubsystemPorts(["shaft"]);
    const first = top("Act1");
    const second = top("Act2");
    expect("subsystem" in first.block && first.block.subsystem.ports).toEqual([]);
    expect("subsystem" in second.block && second.block.subsystem.ports).toEqual([]);
    expect(doc().definitions?.Actuator?.ports).toEqual([]);
    // Every connection on `shaft` is gone, at both instances.
    expect(
      doc().diagram.connections.filter((entry) => entry.from.port === "shaft" || entry.to.port === "shaft"),
    ).toEqual([]);
    expect(before).toBe(2);
    expect(doc().diagram.connections).toHaveLength(0);
  });

  it("a renamed port keeps its connections at every instance", () => {
    twoActuators();
    store().enterSubsystem("n1");
    expect(store().renameSubsystemPort("shaft", "axle").ok).toBe(true);
    const second = top("Act2");
    expect("subsystem" in second.block && second.block.subsystem.ports.map((port) => port.name)).toEqual([
      "axle",
    ]);
    expect(doc().diagram.connections.find((entry) => entry.id === "c1")?.from).toEqual({
      node: "n1",
      port: "axle",
    });
  });
});

describe("definitions inside definitions", () => {
  it("an edit of the inner one reaches the copies inside the outer one", () => {
    twoActuators();
    // Group both actuators into a subsystem and make that reusable too.
    const leg: ModelNode = node("n9", "Leg1", {
      subsystem: { ports: [], diagram: { nodes: [top("Act1"), top("Act2")], connections: [] } },
    });
    const model = { ...doc(), diagram: { nodes: [leg], connections: [] } };
    store().openDocument("demo", "Robot", model);
    expect(store().makeSubsystemReusable("n9", "Leg", [])).toEqual({ ok: true });

    store().navigateToPath(["n9", "n1"]);
    expect(enclosingInstance(doc(), ["n9", "n1"])?.name).toBe("Actuator");
    store().setNodeParam("a3", "r", "0.33");

    const legDiagram = inner("Leg1");
    for (const entry of legDiagram.nodes) {
      expect("subsystem" in entry.block && readPin(entry.block.subsystem.diagram, "params", "damper/r")).toBe(
        "0.33",
      );
    }
    const stored = doc().definitions?.Leg?.diagram.nodes[1];
    expect(
      stored !== undefined && "subsystem" in stored.block
        ? readPin(stored.block.subsystem.diagram, "params", "damper/r")
        : null,
    ).toBe("0.33");
  });

  it("a definition cannot hold an instance of itself", () => {
    twoActuators();
    store().enterSubsystem("n1");
    const before = doc();
    expect(store().addBlock(ACTUATOR_BLOCK, { x: 0, y: 0 })).toBeNull();
    expect(doc()).toBe(before);
    expect(store().editNotice).toContain("cannot hold an instance of itself");
    store().clearEditNotice();
    expect(store().editNotice).toBeNull();
  });
});

describe("detaching and removing", () => {
  it("a detached instance no longer follows the definition", () => {
    twoActuators();
    expect(store().detachInstance(top("Act2").id)).toEqual({ ok: true });
    expect(linkedDefinition(top("Act2"))).toBeNull();
    store().enterSubsystem("n1");
    store().setNodeParam("a3", "r", "0.5");
    expect(readPin(inner("Act2"), "params", "damper/r")).toBe("0.1");
  });

  it("removing the definition leaves ordinary subsystems", () => {
    twoActuators();
    expect(store().removeDefinition("Actuator")).toEqual({ ok: true });
    expect(linkedDefinition(top("Act1"))).toBeNull();
    expect(linkedDefinition(top("Act2"))).toBeNull();
    expect(doc().definitions).toEqual({});
  });

  it("a pasted copy of an unknown definition is an ordinary subsystem", () => {
    const model = robot();
    const stray = actuatorNode("n5", "Stray");
    if ("subsystem" in stray.block) {
      stray.block.subsystem.definition = "Elsewhere";
    }
    const synced = syncLinked({ ...model, diagram: { ...model.diagram, nodes: [stray] } }, model);
    expect(synced.ok && linkedDefinition(synced.model.diagram.nodes[0] as ModelNode)).toBeNull();
  });
});

describe("the saved form", () => {
  it("stores an instance as a reference with its own values, and opens it again", () => {
    twoActuators();
    store().setDefinitionPin("Actuator", "params", "rotor/i", true);
    store().setInstanceValue(top("Act2").id, "params", "rotor/i", "0.08");

    const { model, files } = dehydrateModel(doc());
    expect(model.definitions).toBeUndefined();
    const saved = model.diagram.nodes;
    expect(saved[0]?.block).toEqual({ ref: "project:Actuator" });
    expect(saved[0]?.params).toBeUndefined();
    expect(saved[2]?.block).toEqual({ ref: "project:Actuator" });
    expect(saved[2]?.params).toEqual({ "rotor/i": "0.08" });
    expect(Object.keys(files)).toEqual(["Actuator"]);
    expect(files.Actuator?.pins).toEqual({ params: ["rotor/i"] });
    expect(files.Actuator?.format).toBe("bgsim.subsystem");

    const opened = hydrateModel(model, files);
    expect(opened.diagram).toEqual(doc().diagram);
    expect(opened.definitions).toEqual(doc().definitions);
    // Opening is stable: nothing has to be brought in line.
    const synced = syncLinked(opened, null);
    expect(synced.ok && synced.model.diagram).toEqual(opened.diagram);
  });

  it("a model without library subsystems is saved as it is", () => {
    const model = robot();
    expect(dehydrateModel(model).model).toBe(model);
    expect(hydrateModel(model, {})).toBe(model);
  });

  it("an instance of a definition inside another is a reference in that file", () => {
    twoActuators();
    const leg: ModelNode = node("n9", "Leg1", {
      subsystem: { ports: [], diagram: { nodes: [top("Act1"), top("Act2")], connections: [] } },
    });
    store().openDocument("demo", "Robot", { ...doc(), diagram: { nodes: [leg], connections: [] } });
    store().makeSubsystemReusable("n9", "Leg", []);
    const { model, files } = dehydrateModel(doc());
    expect(model.diagram.nodes[0]?.block).toEqual({ ref: "project:Leg" });
    expect(files.Leg?.diagram.nodes.map((entry) => entry.block)).toEqual([
      { ref: "project:Actuator" },
      { ref: "project:Actuator" },
    ]);
    expect(hydrateModel(model, files).diagram).toEqual(doc().diagram);
  });
});

describe("saving to the project library", () => {
  async function withBackend(run: (calls: string[], bodies: unknown[]) => Promise<void>): Promise<void> {
    const calls: string[] = [];
    const bodies: unknown[] = [];
    const original = globalThis.fetch;
    globalThis.fetch = (async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input);
      calls.push(`${init?.method ?? "GET"} ${url}`);
      bodies.push(typeof init?.body === "string" ? JSON.parse(init.body) : undefined);
      const body = url.endsWith("/subsystems") ? { definitions: {}, problems: {} } : {};
      return new Response(JSON.stringify(body), {
        status: 200,
        headers: { "content-type": "application/json" },
      });
    }) as typeof fetch;
    try {
      await run(calls, bodies);
    } finally {
      globalThis.fetch = original;
    }
  }

  it("writes changed definitions to the backend paths, and deletes only what was removed", async () => {
    const { saveDefinitions, openWithDefinitions, resetDefinitionFiles } = await import(
      "../src/state/definitionFiles"
    );
    const { listSubsystems } = await import("../src/state/modelApi");
    resetDefinitionFiles();
    await withBackend(async (calls, bodies) => {
      expect(await listSubsystems("demo")).toEqual({});
      twoActuators();
      openWithDefinitions("demo", robot(), {});
      const first = await saveDefinitions("demo", doc());
      expect(first.libraryChanged).toBe(true);
      expect(first.model.definitions).toBeUndefined();
      expect(first.model.diagram.nodes[0]?.block).toEqual({ ref: "project:Actuator" });
      expect(await first.finish()).toBe(false);
      expect(calls).toEqual([
        "GET /api/projects/demo/subsystems",
        "PUT /api/projects/demo/subsystems/Actuator",
      ]);
      expect((bodies[1] as SubsystemDefinition).format).toBe("bgsim.subsystem");

      // Nothing changed: nothing is written again.
      const second = await saveDefinitions("demo", doc());
      expect(second.libraryChanged).toBe(false);
      expect(await second.finish()).toBe(false);
      expect(calls).toHaveLength(2);

      // Removed by the user: the file goes, but only once the model is stored (`finish`).
      store().removeDefinition("Actuator");
      const third = await saveDefinitions("demo", doc());
      expect(calls).toHaveLength(2);
      expect(await third.finish()).toBe(true);
      expect(calls[2]).toBe("DELETE /api/projects/demo/subsystems/Actuator");
    });
  });

  it("never deletes a library subsystem because the document does not hold it", async () => {
    const { saveDefinitions, openWithDefinitions, resetDefinitionFiles } = await import(
      "../src/state/definitionFiles"
    );
    resetDefinitionFiles();
    await withBackend(async (calls) => {
      twoActuators();
      const { model, files } = dehydrateModel(doc());
      // The project library holds Actuator; then a document arrives that knows nothing of it.
      openWithDefinitions("demo", model, files);
      const result = await saveDefinitions("demo", { ...robot(), definitions: {} });
      expect(await result.finish()).toBe(false);
      expect(calls.filter((entry) => entry.startsWith("DELETE"))).toEqual([]);
    });
  });

  it("a document from outside the editor is opened with the library subsystems in place", () => {
    twoActuators();
    store().setDefinitionPin("Actuator", "params", "rotor/i", true);
    store().setInstanceValue(top("Act2").id, "params", "rotor/i", "0.08");
    const before = doc();
    // What the assistant hands over when a draft is applied: the saved form.
    const saved = dehydrateModel(before).model;
    expect(saved.definitions).toBeUndefined();
    store().replaceDocument(saved);
    expect(doc().definitions?.Actuator?.pins).toEqual({ params: ["rotor/i"] });
    expect(linkedDefinition(top("Act1"))).toBe("Actuator");
    expect(readPin(inner("Act2"), "params", "rotor/i")).toBe("0.08");
    expect(doc().diagram).toEqual(before.diagram);
  });
});

describe("pins follow the blocks they name", () => {
  it("renaming a pinned block keeps the pin, the library value and the value of every instance", () => {
    twoActuators();
    store().setDefinitionPin("Actuator", "params", "rotor/i", true);
    store().setInstanceValue("n1", "params", "rotor/i", "0.5");
    store().setInstanceValue(top("Act2").id, "params", "rotor/i", "0.08");

    store().enterSubsystem("n1");
    expect(store().renameNode("a2", "motor").ok).toBe(true);

    const definition = doc().definitions?.Actuator as SubsystemDefinition;
    expect(definition.pins).toEqual({ params: ["motor/i"] });
    expect(readPin(definition.diagram, "params", "motor/i")).toBe("0.02");
    expect(readPin(inner("Act1"), "params", "motor/i")).toBe("0.5");
    expect(readPin(inner("Act2"), "params", "motor/i")).toBe("0.08");
    expect(dehydrateModel(doc()).model.diagram.nodes.map((entry) => entry.params)).toEqual([
      { "motor/i": "0.5" },
      { r: "1.0" },
      { "motor/i": "0.08" },
    ]);

    store().undo();
    expect(doc().definitions?.Actuator?.pins).toEqual({ params: ["rotor/i"] });
    expect(readPin(inner("Act2"), "params", "rotor/i")).toBe("0.08");
  });

  it("deleting a pinned block removes its pin and leaves the other values alone", () => {
    twoActuators();
    store().setDefinitionPin("Actuator", "params", "rotor/i", true);
    store().setDefinitionPin("Actuator", "params", "damper/r", true);
    store().setInstanceValue(top("Act2").id, "params", "damper/r", "0.9");
    store().enterSubsystem("n1");
    store().setSelection(["a2"], []);
    store().deleteSelection();
    expect(doc().definitions?.Actuator?.pins).toEqual({ params: ["damper/r"] });
    expect(readPin(inner("Act2"), "params", "damper/r")).toBe("0.9");
    expect(readPin(doc().definitions?.Actuator?.diagram as ModelDiagram, "params", "damper/r")).toBe("0.1");
  });

  it("a renamed global parameter is renamed in the definition too", () => {
    twoActuators();
    store().addGlobalParameter({ name: "m", value: "2" });
    store().enterSubsystem("n1");
    store().setNodeParam("a3", "r", "m*2");
    store().navigateToPath([]);
    expect(store().renameGlobalParameter("m", "mass").ok).toBe(true);
    expect(readPin(doc().definitions?.Actuator?.diagram as ModelDiagram, "params", "damper/r")).toBe("mass*2");
    expect(readPin(inner("Act1"), "params", "damper/r")).toBe("mass*2");
    expect(readPin(inner("Act2"), "params", "damper/r")).toBe("mass*2");
  });
});

describe("a port change and the subsystems around the other instances", () => {
  /** `Act2` inside an ordinary subsystem `S` that exposes its `shaft` as `out`. */
  function wrapped(): void {
    twoActuators();
    const act2 = top("Act2");
    const current = doc();
    const wrapper: ModelNode = node("n7", "S", {
      subsystem: {
        ports: [{ name: "out", kind: "power", domain: "Generic", size: [1], node: act2.id, port: "shaft" }],
        diagram: { nodes: [act2], connections: [] },
      },
    });
    store().openDocument("demo", "Robot", {
      ...current,
      diagram: {
        nodes: [top("Act1"), top("Load"), wrapper],
        connections: [
          ...current.diagram.connections,
          { id: "c9", kind: "bond", from: { node: "n7", port: "out" }, to: { node: "n2", port: "p" } },
        ],
      },
    });
  }
  const wrapperPorts = () => {
    const found = top("S");
    return "subsystem" in found.block ? found.block.subsystem.ports : [];
  };

  it("a rename reaches the port that exposes it one level up", () => {
    wrapped();
    store().enterSubsystem("n1");
    expect(store().renameSubsystemPort("shaft", "axle").ok).toBe(true);
    expect(wrapperPorts().map((port) => [port.name, port.port])).toEqual([["out", "axle"]]);
    expect(doc().diagram.connections.map((entry) => entry.id)).toEqual(["c1", "c9"]);
  });

  it("a removal takes the exposing port and its connections with it", () => {
    wrapped();
    store().enterSubsystem("n1");
    store().deleteSubsystemPorts(["shaft"]);
    expect(wrapperPorts()).toEqual([]);
    expect(doc().diagram.connections).toEqual([]);
  });
});

describe("exporting as a code block", () => {
  it("is refused inside a library subsystem, where it would change every instance", async () => {
    const { saveSubsystemToProjectLibrary } = await import("../src/library/saveSubsystem");
    twoActuators();
    store().enterSubsystem("n1");
    const before = doc();
    await expect(
      saveSubsystemToProjectLibrary("demo", {
        nodeId: "a2",
        path: "Act1/rotor",
        name: "Rotor",
        plan: { problems: [], notes: [], blocks: [], instance: { params: {}, constants: {}, starts: {} }, exposed: [], bondRenames: [] },
      }),
    ).rejects.toThrow("inside the library subsystem Actuator");
    expect(doc()).toBe(before);
  });
});
