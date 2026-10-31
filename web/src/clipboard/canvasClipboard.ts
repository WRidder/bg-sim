/**
 * Copy, cut and paste on the diagram canvas through the browser's clipboard events.
 *
 * Ctrl+C / Ctrl+X / Ctrl+V only arm the events (no preventDefault, which would cancel
 * them); the `copy`/`cut` handler writes the envelope to `clipboardData` (`text/plain`
 * JSON plus a custom type) and the `paste` handler reads it, so no permission prompt
 * is needed and the copy reaches other windows and projects. The document store keeps
 * the last envelope as well: a browser that fires no paste event within
 * {@link PASTE_EVENT_WAIT_MS} gets the in-window copy.
 *
 * Text fields, CodeMirror and the docs are untouched: events whose target is editable
 * are left alone, and a copy while text outside the canvas is selected copies the text.
 * Ctrl+V on a selected subsystem with an image on the clipboard still sets its image.
 */

import type { ClipboardEnvelope, ClipboardSource } from "../contracts/clipboard";
import type { ModelPoint } from "../contracts/model";
import { useDocumentStore } from "../state/documentStore";
import {
  CLIPBOARD_MIME,
  isEmptyEnvelope,
  MAX_CLIPBOARD_CHARS,
  readEnvelopeText,
  serializeEnvelope,
} from "./envelope";
import { copyForClipboard, pasteEnvelope, pasteEnvelopeValue } from "./pasteFlow";
import { usePasteUiStore } from "./pasteUi";

/**
 * How long Ctrl+V waits for the browser's `paste` event before it falls back to the
 * in-window clipboard (a browser that fires no paste event outside text fields).
 */
export const PASTE_EVENT_WAIT_MS = 300;
/** How long an envelope armed by Ctrl+C/X waits for its copy/cut event. */
const ARMED_MS = 1000;

export function editableTarget(target: EventTarget | null): boolean {
  if (!(target instanceof HTMLElement)) {
    return false;
  }
  const tag = target.tagName;
  return tag === "INPUT" || tag === "TEXTAREA" || tag === "SELECT" || target.isContentEditable;
}

/** Inside the inspector's image paste area, which handles Ctrl+V itself. */
export function imagePasteTarget(target: EventTarget | null): boolean {
  return target instanceof Element && target.closest("[data-node-image-paste]") !== null;
}

/** The source of a parsed (not yet validated) envelope, for the paste position. */
export function sourceOf(value: unknown): ClipboardSource | null {
  if (typeof value !== "object" || value === null) {
    return null;
  }
  const source = (value as { source?: unknown }).source;
  if (typeof source !== "object" || source === null) {
    return null;
  }
  const record = source as Record<string, unknown>;
  const text = (entry: unknown): string | null => (typeof entry === "string" ? entry : null);
  return {
    project: text(record.project),
    model: text(record.model),
    path: Array.isArray(record.path) ? record.path.filter((id): id is string => typeof id === "string") : [],
  };
}

/** Write an envelope to a copy/cut event's clipboard data; false when it is too large. */
export function writeEnvelope(data: DataTransfer, envelope: ClipboardEnvelope): boolean {
  const text = serializeEnvelope(envelope);
  if (text.length > MAX_CLIPBOARD_CHARS) {
    return false;
  }
  data.setData("text/plain", text);
  try {
    data.setData(CLIPBOARD_MIME, text);
  } catch {
    // A browser that refuses custom types still has text/plain.
  }
  return true;
}

function tooLarge(): void {
  usePasteUiStore.getState().showNotice({
    tone: "error",
    title: "Copied for this window only",
    lines: [
      `The selection is larger than ${MAX_CLIPBOARD_CHARS / (1024 * 1024)} MB (subsystem images count), so it was not put on the system clipboard. Ctrl+V in this window still pastes it.`,
    ],
  });
}

export interface CanvasClipboardOptions {
  /** The canvas element; a text selection outside it keeps the browser's text copy. */
  canvas: () => HTMLElement | null;
  /** The flow position a paste of `source` goes to (null: the copied layout plus the offset). */
  anchor: (source: ClipboardSource | null) => ModelPoint | null;
  /** Delete the selection (Ctrl+X), with the port-delete confirmation where needed. */
  deleteSelection: () => void;
  /** The only selected element when it is a subsystem node, else null. */
  soleSubsystem: () => string | null;
  /** The image a paste event carries, or null; applying it sets the subsystem image. */
  pasteImage: (nodeId: string, data: DataTransfer | null) => boolean;
}

export interface CanvasClipboard {
  /** Handle Ctrl+C/X/V of the canvas keydown; true when the key was one of them. */
  keydown: (key: string) => boolean;
  /** Paste through the async clipboard (the context menu), falling back to the in-window copy. */
  pasteFromMenu: (at: ModelPoint) => Promise<void>;
  /** Copy the selection through the async clipboard (the context menu). */
  copyFromMenu: () => Promise<void>;
  install: () => () => void;
}

function dialogOpen(): boolean {
  const ui = usePasteUiStore.getState();
  return ui.dialog !== null || ui.busy;
}

/** Paste the in-window copy (no validation needed: this editor made it). */
function pasteWindowCopy(at: ModelPoint | null): void {
  const clip = useDocumentStore.getState().clipboard;
  if (!isEmptyEnvelope(clip)) {
    void pasteEnvelope(clip, { at });
  }
}

