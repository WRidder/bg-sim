/**
 * Contract -> CodeMirror mapping for block diagnostics (plan 3.4, 7.7).
 *
 * The contract's `SourceRange` is 1-based, and `endLine`/`endCol` are
 * exclusive: `col = 9, endCol = 11` covers the two characters at columns 9 and
 * 10. CodeMirror wants absolute, zero-based offsets, so this module converts a
 * string (the code being linted) into document offsets. Ranges are clamped:
 * a parser that reports a position one line past the end (E000 at EOF) still
 * maps to a selection instead of throwing.
 */

import type { Diagnostic } from "@codemirror/lint";
import type { EditorView } from "@codemirror/view";
import type { Diagnostic as ContractDiagnostic, SourceRange } from "../contracts/diagnostic";

export type LintSeverity = "error" | "warning" | "info";

export interface Span {
  from: number;
  to: number;
}

export interface MappedDiagnostic {
  code: string;
  severity: LintSeverity;
  /** What the editor shows: `E001: ...`. */
  message: string;
  /** The plain contract message, for lists that show the code separately. */
  detail: string;
  hint: string | null;
  scope: string | null;
  from: number;
  to: number;
  contract: ContractDiagnostic;
}

/** The start offset of every line; index 0 is line 1, plus a final EOF entry. */
export function lineStarts(source: string): number[] {
  const starts = [0];
  for (let index = 0; index < source.length; index += 1) {
    if (source.charCodeAt(index) === 10) {
      starts.push(index + 1);
    }
  }
  return starts;
}

function lineEndOffset(source: string, starts: readonly number[], lineIndex: number): number {
  const next = starts[lineIndex + 1];
  if (next === undefined) {
    return source.length;
  }
  // The newline belongs to the preceding line's terminator, not to its text.
  return next - 1;
}

/**
 * The offset of a 1-based line/column. Columns count UTF-16 code units, which
 * is what CodeMirror and JavaScript strings use. Out-of-range values clamp.
 */
export function offsetAt(source: string, line: number, col: number, starts?: number[]): number {
  const lines = starts ?? lineStarts(source);
  const requested = Math.trunc(line);
  if (requested > lines.length) {
    return source.length;
  }
  const index = Math.max(requested, 1) - 1;
  const start = lines[index] ?? 0;
  const end = lineEndOffset(source, lines, index);
  const offset = start + Math.max(0, Math.trunc(col) - 1);
  return Math.min(Math.max(offset, start), end);
}

/** Convert a contract range to a clamped, ordered offset span. */
export function rangeToSpan(source: string, range: SourceRange, starts?: number[]): Span {
  const lines = starts ?? lineStarts(source);
  const from = offsetAt(source, range.line, range.col, lines);
  let to = offsetAt(source, range.endLine, range.endCol, lines);
  if (to < from) {
    to = from;
  }
  return { from, to };
}

export function severityFor(severity: ContractDiagnostic["severity"]): LintSeverity {
  switch (severity) {
    case "error":
      return "error";
    case "warning":
      return "warning";
    default:
      return "info";
  }
}

/**
 * Map a block-check answer to editor spans, preserving order and the contract
 * fields the tooltip and the footer show.
 */
export function mapDiagnostics(
  source: string,
  diagnostics: readonly ContractDiagnostic[],
): MappedDiagnostic[] {
  const starts = lineStarts(source);
  return diagnostics.map((diagnostic) => {
    const range = diagnostic.source?.range ?? null;
    const span: Span = range === null ? { from: 0, to: 0 } : rangeToSpan(source, range, starts);
    return {
      code: diagnostic.code,
      severity: severityFor(diagnostic.severity),
      message: `${diagnostic.code}: ${diagnostic.message}`,
      detail: diagnostic.message,
      hint: diagnostic.hint ?? null,
      scope: diagnostic.scope ?? null,
      from: span.from,
      to: span.to,
      contract: diagnostic,
    };
  });
}

/** The shape `@codemirror/lint` consumes; `renderMessage` is added by the editor. */
export function toCodeMirrorDiagnostic(
  mapped: MappedDiagnostic,
  options: {
    source?: string;
    renderMessage?: (view: EditorView) => Node;
    actions?: Diagnostic["actions"];
  } = {},
): Diagnostic {
  return {
    from: mapped.from,
    to: mapped.to,
    severity: mapped.severity,
    message: mapped.message,
    source: options.source ?? mapped.scope ?? "block.check",
    ...(options.renderMessage === undefined ? {} : { renderMessage: options.renderMessage }),
    ...(options.actions === undefined ? {} : { actions: options.actions }),
  };
}
