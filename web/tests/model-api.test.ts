/**
 * The model/project client and the URL session route (plan 3.7).
 */

import { afterEach, describe, expect, it, vi } from "vitest";

import modelJson from "../../contracts/fixtures/model/valid/model.dcmotor.json";
import type { Model } from "../src/contracts/model";
import {
  ensureProject,
  getModel,
  isModelDocument,
  ProjectApiError,
  putModel,
} from "../src/state/modelApi";
import { readSessionRoute } from "../src/state/session";

const dcmotor = modelJson as unknown as Model;

function answer(status: number, body: unknown): Response {
  return {
    status,
    ok: status >= 200 && status < 300,
    text: async () => (body === undefined ? "" : JSON.stringify(body)),
  } as unknown as Response;
}

function fetchMock() {
  return vi.fn(async (_input: RequestInfo | URL, _init?: RequestInit) => answer(200, {}));
}

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("session route", () => {
  it("defaults to demo/Model1", () => {
    expect(readSessionRoute("")).toEqual({ project: "demo", model: "Model1" });
    expect(readSessionRoute("?project=&model=")).toEqual({ project: "demo", model: "Model1" });
  });

  it("reads the project and model from the URL", () => {
    expect(readSessionRoute("?project=dc-motor&model=DCMotorSpeed")).toEqual({
      project: "dc-motor",
      model: "DCMotorSpeed",
    });
  });
});

describe("model documents", () => {
  it("accepts the contract fixture", () => {
    expect(isModelDocument(dcmotor)).toBe(true);
    expect(isModelDocument({ format: "bgsim.model", name: "x" })).toBe(false);
    expect(isModelDocument(null)).toBe(false);
  });

  it("returns null for a model that does not exist yet", async () => {
    const mock = fetchMock();
    mock.mockResolvedValueOnce(answer(404, { detail: "unknown model" }));
    vi.stubGlobal("fetch", mock);

    await expect(getModel("demo", "New")).resolves.toBeNull();
    expect(String(mock.mock.calls[0]?.[0])).toContain("/api/projects/demo/models/New");
  });

  it("loads a model document", async () => {
    const mock = fetchMock();
    mock.mockResolvedValueOnce(answer(200, dcmotor));
    vi.stubGlobal("fetch", mock);

    const document = await getModel("demo", "DCMotorSpeed");
    expect(document?.name).toBe("DCMotorSpeed");
    expect(document?.diagram.nodes).toHaveLength(dcmotor.diagram.nodes.length);
  });

  it("reports a malformed model instead of opening it", async () => {
    const mock = fetchMock();
    mock.mockResolvedValueOnce(answer(200, { hello: "world" }));
    vi.stubGlobal("fetch", mock);

    await expect(getModel("demo", "Broken")).rejects.toBeInstanceOf(ProjectApiError);
  });

  it("PUTs the document and returns the backend's normalised copy", async () => {
    const mock = fetchMock();
    mock.mockResolvedValueOnce(answer(200, dcmotor));
    vi.stubGlobal("fetch", mock);

    const saved = await putModel("demo", "DCMotorSpeed", dcmotor);
    expect(saved.name).toBe("DCMotorSpeed");
    const init = mock.mock.calls[0]?.[1];
    expect(init?.method).toBe("PUT");
    expect(init?.headers).toMatchObject({ "content-type": "application/json" });
    const body = JSON.parse(String(init?.body)) as Model;
    expect(body.format).toBe("bgsim.model");
    expect(body.diagram.connections).toHaveLength(dcmotor.diagram.connections.length);
  });

  it("surfaces the backend's 422 message", async () => {
    const mock = fetchMock();
    mock.mockResolvedValueOnce(
      answer(422, { detail: { message: "the model document is invalid", errors: [] } }),
    );
    vi.stubGlobal("fetch", mock);

    await expect(putModel("demo", "Broken", dcmotor)).rejects.toMatchObject({
      status: 422,
      message: "the model document is invalid",
    });
  });
});

describe("projects", () => {
  it("creates a project when the backend answers 404", async () => {
    const mock = fetchMock();
    mock
      .mockResolvedValueOnce(answer(404, { detail: "unknown project" }))
      .mockResolvedValueOnce(answer(201, { name: "demo" }))
      .mockResolvedValueOnce(answer(200, dcmotor));
    vi.stubGlobal("fetch", mock);

    await ensureProject("demo");
    expect(mock).toHaveBeenCalledTimes(2);
    expect(String(mock.mock.calls[0]?.[0])).toContain("/api/projects/demo");
    expect(String(mock.mock.calls[1]?.[0])).toContain("/api/projects");
    expect(mock.mock.calls[1]?.[1]?.method).toBe("POST");
    expect(JSON.parse(String(mock.mock.calls[1]?.[1]?.body))).toEqual({ name: "demo" });
  });

  it("treats a concurrent 409 creation as success", async () => {
    const mock = fetchMock();
    mock
      .mockResolvedValueOnce(answer(404, { detail: "unknown project" }))
      .mockResolvedValueOnce(answer(409, { detail: "already exists" }));
    vi.stubGlobal("fetch", mock);
    await expect(ensureProject("demo")).resolves.toBeUndefined();
  });

  it("reports a project error", async () => {
    const mock = fetchMock();
    mock.mockResolvedValueOnce(answer(500, { detail: "could not read the projects root" }));
    vi.stubGlobal("fetch", mock);
    await expect(ensureProject("demo")).rejects.toMatchObject({
      status: 500,
      message: "could not read the projects root",
    });
  });

  it("reports an unreachable backend", async () => {
    const mock = vi.fn(async () => {
      throw new TypeError("fetch failed");
    });
    vi.stubGlobal("fetch", mock);
    await expect(getModel("demo", "Model1")).rejects.toMatchObject({
      status: 0,
      message: expect.stringContaining("Cannot reach the bg-sim backend"),
    });
  });
});
