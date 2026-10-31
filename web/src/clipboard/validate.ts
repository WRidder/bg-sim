/**
 * Schema validation of a pasted clipboard envelope against the contract
 * (`contracts/schemas/clipboard.schema.json`, which reuses the model schema's nodes,
 * connections, notes, shapes and globals). Ajv and the schemas are loaded with this
 * module, which the paste imports on demand, so the editor's first load stays small.
 */

import Ajv2020 from "ajv/dist/2020";

import bindingsSchema from "../../../contracts/schemas/bindings.schema.json";
import clipboardSchema from "../../../contracts/schemas/clipboard.schema.json";
import modelSchema from "../../../contracts/schemas/model.schema.json";
import type { ClipboardEnvelope } from "../contracts/clipboard";

type Validator = ((value: unknown) => boolean) & {
  errors?: { instancePath: string; message?: string }[] | null;
};

let compiled: Validator | null = null;

function validator(): Validator {
  if (compiled === null) {
    // strict: false tolerates the schemas' documentation keywords; formats are unused.
    const ajv = new Ajv2020({ allErrors: false, strict: false, validateFormats: false });
    ajv.addSchema(bindingsSchema);
    ajv.addSchema(modelSchema);
    compiled = ajv.compile(clipboardSchema) as Validator;
  }
  return compiled;
}

export type ValidationResult =
  | { ok: true; envelope: ClipboardEnvelope }
  | { ok: false; message: string };

/** Validate a parsed envelope; the message names the first offending place. */
export function validateEnvelope(value: unknown): ValidationResult {
  const validate = validator();
  if (validate(value)) {
    return { ok: true, envelope: value as ClipboardEnvelope };
  }
  const first = validate.errors?.[0];
  const where = first?.instancePath ? ` at ${first.instancePath}` : "";
  return {
    ok: false,
    message: `The clipboard holds bg-sim elements that do not match the clipboard format${where}${first?.message ? ` (${first.message})` : ""}. Copy them again.`,
  };
}
