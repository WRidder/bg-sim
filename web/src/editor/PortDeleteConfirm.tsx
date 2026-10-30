/**
 * Deleting exposed subsystem ports from inside the subsystem.
 *
 * A port with outside connections asks first, with the editor's in-app
 * dialog (never `window.confirm`): deleting it removes those connections from
 * the parent diagram in the same undo step. The canvas (Delete on a selected
 * terminal) and the inspector ("Delete port") share this request.
 */

import { useCallback, useRef } from "react";
import { create } from "zustand";

import { useDialogFocus } from "../app/useDialogFocus";
import { subsystemPortDeleteImpact, useDocumentStore } from "../state/documentStore";
import { terminalPortName } from "./subsystemBoundary";
import { endpointLabel, exposedOneLevelUp, subsystemAtPath } from "./subsystemPorts";

export interface PortDeleteRequest {
  names: string[];
  /** `Plant.u ← Step1.y` style lines for the outside connections that go too. */
  connections: string[];
  /** `selection`: Delete on the canvas (the rest of the selection goes too); `ports`: just these ports. */
  action: "selection" | "ports";
}

interface PortDeleteState {
  request: PortDeleteRequest | null;
  open: (request: PortDeleteRequest) => void;
  close: () => void;
}

export const usePortDeleteStore = create<PortDeleteState>()((set) => ({
  request: null,
  open: (request) => set({ request }),
  close: () => set({ request: null }),
}));

function run(action: PortDeleteRequest["action"], names: readonly string[]): string | null {
  const store = useDocumentStore.getState();
  if (action === "selection") {
    store.deleteSelection();
    return null;
  }
  const result = store.deleteSubsystemPorts(names);
  return result.ok ? null : (result.error ?? "The port was not deleted.");
}

/**
 * Delete exposed ports `names` of the open subsystem, or the whole selection
 * (`action: "selection"`, where `names` are the selected terminals). Returns
 * a refusal message, or null when the ports went or a confirmation opened.
 */
export function requestSubsystemPortDelete(
  names: readonly string[],
  action: PortDeleteRequest["action"],
): string | null {
  const state = useDocumentStore.getState();
  const doc = state.doc;
  if (doc === null) {
    return null;
  }
  const path = state.activePath;
  for (const name of names) {
    const up = exposedOneLevelUp(doc, path, name);
    if (up !== null) {
      return `${name} is exposed again by ${up.owner} as ${up.port.name}; delete that port first.`;
    }
  }
  const impact = subsystemPortDeleteImpact(doc, path, names);
  if (impact.length === 0) {
    return run(action, names);
  }
  const parent = subsystemAtPath(doc, path)?.parent;
  const nodes = parent?.nodes ?? [];
  usePortDeleteStore.getState().open({
    names: [...names],
    connections: impact.map(
      (connection) =>
        `${endpointLabel(nodes, connection.from.node, connection.from.port)} → ${endpointLabel(nodes, connection.to.node, connection.to.port)}`,
    ),
    action,
  });
  return null;
}

/** The selected terminals' port names. */
export function selectedTerminalPorts(): string[] {
  return useDocumentStore
    .getState()
    .selection.nodes.map(terminalPortName)
    .filter((name): name is string => name !== null);
}

export function PortDeleteConfirm({ onRefused }: { onRefused?: (message: string) => void }) {
  const request = usePortDeleteStore((state) => state.request);
  const close = usePortDeleteStore((state) => state.close);
  const dialog = useRef<HTMLDivElement>(null);
  const cancel = useCallback(() => close(), [close]);
  useDialogFocus(request !== null, dialog, cancel);
  if (request === null) {
    return null;
  }
  const plural = request.names.length > 1;
  const count = request.connections.length;
  return (
    <div className="dialog-backdrop" data-testid="port-delete-backdrop">
      <div
        className="docs-dialog port-delete-dialog"
        role="dialog"
        aria-modal="true"
        aria-labelledby="port-delete-title"
        data-testid="port-delete-dialog"
        ref={dialog}
        tabIndex={-1}
      >
        <h2 id="port-delete-title" className="docs-dialog__title">
          Delete subsystem {plural ? "ports" : "port"} {request.names.join(", ")}?
        </h2>
        <p className="docs-dialog__text">
          {plural ? "These ports are" : "This port is"} connected outside the subsystem. Deleting{" "}
          {plural ? "them" : "it"} also removes {count === 1 ? "this connection" : `these ${count} connections`}{" "}
          from the parent diagram (Ctrl+Z restores everything):
        </p>
        <ul className="port-delete-dialog__list">
          {request.connections.map((line) => (
            <li key={line}>
              <code>{line}</code>
            </li>
          ))}
        </ul>
        <div className="docs-dialog__actions">
          <button type="button" className="button" data-testid="port-delete-cancel" onClick={cancel}>
            Cancel
          </button>
          <button
            type="button"
            className="button button--primary"
            data-testid="port-delete-confirm"
            onClick={() => {
              close();
              const refusal = run(request.action, request.names);
              if (refusal !== null) {
                onRefused?.(refusal);
              }
            }}
          >
            Delete {plural ? "ports" : "port"} and {count === 1 ? "connection" : "connections"}
          </button>
        </div>
      </div>
    </div>
  );
}
