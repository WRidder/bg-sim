/**
 * W2.1 lint mapping (plan 7.7): contract ranges are 1-based with exclusive
 * end columns; CodeMirror needs absolute offsets. The multi-line case and the
 * clamp at end-of-file are the ones a hand-written conversion gets wrong.
 */

import { describe, expect, it } from "vitest";

import type { Diagnostic } from "../src/contracts/diagnostic";
import {
  lineStarts,
  mapDiagnostics,
  offsetAt,
  rangeToSpan,
  severityFor,
  toCodeMirrorDiagnostic,
} from "../src/code/lintMapping";

function diagnostic(overrides: Partial<Diagnostic> = {}): Diagnostic {
  return {
    code: "E001",
    severity: "error",
    message: "`=` is not allowed in @equations",
    hint: "use `~` for equations",
    path: null,
    block: null,
    scope: "@equations",
    source: {
      kind: "inline",
      ref: "inline:n4",
      range: { line: 2, col: 5, endLine: 2, endCol: 6 },
    },
    node: null,
    connection: null,
    ...overrides,
  };
}

describe("line and column mapping", () => {
  it("finds every line start, including the last empty line", () => {
    expect(lineStarts("a\nbb\nccc")).toEqual([0, 2, 5]);
    expect(lineStarts("")).toEqual([0]);
    expect(lineStarts("\n")).toEqual([0, 1]);
  });

  it("maps 1-based columns to string offsets", () => {
    const source = "hello\nworld";
    expect(offsetAt(source, 1, 1)).toBe(0);
    expect(offsetAt(source, 1, 6)).toBe(5);
    expect(offsetAt(source, 2, 1)).toBe(6);
    expect(offsetAt(source, 2, 5)).toBe(10);
  });

  it("clamps lines and columns instead of throwing", () => {
    const source = "ab\ncd";
    expect(offsetAt(source, 9, 1)).toBe(source.length);
    expect(offsetAt(source, 1, 99)).toBe(2);
    expect(offsetAt(source, 0, 0)).toBe(0);
  });

  it("treats endColumn as exclusive", () => {
    const source = "@equations y = u";
    // `=` is the 14th character.
    expect(rangeToSpan(source, { line: 1, col: 14, endLine: 1, endCol: 15 })).toEqual({
      from: 13,
      to: 14,
    });
  });

  it("maps a multi-line range across the newline", () => {
    const source = "a\nbb\nccc\n";
    // Line 2 column 1 through line 3 column 3: "bb\ncc".
    expect(rangeToSpan(source, { line: 2, col: 1, endLine: 3, endCol: 3 })).toEqual({
      from: 2,
      to: 7,
    });
  });

  it("keeps a zero-width EOF range as a caret", () => {
    const source = "@block X begin\nend\n";
    expect(rangeToSpan(source, { line: 3, col: 1, endLine: 3, endCol: 1 })).toEqual({
      from: source.length,
      to: source.length,
    });
  });

  it("orders a reversed range instead of returning to < from", () => {
    const source = "abcdef";
    const span = rangeToSpan(source, { line: 1, col: 5, endLine: 1, endCol: 2 });
    expect(span.from).toBe(4);
    expect(span.to).toBe(4);
  });
});

describe("diagnostic mapping", () => {
  it("keeps the code, message, hint and scope", () => {
    const source = "@block F begin\n    @equations y = u\nend\n";
    const mapped = mapDiagnostics(source, [diagnostic()]);
    expect(mapped).toHaveLength(1);
    expect(mapped[0]?.code).toBe("E001");
    expect(mapped[0]?.message).toBe("E001: `=` is not allowed in @equations");
    expect(mapped[0]?.detail).toBe("`=` is not allowed in @equations");
    expect(mapped[0]?.hint).toBe("use `~` for equations");
    expect(mapped[0]?.scope).toBe("@equations");
    expect(mapped[0]?.severity).toBe("error");
  });

  it("maps all three contract severities", () => {
    expect(severityFor("error")).toBe("error");
    expect(severityFor("warning")).toBe("warning");
    expect(severityFor("info")).toBe("info");
  });

  it("falls back to offset 0 when a diagnostic has no source range", () => {
    const mapped = mapDiagnostics("abc", [
      diagnostic({ source: null, scope: null }),
    ]);
    expect(mapped[0]?.from).toBe(0);
    expect(mapped[0]?.to).toBe(0);
  });

  it("builds the CodeMirror shape with the range and the rich source", () => {
    const source = "one\ntwo = three\n";
    const mapped = mapDiagnostics(source, [
      diagnostic({
        source: {
          kind: "inline",
          ref: "inline:n1",
          range: { line: 2, col: 5, endLine: 2, endCol: 6 },
        },
      }),
    ]);
    const cm = toCodeMirrorDiagnostic(mapped[0]!, { source: "E001" });
    expect(cm).toMatchObject({
      from: 8,
      to: 9,
      severity: "error",
      message: "E001: `=` is not allowed in @equations",
      source: "E001",
    });
  });
});
