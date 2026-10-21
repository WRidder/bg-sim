/**
 * The API client (plan 3.7): a typed fetch wrapper that turns transport and
 * protocol failures into ApiError and validates the health payload.
 */

import { afterEach, describe, expect, it, vi } from "vitest";

import { ApiError, getHealth, requestJson } from "../src/api/client";
import { describeHealth, isFakeWorker } from "../src/api/health";

const fetchMock = vi.fn<typeof fetch>();

afterEach(() => {
  fetchMock.mockReset();
});

function jsonResponse(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "content-type": "application/json" },
  });
}

describe("getHealth", () => {
  it("parses the plan 3.7 payload", async () => {
    vi.stubGlobal("fetch", fetchMock);
    fetchMock.mockResolvedValue(
      jsonResponse({
        backend: "0.1.0",
        worker: "warming",
        versions: { bgsim: "0.1.0", julia: "1.13.2" },
      }),
    );

    const health = await getHealth();

    expect(health).toEqual({
      backend: "0.1.0",
      worker: "warming",
      versions: { bgsim: "0.1.0", julia: "1.13.2" },
    });
    expect(fetchMock).toHaveBeenCalledWith("/api/health", expect.objectContaining({ headers: { accept: "application/json" } }));
  });

  it("rejects an unknown worker state", async () => {
    vi.stubGlobal("fetch", fetchMock);
    fetchMock.mockResolvedValue(jsonResponse({ backend: "0.1.0", worker: "melting", versions: {} }));

    await expect(getHealth()).rejects.toBeInstanceOf(ApiError);
  });

  it("reports a non-2xx answer with its status", async () => {
    vi.stubGlobal("fetch", fetchMock);
    fetchMock.mockResolvedValue(jsonResponse({ detail: "nope" }, 503));

    const error = await getHealth().catch((reason: unknown) => reason);

    expect(error).toBeInstanceOf(ApiError);
    expect((error as ApiError).status).toBe(503);
    expect((error as ApiError).message).toContain("503");
  });

  it("reports an unreachable backend", async () => {
    vi.stubGlobal("fetch", fetchMock);
    fetchMock.mockRejectedValue(new TypeError("fetch failed"));

    const error = await getHealth().catch((reason: unknown) => reason);

    expect(error).toBeInstanceOf(ApiError);
    expect((error as ApiError).status).toBe(0);
    expect((error as ApiError).message).toContain("Cannot reach the bg-sim backend");
  });

  it("rethrows an abort instead of wrapping it", async () => {
    vi.stubGlobal("fetch", fetchMock);
    const abortError = new DOMException("The operation was aborted.", "AbortError");
    fetchMock.mockRejectedValue(abortError);

    await expect(requestJson("/api/health")).rejects.toBe(abortError);
  });

  it("reports a body that is not JSON", async () => {
    vi.stubGlobal("fetch", fetchMock);
    fetchMock.mockResolvedValue(new Response("<html>", { status: 200 }));

    await expect(requestJson("/api/health")).rejects.toBeInstanceOf(ApiError);
  });
});

describe("health helpers", () => {
  it("detects a fake worker from the versions payload or the backend string", () => {
    expect(isFakeWorker({ backend: "0.1.0", versions: { fakeWorker: true } })).toBe(true);
    expect(isFakeWorker({ backend: "0.1.0", versions: { worker: "fake" } })).toBe(true);
    expect(isFakeWorker({ backend: "0.1.0 (fake)", versions: {} })).toBe(true);
    expect(isFakeWorker({ backend: "0.1.0", versions: { bgsim: "0.1.0" } })).toBe(false);
    expect(isFakeWorker({ backend: "0.1.0", versions: { fakeWorker: false } })).toBe(false);
  });

  it("describes the backend and its version stamps", () => {
    expect(describeHealth({ backend: "0.1.0", worker: "ready", versions: { julia: "1.13.2" } })).toBe(
      "backend 0.1.0 · julia 1.13.2",
    );
    expect(describeHealth({ backend: "0.1.0", worker: "ready", versions: {} })).toBe("backend 0.1.0");
  });
});
