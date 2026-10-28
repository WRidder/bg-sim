/**
 * `POST /api/check/model` (plan 3.7): the live model check behind the
 * diagnostics panel and the canvas markers.
 *
 * The backend validates the worker's answer against
 * `contracts/schemas/worker-rpc.schema.json` before it answers, so the client
 * only checks that the envelope has the shape the UI reads. A worker error
 * answers 422 with `{ message, diagnostics }`; those diagnostics are surfaced
 * instead of being thrown away.
 */

import { API_BASE } from "../api/client";
import type { Diagnostic } from "../contracts/diagnostic";
import type { Model } from "../contracts/model";
import type { ModelCheckResult } from "../contracts/worker-rpc";

export class ModelCheckError extends Error {
  readonly status: number;
  readonly diagnostics: Diagnostic[];

  constructor(message: string, status: number, diagnostics: Diagnostic[] = []) {
    super(message);
    this.name = "ModelCheckError";
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
  const direct = body.diagnostics;
  if (Array.isArray(direct)) {
    return direct as Diagnostic[];
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
  return `The bg-sim backend answered ${status} for the model check.`;
}

export interface CheckModelOptions {
  signal?: AbortSignal;
  projectDir?: string;
  /** Project name; the backend derives `projectDir` from it (plan 3.7). */
  project?: string | null;
}

/**
 * Ask the worker to check `model`. Aborts are re-thrown unchanged so the check
 * loop can discard them silently; every other failure is a `ModelCheckError`.
 */
export async function checkModel(
  model: Model,
  options: CheckModelOptions = {},
): Promise<ModelCheckResult> {
  const query =
    options.project !== undefined && options.project !== null && options.project.length > 0
      ? `?project=${encodeURIComponent(options.project)}`
      : "";
  const url = `${API_BASE}/api/check/model${query}`;
  const body: Record<string, unknown> = { model };
  if (options.projectDir !== undefined) {
    body.projectDir = options.projectDir;
  }

  let response: Response;
  try {
    response = await fetch(url, {
      method: "POST",
      headers: { accept: "application/json", "content-type": "application/json" },
      body: JSON.stringify(body),
      signal: options.signal,
    });
  } catch (error) {
    if (options.signal?.aborted) {
      throw error;
    }
    throw new ModelCheckError(
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

  if (!response.ok) {
    throw new ModelCheckError(
      messageFrom(payload, response.status),
      response.status,
      diagnosticsFrom(payload),
    );
  }

  if (!isRecord(payload) || !Array.isArray(payload.diagnostics)) {
    throw new ModelCheckError("The model check answer is not a ModelCheckResult.", response.status);
  }

  return {
    diagnostics: payload.diagnostics as Diagnostic[],
    domains: isRecord(payload.domains) ? (payload.domains as ModelCheckResult["domains"]) : {},
    causality: isRecord(payload.causality)
      ? (payload.causality as ModelCheckResult["causality"])
      : {},
    frames: isRecord(payload.frames)
      ? (payload.frames as ModelCheckResult["frames"])
      : {},
    unitFactors: isRecord(payload.unitFactors)
      ? (payload.unitFactors as ModelCheckResult["unitFactors"])
      : {},
    signals: Array.isArray(payload.signals)
      ? (payload.signals as ModelCheckResult["signals"])
      : [],
    stats:
      isRecord(payload.stats) &&
      typeof payload.stats.states === "number" &&
      typeof payload.stats.equations === "number"
        ? { states: payload.stats.states, equations: payload.stats.equations }
        : { states: 0, equations: 0 },
  };
}
