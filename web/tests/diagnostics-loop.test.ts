/**
 * W1.3 (plan 7.3): the debounced `model.check` loop.
 *
 * * rapid edits coalesce into one request after 400 ms of quiet;
 * * no request is sent while the worker is not ready;
 * * a response for a superseded request is discarded by sequence number,
 *   even when the transport ignores the abort.
 */

import { afterEach, describe, expect, it, vi } from "vitest";

import type { Model } from "../src/contracts/model";
import type { ModelCheckResult } from "../src/contracts/worker-rpc";
import { createCheckLoop } from "../src/diagnostics/checkLoop";
import { createEmptyModel } from "../src/state/modelFactory";

function checkResult(code: string): ModelCheckResult {
  return {
    diagnostics: [{ code, severity: "error", message: code }],
    domains: {},
    causality: {},
    unitFactors: {},
    signals: [],
    stats: { states: 0, equations: 0 },
  };
}

function deferred<T>() {
  let resolve!: (value: T) => void;
  let reject!: (reason?: unknown) => void;
  const promise = new Promise<T>((res, rej) => {
    resolve = res;
    reject = rej;
  });
  return { promise, resolve, reject };
}

async function flush(): Promise<void> {
  await Promise.resolve();
  await Promise.resolve();
}

afterEach(() => {
  vi.useRealTimers();
});

describe("the debounced model check loop", () => {
  it("coalesces rapid edits into one request and reports the newest revision", async () => {
    vi.useFakeTimers();
    const model = createEmptyModel("M");
    const check = vi.fn(async (_model: Model, _signal: AbortSignal) => checkResult("E1"));
    const onResult = vi.fn();
    const onError = vi.fn();
    const loop = createCheckLoop({ check, onResult, onError, debounceMs: 400 });
    loop.setReady(true);

    loop.schedule(model, 1);
    await vi.advanceTimersByTimeAsync(100);
    loop.schedule(model, 2);
    await vi.advanceTimersByTimeAsync(100);
    loop.schedule(model, 3);
    await vi.advanceTimersByTimeAsync(399);

    expect(check).not.toHaveBeenCalled();

    await vi.advanceTimersByTimeAsync(1);
    expect(check).toHaveBeenCalledTimes(1);
    await flush();
    expect(onResult).toHaveBeenCalledTimes(1);
    expect(onResult.mock.calls[0]?.[1]).toBe(3);
    expect(onError).not.toHaveBeenCalled();

    loop.dispose();
  });

  it("does not fire while the worker is not ready, then fires when it becomes ready", async () => {
    vi.useFakeTimers();
    const check = vi.fn(async (_model: Model, _signal: AbortSignal) => checkResult("E1"));
    const onStatus = vi.fn();
    const loop = createCheckLoop({
      check,
      onResult: vi.fn(),
      onError: vi.fn(),
      onStatus,
      debounceMs: 400,
    });

    loop.setReady(false);
    loop.schedule(createEmptyModel("M"), 1);
    await vi.advanceTimersByTimeAsync(800);
    expect(check).not.toHaveBeenCalled();
    expect(onStatus).toHaveBeenCalledWith("waiting");

    loop.setReady(true);
    await vi.advanceTimersByTimeAsync(400);
    expect(check).toHaveBeenCalledTimes(1);

    loop.dispose();
  });

  it("discards a stale response that resolves after a newer request", async () => {
    vi.useFakeTimers();
    const model = createEmptyModel("M");
    const first = deferred<ModelCheckResult>();
    const second = deferred<ModelCheckResult>();
    const check = vi
      .fn<(_model: Model, _signal: AbortSignal) => Promise<ModelCheckResult>>()
      .mockReturnValueOnce(first.promise)
      .mockReturnValueOnce(second.promise);
    const onResult = vi.fn();
    const loop = createCheckLoop({
      check,
      onResult,
      onError: vi.fn(),
      debounceMs: 400,
    });
    loop.setReady(true);

    loop.schedule(model, 1);
    await vi.advanceTimersByTimeAsync(400);
    expect(check).toHaveBeenCalledTimes(1);

    // A newer edit makes the first response stale before the second even fires.
    loop.schedule(model, 2);
    await vi.advanceTimersByTimeAsync(400);
    expect(check).toHaveBeenCalledTimes(2);

    second.resolve(checkResult("E2"));
    await flush();
    expect(onResult).toHaveBeenCalledTimes(1);
    expect(onResult.mock.calls[0]?.[0].diagnostics[0]?.code).toBe("E2");
    expect(onResult.mock.calls[0]?.[1]).toBe(2);

    first.resolve(checkResult("E1"));
    await flush();
    expect(onResult).toHaveBeenCalledTimes(1);
    expect(onResult.mock.calls[0]?.[0].diagnostics[0]?.code).toBe("E2");

    loop.dispose();
  });

  it("cancels a pending check and stops after dispose", async () => {
    vi.useFakeTimers();
    const check = vi.fn(async (_model: Model, _signal: AbortSignal) => checkResult("E1"));
    const loop = createCheckLoop({
      check,
      onResult: vi.fn(),
      onError: vi.fn(),
      debounceMs: 400,
    });
    loop.setReady(true);

    loop.schedule(createEmptyModel("M"), 1);
    loop.cancel();
    await vi.advanceTimersByTimeAsync(500);
    expect(check).not.toHaveBeenCalled();
    expect(loop.pendingRevision()).toBeNull();

    loop.schedule(createEmptyModel("M"), 2);
    loop.dispose();
    await vi.advanceTimersByTimeAsync(500);
    expect(check).not.toHaveBeenCalled();
  });
});
