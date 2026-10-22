/**
 * `POST /api/check/block` (plan 3.7, 7.7): the fast as-you-type check of one
 * block source. The backend validates the worker's answer against
 * `contracts/schemas/worker-rpc.schema.json` before it answers, so the client
 * checks the envelope and trusts the ranges.
 *
 * A worker error answers 422 with `{ message, diagnostics }`; those
 * diagnostics are the user's E001, so they are returned as a normal result
 * with `interface: null` instead of being thrown away. Only transport and
 * contract failures throw.
 *
 * Identical in-flight requests share one promise: the linter and the canvas
 * interface sync both ask for the same source on every keystroke.
 */

import { API_BASE } from "../api/client";
import type { Diagnostic } from "../contracts/diagnostic";
import type { BlockCheckResult, BlockInterface } from "../contracts/worker-rpc";

export class BlockCheckError extends Error {
  readonly status: number;
  readonly diagnostics: Diagnostic[];

  constructor(message: string, status: number, diagnostics: Diagnostic[] = []) {
    super(message);
    this.name = "BlockCheckError";
    this.status = status;
    this.diagnostics = diagnostics;
  }
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function diagnosticsFrom(body: unknown): Diagnostic[] {
  if (!isRecord(body)) {
    return [];
  }
  if (Array.isArray(body.diagnostics)) {
    return body.diagnostics as Diagnostic[];
  }
  const detail = body.detail;
  if (isRecord(detail) && Array.isArray(detail.diagnostics)) {
    return detail.diagnostics as Diagnostic[];
  }
  return [];
}

function messageFrom(body: unknown, status: number): string {
  if (isRecord(body)) {
    if (typeof body.message === "string" && body.message.length > 0) {
      return body.message;
    }
    if (typeof body.detail === "string" && body.detail.length > 0) {
      return body.detail;
    }
    if (isRecord(body.detail) && typeof body.detail.message === "string") {
      return body.detail.message;
    }
  }
  return `The bg-sim backend answered ${status} for the block check.`;
}

function interfaceFrom(value: unknown): BlockInterface | null {
  if (!isRecord(value)) {
    return null;
  }
  const array = (key: string): unknown[] => (Array.isArray(value[key]) ? value[key] : []);
  return {
    constants: array("constants") as BlockInterface["constants"],
    parameters: array("parameters") as BlockInterface["parameters"],
    inputs: array("inputs") as BlockInterface["inputs"],
    outputs: array("outputs") as BlockInterface["outputs"],
    ports: array("ports") as BlockInterface["ports"],
    variables: array("variables") as BlockInterface["variables"],
    causality: array("causality") as BlockInterface["causality"],
  };
}

export interface CheckBlockOptions {
  signal?: AbortSignal;
}

/**
 * Ask the worker to check one block source. `ref` is the block being edited:
 * `inline:<nodeId>` or a catalog ref (plan 3.6 `block.check`).
 */
export async function checkBlockSource(
  source: string,
  ref: string | null = null,
  options: CheckBlockOptions = {},
): Promise<BlockCheckResult> {
  return runCheck(source, ref, options.signal);
}

async function runCheck(
  source: string,
  ref: string | null,
  signal: AbortSignal | undefined,
): Promise<BlockCheckResult> {
  const url = `${API_BASE}/api/check/block`;
  let response: Response;
  try {
    response = await fetch(url, {
      method: "POST",
      headers: { accept: "application/json", "content-type": "application/json" },
      body: JSON.stringify({ source, ref }),
      signal,
    });
  } catch (error) {
    if (signal?.aborted) {
      throw error;
    }
    throw new BlockCheckError(
      `Cannot reach the bg-sim backend at ${url}. Is it running?`,
      0,
    );
  }

  const text = await response.text();
  let payload: unknown = null;
  if (text.length > 0) {
    try {
      payload = JSON.parse(text) as unknown;
    } catch {
      payload = null;
    }
  }

  if (response.status === 422) {
    return { diagnostics: diagnosticsFrom(payload), interface: null };
  }

  if (!response.ok) {
    throw new BlockCheckError(messageFrom(payload, response.status), response.status);
  }

  if (!isRecord(payload) || !Array.isArray(payload.diagnostics)) {
    throw new BlockCheckError(
      "The block check answer is not a BlockCheckResult.",
      response.status,
    );
  }

  return {
    diagnostics: payload.diagnostics as Diagnostic[],
    interface: interfaceFrom(payload.interface),
  };
}
