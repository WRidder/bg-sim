/**
 * The CodeMirror 6 editor of a docs page (W5.6): Markdown highlighting, Ctrl+S to save, Ctrl+E
 * to switch the mode, and the image pipeline: pasting or dropping an image uploads it to the
 * model's `assets/` and inserts `![](assets/<hash>.<ext>)`; copying text that refers to assets
 * remembers its model, and pasting that text into another model copies the assets over.
 */

import { useEffect, useRef } from "react";

import { markdown } from "@codemirror/lang-markdown";
import { defaultKeymap, history, historyKeymap } from "@codemirror/commands";
import { HighlightStyle, syntaxHighlighting } from "@codemirror/language";
import { EditorState, Prec } from "@codemirror/state";
import {
  EditorView,
  drawSelection,
  dropCursor,
  highlightActiveLine,
  keymap,
  placeholder,
} from "@codemirror/view";
import { tags } from "@lezer/highlight";

import { copyAssets, uploadAsset } from "./docsApi";
import {
  DOCS_CLIP_MIME,
  addImages,
  assetRefs,
  imageFilesOf,
  planPaste,
  recallCopy,
  rememberCopy,
} from "./docsImages";

export interface MarkdownEditorProps {
  /** A different page recreates the editor (and its undo history). */
  pageKey: string;
  value: string;
  project: string;
  model: string;
  /** Asset names that exist already (not uploaded again). */
  knownAssets: ReadonlySet<string>;
  ariaLabel: string;
  onChange: (text: string) => void;
  onSave: () => void;
  onToggleMode: () => void;
  onAssetAdded: (name: string) => void;
  onProblem: (message: string | null) => void;
}

const markdownHighlight = HighlightStyle.define([
  { tag: tags.heading, color: "var(--code-definition)", fontWeight: "600" },
  { tag: [tags.strong], fontWeight: "700" },
  { tag: [tags.emphasis], fontStyle: "italic" },
  { tag: [tags.link, tags.url], color: "var(--code-keyword)" },
  { tag: [tags.monospace], color: "var(--code-string)" },
  { tag: [tags.quote], color: "var(--code-comment)", fontStyle: "italic" },
  { tag: [tags.processingInstruction, tags.contentSeparator], color: "var(--color-text-muted)" },
]);

const editorTheme = EditorView.theme({
  "&": {
    height: "100%",
    color: "var(--color-text)",
    backgroundColor: "var(--color-surface)",
    fontSize: "var(--font-size-md)",
  },
  ".cm-scroller": { fontFamily: "var(--font-mono)", lineHeight: "1.55", overflow: "auto" },
  ".cm-content": { caretColor: "var(--color-text)", padding: "var(--space-3) 0" },
  ".cm-line": { padding: "0 var(--space-3)" },
  "&.cm-focused": { outline: "2px solid var(--color-focus)", outlineOffset: "-2px" },
  ".cm-activeLine": { backgroundColor: "color-mix(in srgb, var(--color-accent) 8%, transparent)" },
  ".cm-selectionBackground, &.cm-focused .cm-selectionBackground": {
    backgroundColor: "color-mix(in srgb, var(--color-accent) 30%, transparent)",
  },
  ".cm-cursor": { borderLeftColor: "var(--color-text)" },
});

