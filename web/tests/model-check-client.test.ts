/**
 * W1.3: the transport of the live model check (`POST /api/check/model`).
 * The project query is what lets the backend give the worker the right
 * `projectDir` for project library blocks (plan 3.6/3.7).
 */

import { afterEach, describe, expect, it, vi } from "vitest";

import { checkModel, ModelCheckError } from "../src/diagnostics/modelCheckClient";
import { createEmptyModel } from "../src/state/modelFactory";

function jsonResponse(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "content-type": "application/json" },
  });
}

const fetchMock = vi.fn<typeof fetch>();

afterEach(() => {
  fetchMock.mockReset();
  vi.unstubAllGlobals();
});

describe("the model check client", () => {
  it("posts the document with the project query and returns the result", async () => {
    vi.stubGlobal("fetch", fetchMock);
    fetchMock.mockResolvedValue(
      jsonResponse({
        diagnostics: [],
        domains: { c1: "Electrical" },
        causality: {},
        frames: {},
        unitFactors: { c2: 0.001 },
        signals: [],
        stats: { states: 3, equations: 3 },
      }),
    );
    const model = createEmptyModel("M");

    const result = await checkModel(model, { project: "demo project" });

    expect(fetchMock).toHaveBeenCalledWith(
      "/api/check/model?project=demo%20project",
      expect.objectContaining({
        method: "POST",
        headers: expect.objectContaining({ "content-type": "application/json" }),
      }),
    );
    const request = fetchMock.mock.calls[0]?.[1];
    expect(JSON.parse(String(request?.body))).toEqual({ model });
    expect(result.domains).toEqual({ c1: "Electrical" });
    expect(result.frames).toEqual({});
    expect(result.unitFactors).toEqual({ c2: 0.001 });
    expect(result.stats).toEqual({ states: 3, equations: 3 });
  });

  it("keeps the worker's diagnostics from a 422 answer", async () => {
    vi.stubGlobal("fetch", fetchMock);
    fetchMock.mockResolvedValue(
      jsonResponse(
        {
          message: "the model could not be checked",
          diagnostics: [{ code: "E103", severity: "error", message: "14 unknowns, 13 equations" }],
        },
        422,
      ),
    );

    const failure = await checkModel(createEmptyModel("M")).catch((error: unknown) => error);

    expect(failure).toBeInstanceOf(ModelCheckError);
    expect((failure as ModelCheckError).status).toBe(422);
    expect((failure as ModelCheckError).message).toBe("the model could not be checked");
    expect((failure as ModelCheckError).diagnostics).toHaveLength(1);
    expect((failure as ModelCheckError).diagnostics[0]?.code).toBe("E103");
  });

  it("rejects a 200 answer that is not a ModelCheckResult", async () => {
    vi.stubGlobal("fetch", fetchMock);
    fetchMock.mockResolvedValue(jsonResponse({ ok: true }));

    await expect(checkModel(createEmptyModel("M"))).rejects.toBeInstanceOf(ModelCheckError);
  });
});
