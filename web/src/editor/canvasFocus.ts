/**
 * Ask the diagram canvas to centre a node, for example after a docs `block:`
 * link selected it. The Diagram tab mounts its canvas only while it is open,
 * so the request is kept until a canvas that shows the node takes it.
 */

export const CENTER_NODE_EVENT = "bgsim:center-node";

let pending: string | null = null;

/** Centre the node with this id on the canvas (now, or when the canvas next shows it). */
export function requestCenterNode(nodeId: string): void {
  pending = nodeId;
  if (typeof window !== "undefined") {
    window.dispatchEvent(new Event(CENTER_NODE_EVENT));
  }
}

/** The node waiting to be centred, if any. */
export function pendingCenterNode(): string | null {
  return pending;
}

/** Drop the request once it is served (only if it is still the one served). */
export function clearCenterNode(nodeId: string): void {
  if (pending === nodeId) {
    pending = null;
  }
}
