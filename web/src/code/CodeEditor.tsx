/**
 * The CodeMirror 6 host of the Code tab (plan 7.7).
 *
 * One editor instance per open source. The parent owns the text: for an
 * inline block it writes through the document store (so Ctrl+Z is the
 * document's undo), for a project block it debounces a library PUT, and for
 * a stdlib block it is read-only. The linter calls `POST /api/check/block`
 * with a 300 ms delay and hands both the CodeMirror squiggles and the plain
 * mapped list back to the parent.
 */

import { useEffect, useRef } from "react";

import {
  autocompletion,
  closeBrackets,
  closeBracketsKeymap,
  completionKeymap,
} from "@codemirror/autocomplete";
import { indentOnInput } from "@codemirror/language";
import { EditorSelection, EditorState } from "@codemirror/state";
import {
  EditorView,
  crosshairCursor,
  drawSelection,
  dropCursor,
  highlightActiveLine,
  highlightActiveLineGutter,
  highlightSpecialChars,
  highlightTrailingWhitespace,
  keymap,
  lineNumbers,
  placeholder,
  rectangularSelection,
} from "@codemirror/view";
import {
  forceLinting,
  linter,
  type Diagnostic as CodeMirrorDiagnostic,
  type LintSource,
} from "@codemirror/lint";

import type { BlockCheckResult } from "../contracts/worker-rpc";
import { checkBlockSource } from "./blockCheck";
import { blockCompletionSource } from "./completion";
import { juliaSupport } from "./juliaSupport";
import {
  mapDiagnostics,
  offsetAt,
  toCodeMirrorDiagnostic,
  type MappedDiagnostic,
} from "./lintMapping";
import "./code.css";

export interface CodeEditorProps {
  /** Changes whenever a different source is opened; recreates the view. */
  targetKey: string;
  source: string;
  readOnly: boolean;
  /** `block.check` ref: `inline:<nodeId>` or a catalog block ref. */
  checkRef: string;
  line: number;
  col: number;
  onChange?: (source: string) => void;
  onCheck?: (source: string, result: BlockCheckResult) => void;
  onDiagnostics?: (diagnostics: MappedDiagnostic[], error: string | null) => void;
  onUndo?: () => void;
  onRedo?: () => void;
  onFocus?: () => void;
  onBlur?: () => void;
}

function renderLintMessage(view: EditorView, entry: MappedDiagnostic): Node {
  const root = document.createElement("div");
  root.className = "code-lint";

  const head = document.createElement("div");
  head.className = "code-lint__head";
  const code = document.createElement("span");
  code.className = "code-lint__code";
  code.textContent = entry.code;
  head.append(code);
  const text = document.createElement("span");
  text.className = "code-lint__message";
  text.textContent = entry.detail;
  head.append(text);
  root.append(head);

  if (entry.hint !== null) {
    const hint = document.createElement("p");
    hint.className = "code-lint__hint";
    hint.textContent = entry.hint;
    root.append(hint);
  }
  if (entry.scope !== null) {
    const scope = document.createElement("p");
    scope.className = "code-lint__scope";
    scope.textContent = entry.scope;
    root.append(scope);
  }
  // The view is used for the action's current-position callback; keeping it in
  // the closure documents that the message belongs to this editor.
  void view;
  return root;
}

/** The D1 quick fix: the E001 range is the `=` that must become `~`. */
function quickFixActions(
  view: EditorView,
  entry: MappedDiagnostic,
): CodeMirrorDiagnostic["actions"] {
  if (entry.code !== "E001") {
    return undefined;
  }
  const span = { from: entry.from, to: Math.max(entry.to, entry.from + 1) };
  if (!view.state.sliceDoc(span.from, span.to).includes("=")) {
    return undefined;
  }
  return [
    {
      name: "Use ~ for equations",
      apply: (target, from, to) => {
        const text = target.state.sliceDoc(from, Math.max(to, from + 1));
        const index = text.indexOf("=");
        if (index < 0) {
          return;
        }
        target.dispatch({
          changes: { from: from + index, to: from + index + 1, insert: "~" },
        });
      },
    },
  ];
}

