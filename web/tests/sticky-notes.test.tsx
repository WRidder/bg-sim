/**
 * Sticky notes (diagram.annotations): the document-store operations (add,
 * text with one undo step per editing session, colour, frame, move, delete,
 * copy/paste, notes inside a subsystem), the canvas nodes they become, and
 * the restricted Markdown of a note.
 */

import { fireEvent, render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import catalogJson from "../../contracts/fixtures/catalog/valid/catalog.min.json";
import notesFixture from "../../contracts/fixtures/model/valid/model.sticky-notes.json";
import type { Catalog } from "../src/contracts/catalog";
import type { Model } from "../src/contracts/model";
import { MarkdownView, type LinkActions } from "../src/docs/MarkdownView";
import type { LinkContext } from "../src/docs/docsLinks";
import { buildDiagram, noteNodes } from "../src/editor/buildFlow";
import { beginNoteTextGesture, endNoteTextGesture } from "../src/editor/noteEditing";
import {
  isNoteId,
  NOTE_MIN_SIZE,
  NOTE_Z_INDEX,
  noteFlowId,
  noteIdOf,
  selectedNoteIds,
} from "../src/editor/notes";
import { activeDiagram, activeModel } from "../src/editor/subsystemPath";
import { buildCatalogIndex } from "../src/library/catalogIndex";
import { resetDocumentStore, useDocumentStore } from "../src/state/documentStore";
import { createEmptyModel } from "../src/state/modelFactory";

const catalog = catalogJson as unknown as Catalog;
const index = buildCatalogIndex(catalog);

function store() {
  return useDocumentStore.getState();
}

function notes() {
  const state = store();
  return state.doc === null ? [] : (activeDiagram(state.doc, state.activePath)?.annotations ?? []);
}

beforeEach(() => {
  resetDocumentStore();
  store().openDocument("demo", "Notes", createEmptyModel("Notes"));
});

describe("note ids", () => {
  it("maps annotation ids to canvas ids and back", () => {
    expect(noteFlowId("a1")).toBe("note:a1");
    expect(noteIdOf("note:a1")).toBe("a1");
    expect(noteIdOf("n1")).toBeNull();
    expect(isNoteId("note:a2")).toBe(true);
    expect(isNoteId("terminal:u")).toBe(false);
    expect(selectedNoteIds(["n1", "note:a1", "terminal:u", "note:a3"])).toEqual(["a1", "a3"]);
  });
});

describe("document store: sticky notes", () => {
  it("adds a note, selects it and undoes it", () => {
    const id = store().addNote({ x: 40.04, y: 80 });
    expect(id).toBe("note:a1");
    expect(store().selection.nodes).toEqual(["note:a1"]);
    expect(notes()).toEqual([{ id: "a1", kind: "text", text: "", x: 40, y: 80, w: 200, h: 200 }]);
    expect(store().addNote({ x: 0, y: 0 }, { color: "pink", text: "hi" })).toBe("note:a2");
    expect(notes()[1]).toMatchObject({ id: "a2", color: "pink", text: "hi" });
    store().undo();
    store().undo();
    expect(notes()).toEqual([]);
    expect(store().selection.nodes).toEqual([]);
    store().redo();
    expect(notes()).toHaveLength(1);
  });

  it("makes one undo step of an editing session", () => {
    store().addNote({ x: 0, y: 0 });
    const before = store().past.length;
    beginNoteTextGesture("a1");
    for (const text of ["*", "**b", "**bold**", "**bold**\n- one"]) {
      store().setNoteText("a1", text, { coalesce: true });
    }
    endNoteTextGesture("a1");
    expect(notes()[0]?.text).toBe("**bold**\n- one");
    expect(store().past.length).toBe(before + 1);
    expect(store().gestureKey).toBeNull();
    store().undo();
    expect(notes()[0]?.text).toBe("");
    store().redo();
    expect(notes()[0]?.text).toBe("**bold**\n- one");

    // A second session is a second step.
    beginNoteTextGesture("a1");
    store().setNoteText("a1", "again", { coalesce: true });
    store().setNoteText("a1", "again!", { coalesce: true });
    endNoteTextGesture("a1");
    expect(store().past.length).toBe(before + 2);
  });

  it("colours notes; yellow is the absent default", () => {
    store().addNote({ x: 0, y: 0 });
    store().addNote({ x: 300, y: 0 });
    store().setNoteColor(["a1", "a2"], "blue");
    expect(notes().map((note) => note.color)).toEqual(["blue", "blue"]);
    store().setNoteColor(["a1"], "yellow");
    expect("color" in (notes()[0] ?? {})).toBe(false);
    const steps = store().past.length;
    store().setNoteColor(["a1"], "yellow");
    expect(store().past.length).toBe(steps);
  });

  it("resizes with a minimum and coalesces one resize drag", () => {
    store().addNote({ x: 0, y: 0 });
    const before = store().past.length;
    store().beginGesture("note-resize");
    store().setNoteFrame("a1", { x: 0, y: 0, w: 260, h: 220 });
    store().setNoteFrame("a1", { x: -10, y: 0, w: 10, h: 5 });
    store().endGesture();
    expect(notes()[0]).toMatchObject({ x: -10, y: 0, w: NOTE_MIN_SIZE.w, h: NOTE_MIN_SIZE.h });
    expect(store().past.length).toBe(before + 1);
  });

  it("moves with the node drag and deletes with the selection", () => {
    store().addNote({ x: 0, y: 0 });
    store().setNodePositions({ "note:a1": { x: 120.06, y: 40 } }, false);
    expect(notes()[0]).toMatchObject({ x: 120.1, y: 40 });
    store().setSelection(["note:a1"], []);
    store().deleteSelection();
    expect(notes()).toEqual([]);
    expect(store().selection.nodes).toEqual([]);
    store().undo();
    expect(notes()).toHaveLength(1);
  });

  it("copies and pastes notes with new ids and an offset", () => {
    store().addNote({ x: 10, y: 20 }, { text: "copy me", color: "green" });
    store().setSelection(["note:a1"], []);
    store().copySelection();
    expect(store().clipboard.annotations).toHaveLength(1);
    store().paste();
    expect(notes().map((note) => note.id)).toEqual(["a1", "a2"]);
    expect(notes()[1]).toMatchObject({ text: "copy me", color: "green", x: 34, y: 44 });
    expect(store().selection.nodes).toEqual(["note:a2"]);
    store().undo();
    expect(notes()).toHaveLength(1);
  });

  it("keeps notes per diagram level (inside a subsystem)", () => {
    store().openDocument("demo", "Notes", notesFixture as unknown as Model);
    expect(notes().map((note) => note.id)).toEqual(["note1", "note2"]);
    expect(store().enterSubsystem("plant")).toBe(true);
    expect(notes().map((note) => note.id)).toEqual(["note1"]);
    const id = store().addNote({ x: 0, y: 0 }, { text: "inner" });
    expect(id).toBe("note:a1");
    expect(notes().map((note) => note.id)).toEqual(["note1", "a1"]);
    store().setSelection(["note:note1"], []);
    expect(store().selection.nodes).toEqual(["note:note1"]);
    store().deleteSelection();
    store().leaveSubsystem();
    // The root notes are untouched.
    expect(notes().map((note) => note.id)).toEqual(["note1", "note2"]);
    const plant = store().doc?.diagram.nodes.find((node) => node.id === "plant");
    const inner = plant !== undefined && "subsystem" in plant.block ? plant.block.subsystem.diagram : null;
    expect(inner?.annotations?.map((note) => note.id)).toEqual(["a1"]);
  });
});

describe("canvas nodes", () => {
  it("builds one note node per annotation, behind everything", () => {
    const doc = notesFixture as unknown as Model;
    const flow = buildDiagram(doc, index, { nodes: [], connections: [] });
    const noteIds = flow.nodes.filter((node) => node.type === "note").map((node) => node.id);
    expect(noteIds).toEqual(["note:note1", "note:note2"]);
    // Notes come first and stay below the edges (z 0) even when selected (+1000).
    expect(flow.nodes[0]?.type).toBe("note");
    expect(NOTE_Z_INDEX + 1000).toBeLessThan(0);
    const [first, second] = noteNodes(doc);
    expect(first).toMatchObject({
      position: { x: 20, y: -120 },
      width: 220,
      height: 120,
      zIndex: NOTE_Z_INDEX,
      data: { noteId: "note1", color: "yellow" },
    });
    expect(second?.data).toMatchObject({ color: "blue" });
    const inner = activeModel(doc, ["plant"]);
    expect(inner === null ? [] : noteNodes(inner).map((node) => node.id)).toEqual(["note:note1"]);
  });
});

describe("note Markdown", () => {
  const links: LinkContext = { pageIds: new Set(["overview"]), model: null, signalIds: null };
  const actions = (): LinkActions => ({
    openPage: vi.fn(),
    showBlock: vi.fn(),
    plotSignal: vi.fn(),
    notify: vi.fn(),
  });
  const note = (text: string, a: LinkActions = actions()) =>
    render(<MarkdownView text={text} project="demo" model="m" links={links} actions={a} variant="note" />);

  it("renders bold, lists and math", () => {
    const { container } = note("**bold** and *it*\n\n- one\n- two\n\n$x^2$");
    expect(container.querySelector("strong")?.textContent).toBe("bold");
    expect(container.querySelectorAll("li")).toHaveLength(2);
    expect(container.querySelector(".katex")).not.toBeNull();
  });

  it("renders headings no bigger than bold text", () => {
    const { container } = note("# Title\n\n## Sub\n\n###### Small\n\ntext");
    for (const level of ["h1", "h2", "h3", "h4", "h5", "h6"]) {
      expect(container.querySelector(level)).toBeNull();
    }
    const headings = [...container.querySelectorAll("p.note-markdown__heading > strong")];
    expect(headings.map((heading) => heading.textContent)).toEqual(["Title", "Sub", "Small"]);
  });

  it("shows no images and no tables", () => {
    const { container } = note(
      "![a diagram](assets/0123456789ab.png)\n\n![](https://example.com/x.png)\n\n| a | b |\n|---|---|\n| 1 | 2 |\n",
    );
    expect(container.querySelector("img")).toBeNull();
    expect(container.querySelector("table")).toBeNull();
    expect(container.querySelector(".note-markdown__alt")?.textContent).toBe("a diagram");
    expect(screen.getByTestId("note-table-omitted")).toBeTruthy();
  });

  it("follows docs page links", () => {
    const a = actions();
    note("see [the overview](page:overview)", a);
    fireEvent.click(screen.getByText("the overview"));
    expect(a.openPage).toHaveBeenCalledWith("overview");
  });

  it("leaves the docs page variant unchanged", () => {
    const { container } = render(
      <MarkdownView text={"# Title\n\n| a |\n|---|\n| 1 |\n"} project="demo" model="m" links={links} actions={actions()} />,
    );
    expect(container.querySelector("h1")).not.toBeNull();
    expect(container.querySelector("table")).not.toBeNull();
  });
});
