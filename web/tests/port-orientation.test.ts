/**
 * Port orientation in the editor (plan/PORT_ORIENTATION_PLAN.md WP-O4, decisions O2, O4, O8, O13, O14).
 *
 * The blocks keep the orientations of the contract catalog (Se and Sf `out`, C, I, R and Df `in`, TF and GY a
 * `through` pair). Two blocks are changed for the tests: De declares nothing (an undeclared leaf port, which
 * cannot be bonded, O22), and `Face` is a textual composite whose undeclared face stays free (`any`): the
 * compiler judges a bond there at the port inside.
 */

import { beforeEach, describe, expect, it } from "vitest";

import catalogJson from "../../contracts/fixtures/catalog/valid/catalog.min.json";
import type { Catalog, OrientationDecl } from "../src/contracts/catalog";
import type { Model, ModelConnection, ModelNode } from "../src/contracts/model";
import { checkConnection, type PortDescriptor } from "../src/editor/connectionRules";
import { interfaceForNode, portDescriptor } from "../src/editor/nodeInterface";
import {
  allowedRoles,
  blockPortOrientation,
  orientBond,
} from "../src/editor/portOrientation";
import { checkReverse, REVERSE_JUNCTION_NOTE } from "../src/editor/reverseBond";
import { buildCatalogIndex, type CatalogIndex } from "../src/library/catalogIndex";
import { resetCatalogStore, useCatalogStore } from "../src/library/catalogStore";
import { resetDocumentStore, useDocumentStore } from "../src/state/documentStore";
import {
  createConnection,
  createEmptyModel,
  createJunctionNode,
  createNodeFromBlock,
} from "../src/state/modelFactory";

const base = catalogJson as unknown as Catalog;
const deBlock = base.blocks.find((block) => block.name === "De");
if (deBlock === undefined) {
  throw new Error("catalog.min.json has no De");
}
const FACE_SOURCE = [
  "@block Face begin",
  "    @ports p::Power{Generic}",
  "    @components begin",
  "        node = Junction(1)",
  "    end",
  "    @connections connect(p, node)",
  "end",
].join("\n");
const catalog: Catalog = {
  ...base,
  blocks: [
    ...base.blocks.map((block) => (block.name === "De" ? { ...block, orientation: [] } : block)),
    { ...deBlock, ref: "stdlib:bondgraph/Face", name: "Face", outputs: [], orientation: [], source: FACE_SOURCE },
  ],
};
const index: CatalogIndex = buildCatalogIndex(catalog);

let counter = 0;
function id(prefix: string): string {
  counter += 1;
  return `${prefix}${counter}`;
}

function block(name: string, instance = name): ModelNode {
  const entry = index.blocksByName.get(name);
  if (entry === undefined) {
    throw new Error(`catalog has no block ${name}`);
  }
  return createNodeFromBlock(entry, { x: 0, y: 0 }, id("n"), instance);
}

function junction(kind: "0" | "1", name = `J${kind}`): ModelNode {
  return createJunctionNode(kind, { x: 0, y: 0 }, id("j"), name);
}

function model(nodes: ModelNode[], connections: ModelConnection[] = []): Model {
  const doc = createEmptyModel("Orientation");
  doc.diagram.nodes = nodes;
  doc.diagram.connections = connections;
  return doc;
}

function port(doc: Model, node: ModelNode, name: string | null): PortDescriptor {
  const found = portDescriptor(node, interfaceForNode(node, index), name);
  if (found === null) {
    throw new Error(`no port ${String(name)} on ${node.name}`);
  }
  expect(doc.diagram.nodes).toContain(node);
  return found;
}

function bond(from: ModelNode, fromPort: string | null, to: ModelNode, toPort: string | null, name = id("c")) {
  return createConnection(
    name,
    "bond",
    fromPort === null ? { node: from.id } : { node: from.id, port: fromPort },
    toPort === null ? { node: to.id } : { node: to.id, port: toPort },
  );
}

function runs(doc: Model, a: PortDescriptor, b: PortDescriptor): { from: string; to: string } {
  const result = checkConnection(doc, a, b);
  if (!result.ok) {
    throw new Error(`refused: ${result.reason}`);
  }
  return { from: result.from.nodeId, to: result.to.nodeId };
}

function refusal(doc: Model, a: PortDescriptor, b: PortDescriptor): string {
  const result = checkConnection(doc, a, b);
  if (result.ok) {
    throw new Error("expected a refusal");
  }
  return result.reason;
}