export function CodeEditor({
  targetKey,
  source,
  readOnly,
  checkRef,
  line,
  col,
  onChange,
  onCheck,
  onDiagnostics,
  onUndo,
  onRedo,
  onFocus,
  onBlur,
}: CodeEditorProps) {
  const hostRef = useRef<HTMLDivElement | null>(null);
  const viewRef = useRef<EditorView | null>(null);
  const callbacks = useRef({ onChange, onCheck, onDiagnostics, onUndo, onRedo });
  callbacks.current = { onChange, onCheck, onDiagnostics, onUndo, onRedo };

  const jumpKey = `${targetKey}:${line}:${col}`;
  const lastJump = useRef("");

  useEffect(() => {
    const host = hostRef.current;
    if (host === null) {
      return;
    }
    const abort = new AbortController();
    let disposed = false;

    const lintSource: LintSource = async (view) => {
      const text = view.state.doc.toString();
      try {
        const result = await checkBlockSource(text, checkRef, { signal: abort.signal });
        if (disposed || abort.signal.aborted || view.state.doc.toString() !== text) {
          return [];
        }
        callbacks.current.onCheck?.(text, result);
        const mapped = mapDiagnostics(text, result.diagnostics);
        callbacks.current.onDiagnostics?.(mapped, null);
        return mapped.map((entry) =>
          toCodeMirrorDiagnostic(entry, {
            renderMessage: (current) => renderLintMessage(current, entry),
            actions: quickFixActions(view, entry),
          }),
        );
      } catch (error) {
        if (disposed || abort.signal.aborted) {
          return [];
        }
        const message = error instanceof Error ? error.message : String(error);
        callbacks.current.onDiagnostics?.([], message);
        return [];
      }
    };

    const undo = (): boolean => {
      callbacks.current.onUndo?.();
      return true;
    };
    const redo = (): boolean => {
      callbacks.current.onRedo?.();
      return true;
    };

    const state = EditorState.create({
      doc: source,
      selection: EditorSelection.cursor(offsetAt(source, line, col)),
      extensions: [
        lineNumbers(),
        highlightActiveLineGutter(),
        highlightSpecialChars(),
        drawSelection(),
        dropCursor(),
        EditorState.allowMultipleSelections.of(true),
        indentOnInput(),
        rectangularSelection(),
        crosshairCursor(),
        highlightActiveLine(),
        highlightTrailingWhitespace(),
        EditorView.lineWrapping,
        EditorState.readOnly.of(readOnly),
        EditorView.editable.of(!readOnly),
        EditorView.contentAttributes.of({
          spellcheck: "false",
          autocapitalize: "off",
          "aria-label": "Block source",
        }),
        placeholder("Open a block or create an inline code node."),
        autocompletion({
          override: [blockCompletionSource],
          activateOnTyping: true,
          closeOnBlur: true,
        }),
        closeBrackets(),
        keymap.of([
          { key: "Mod-z", run: undo },
          { key: "Mod-Shift-z", run: redo },
          { key: "Mod-y", run: redo },
          ...closeBracketsKeymap,
          ...completionKeymap,
        ]),
        ...juliaSupport,
        linter(lintSource, { delay: 300 }),
        EditorView.updateListener.of((update) => {
          if (update.docChanged) {
            callbacks.current.onChange?.(update.state.doc.toString());
          }
        }),
      ],
    });

    const view = new EditorView({ state, parent: host });
    viewRef.current = view;
    view.focus();
    lastJump.current = `${line}:${col}`;
    view.dispatch({
      effects: EditorView.scrollIntoView(offsetAt(source, line, col), { y: "center" }),
    });
    const timer = setTimeout(() => {
      if (!disposed) {
        forceLinting(view);
      }
    }, 0);

    return () => {
      disposed = true;
      abort.abort();
      clearTimeout(timer);
      view.destroy();
      viewRef.current = null;
    };
    // The editor is recreated only for a different source or a mode change;
    // text edits and caret moves are handled by the effects below.
  }, [targetKey, readOnly]);

  // Write-through from the parent (undo/redo, a catalog refresh, a copy).
  useEffect(() => {
    const view = viewRef.current;
    if (view === null) {
      return;
    }
    const current = view.state.doc.toString();
    if (current === source) {
      return;
    }
    const anchor = Math.min(view.state.selection.main.anchor, source.length);
    view.dispatch({
      changes: { from: 0, to: current.length, insert: source },
      selection: { anchor },
    });
  }, [source]);

  // Jump when a diagnostic or "open source" gives a line and column.
  useEffect(() => {
    const view = viewRef.current;
    if (view === null || lastJump.current === jumpKey) {
      return;
    }
    lastJump.current = jumpKey;
    const position = offsetAt(view.state.doc.toString(), line, col);
    view.dispatch({
      selection: { anchor: position },
      effects: EditorView.scrollIntoView(position, { y: "center" }),
    });
    view.focus();
  }, [jumpKey, line, col]);

  return (
    <div
      className="code-editor"
      data-testid="code-editor"
      data-read-only={readOnly ? "true" : "false"}
      ref={hostRef}
      onFocus={onFocus}
      onBlur={onBlur}
    />
  );
}
