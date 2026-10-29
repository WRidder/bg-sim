/**
 * Frame display for the inspector (D-MB5, FIX-MB-6).
 *
 * A catalog port declares an **unqualified** frame name (`body`). The model
 * check reports one display-qualified name per connection, `"{path}/{frame}"`
 * (e.g. `Arm1/body`), where the path is the instance path from the model root.
 * Frame identity is face-scoped (FIX-MB-6): composite/subsystem faces compare
 * as (instance path, name), primitive ports keep bare names, `world` is global.
 * The web cannot tell a face from a primitive port, so it never re-implements
 * that rule: it builds the readable strings and relays the worker's E007.
 */

import type { Diagnostic } from "../contracts/diagnostic";
import type { ModelNode } from "../contracts/model";
import type { PortSpec } from "../editor/nodeInterface";

/** The instance path of a node inside the model, root first (e.g. `Sub1/Arm1`). */
export function instancePath(segments: readonly string[]): string {
  return segments
    .map((segment) => segment.trim())
    .filter((segment) => segment.length > 0)
    .join("/");
}

/**
 * `"{path}/{frame}"`, the display form the worker puts in `model.check.frames`.
 * A null, empty or whitespace-only frame is frame-neutral and has no qualified
 * name.
 */
export function qualifiedFrame(
  path: readonly string[],
  frame: string | null | undefined,
): string | null {
  if (frame === null || frame === undefined) {
    return null;
  }
  const name = frame.trim();
  if (name.length === 0) {
    return null;
  }
  const prefix = instancePath(path);
  return prefix.length === 0 ? name : `${prefix}/${name}`;
}

export interface PortFrame {
  /** The node and port the frame belongs to, e.g. `Arm1.p`. */
  endpoint: string;
  /** The declared frame, unqualified; null when frame-neutral. */
  declared: string | null;
  /** The instance-qualified display name, or null when frame-neutral. */
  qualified: string | null;
}

/** One endpoint's frame, with the node and port it came from. */
export function portFrame(
  node: ModelNode,
  port: PortSpec,
  path: readonly string[],
): PortFrame {
  const declared =
    port.frame === null || port.frame === undefined || port.frame.trim().length === 0
      ? null
      : port.frame.trim();
  return {
    endpoint: `${node.name}.${port.name}`,
    declared,
    qualified: qualifiedFrame([...path, node.name], declared),
  };
}

export interface BondFrames {
  from: PortFrame;
  to: PortFrame;
  /** The worker's `model.check.frames[connectionId]`, if it reported one. */
  reported: string | null;
  /** The E007 diagnostic the model check raised for this connection, if any. */
  e007?: Diagnostic | null;
}

/** The E007 diagnostic that belongs to a connection (matched by connection id). */
export function frameDiagnostic(
  diagnostics: readonly Diagnostic[],
  connectionId: string,
): Diagnostic | null {
  return (
    diagnostics.find(
      (diagnostic) => diagnostic.code === "E007" && diagnostic.connection === connectionId,
    ) ?? null
  );
}

/**
 * A readable explanation of what a bond does to its two frames.
 *
 * A bond never transforms; a FixedTransform/JointTransform is the only legal
 * bridge. Whether two ends agree is the worker's call (face-scoped identity,
 * FIX-MB-6): an E007 for this connection is shown with its message and hint;
 * without one the check accepted the bond. `reported` is the worker's
 * display-qualified name, shown as-is.
 */
export function explainBondFrames({ from, to, reported, e007 }: BondFrames): string {
  if (e007 !== undefined && e007 !== null) {
    const hint = e007.hint === undefined || e007.hint === null || e007.hint === "" ? "" : ` Hint: ${e007.hint}`;
    return `Frame mismatch (E007): ${e007.message}${hint}`;
  }
  if (from.declared !== null && to.declared !== null) {
    if (from.declared === to.declared) {
      const fromName = from.qualified ?? from.declared;
      const toName = to.qualified ?? to.declared;
      if (fromName === toName) {
        return `Both ends are in frame ${fromName}; the bond passes the twist and wrench through unchanged.`;
      }
      return (
        `Both ends declare frame name ${from.declared}, displayed as ${fromName} and ${toName}. ` +
        `The model check accepts this bond (no E007), for example for primitive ports or a legal bridge.`
      );
    }
    return (
      `This bond joins ${from.qualified ?? from.declared} at ${from.endpoint} ` +
      `and ${to.qualified ?? to.declared} at ${to.endpoint}. A bond cannot change frame ` +
      `(E007); a FixedTransform or JointTransform is the only legal bridge.`
    );
  }
  if (reported !== null) {
    return `The model check reports ${reported} for this bond.`;
  }
  if (from.qualified !== null || to.qualified !== null) {
    const known = from.qualified ?? to.qualified;
    return `${known} at one end; the other port is frame-neutral, so the bond adopts it.`;
  }
  return "Neither end declares a frame; the bond is frame-neutral.";
}