export function createCanvasClipboard(options: CanvasClipboardOptions): CanvasClipboard {
  let pendingPaste: number | null = null;
  let armed: { envelope: ClipboardEnvelope; cut: boolean; time: number } | null = null;
  let lastPointerInCanvas = true;

  /** Text selected outside the canvas (after the last click there) is copied as text. */
  const textSelectedElsewhere = (): boolean => {
    const selection = window.getSelection();
    if (selection === null || selection.isCollapsed || selection.toString().length === 0) {
      return false;
    }
    const canvas = options.canvas();
    const anchor = selection.anchorNode;
    if (canvas !== null && anchor !== null && canvas.contains(anchor)) {
      return false;
    }
    return !lastPointerInCanvas;
  };

  const onPointerDown = (event: PointerEvent): void => {
    const canvas = options.canvas();
    lastPointerInCanvas = canvas !== null && event.target instanceof Node && canvas.contains(event.target);
  };

  const onCopyOrCut = (event: ClipboardEvent): void => {
    const cut = event.type === "cut";
    // The envelope Ctrl+C/X armed belongs to this event only when it follows the key at once.
    if (armed !== null && performance.now() - armed.time > ARMED_MS) {
      armed = null;
    }
    if (editableTarget(event.target) || dialogOpen() || (armed === null && textSelectedElsewhere())) {
      armed = null;
      return;
    }
    let envelope = armed?.envelope ?? null;
    const deleted = armed?.cut ?? false;
    armed = null;
    if (envelope === null) {
      envelope = copyForClipboard();
    }
    if (envelope === null || event.clipboardData === null) {
      return;
    }
    event.preventDefault();
    if (!writeEnvelope(event.clipboardData, envelope)) {
      tooLarge();
    }
    if (cut && !deleted) {
      options.deleteSelection();
    }
  };

  const onPaste = (event: ClipboardEvent): void => {
    if (editableTarget(event.target) || imagePasteTarget(event.target) || dialogOpen()) {
      return;
    }
    if (pendingPaste !== null) {
      window.clearTimeout(pendingPaste);
      pendingPaste = null;
    }
    const data = event.clipboardData;
    const subsystem = options.soleSubsystem();
    if (subsystem !== null && options.pasteImage(subsystem, data)) {
      event.preventDefault();
      return;
    }
    const text = data?.getData(CLIPBOARD_MIME) || data?.getData("text/plain") || null;
    const read = readEnvelopeText(text);
    if (read.kind === "envelope") {
      event.preventDefault();
      void pasteEnvelopeValue(read.value, { at: options.anchor(sourceOf(read.value)) });
      return;
    }
    if (read.kind === "invalid") {
      event.preventDefault();
      usePasteUiStore.getState().showNotice({ tone: "error", title: "Nothing was pasted", lines: [read.message] });
      return;
    }
    // Not bg-sim elements: the in-window copy, as before the system clipboard was used.
    const clip = useDocumentStore.getState().clipboard;
    if (!isEmptyEnvelope(clip)) {
      event.preventDefault();
      pasteWindowCopy(options.anchor(clip.source));
    }
  };

  const keydown = (key: string): boolean => {
    if (key !== "c" && key !== "x" && key !== "v") {
      return false;
    }
    if (dialogOpen()) {
      return true;
    }
    const store = useDocumentStore.getState();
    if (key === "c" || key === "x") {
      if (store.selection.nodes.length === 0 || textSelectedElsewhere()) {
        armed = null;
        return true;
      }
      // No preventDefault: the copy/cut event writes the system clipboard.
      const envelope = copyForClipboard();
      armed = envelope === null ? null : { envelope, cut: key === "x", time: performance.now() };
      if (envelope !== null && key === "x") {
        options.deleteSelection();
      }
      return true;
    }
    // Ctrl+V: wait for the paste event; without one, paste the in-window copy.
    if (pendingPaste !== null) {
      window.clearTimeout(pendingPaste);
    }
    pendingPaste = window.setTimeout(() => {
      pendingPaste = null;
      pasteWindowCopy(options.anchor(useDocumentStore.getState().clipboard.source));
    }, PASTE_EVENT_WAIT_MS);
    return true;
  };

  const pasteFromMenu = async (at: ModelPoint): Promise<void> => {
    let text: string | null;
    try {
      text = await navigator.clipboard.readText();
    } catch {
      text = null; // No permission or no async clipboard: the in-window copy.
    }
    const read = readEnvelopeText(text);
    if (read.kind === "envelope") {
      await pasteEnvelopeValue(read.value, { at });
    } else if (read.kind === "invalid") {
      usePasteUiStore.getState().showNotice({ tone: "error", title: "Nothing was pasted", lines: [read.message] });
    } else {
      pasteWindowCopy(at);
    }
  };

  const copyFromMenu = async (): Promise<void> => {
    const envelope = copyForClipboard();
    if (envelope === null) {
      return;
    }
    const text = serializeEnvelope(envelope);
    if (text.length > MAX_CLIPBOARD_CHARS) {
      tooLarge();
      return;
    }
    try {
      await navigator.clipboard.writeText(text);
    } catch {
      // The in-window copy still works for Ctrl+V and Paste in this window.
    }
  };

  const install = (): (() => void) => {
    window.addEventListener("copy", onCopyOrCut);
    window.addEventListener("cut", onCopyOrCut);
    window.addEventListener("paste", onPaste);
    window.addEventListener("pointerdown", onPointerDown, true);
    return () => {
      window.removeEventListener("copy", onCopyOrCut);
      window.removeEventListener("cut", onCopyOrCut);
      window.removeEventListener("paste", onPaste);
      window.removeEventListener("pointerdown", onPointerDown, true);
      if (pendingPaste !== null) {
        window.clearTimeout(pendingPaste);
        pendingPaste = null;
      }
    };
  };

  return { keydown, pasteFromMenu, copyFromMenu, install };
}