export function MarkdownEditor(props: MarkdownEditorProps) {
  const { pageKey, value, ariaLabel } = props;
  const hostRef = useRef<HTMLDivElement | null>(null);
  const viewRef = useRef<EditorView | null>(null);
  const latest = useRef(props);
  latest.current = props;

  useEffect(() => {
    const host = hostRef.current;
    if (host === null) {
      return;
    }

    /** Insert at the main selection, replacing it. */
    const insert = (view: EditorView, text: string, at?: number): void => {
      const range = at === undefined ? view.state.selection.main : { from: at, to: at };
      view.dispatch({
        changes: { from: range.from, to: range.to, insert: text },
        selection: { anchor: range.from + text.length },
        userEvent: "input.paste",
      });
      view.focus();
    };

    const insertImages = async (view: EditorView, files: File[], at?: number): Promise<void> => {
      const { project, model, knownAssets, onAssetAdded, onProblem } = latest.current;
      const result = await addImages(files, {
        upload: (file) => uploadAsset(project, model, file),
        known: knownAssets,
        onUploaded: onAssetAdded,
      });
      for (const name of result.names) {
        onAssetAdded(name);
      }
      onProblem(result.problems.length > 0 ? result.problems.join(" ") : null);
      if (result.markdown !== "") {
        insert(view, result.markdown, at);
      }
    };

    const pasteMarkdown = async (
      view: EditorView,
      text: string,
      from: { project: string; model: string },
      files: string[],
    ): Promise<void> => {
      const { project, model, onAssetAdded, onProblem } = latest.current;
      try {
        const result = await copyAssets(project, model, from, files);
        for (const name of [...result.copied, ...result.existing]) {
          onAssetAdded(name);
        }
        onProblem(
          result.missing.length > 0
            ? `${result.missing.length} image(s) could not be copied because ${from.model} no longer has them: ${result.missing.join(", ")}. Add the images again.`
            : null,
        );
      } catch (error) {
        onProblem(error instanceof Error ? error.message : String(error));
      }
      insert(view, text);
    };

    const handlers = EditorView.domEventHandlers({
      paste(event, view) {
        const data = event.clipboardData;
        if (data === null) {
          return false;
        }
        const { project, model } = latest.current;
        const text = data.getData("text/plain");
        const plan = planPaste({
          files: imageFilesOf(data),
          text,
          custom: data.getData(DOCS_CLIP_MIME) || null,
          remembered: recallCopy(),
          target: { project, model },
        });
        if (plan.kind === "default") {
          return false;
        }
        event.preventDefault();
        if (plan.kind === "images") {
          void insertImages(view, plan.files);
        } else {
          void pasteMarkdown(view, text, plan.from, plan.files);
        }
        return true;
      },
      drop(event, view) {
        const files = imageFilesOf(event.dataTransfer);
        if (files.length === 0) {
          return false;
        }
        event.preventDefault();
        const at = view.posAtCoords({ x: event.clientX, y: event.clientY }) ?? undefined;
        void insertImages(view, files, at);
        return true;
      },
      copy(event, view) {
        remember(event, view);
        return false;
      },
      cut(event, view) {
        remember(event, view);
        return false;
      },
    });

    /** Note where copied Markdown with image references came from. */
    const remember = (event: ClipboardEvent, view: EditorView): void => {
      const range = view.state.selection.main;
      if (range.empty) {
        return;
      }
      const text = view.state.sliceDoc(range.from, range.to);
      if (assetRefs(text).length === 0) {
        return;
      }
      const { project, model } = latest.current;
      const source = { project, model, text };
      rememberCopy(source);
      event.clipboardData?.setData(DOCS_CLIP_MIME, JSON.stringify(source));
    };

    const view = new EditorView({
      parent: host,
      state: EditorState.create({
        doc: latest.current.value,
        extensions: [
          history(),
          drawSelection(),
          dropCursor(),
          highlightActiveLine(),
          EditorView.lineWrapping,
          markdown(),
          syntaxHighlighting(markdownHighlight),
          editorTheme,
          placeholder("Write Markdown. Paste or drop an image to add it."),
          EditorView.contentAttributes.of({ "aria-label": ariaLabel, spellcheck: "true" }),
          Prec.high(
            keymap.of([
              {
                key: "Mod-s",
                preventDefault: true,
                run: () => {
                  latest.current.onSave();
                  return true;
                },
              },
              {
                key: "Mod-e",
                preventDefault: true,
                run: () => {
                  latest.current.onToggleMode();
                  return true;
                },
              },
            ]),
          ),
          keymap.of([...defaultKeymap, ...historyKeymap]),
          handlers,
          EditorView.updateListener.of((update) => {
            if (update.docChanged) {
              latest.current.onChange(update.state.doc.toString());
            }
          }),
        ],
      }),
    });
    viewRef.current = view;
    return () => {
      view.destroy();
      viewRef.current = null;
    };
    // One editor per page; text changes flow through the effect below.
  }, [pageKey, ariaLabel]);

  // Write-through from the store (a reload, a revert) without losing the caret.
  useEffect(() => {
    const view = viewRef.current;
    if (view === null) {
      return;
    }
    const current = view.state.doc.toString();
    if (current !== value) {
      view.dispatch({
        changes: { from: 0, to: current.length, insert: value },
        selection: { anchor: Math.min(view.state.selection.main.anchor, value.length) },
      });
    }
  }, [value]);

  return <div className="docs-editor" data-testid="docs-editor" ref={hostRef} />;
}
