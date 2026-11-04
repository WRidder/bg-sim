/**
 * What the user has selected for the assistant to see. The Code and Docs tabs publish text here;
 * the diagram's selection is read from the document store (`diagramSelection`). A pick is sticky:
 * clicking into the chat box must not lose it, so it goes when the user clears it where it was
 * made, removes its chip or sends it. A chip that was removed or sent stays away until the
 * selection changes.
 */

import { create } from "zustand";

import type {
  AssistantSelectionCode,
  AssistantSelectionDiagram,
  AssistantSelectionDoc,
  AssistantSelectionItem,
} from "../contracts/assistant";
import type { Model, ModelDiagram, ModelEndpoint } from "../contracts/model";
import { activeDiagram } from "../editor/subsystemPath";

export const MAX_SELECTED_TEXT = 20000;
const MAX_SELECTED_ELEMENTS = 200;

/** The attributes of a docs page's rendered text, read by `trackDocSelection`. */
export const DOC_PAGE_ATTRIBUTE = "data-assistant-doc-page";
export const DOC_MODEL_ATTRIBUTE = "data-assistant-doc-model";

export function selectionKey(item: AssistantSelectionItem): string {
  return `${item.kind}:${JSON.stringify(item)}`;
}

export interface AssistantSelectionState {
  code: AssistantSelectionCode | null;
  doc: AssistantSelectionDoc | null;
  /** Keys of the chips removed or sent. */
  dismissed: ReadonlySet<string>;
  setCode: (code: AssistantSelectionCode | null) => void;
  setDoc: (doc: AssistantSelectionDoc | null) => void;
  dismiss: (keys: readonly string[]) => void;
  /** Forget the removed chips of one kind: its selection is gone. */
  forget: (kind: AssistantSelectionItem["kind"]) => void;
}

function without(keys: ReadonlySet<string>, kind: AssistantSelectionItem["kind"]): ReadonlySet<string> {
  return new Set([...keys].filter((key) => !key.startsWith(`${kind}:`)));
}

export const useAssistantSelectionStore = create<AssistantSelectionState>()((set) => ({
  code: null,
  doc: null,
  dismissed: new Set(),
  setCode: (code) =>
    set((state) => ({ code, dismissed: code === null ? without(state.dismissed, "code") : state.dismissed })),
  setDoc: (doc) =>
    set((state) => ({ doc, dismissed: doc === null ? without(state.dismissed, "doc") : state.dismissed })),
  dismiss: (keys) => set((state) => ({ dismissed: new Set([...state.dismissed, ...keys]) })),
  forget: (kind) => set((state) => ({ dismissed: without(state.dismissed, kind) })),
}));

/** The Code tab's selection; an empty one clears the pick. */
export function publishCodeSelection(source: string, text: string, fromLine: number, toLine: number): void {
  const trimmed = text.slice(0, MAX_SELECTED_TEXT);
  useAssistantSelectionStore
    .getState()
    .setCode(trimmed.trim() === "" ? null : { kind: "code", source, text: trimmed, fromLine, toLine });
}

/**
 * Follow text selections inside docs pages. A selection anywhere else (the chat box) leaves the
 * pick alone; one collapsed inside a page clears it. Returns the function that stops listening.
 */
export function trackDocSelection(root: Document = document): () => void {
  const onChange = (): void => {
    const selection = root.getSelection();
    const anchor = selection?.anchorNode ?? null;
    const element = anchor instanceof Element ? anchor : (anchor?.parentElement ?? null);
    const host = element?.closest<HTMLElement>(`[${DOC_PAGE_ATTRIBUTE}]`) ?? null;
    if (host === null) {
      return;
    }
    const text = (selection?.toString() ?? "").trim().slice(0, MAX_SELECTED_TEXT);
    const store = useAssistantSelectionStore.getState();
    store.setDoc(
      text === ""
        ? null
        : {
            kind: "doc",
            model: host.getAttribute(DOC_MODEL_ATTRIBUTE),
            page: host.getAttribute(DOC_PAGE_ATTRIBUTE) ?? "",
            text,
          },
    );
  };
  root.addEventListener("selectionchange", onChange);
  return () => root.removeEventListener("selectionchange", onChange);
}

function endpointName(diagram: ModelDiagram, end: ModelEndpoint): string {
  const node = diagram.nodes.find((entry) => entry.id === end.node);
  return `${node?.name ?? end.node}${end.port === undefined ? "" : `.${end.port}`}`;
}

/** The canvas selection by name, as the assistant knows the model; null when nothing is selected. */
export function diagramSelection(
  doc: Model | null,
  modelName: string | null,
  path: readonly string[],
  selection: { nodes: readonly string[]; connections: readonly string[] },
): AssistantSelectionDiagram | null {
  if (doc === null || modelName === null || selection.nodes.length + selection.connections.length === 0) {
    return null;
  }
  const diagram = activeDiagram(doc, path);
  if (diagram === null) {
    return null;
  }
  const names: string[] = [];
  let level = doc.diagram;
  for (const id of path) {
    const node = level.nodes.find((entry) => entry.id === id);
    if (node === undefined || !("subsystem" in node.block)) {
      break;
    }
    names.push(node.name);
    level = node.block.subsystem.diagram;
  }
  const nodes = selection.nodes.flatMap((id) => diagram.nodes.find((node) => node.id === id)?.name ?? []);
  const connections = selection.connections.flatMap((id) => {
    const connection = diagram.connections.find((entry) => entry.id === id);
    return connection === undefined
      ? []
      : `${endpointName(diagram, connection.from)} -> ${endpointName(diagram, connection.to)}`;
  });
  if (nodes.length + connections.length === 0) {
    return null;
  }
  return {
    kind: "diagram",
    model: modelName,
    path: names,
    nodes: nodes.slice(0, MAX_SELECTED_ELEMENTS),
    connections: connections.slice(0, MAX_SELECTED_ELEMENTS),
  };
}

/** A chip's short label. */
export function selectionLabel(item: AssistantSelectionItem): string {
  if (item.kind === "diagram") {
    const parts = [
      ...item.nodes,
      ...(item.connections.length > 0
        ? [`${item.connections.length} connection${item.connections.length === 1 ? "" : "s"}`]
        : []),
    ];
    return parts.length > 3 ? `${parts.slice(0, 3).join(", ")} +${parts.length - 3}` : parts.join(", ");
  }
  if (item.kind === "code") {
    const lines = item.fromLine === item.toLine ? `line ${item.fromLine}` : `lines ${item.fromLine}-${item.toLine}`;
    return `${item.source.replace(/^.*[:/]/, "")}, ${lines}`;
  }
  return `${item.page}: "${item.text.length > 32 ? `${item.text.slice(0, 32)}…` : item.text}"`;
}
