/**
 * The editing keys of the Code tab editor: Tab indents (and keeps the focus),
 * Shift+Tab dedents, Enter keeps the indentation and follows the block
 * structure (`begin` opens a level, `end` closes it), and Ctrl+Enter stays
 * with the app (run the model).
 */

import { fireEvent, render } from "@testing-library/react";
import { EditorSelection } from "@codemirror/state";
import { EditorView } from "@codemirror/view";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { CodeEditor } from "../src/code/CodeEditor";

vi.mock("../src/code/blockCheck", () => ({
  checkBlockSource: vi.fn(() => new Promise(() => undefined)),
}));

const SOURCE = `@block Gain begin
    @parameters begin
        k::Real = 2.0
    end
end
`;

let changes: string[] = [];

beforeEach(() => {
  changes = [];
});

function mountEditor(source: string, readOnly = false): EditorView {
  const { container } = render(
    <CodeEditor
      targetKey="inline:n1"
      source={source}
      readOnly={readOnly}
      checkRef="inline:n1"
      line={1}
      col={1}
      onChange={(text) => changes.push(text)}
    />,
  );
  const editor = container.querySelector<HTMLElement>(".cm-editor");
  if (editor === null) {
    throw new Error("no CodeMirror editor rendered");
  }
  const view = EditorView.findFromDOM(editor);
  if (view === null) {
    throw new Error("no EditorView on the editor element");
  }
  return view;
}

/** Fire a key on the editor content; returns false when the editor handled it. */
function press(view: EditorView, key: string, init: KeyboardEventInit = {}): boolean {
  const keyCode = { Tab: 9, Enter: 13, Escape: 27 }[key] ?? 0;
  return fireEvent.keyDown(view.contentDOM, { key, keyCode, ...init });
}

function cursorAt(view: EditorView, position: number): void {
  view.dispatch({ selection: EditorSelection.cursor(position) });
}

function type(view: EditorView, text: string): void {
  const { from, to } = view.state.selection.main;
  view.dispatch({
    changes: { from, to, insert: text },
    selection: EditorSelection.cursor(from + text.length),
    userEvent: "input.type",
  });
}

function text(view: EditorView): string {
  return view.state.doc.toString();
}

describe("Tab and Shift+Tab", () => {
  it("inserts 4 spaces at the cursor and keeps the focus in the editor", () => {
    const view = mountEditor("x\n");
    cursorAt(view, 0);
    expect(press(view, "Tab")).toBe(false); // default (move focus) prevented
    expect(text(view)).toBe("    x\n");
    expect(view.state.selection.main.head).toBe(4);
    expect(changes.at(-1)).toBe("    x\n");
  });

  it("pads to the next indent stop inside a line", () => {
    const view = mountEditor("ab\n");
    cursorAt(view, 2);
    press(view, "Tab");
    expect(text(view)).toBe("ab  \n");
  });

  it("indents and dedents every selected line", () => {
    const view = mountEditor("a\nb\nc\n");
    view.dispatch({ selection: EditorSelection.range(0, 3) });
    press(view, "Tab");
    expect(text(view)).toBe("    a\n    b\nc\n");
    press(view, "Tab", { shiftKey: true });
    expect(text(view)).toBe("a\nb\nc\n");
  });

  it("dedents the cursor line with Shift+Tab", () => {
    const view = mountEditor("        k = 1\n");
    cursorAt(view, 10);
    expect(press(view, "Tab", { shiftKey: true })).toBe(false);
    expect(text(view)).toBe("    k = 1\n");
  });

  it("leaves Tab to the browser after Esc (the keyboard escape)", () => {
    const view = mountEditor("x\n");
    cursorAt(view, 0);
    press(view, "Escape");
    expect(press(view, "Tab")).toBe(true);
    expect(text(view)).toBe("x\n");
  });

  it("does not edit a read-only (stdlib) source", () => {
    const view = mountEditor("x\n", true);
    cursorAt(view, 0);
    press(view, "Tab");
    expect(text(view)).toBe("x\n");
  });
});

describe("Enter", () => {
  it("keeps the indentation of an indented line", () => {
    const view = mountEditor(SOURCE);
    const end = text(view).indexOf("2.0") + 3;
    cursorAt(view, end);
    expect(press(view, "Enter")).toBe(false);
    const lines = text(view).split("\n");
    expect(lines[2]).toBe("        k::Real = 2.0");
    expect(lines[3]).toBe("        ");
    expect(view.state.selection.main.head).toBe(end + 1 + 8);
  });

  it("indents one level after a line that opens a block", () => {
    const view = mountEditor("@block Gain begin");
    cursorAt(view, view.state.doc.length);
    press(view, "Enter");
    expect(text(view)).toBe("@block Gain begin\n    ");
    type(view, "@equations begin");
    press(view, "Enter");
    expect(text(view)).toBe("@block Gain begin\n    @equations begin\n        ");
  });

  it("indents after for, if and function", () => {
    for (const opener of ["for i in 1:3", "if x > 0", "function f(x)"]) {
      const head = `@block B begin\n    ${opener}`;
      const view = mountEditor(head);
      cursorAt(view, view.state.doc.length);
      press(view, "Enter");
      expect(text(view)).toBe(`${head}\n        `);
      view.destroy();
    }
  });

  it("dedents a typed end to the level of its begin", () => {
    const view = mountEditor("@block Gain begin\n    @equations begin\n        y ~ k * u");
    cursorAt(view, view.state.doc.length);
    press(view, "Enter");
    type(view, "end");
    expect(text(view).split("\n").at(-1)).toBe("    end");
    press(view, "Enter");
    type(view, "end");
    expect(text(view).split("\n").at(-1)).toBe("end");
  });

  it("leaves Ctrl+Enter to the app (run the model)", () => {
    const view = mountEditor("x\n");
    cursorAt(view, 1);
    expect(press(view, "Enter", { ctrlKey: true })).toBe(true);
    expect(text(view)).toBe("x\n");
  });
});
