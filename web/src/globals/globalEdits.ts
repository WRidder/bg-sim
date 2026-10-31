/**
 * The document edits of the global parameter table (the Equations manager).
 *
 * Each function validates against the current document and returns either a
 * refusal message or an immer recipe; the document store runs the recipe with
 * `commit`, so every edit (a rename with its reference rewrite included) is one
 * undo step.
 */

import type { Model, ModelGlobalParameter } from "../contracts/model";
import { activeDiagram } from "../editor/subsystemPath";
import { parseExpression, renameIdentifier, stripEquationPrefix } from "../inspector/expression";
import {
  type ExpressionField,
  globalDependents,
  globalNameIssue,
  globalsOf,
  globalUsages,
  nextGlobalName,
  renameInDiagram,
} from "./globals";

export type Recipe = (draft: Model) => void;
export type EditPlan = { ok: true; recipe: Recipe; name?: string } | { ok: false; error: string };

export interface GlobalPatch {
  value?: string;
  unit?: string | null;
  description?: string | null;
}

function refuse(error: string): EditPlan {
  return { ok: false, error };
}

/** The syntax problem of a global's value, or null. */
export function globalValueIssue(text: string): string | null {
  const parsed = parseExpression(text);
  return parsed.ok ? null : parsed.message;
}

export function planAddGlobal(doc: Model, init: Partial<ModelGlobalParameter> = {}): EditPlan {
  const globals = globalsOf(doc);
  const name = init.name ?? nextGlobalName(globals);
  const issue = globalNameIssue(globals, name);
  if (issue !== null) {
    return refuse(issue);
  }
  const entry: ModelGlobalParameter = { name, value: stripEquationPrefix(init.value ?? "0") };
  if (init.unit !== undefined && init.unit !== null && init.unit.length > 0) {
    entry.unit = init.unit;
  }
  if (init.description !== undefined && init.description !== null && init.description.length > 0) {
    entry.description = init.description;
  }
  return {
    ok: true,
    name,
    recipe: (draft) => {
      draft.parameters = [...(draft.parameters ?? []), entry];
    },
  };
}

export function planUpdateGlobal(doc: Model, name: string, patch: GlobalPatch): EditPlan {
  const index = globalsOf(doc).findIndex((entry) => entry.name === name);
  if (index < 0) {
    return refuse(`There is no global parameter "${name}".`);
  }
  let value: string | undefined;
  if (patch.value !== undefined) {
    value = stripEquationPrefix(patch.value);
    if (value.length === 0) {
      return refuse("Enter a value.");
    }
    const issue = globalValueIssue(value);
    if (issue !== null) {
      return refuse(issue);
    }
  }
  return {
    ok: true,
    recipe: (draft) => {
      const entry = draft.parameters?.[index];
      if (entry === undefined) {
        return;
      }
      if (value !== undefined) {
        entry.value = value;
      }
      for (const key of ["unit", "description"] as const) {
        const next = patch[key];
        if (next === undefined) {
          continue;
        }
        const text = next?.trim() ?? "";
        if (text.length === 0) {
          delete entry[key];
        } else {
          entry[key] = text;
        }
      }
    },
  };
}

/**
 * Rename a global and rewrite every whole-identifier reference: other globals'
 * values and every node's params, starts and string constants at every diagram
 * level. One recipe, so one undo step.
 */
export function planRenameGlobal(doc: Model, name: string, next: string): EditPlan {
  const globals = globalsOf(doc);
  const index = globals.findIndex((entry) => entry.name === name);
  if (index < 0) {
    return refuse(`There is no global parameter "${name}".`);
  }
  const target = next.trim();
  if (target === name) {
    return { ok: true, recipe: () => undefined };
  }
  const issue = globalNameIssue(globals, target, name);
  if (issue !== null) {
    return refuse(issue);
  }
  return {
    ok: true,
    name: target,
    recipe: (draft) => {
      const list = draft.parameters ?? [];
      for (const [position, entry] of list.entries()) {
        if (position === index) {
          entry.name = target;
        }
        entry.value = renameIdentifier(entry.value, name, target);
      }
      renameInDiagram(draft.diagram, name, target);
    },
  };
}