describe("the orientation of a catalog port", () => {
  it("reads in, out, through, and undeclared for a port in no entry (any on a composite face)", () => {
    const decls: OrientationDecl[] = [
      { ports: ["a"], kind: "in" },
      { ports: ["b"], kind: "out" },
      { ports: ["c", "d"], kind: "through" },
    ];
    expect(blockPortOrientation(decls, "a")).toEqual({ kind: "in" });
    expect(blockPortOrientation(decls, "b")).toEqual({ kind: "out" });
    expect(blockPortOrientation(decls, "c")).toEqual({ kind: "through", partner: "d", partnerFixed: null });
    expect(blockPortOrientation(decls, "d")).toEqual({ kind: "through", partner: "c", partnerFixed: null });
    expect(blockPortOrientation(decls, "e")).toEqual({ kind: "undeclared" });
    expect(blockPortOrientation(undefined, "a")).toEqual({ kind: "undeclared" });
    expect(blockPortOrientation(decls, "e", true)).toEqual({ kind: "any" });
    expect(blockPortOrientation(decls, "a", true)).toEqual({ kind: "in" });
  });

  it("puts the orientation on the node interface and on the port descriptor", () => {
    const c = block("C");
    expect(interfaceForNode(c, index).ports[0]?.orientation).toEqual({ kind: "in" });
    expect(portDescriptor(c, interfaceForNode(c, index), "p")?.orientation).toEqual({ kind: "in" });
    const de = block("De");
    expect(interfaceForNode(de, index).ports[0]?.orientation).toEqual({ kind: "undeclared" });
    const face = block("Face");
    expect(interfaceForNode(face, index).ports[0]?.orientation).toBeUndefined();
  });
});

describe("a new bond is oriented by the ports", () => {
  it("runs out -> in whichever end the drag starts at", () => {
    const se = block("Se");
    const c = block("C");
    const doc = model([se, c]);
    expect(runs(doc, port(doc, se, "p"), port(doc, c, "p"))).toEqual({ from: se.id, to: c.id });
    expect(runs(doc, port(doc, c, "p"), port(doc, se, "p"))).toEqual({ from: se.id, to: c.id });
  });

  it("points a junction -> in and out -> junction from either end", () => {
    const se = block("Se");
    const c = block("C");
    const j = junction("1");
    const doc = model([se, c, j]);
    expect(runs(doc, port(doc, c, "p"), port(doc, j, null))).toEqual({ from: j.id, to: c.id });
    expect(runs(doc, port(doc, j, null), port(doc, c, "p"))).toEqual({ from: j.id, to: c.id });
    expect(runs(doc, port(doc, j, null), port(doc, se, "p"))).toEqual({ from: se.id, to: j.id });
    expect(runs(doc, port(doc, se, "p"), port(doc, j, null))).toEqual({ from: se.id, to: j.id });
  });

  it("treats a composite face that declares nothing (any) like a junction", () => {
    const se = block("Se");
    const c = block("C");
    const face = block("Face");
    const doc = model([se, c, face]);
    expect(runs(doc, port(doc, face, "p"), port(doc, c, "p"))).toEqual({ from: face.id, to: c.id });
    expect(runs(doc, port(doc, c, "p"), port(doc, face, "p"))).toEqual({ from: face.id, to: c.id });
    expect(runs(doc, port(doc, face, "p"), port(doc, se, "p"))).toEqual({ from: se.id, to: face.id });
  });

  it("leaves junction-junction and any-any bonds free, in the drag order", () => {
    const j1 = junction("1");
    const j0 = junction("0");
    const f1 = block("Face", "F1");
    const f2 = block("Face", "F2");
    const doc = model([j1, j0, f1, f2]);
    expect(runs(doc, port(doc, j1, null), port(doc, j0, null))).toEqual({ from: j1.id, to: j0.id });
    expect(runs(doc, port(doc, j0, null), port(doc, j1, null))).toEqual({ from: j0.id, to: j1.id });
    expect(runs(doc, port(doc, f1, "p"), port(doc, f2, "p"))).toEqual({ from: f1.id, to: f2.id });
  });

  it("refuses a bond to a port that declares no orientation, from either end, with the reason (O22)", () => {
    const de = block("De", "De1");
    const j = junction("1");
    const se = block("Se");
    const face = block("Face");
    const doc = model([de, j, se, face]);
    const reason = "`De1.p` declares no orientation: add `@orientation` to the block";
    for (const other of [j, se, face]) {
      const name = other.id === j.id ? null : "p";
      expect(refusal(doc, port(doc, de, "p"), port(doc, other, name))).toBe(reason);
      expect(refusal(doc, port(doc, other, name), port(doc, de, "p"))).toBe(reason);
    }
    expect(allowedRoles(doc, port(doc, de, "p")).size).toBe(0);
  });

  it("refuses in-in and out-out with the junction hint, from either end", () => {
    const c = block("C");
    const i = block("I");
    const se = block("Se");
    const sf = block("Sf");
    const doc = model([c, i, se, sf]);
    for (const [a, b, kind] of [
      [c, i, "in"],
      [i, c, "in"],
      [se, sf, "out"],
      [sf, se, "out"],
    ] as const) {
      const reason = refusal(doc, port(doc, a, "p"), port(doc, b, "p"));
      expect(reason).toContain("put a junction in between");
      expect(reason).toContain(`declared \`${kind}\``);
    }
  });

  it("leaves wires and signals alone", () => {
    const resistor = block("Resistor");
    const capacitor = block("Capacitor");
    const doc = model([resistor, capacitor]);
    const result = checkConnection(doc, port(doc, resistor, "p"), port(doc, capacitor, "p"));
    expect(result.ok && result.kind).toBe("wire");
  });
});

