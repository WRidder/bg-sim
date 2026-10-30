/**
 * The edits of a debug session (plan 3.8, 7.9): the `debug.edits` of the run
 * manifest, and "Save parameters to model", which writes the edited parameter
 * values into the model document. State edits are never saved: they belong to
 * one run, the parameters belong to the model.
 */

import type { Edit } from "../../contracts/debug";
import type { Model, ModelDiagram } from "../../contracts/model";
import { formatNumber } from "./frameFormat";

export interface ParameterChange {
  /** Instance names from the root diagram to the node, e.g. `["Rig", "Motor1"]`. */
  path: string[];
  /** The parameter name. */
  name: string;
  value: number;
}

/** `Motor1/R` -> path `["Motor1"]`, name `R`; null for a target without an instance. */
export function splitParameterTarget(target: string): { path: string[]; name: string } | null {
  const parts = target.split("/").filter((part) => part.length > 0);
  const name = parts.pop();
  return name === undefined || parts.length === 0 ? null : { path: parts, name };
}

/** The parameter edits to save: the last edit of each target wins; state edits are skipped. */
export function parameterChangesOf(edits: readonly Edit[]): { changes: ParameterChange[]; skipped: string[] } {
  const latest = new Map<string, Edit>();
  for (const edit of edits) {
    if (edit.kind === "parameter") {
      latest.set(edit.target, edit);
    }
  }
  const changes: ParameterChange[] = [];
  const skipped: string[] = [];
  for (const edit of latest.values()) {
    const split = splitParameterTarget(edit.target);
    if (split === null || !Number.isFinite(edit.value)) {
      skipped.push(edit.target);
    } else {
      changes.push({ ...split, value: edit.value });
    }
  }
  return { changes, skipped };
}

function diagramOf(node: ModelDiagram["nodes"][number]): ModelDiagram | null {
  return "subsystem" in node.block ? node.block.subsystem.diagram : null;
}

/**
 * Write the changes into a (draft) model. Returns the targets that no node
 * answers to, so the caller can tell the user instead of dropping them silently.
 */
export function applyParameterChanges(draft: Model, changes: readonly ParameterChange[]): string[] {
  const missing: string[] = [];
  for (const change of changes) {
    let diagram: ModelDiagram | null = draft.diagram;
    let node: ModelDiagram["nodes"][number] | undefined;
    for (let index = 0; index < change.path.length; index += 1) {
      node = diagram?.nodes.find((entry) => entry.name === change.path[index]);
      if (node === undefined) {
        break;
      }
      if (index < change.path.length - 1) {
        diagram = diagramOf(node);
        if (diagram === null) {
          node = undefined;
          break;
        }
      }
    }
    if (node === undefined) {
      missing.push([...change.path, change.name].join("/"));
      continue;
    }
    node.params = { ...(node.params ?? {}), [change.name]: String(change.value) };
  }
  return missing;
}

/** `Motor1/R = 2.5 at t = 0.1234 s`. */
export function editText(edit: Edit): string {
  return `${edit.target} = ${formatNumber(edit.value)} at t = ${Number.isFinite(edit.t) ? edit.t.toFixed(4) : edit.t} s`;
}