/** Who uses a global: instance fields and other globals. */
export interface GlobalUsers {
  fields: ExpressionField[];
  globals: string[];
}

export function usersOf(doc: Model, name: string): GlobalUsers {
  return {
    fields: globalUsages(doc, name),
    globals: globalDependents(globalsOf(doc), name).filter((other) => other !== name),
  };
}

function describeUsers(users: GlobalUsers): string {
  const parts = [
    ...users.fields.map((field) => `${field.instancePath.join("/")}.${field.key}`),
    ...users.globals.map((other) => `global ${other}`),
  ];
  const shown = parts.slice(0, 6).join(", ");
  return parts.length > 6 ? `${shown} and ${parts.length - 6} more` : shown;
}

/** Delete a global; refused while anything still uses it (the message lists the users). */
export function planDeleteGlobal(doc: Model, name: string): EditPlan {
  const index = globalsOf(doc).findIndex((entry) => entry.name === name);
  if (index < 0) {
    return refuse(`There is no global parameter "${name}".`);
  }
  const users = usersOf(doc, name);
  if (users.fields.length > 0 || users.globals.length > 0) {
    return refuse(`"${name}" is still used by ${describeUsers(users)}. Change those first.`);
  }
  return {
    ok: true,
    recipe: (draft) => {
      const list = draft.parameters ?? [];
      list.splice(index, 1);
      if (list.length === 0) {
        delete draft.parameters;
      }
    },
  };
}

/** Move a row to `toIndex` (clamped); the order is the table's, evaluation order is separate. */
export function planMoveGlobal(doc: Model, name: string, toIndex: number): EditPlan {
  const globals = globalsOf(doc);
  const from = globals.findIndex((entry) => entry.name === name);
  if (from < 0) {
    return refuse(`There is no global parameter "${name}".`);
  }
  const to = Math.max(0, Math.min(globals.length - 1, toIndex));
  return {
    ok: true,
    recipe: (draft) => {
      const list = draft.parameters;
      if (list === undefined || from === to) {
        return;
      }
      const [entry] = list.splice(from, 1);
      if (entry !== undefined) {
        list.splice(to, 0, entry);
      }
    },
  };
}

/** Where an instance expression lives: the Equations view edits fields anywhere in the model. */
export interface FieldRef {
  diagramPath: readonly string[];
  nodeId: string;
  kind: ExpressionField["kind"];
  key: string;
}

/** Set one instance expression by reference (an empty start removes the override). */
export function planSetField(doc: Model, field: FieldRef, text: string): EditPlan {
  const diagram = activeDiagram(doc, field.diagramPath);
  if (diagram === null || !diagram.nodes.some((node) => node.id === field.nodeId)) {
    return refuse("That block is no longer in the model.");
  }
  const value = stripEquationPrefix(text);
  if (value.length === 0 && field.kind !== "start") {
    return refuse("Enter a value.");
  }
  if (value.length > 0) {
    const issue = globalValueIssue(value);
    if (issue !== null) {
      return refuse(issue);
    }
  }
  const path = [...field.diagramPath];
  return {
    ok: true,
    recipe: (draft) => {
      const node = activeDiagram(draft, path)?.nodes.find((entry) => entry.id === field.nodeId);
      if (node === undefined) {
        return;
      }
      if (field.kind === "param") {
        node.params = { ...(node.params ?? {}), [field.key]: value };
      } else if (field.kind === "start") {
        if (value.length === 0) {
          delete node.starts?.[field.key];
        } else {
          node.starts = { ...(node.starts ?? {}), [field.key]: value };
        }
      } else {
        node.constants = { ...(node.constants ?? {}), [field.key]: value };
      }
    },
  };
}
