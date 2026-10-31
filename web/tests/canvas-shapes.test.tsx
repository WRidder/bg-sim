/**
 * Background shapes (diagram.shapes): the pure helpers (ids, z order, line
 * geometry, styles), the document-store operations (add, style, label, frame,
 * reorder, lock, duplicate, move, delete, copy/paste, undo, nested diagrams),
 * the canvas nodes they become and the shape menu.
 */

import { fireEvent, render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import catalogJson from "../../contracts/fixtures/catalog/valid/catalog.min.json";
import shapesFixture from "../../contracts/fixtures/model/valid/model.canvas-shapes.json";
import type { Catalog } from "../src/contracts/catalog";
import type { Model, ModelShape } from "../src/contracts/model";
import { buildDiagram, shapeNodes } from "../src/editor/buildFlow";
import { NOTE_Z_INDEX } from "../src/editor/notes";
import { ShapeMenuItems } from "../src/editor/ShapeMenu";
import { ShapeInspector } from "../src/inspector/ShapeInspector";
import {
  applyShapeStyle,
  canReorder,
  isShapeId,
  LINE_PAD,
  reorderShapes,
  SHAPE_MIN_SIZE,
  selectedShapeIds,
  shapeFlowId,
  shapeIdOf,
  shapeNodeFrame,
  shapeOriginAt,
  shapeStyle,
  shapeZIndex,
} from "../src/editor/shapes";
import { activeDiagram, activeModel } from "../src/editor/subsystemPath";
import { buildCatalogIndex } from "../src/library/catalogIndex";
import { resetDocumentStore, useDocumentStore } from "../src/state/documentStore";
import { createEmptyModel } from "../src/state/modelFactory";

const catalog = catalogJson as unknown as Catalog;
const index = buildCatalogIndex(catalog);
const fixture = shapesFixture as unknown as Model;

function store() {
  return useDocumentStore.getState();
}

function shapes(): ModelShape[] {
  const state = store();
  return state.doc === null ? [] : (activeDiagram(state.doc, state.activePath)?.shapes ?? []);
}

function order(): string[] {
  return shapes().map((shape) => shape.id);
}

beforeEach(() => {
  resetDocumentStore();
  store().openDocument("demo", "Shapes", createEmptyModel("Shapes"));
});

describe("shape ids and geometry", () => {
  it("maps shape ids to canvas ids and back", () => {
    expect(shapeFlowId("s1")).toBe("shape:s1");
    expect(shapeIdOf("shape:s1")).toBe("s1");
    expect(shapeIdOf("note:a1")).toBeNull();
    expect(isShapeId("shape:s2")).toBe(true);
    expect(isShapeId("n1")).toBe(false);
    expect(selectedShapeIds(["n1", "shape:s1", "note:a1", "shape:s3"])).toEqual(["s1", "s3"]);
  });

  it("keeps every shape below the notes, in document order, selected or not", () => {
    const count = 4;
    const z = Array.from({ length: count }, (_, i) => shapeZIndex(i, count));
    for (let i = 0; i < count; i += 1) {
      // xyflow raises a selected node by 1000.
      expect((z[i] ?? 0) + 1000).toBeLessThan(NOTE_Z_INDEX);
      if (i + 1 < count) {
        expect((z[i] ?? 0) + 1000).toBeLessThan(z[i + 1] ?? 0);
      }
    }
  });

  it("frames a line with padding and maps a dragged box back to its start", () => {
    const line: ModelShape = { id: "s1", kind: "arrow", x: 100, y: 50, w: -60, h: 40 };
    expect(shapeNodeFrame(line)).toEqual({
      x: 40 - LINE_PAD,
      y: 50 - LINE_PAD,
      width: 60 + 2 * LINE_PAD,
      height: 40 + 2 * LINE_PAD,
    });
    // The box moved by (+10, +20): the start moves by the same.
    const frame = shapeNodeFrame(line);
    expect(shapeOriginAt(line, { x: frame.x + 10, y: frame.y + 20 })).toEqual({ x: 110, y: 70 });
    const rect: ModelShape = { id: "s2", kind: "rectangle", x: 0, y: 0, w: 10, h: 10 };
    expect(shapeOriginAt(rect, { x: 5, y: 6 })).toEqual({ x: 5, y: 6 });
  });

  it("resolves defaults and writes only what differs from them", () => {
    const shape: ModelShape = { id: "s1", kind: "rectangle", x: 0, y: 0, w: 10, h: 10 };
    expect(shapeStyle(shape)).toEqual({
      fill: "none",
      stroke: "ink",
      strokeWidth: 2,
      strokeStyle: "solid",
      opacity: 1,
      labelPosition: "center",
    });
    applyShapeStyle(shape, { fill: "blue", strokeWidth: 99, opacity: 0.333, strokeStyle: "dashed" });
    expect(shape).toMatchObject({ fill: "blue", strokeWidth: 24, opacity: 0.33, strokeStyle: "dashed" });
    applyShapeStyle(shape, { fill: "none", strokeWidth: 2, opacity: 1, strokeStyle: "solid" });
    expect(shape).toEqual({ id: "s1", kind: "rectangle", x: 0, y: 0, w: 10, h: 10 });
    // Lines have no fill.
    expect(shapeStyle({ id: "s2", kind: "line", x: 0, y: 0, w: 1, h: 0, fill: "pink" }).fill).toBe("none");
  });
});

describe("z order", () => {
  const list = ["a", "b", "c", "d", "e"].map((id) => ({ id }));
  const ids = (items: readonly { id: string }[]) => items.map((item) => item.id).join("");

  it("brings to front and sends to back, keeping the relative order", () => {
    expect(ids(reorderShapes(list, ["b", "d"], "front"))).toBe("acebd");
    expect(ids(reorderShapes(list, ["b", "d"], "back"))).toBe("bdace");
  });

  it("moves one step forward or backward past unchosen neighbours", () => {
    expect(ids(reorderShapes(list, ["b"], "forward"))).toBe("acbde");
    expect(ids(reorderShapes(list, ["b"], "backward"))).toBe("bacde");
    expect(ids(reorderShapes(list, ["a", "b"], "forward"))).toBe("cabde");
    expect(ids(reorderShapes(list, ["d", "e"], "backward"))).toBe("abdec");
    expect(ids(reorderShapes(list, ["b", "d"], "forward"))).toBe("acbed");
  });

  it("returns the same array when nothing moves", () => {
    expect(reorderShapes(list, ["e"], "front")).toBe(list);
    expect(reorderShapes(list, ["e"], "forward")).toBe(list);
    expect(reorderShapes(list, ["a"], "back")).toBe(list);
    expect(reorderShapes(list, ["a", "b"], "backward")).toBe(list);
    expect(reorderShapes(list, ["zz"], "front")).toBe(list);
    expect(canReorder(list, ["e"], "front")).toBe(false);
    expect(canReorder(list, ["e"], "back")).toBe(true);
  });
});

describe("document store: shapes", () => {
  it("adds shapes in front, selects the new one and undoes", () => {
    expect(store().addShape("rectangle", { x: 40.04, y: 80 })).toBe("shape:s1");
    expect(store().selection.nodes).toEqual(["shape:s1"]);
    expect(shapes()).toEqual([{ id: "s1", kind: "rectangle", x: 40, y: 80, w: 200, h: 120 }]);
    store().addShape("arrow", { x: 0, y: 0 }, { style: { stroke: "pink" }, text: "flow" });
    expect(shapes()[1]).toEqual({
      id: "s2",
      kind: "arrow",
      x: 0,
      y: 0,
      w: 200,
      h: 0,
      stroke: "pink",
      text: "flow",
    });
    store().undo();
    store().undo();
    expect(shapes()).toEqual([]);
    expect(store().selection.nodes).toEqual([]);
    store().redo();
    expect(order()).toEqual(["s1"]);
  });

  it("restyles several shapes in one undo step and labels with one step per session", () => {
    store().addShape("rectangle", { x: 0, y: 0 });
    store().addShape("ellipse", { x: 300, y: 0 });
    const before = store().past.length;
    store().setShapeStyle(["s1", "s2"], { fill: "green", strokeStyle: "dotted" });
    expect(shapes().map((shape) => [shape.fill, shape.strokeStyle])).toEqual([
      ["green", "dotted"],
      ["green", "dotted"],
    ]);
    expect(store().past.length).toBe(before + 1);
    store().beginGesture("shape-text:s1");
    for (const text of ["P", "Pl", "Plant"]) {
      store().setShapeText("s1", text, { coalesce: true });
    }
    store().endGesture();
    expect(shapes()[0]?.text).toBe("Plant");
    expect(store().past.length).toBe(before + 2);
    store().setShapeText("s1", "");
    expect("text" in (shapes()[0] ?? {})).toBe(false);
  });

  it("reorders through the store in one undo step; a no-op adds none", () => {
    for (let i = 0; i < 3; i += 1) {
      store().addShape("rectangle", { x: i * 10, y: 0 });
    }
    const before = store().past.length;
    store().reorderShapes(["s1"], "front");
    expect(order()).toEqual(["s2", "s3", "s1"]);
    store().reorderShapes(["s1"], "front");
    expect(store().past.length).toBe(before + 1);
    store().reorderShapes(["s3"], "back");
    store().reorderShapes(["s2"], "forward");
    expect(order()).toEqual(["s3", "s1", "s2"]);
    store().undo();
    store().undo();
    expect(order()).toEqual(["s2", "s3", "s1"]);
    store().undo();
    expect(order()).toEqual(["s1", "s2", "s3"]);
  });

  it("resizes a frame with a minimum and moves a line's end freely", () => {
    store().addShape("rectangle", { x: 0, y: 0 });
    store().addShape("line", { x: 0, y: 0 });
    store().beginGesture("shape-resize:s1");
    store().setShapeFrame("s1", { x: 0, y: 0, w: 300, h: 200 }, "shape-resize:s1");
    store().setShapeFrame("s1", { x: -10, y: 0, w: 5, h: 5 }, "shape-resize:s1");
    store().endGesture();
    expect(shapes()[0]).toMatchObject({ x: -10, y: 0, w: SHAPE_MIN_SIZE.w, h: SHAPE_MIN_SIZE.h });
    store().setShapeFrame("s2", { x: 0, y: 0, w: -80.04, h: 60 });
    expect(shapes()[1]).toMatchObject({ x: 0, y: 0, w: -80, h: 60 });
  });

  it("locks a shape against moves, resizes and Del, but not against selection", () => {
    store().addShape("rectangle", { x: 0, y: 0 });
    store().addShape("ellipse", { x: 300, y: 0 });
    store().setShapeLocked(["s1"], true);
    expect(shapes()[0]?.locked).toBe(true);

    store().setNodePositions({ "shape:s1": { x: 500, y: 500 }, "shape:s2": { x: 320, y: 40 } }, false);
    expect(shapes()[0]).toMatchObject({ x: 0, y: 0 });
    expect(shapes()[1]).toMatchObject({ x: 320, y: 40 });
    store().setShapeFrame("s1", { x: 0, y: 0, w: 400, h: 400 });
    expect(shapes()[0]).toMatchObject({ w: 200, h: 120 });

    // Del with only the locked shape selected changes nothing.
    store().setSelection(["shape:s1"], []);
    expect(store().selection.nodes).toEqual(["shape:s1"]);
    const steps = store().past.length;
    store().deleteSelection();
    expect(order()).toEqual(["s1", "s2"]);
    expect(store().past.length).toBe(steps);
    // Del with both deletes the unlocked one and keeps the locked one selected.
    store().setSelection(["shape:s1", "shape:s2"], []);
    store().deleteSelection();
    expect(order()).toEqual(["s1"]);
    expect(store().selection.nodes).toEqual(["shape:s1"]);

    // Unlocked again: the field goes away and Del works.
    store().setShapeLocked(["s1"], false);
    expect("locked" in (shapes()[0] ?? {})).toBe(false);
    store().deleteSelection();
    expect(order()).toEqual([]);
    store().undo();
    store().undo();
    expect(shapes()[0]?.locked).toBe(true);
  });

  it("copies, pastes and duplicates in front, offset and unlocked", () => {
    store().addShape("rectangle", { x: 10, y: 20 }, { style: { fill: "yellow" } });
    store().addShape("ellipse", { x: 100, y: 20 });
    store().addShape("line", { x: 0, y: 200 });
    store().setShapeLocked(["s1"], true);
    store().setSelection(["shape:s2", "shape:s1"], []);
    store().copySelection();
    // The clipboard keeps the document (z) order.
    expect(store().clipboard.shapes.map((shape) => shape.id)).toEqual(["s1", "s2"]);
    store().paste();
    expect(order()).toEqual(["s1", "s2", "s3", "s4", "s5"]);
    expect(shapes()[3]).toEqual({ id: "s4", kind: "rectangle", x: 34, y: 44, w: 200, h: 120, fill: "yellow" });
    expect(store().selection.nodes).toEqual(["shape:s4", "shape:s5"]);
    store().undo();
    expect(order()).toEqual(["s1", "s2", "s3"]);

    expect(store().duplicateShapes(["s3"])).toEqual(["shape:s4"]);
    expect(shapes()[3]).toMatchObject({ kind: "line", x: 24, y: 224 });
    expect(store().selection.nodes).toEqual(["shape:s4"]);
  });

  it("keeps shapes per diagram level (inside a subsystem)", () => {
    store().openDocument("demo", "Shapes", fixture);
    expect(order()).toEqual(["s1", "s2", "s3", "s4", "s5"]);
    expect(store().enterSubsystem("plant")).toBe(true);
    expect(order()).toEqual(["s1"]);
    expect(store().addShape("rectangle", { x: 0, y: 0 })).toBe("shape:s2");
    store().reorderShapes(["s2"], "back");
    expect(order()).toEqual(["s2", "s1"]);
    store().leaveSubsystem();
    expect(order()).toEqual(["s1", "s2", "s3", "s4", "s5"]);
  });
});

describe("canvas nodes", () => {
  it("builds the shapes first, back to front, behind the notes", () => {
    const flow = buildDiagram(fixture, index, { nodes: [], connections: [] });
    const types = flow.nodes.map((node) => node.type);
    expect(types.slice(0, 5)).toEqual(["shape", "shape", "shape", "shape", "shape"]);
    expect(types.slice(5, 7)).toEqual(["note", "note"]);
    const nodes = shapeNodes(fixture);
    expect(nodes.map((node) => node.id)).toEqual([
      "shape:s1",
      "shape:s2",
      "shape:s3",
      "shape:s4",
      "shape:s5",
    ]);
    const z = nodes.map((node) => node.zIndex ?? 0);
    expect([...z].sort((a, b) => a - b)).toEqual(z);
    expect(Math.max(...z) + 1000).toBeLessThan(NOTE_Z_INDEX);
    // s1 is locked: not draggable, not box-selectable; the others are.
    expect(nodes[0]).toMatchObject({ draggable: false, selectable: false, data: { locked: true } });
    expect(nodes[1]).toMatchObject({ draggable: true, selectable: true, data: { locked: false } });
    // The node box takes no pointer events; only the painted shape does.
    expect(nodes.every((node) => node.style?.pointerEvents === "none")).toBe(true);
    expect(nodes[0]?.data).toMatchObject({ fill: "blue", stroke: "blue", opacity: 0.6, text: "Drive" });
    expect(nodes[1]?.data).toMatchObject({ fill: "none", stroke: "ink", strokeWidth: 2 });
    // The arrow (start 480,-40, direction -120,100) gets its padded bounds.
    expect(nodes[4]).toMatchObject({
      position: { x: 360 - LINE_PAD, y: -40 - LINE_PAD },
      width: 120 + 2 * LINE_PAD,
      height: 100 + 2 * LINE_PAD,
    });
    const inner = activeModel(fixture, ["plant"]);
    expect(inner === null ? [] : shapeNodes(inner).map((node) => node.id)).toEqual(["shape:s1"]);
  });
});

describe("label position", () => {
  it("stores only a non-centre position and sets it from the inspector", () => {
    const shape: ModelShape = { id: "s1", kind: "rectangle", x: 0, y: 0, w: 10, h: 10, text: "Plant" };
    applyShapeStyle(shape, { labelPosition: "topLeft" });
    expect(shape.labelPosition).toBe("topLeft");
    applyShapeStyle(shape, { labelPosition: "center" });
    expect("labelPosition" in shape).toBe(false);

    store().addShape("rectangle", { x: 0, y: 0 });
    store().setShapeText("s1", "Plant");
    const { rerender } = render(<ShapeInspector shapes={shapes()} all={shapes()} />);
    const picker = screen.getByTestId("shape-label-position");
    expect(picker.querySelectorAll("input[type=radio]")).toHaveLength(9);
    expect((screen.getByTestId("shape-label-position-center") as HTMLInputElement).checked).toBe(true);
    fireEvent.click(screen.getByTestId("shape-label-position-bottomRight"));
    expect(shapes()[0]?.labelPosition).toBe("bottomRight");
    rerender(<ShapeInspector shapes={shapes()} all={shapes()} />);
    expect((screen.getByLabelText("Bottom right") as HTMLInputElement).checked).toBe(true);

    // A line centres its label: no picker.
    store().addShape("line", { x: 0, y: 200 });
    const line = shapes().filter((item) => item.kind === "line");
    rerender(<ShapeInspector shapes={line} all={shapes()} />);
    expect(screen.queryByTestId("shape-label-position")).toBeNull();
  });
});

describe("shape menu", () => {
  it("offers arrange, lock, duplicate and delete with the right states", () => {
    store().openDocument("demo", "Shapes", fixture);
    store().setSelection(["shape:s5"], []);
    const done = vi.fn();
    const remove = vi.fn();
    const { unmount } = render(
      <div role="menu">
        <ShapeMenuItems flowId="shape:s5" onDone={done} onDelete={remove} />
      </div>,
    );
    // s5 is the front-most shape.
    expect(screen.getByTestId("shape-order-front")).toHaveProperty("disabled", true);
    expect(screen.getByTestId("shape-order-forward")).toHaveProperty("disabled", true);
    expect(screen.getByTestId("shape-order-back")).toHaveProperty("disabled", false);
    fireEvent.click(screen.getByTestId("shape-order-back"));
    expect(order()).toEqual(["s5", "s1", "s2", "s3", "s4"]);
    expect(done).toHaveBeenCalledTimes(1);
    fireEvent.click(screen.getByTestId("shape-lock"));
    expect(shapes()[0]?.locked).toBe(true);
    unmount();

    // A locked shape: Unlock instead of Lock, and Delete is disabled.
    render(
      <div role="menu">
        <ShapeMenuItems flowId="shape:s1" onDone={done} onDelete={remove} />
      </div>,
    );
    expect(screen.getByTestId("shape-unlock").textContent).toBe("Unlock");
    expect(screen.getByTestId("shape-delete")).toHaveProperty("disabled", true);
    fireEvent.click(screen.getByTestId("shape-duplicate"));
    expect(order()).toHaveLength(6);
    expect(shapes()[5]?.locked).toBeUndefined();
  });
});
