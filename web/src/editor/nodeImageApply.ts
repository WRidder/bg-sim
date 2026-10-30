/**
 * Setting a node image from a file, the Paste button or Ctrl+V, and the status line the
 * inspector shows for it. The canvas (Ctrl+V on a selected subsystem) and the inspector's
 * Image section share this path, so both fit the image the same way and report it in the
 * same place. The document change itself is one `setNodeImage` command: one undo step,
 * and it marks the model dirty like any other edit.
 */

import { create } from "zustand";

import { useDocumentStore } from "../state/documentStore";
import {
  fitNodeImage,
  NodeImageError,
  type FittedImage,
  type ImageInput,
  type NodeImageFit,
  type RasterBackend,
} from "./nodeImage";
import { browserRasterBackend } from "./nodeImageRaster";
import { activeDiagram } from "./subsystemPath";

export interface NodeImageStatus {
  nodeId: string;
  kind: "busy" | "done" | "error";
  message: string;
}

interface NodeImageStatusStore {
  status: NodeImageStatus | null;
  setStatus: (status: NodeImageStatus | null) => void;
}

export const useNodeImageStatus = create<NodeImageStatusStore>()((set) => ({
  status: null,
  setStatus: (status) => set({ status }),
}));

let backend: RasterBackend = browserRasterBackend;

/** Replace the canvas backend (unit tests run in jsdom, which has no canvas). */
export function setNodeImageBackend(next: RasterBackend | null): void {
  backend = next ?? browserRasterBackend;
}

function errorText(error: unknown): string {
  if (error instanceof NodeImageError) {
    return error.message;
  }
  return `The image could not be read: ${error instanceof Error ? error.message : String(error)}`;
}

function doneText(fitted: FittedImage): string {
  return fitted.message ?? "Image set.";
}

/**
 * Fit `load()`'s image into the limit and store it on the node. Resolves to the fitted
 * image, or null when it was refused (the status line says why).
 */
export async function applyNodeImage(
  nodeId: string,
  load: () => Promise<ImageInput>,
  fit?: NodeImageFit,
): Promise<FittedImage | null> {
  const { setStatus } = useNodeImageStatus.getState();
  setStatus({ nodeId, kind: "busy", message: "Reading the image…" });
  try {
    const input = await load();
    const fitted = await fitNodeImage(input, backend);
    const store = useDocumentStore.getState();
    const current = findNode(nodeId);
    const outcome = store.setNodeImage(nodeId, {
      mime: fitted.mime,
      data: fitted.data,
      fit: fit ?? current?.ui?.image?.fit ?? "contain",
    });
    if (!outcome.ok) {
      setStatus({ nodeId, kind: "error", message: outcome.error ?? "The image was refused." });
      return null;
    }
    setStatus({ nodeId, kind: "done", message: doneText(fitted) });
    return fitted;
  } catch (error) {
    setStatus({ nodeId, kind: "error", message: errorText(error) });
    return null;
  }
}

/** Report a problem found before any image was read (no image on the clipboard, ...). */
export function reportNodeImageError(nodeId: string, error: unknown): void {
  useNodeImageStatus.getState().setStatus({ nodeId, kind: "error", message: errorText(error) });
}

function findNode(nodeId: string) {
  const state = useDocumentStore.getState();
  if (state.doc === null) {
    return undefined;
  }
  return activeDiagram(state.doc, state.activePath)?.nodes.find((entry) => entry.id === nodeId);
}