describe("a through pair", () => {
  it("takes either direction while the other port is free", () => {
    const tf = block("TF");
    const se = block("Se");
    const c = block("C");
    const doc = model([tf, se, c]);
    expect(runs(doc, port(doc, se, "p"), port(doc, tf, "p1"))).toEqual({ from: se.id, to: tf.id });
    expect(runs(doc, port(doc, tf, "p1"), port(doc, c, "p"))).toEqual({ from: tf.id, to: c.id });
    expect(allowedRoles(doc, port(doc, tf, "p1"))).toEqual(new Set(["from", "to"]));
  });

  it("must leave when the other bond arrives, and arrive when the other leaves", () => {
    const tf = block("TF");
    const j = junction("1");
    const other = junction("0");
    // A bond arrives at p1: a bond at p2 must leave.
    const arrives = model([tf, j, other], [bond(j, null, tf, "p1")]);
    expect(runs(arrives, port(arrives, tf, "p2"), port(arrives, other, null))).toEqual({
      from: tf.id,
      to: other.id,
    });
    expect(runs(arrives, port(arrives, other, null), port(arrives, tf, "p2"))).toEqual({
      from: tf.id,
      to: other.id,
    });
    // A bond leaves p1: a bond at p2 must arrive.
    const leaves = model([tf, j, other], [bond(tf, "p1", j, null)]);
    expect(runs(leaves, port(leaves, tf, "p2"), port(leaves, other, null))).toEqual({
      from: other.id,
      to: tf.id,
    });
  });

  it("refuses a bond with a fixed port that would need the same direction as the pair", () => {
    const tf = block("TF");
    const j = junction("1");
    const c = block("C");
    const se = block("Se");
    // p1's bond arrives, so a bond at p2 must leave; an `in` port needs a bond that ends there.
    const doc = model([tf, j, c, se], [bond(j, null, tf, "p1")]);
    const reason = refusal(doc, port(doc, tf, "p2"), port(doc, se, "p"));
    expect(reason).toContain("put a junction in between");
    expect(reason).toContain("paired with `p1`");
    // An in port is fine: p2 leaves and ends at C.
    expect(runs(doc, port(doc, c, "p"), port(doc, tf, "p2"))).toEqual({ from: tf.id, to: c.id });
  });
});

