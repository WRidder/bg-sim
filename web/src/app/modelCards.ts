/**
 * Presentation helpers of the model picker cards (ModelCardGrid.tsx): the short
 * description and the miniature diagram layout.
 */

import type { ModelPreview } from "../state/modelApi";

/** The longest description a card shows (characters, before the ellipsis). */
export const SHORT_DESCRIPTION_LIMIT = 180;

/** A work-package or plan reference such as `Plan 9.1`, `X2.5`, `DEC-M5-3`, `J-EX9`, `X-MB1`. */
const REFERENCE = String.raw`\bplan\s+\d|\bX\d+(?:\.\d+)?\b|\bX-MB\d+|\bDEC-[A-Z0-9-]+|\bJ-EX\d+`;
const PLAN_REFERENCE = new RegExp(REFERENCE, "i");
/** A parenthesis that holds a plan reference: "(plan 9.1)", "(plan 9.1, milestone M1)", "(X2.5)". */
const PLAN_PARENTHESIS = new RegExp(String.raw`\s*\((?=[^()]*(?:${REFERENCE}))[^()]*\)`, "gi");
/** A tag that opens a comment: everything before the first ": " or ". " within the first 70 characters. */
const LEADING_TAG = /^(.{1,70}?)(?::|\.)\s+/;

/** Drop the plan bookkeeping a model comment often carries; it means nothing to a reader. */
export function withoutPlanReferences(text: string): string {
  let result = text.replace(/\s+/g, " ").trim().replace(PLAN_PARENTHESIS, "");
  const tag = LEADING_TAG.exec(result);
  if (tag !== null && PLAN_REFERENCE.test(tag[1] ?? "")) {
    result = result.slice(tag[0].length);
  }
  result = result.trim();
  return result.length > 0 ? result.charAt(0).toUpperCase() + result.slice(1) : result;
}

function cutAtWord(text: string, limit: number): string {
  if (text.length <= limit) {
    return text;
  }
  const head = text.slice(0, limit);
  const space = head.lastIndexOf(" ");
  return `${(space > limit / 2 ? head.slice(0, space) : head).replace(/[\s,;:.(–-]+$/, "")}…`;
}

/**
 * A card's description: plan references removed, then whole sentences up to
 * `limit` characters (always the first one, cut at a word with an ellipsis when
 * it alone is too long). A trailing fragment that introduces a list ("The chain
 * is:") is left out. Null when nothing readable remains.
 */
export function shortDescription(
  text: string | null | undefined,
  limit = SHORT_DESCRIPTION_LIMIT,
): string | null {
  if (text === null || text === undefined) {
    return null;
  }
  const clean = withoutPlanReferences(text);
  if (clean.length === 0) {
    return null;
  }
  const sentences = clean.split(/(?<=[.!?])\s+(?=[A-Z0-9“"(])/);
  // A trailing fragment that leads into a formula or list ("The chain is") reads as cut off.
  if (sentences.length > 1 && !/[.!?…"”')]$/.test(sentences[sentences.length - 1] ?? "")) {
    sentences.pop();
  }
  let result = "";
  for (const sentence of sentences) {
    const next = result.length === 0 ? sentence : `${result} ${sentence}`;
    if (result.length > 0 && (next.length > limit || /:$/.test(sentence) || /…$/.test(sentence))) {
      break;
    }
    result = next;
    if (result.length >= limit) {
      break;
    }
  }
  result = result.replace(/:$/, "…");
  return cutAtWord(result, limit);
}

export interface PreviewLayout {
  /** The SVG view box: `minX minY width height`. */
  viewBox: string;
  /** The node marker size in view-box units. */
  size: number;
}

/** The view box that fits every node of the miniature with a margin; null for an empty diagram. */
export function previewLayout(preview: ModelPreview): PreviewLayout | null {
  if (preview.nodes.length === 0) {
    return null;
  }
  let minX = Infinity;
  let minY = Infinity;
  let maxX = -Infinity;
  let maxY = -Infinity;
  for (const [x, y] of preview.nodes) {
    minX = Math.min(minX, x);
    minY = Math.min(minY, y);
    maxX = Math.max(maxX, x);
    maxY = Math.max(maxY, y);
  }
  // Keep the card's 8:5 aspect and a margin of one node size around the blocks.
  const spanX = Math.max(maxX - minX, 1);
  const spanY = Math.max(maxY - minY, 1);
  const size = Math.max(Math.min(Math.max(spanX, spanY) / 14, 60), 18);
  let width = spanX + 4 * size;
  let height = spanY + 4 * size;
  if (width / height > 8 / 5) {
    height = (width * 5) / 8;
  } else {
    width = (height * 8) / 5;
  }
  const cx = (minX + maxX) / 2;
  const cy = (minY + maxY) / 2;
  const round = (value: number): number => Math.round(value * 10) / 10;
  return {
    viewBox: `${round(cx - width / 2)} ${round(cy - height / 2)} ${round(width)} ${round(height)}`,
    size: round(size),
  };
}

/** "3 Nov 2026" style date of a model file, or "" when unknown. */
export function modifiedDate(value: string | null): string {
  if (value === null) {
    return "";
  }
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? "" : date.toLocaleDateString();
}
