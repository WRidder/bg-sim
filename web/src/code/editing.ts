/**
 * Indentation and the standard editing keys of the Code tab.
 *
 * Block sources are indented 4 spaces (`@block Name begin`, one level per
 * `begin ... end`). Enter keeps the indentation through the Julia language's
 * indent service (one level deeper after `begin`, `for`, `if`, `function`,
 * ..., one level less on `end`), Tab indents and Shift+Tab dedents, and
 * pressing Esc and then Tab (or toggling with Ctrl+M) moves focus out of the
 * editor instead, the CodeMirror convention for keyboard users.
 */

import { defaultKeymap, indentLess, indentMore } from "@codemirror/commands";
import { getIndentUnit, indentUnit } from "@codemirror/language";
import { EditorSelection, EditorState, countColumn, type StateCommand } from "@codemirror/state";
import type { KeyBinding } from "@codemirror/view";

/** One indentation level of a block source. */
export const INDENT = "    ";

/** The indent unit and the tab width, both 4 columns. */
export const indentation = [indentUnit.of(INDENT), EditorState.tabSize.of(INDENT.length)];

/**
 * Tab: with a selection, indent the selected lines one level (`indentMore`);
 * with a plain cursor, insert spaces up to the next indent stop at the cursor.
 */
export const insertIndent: StateCommand = ({ state, dispatch }) => {
  if (state.readOnly) {
    return false;
  }
  if (state.selection.ranges.some((range) => !range.empty)) {
    return indentMore({ state, dispatch });
  }
  const unit = getIndentUnit(state);
  const changes = state.changeByRange((range) => {
    const line = state.doc.lineAt(range.head);
    const column = countColumn(line.text.slice(0, range.head - line.from), state.tabSize);
    const insert = " ".repeat(unit - (column % unit));
    return {
      changes: { from: range.head, insert },
      range: EditorSelection.cursor(range.head + insert.length),
    };
  });
  dispatch(state.update(changes, { scrollIntoView: true, userEvent: "input.indent" }));
  return true;
};

/** Tab indents, Shift+Tab dedents the current or selected lines. */
export const tabKeymap: readonly KeyBinding[] = [
  { key: "Tab", run: insertIndent, shift: indentLess },
];

/**
 * CodeMirror's default keymap (Enter with indentation, Backspace, Home/End,
 * line moves, Ctrl+/ comments, Ctrl+[ and Ctrl+] for indentation, ...). Undo
 * and redo are bound separately by the editor because they go through the
 * document store; Ctrl+Enter is left to the app, where it runs the model.
 */
export const editingKeymap: readonly KeyBinding[] = defaultKeymap.filter(
  (binding) => binding.key !== "Mod-Enter",
);