describe("a subsystem port forwards the orientation of the port it exposes", () => {
  function subsystemOf(
    name: string,
    inner: Model["diagram"],
    ports: { name: string; node: string; port: string }[],
  ): ModelNode {
    return {
      id: id("s"),
      name,
      position: { x: 0, y: 0 },
      block: {
        subsystem: {
          ports: ports.map((entry) => ({
            kind: "power" as const,
            domain: "Generic" as const,
            size: [] as unknown as [1],
            ...entry,
          })),
          diagram: inner,
        },
      },
    };
  }

  it("forwards in and out", () => {
    const c = block("C");
    const se = block("Se");
    const sub = subsystemOf("Sub", model([c, se]).diagram, [
      { name: "P", node: c.id, port: "p" },
      { name: "Q", node: se.id, port: "p" },
    ]);
    const ports = interfaceForNode(sub, index).ports;
    expect(ports.find((entry) => entry.name === "P")?.orientation).toEqual({ kind: "in" });
    expect(ports.find((entry) => entry.name === "Q")?.orientation).toEqual({ kind: "out" });
  });

  it("forwards through nested subsystems and gives no orientation to a junction", () => {
    const c = block("C");
    const j = junction("1");
    const inner = subsystemOf("Inner", model([c]).diagram, [{ name: "P", node: c.id, port: "p" }]);
    const outer = subsystemOf("Outer", model([inner, j]).diagram, [
      { name: "A", node: inner.id, port: "P" },
      { name: "B", node: j.id, port: "junction" },
    ]);
    const ports = interfaceForNode(outer, index).ports;
    expect(ports.find((entry) => entry.name === "A")?.orientation).toEqual({ kind: "in" });
    expect(ports.find((entry) => entry.name === "B")?.orientation).toBeUndefined();

    const se = block("Se");
    const doc = model([outer, se]);
    expect(runs(doc, port(doc, outer, "A"), port(doc, se, "p"))).toEqual({ from: se.id, to: outer.id });
    const other = block("I");
    expect(refusal(model([outer, other]), port(doc, outer, "A"), port(model([outer, other]), other, "p"))).toContain(
      "put a junction in between",
    );
  });

  it("keeps a through pair across the boundary, with the partner exposed or bonded inside", () => {
    const tf = block("TF");
    // Both ports exposed: they are partners under their subsystem names.
    const both = subsystemOf("Both", model([tf]).diagram, [
      { name: "A", node: tf.id, port: "p1" },
      { name: "B", node: tf.id, port: "p2" },
    ]);
    const bothPorts = interfaceForNode(both, index).ports;
    expect(bothPorts.find((entry) => entry.name === "A")?.orientation).toEqual({
      kind: "through",
      partner: "B",
      partnerFixed: null,
    });

    // Only p1 exposed, and p2 bonded inside to a junction (it leaves): a bond at A must arrive.
    const j = junction("1");
    const tf2 = block("TF", "TF2");
    const inside = subsystemOf("Inside", model([tf2, j], [bond(tf2, "p2", j, null)]).diagram, [
      { name: "A", node: tf2.id, port: "p1" },
    ]);
    expect(interfaceForNode(inside, index).ports[0]?.orientation).toEqual({
      kind: "through",
      partner: null,
      partnerFixed: "leaves",
    });
    const other = junction("0");
    const doc = model([inside, other]);
    expect(runs(doc, port(doc, inside, "A"), port(doc, other, null))).toEqual({
      from: other.id,
      to: inside.id,
    });
  });
});

describe("the document store orients the bond it creates", () => {
  beforeEach(() => {
    resetDocumentStore();
    resetCatalogStore();
    useCatalogStore.getState().setCatalog(catalog);
  });

  it("stores out -> in when the user starts at the in port", () => {
    const se = block("Se");
    const c = block("C");
    const doc = model([se, c]);
    useDocumentStore.getState().openDocument("demo", "Orientation", doc);
    const result = useDocumentStore.getState().connect(port(doc, c, "p"), port(doc, se, "p"));
    expect(result.ok).toBe(true);
    const stored = useDocumentStore.getState().doc?.diagram.connections[0];
    expect(stored?.from.node).toBe(se.id);
    expect(stored?.to.node).toBe(c.id);
  });

  it("refuses in-in and adds no connection", () => {
    const c = block("C");
    const i = block("I");
    const doc = model([c, i]);
    useDocumentStore.getState().openDocument("demo", "Orientation", doc);
    const result = useDocumentStore.getState().connect(port(doc, c, "p"), port(doc, i, "p"));
    expect(result.ok).toBe(false);
    expect(result.reason).toContain("put a junction in between");
    expect(useDocumentStore.getState().doc?.diagram.connections).toHaveLength(0);
  });

  it("keeps the stored direction of a pasted bond, even a wrong one", () => {
    const se = block("Se");
    const c = block("C");
    // Stored the wrong way round: C.p -> Se.p (the compiler reports E114; the editor does not rewrite it).
    const wrong = bond(c, "p", se, "p", "c1");
    const doc = model([se, c], [wrong]);
    useDocumentStore.getState().openDocument("demo", "Orientation", doc);
    useDocumentStore.getState().setSelection([se.id, c.id], []);
    const clip = useDocumentStore.getState().copySelection();
    expect(clip).not.toBeNull();
    if (clip === null) {
      return;
    }
    const pasted = useDocumentStore.getState().pasteClip(clip);
    expect(pasted?.connections).toBe(1);
    const connections = useDocumentStore.getState().doc?.diagram.connections ?? [];
    expect(connections).toHaveLength(2);
    const copy = connections.find((entry) => entry.id !== "c1");
    const names = new Map((useDocumentStore.getState().doc?.diagram.nodes ?? []).map((n) => [n.id, n.name]));
    expect(names.get(copy?.from.node ?? "")).toMatch(/^C/);
    expect(names.get(copy?.to.node ?? "")).toMatch(/^Se/);
  });
});

