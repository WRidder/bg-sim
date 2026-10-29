/**
 * Julia support for the Code tab (plan 7.7): the CodeMirror 6 legacy Julia
 * mode, the default syntax highlighting, and one extra highlighter for the
 * declaration macros and the `~` equation operator. The macros are the only
 * words in a block source that are language structure rather than Julia, so
 * they get their own colour in the line, independent of the tooltip/lint
 * decoration.
 */

import { HighlightStyle, StreamLanguage, syntaxHighlighting } from "@codemirror/language";
import { julia } from "@codemirror/legacy-modes/mode/julia";
import {
  Decoration,
  EditorView,
  MatchDecorator,
  ViewPlugin,
  type DecorationSet,
  type ViewUpdate,
} from "@codemirror/view";

import { tags } from "@lezer/highlight";

import { SCOPE_MACROS } from "./completion";

/**
 * Syntax colours from the `--code-*` tokens, so the editor follows the theme
 * with no rebuild (the default highlight style is light-only and fails contrast
 * on the dark surface).
 */
export const codeHighlightStyle = HighlightStyle.define([
  { tag: [tags.keyword, tags.controlKeyword, tags.definitionKeyword, tags.moduleKeyword], color: "var(--code-keyword)" },
  { tag: [tags.string, tags.special(tags.string), tags.character], color: "var(--code-string)" },
  { tag: [tags.number, tags.bool, tags.atom, tags.null], color: "var(--code-number)" },
  { tag: [tags.comment, tags.lineComment, tags.blockComment], color: "var(--code-comment)", fontStyle: "italic" },
  { tag: [tags.definition(tags.variableName), tags.function(tags.variableName), tags.macroName], color: "var(--code-definition)" },
  { tag: [tags.typeName, tags.className, tags.namespace], color: "var(--code-type)" },
  { tag: [tags.operator, tags.punctuation, tags.bracket], color: "var(--color-text-muted)" },
  { tag: tags.invalid, color: "var(--color-error-text)" },
]);

export const juliaLanguage = StreamLanguage.define(julia);

const macroNames = SCOPE_MACROS.map((macro) => macro.slice(1)).join("|");
const macroDecoration = Decoration.mark({ class: "cm-bgsim-scope" });
const tildeDecoration = Decoration.mark({ class: "cm-bgsim-tilde" });

const languageMatcher = new MatchDecorator({
  regexp: new RegExp(`@(?:${macroNames})\\b|~`, "g"),
  decorate: (add, from, to, match) => {
    add(from, to, match[0] === "~" ? tildeDecoration : macroDecoration);
  },
});

/** Decorate the visible declaration macros and `~`; updates are incremental. */
export const scopeHighlighter = ViewPlugin.fromClass(
  class {
    decorations: DecorationSet;

    constructor(view: EditorView) {
      this.decorations = languageMatcher.createDeco(view);
    }

    update(update: ViewUpdate): void {
      this.decorations = languageMatcher.updateDeco(update, this.decorations);
    }
  },
  { decorations: (plugin) => plugin.decorations },
);

/**
 * The editor's palette. Everything is a design token, so light and dark theme
 * switching is a CSS change with no editor rebuild.
 */
export const codeTheme = EditorView.theme({
  "&": {
    height: "100%",
    color: "var(--color-text)",
    backgroundColor: "var(--color-surface)",
    fontSize: "var(--font-size-sm)",
  },
  ".cm-scroller": {
    fontFamily: "var(--font-mono)",
    lineHeight: "1.5",
    overflow: "auto",
  },
  ".cm-content": {
    caretColor: "var(--color-accent)",
    padding: "8px 0",
  },
  ".cm-cursor, .cm-dropCursor": {
    borderLeftColor: "var(--color-accent)",
  },
  "&.cm-focused .cm-selectionBackground, .cm-selectionBackground, .cm-content ::selection": {
    backgroundColor: "color-mix(in srgb, var(--color-accent) 28%, transparent)",
  },
  ".cm-activeLine": {
    backgroundColor: "color-mix(in srgb, var(--color-accent) 6%, transparent)",
  },
  ".cm-gutters": {
    backgroundColor: "var(--color-surface-sunken)",
    color: "var(--color-text-muted)",
    borderRight: "1px solid var(--color-border)",
  },
  ".cm-activeLineGutter": {
    backgroundColor: "color-mix(in srgb, var(--color-accent) 10%, transparent)",
  },
  ".cm-lintRange-error": {
    backgroundImage: "none",
    borderBottom: "2px wavy var(--color-error)",
  },
  ".cm-lintRange-warning": {
    backgroundImage: "none",
    borderBottom: "2px wavy var(--color-warning)",
  },
  ".cm-lintRange-info": {
    backgroundImage: "none",
    borderBottom: "2px dotted var(--color-accent)",
  },
  ".cm-tooltip": {
    color: "var(--color-text)",
    backgroundColor: "var(--color-surface-raised, var(--color-surface))",
    border: "1px solid var(--color-border)",
    borderRadius: "var(--radius-sm, 4px)",
    boxShadow: "var(--shadow-md, 0 4px 12px rgb(0 0 0 / 25%))",
  },
  ".cm-tooltip-autocomplete > ul > li[aria-selected]": {
    backgroundColor: "var(--color-accent)",
    color: "var(--color-on-accent, #fff)",
  },
  ".cm-bgsim-scope": {
    color: "var(--code-scope-macro, var(--color-warning-text))",
    fontWeight: "600",
  },
  ".cm-bgsim-tilde": {
    color: "var(--code-equation-op, var(--color-accent))",
    fontWeight: "700",
  },
});

export const juliaSupport = [
  juliaLanguage,
  syntaxHighlighting(codeHighlightStyle),
  scopeHighlighter,
  codeTheme,
];