describe("reversing a bond", () => {
  it("is refused at an in port, with the reason", () => {
    const se = block("Se");
    const c = block("C", "C1");
    const b = bond(se, "p", c, "p");
    const doc = model([se, c], [b]);
    const check = checkReverse(doc, index, b);
    expect(check.ok).toBe(false);
    if (!check.ok) {
      expect(check.reason).toContain("the port `C1.p` is declared `in`: a bond must end there");
    }
  });

  it("is refused at an out port, with the reason", () => {
    const se = block("Se", "Se1");
    const j = junction("1");
    const b = bond(se, "p", j, null);
    const doc = model([se, j], [b]);
    const check = checkReverse(doc, index, b);
    expect(check.ok).toBe(false);
    if (!check.ok) {
      expect(check.reason).toContain("the port `Se1.p` is declared `out`: a bond must start there");
    }
  });

  it("is allowed between two any ends and between junctions of the same kind, without a warning", () => {
    const f1 = block("Face", "F1");
    const f2 = block("Face", "F2");
    const j1 = junction("1", "Ja");
    const j2 = junction("1", "Jb");
    const anyBond = bond(f1, "p", f2, "p");
    const jjBond = bond(j1, null, j2, null);
    const doc = model([f1, f2, j1, j2], [anyBond, jjBond]);
    expect(checkReverse(doc, index, anyBond)).toEqual({ ok: true, note: null });
    expect(checkReverse(doc, index, jjBond)).toEqual({ ok: true, note: null });
  });

  it("is refused at a port that declares no orientation", () => {
    const de = block("De", "De1");
    const j = junction("1");
    const b = bond(j, null, de, "p");
    const check = checkReverse(model([de, j], [b]), index, b);
    expect(check).toEqual({ ok: false, reason: "`De1.p` declares no orientation: add `@orientation` to the block" });
  });

  it("stays allowed for a 0-1 bond and says what it does", () => {
    const zero = junction("0");
    const one = junction("1");
    const b = bond(zero, null, one, null);
    const doc = model([zero, one], [b]);
    const check = checkReverse(doc, index, b);
    expect(check).toEqual({ ok: true, note: REVERSE_JUNCTION_NOTE });
    expect(REVERSE_JUNCTION_NOTE.toLowerCase()).toContain(
      "reverses the reference direction of everything behind this bond",
    );
    expect(REVERSE_JUNCTION_NOTE.toLowerCase()).not.toContain("harmless");
  });

  it("fixes a bond stored the wrong way round", () => {
    const c = block("C");
    const j = junction("1");
    const wrong = bond(c, "p", j, null);
    const doc = model([c, j], [wrong]);
    expect(checkReverse(doc, index, wrong)).toEqual({ ok: true, note: null });
  });

  it("is refused when the other bond of a through pair already takes the role", () => {
    const tf = block("TF", "TF1");
    const j = junction("1");
    const other = junction("0");
    const first = bond(j, null, tf, "p1");
    const second = bond(tf, "p2", other, null);
    const doc = model([tf, j, other], [first, second]);
    // Reversing `second` would make both bonds arrive at TF1.
    const check = checkReverse(doc, index, second);
    expect(check.ok).toBe(false);
    if (!check.ok) {
      expect(check.reason).toContain("`TF1.p2`");
      expect(check.reason).toContain("paired with `p1`");
    }
    // A through bond with a free partner may be reversed.
    const alone = model([tf, other], [second]);
    expect(checkReverse(alone, index, second)).toEqual({ ok: true, note: null });
  });
});

describe("orientBond", () => {
  it("is symmetric: both argument orders give the same direction when only one is valid", () => {
    const se = block("Se");
    const c = block("C");
    const doc = model([se, c]);
    const a = port(doc, se, "p");
    const b = port(doc, c, "p");
    const forward = orientBond(doc, a, b);
    const backward = orientBond(doc, b, a);
    expect(forward.ok && backward.ok && forward.from.nodeId === backward.from.nodeId).toBe(true);
  });
});
