/**
 * "Copy to project library" (plan 7.4): the fork renames the @block
 * declaration, writes the project-library file with the plan 3.7 PUT, and
 * re-points only when the refreshed catalog publishes the project block.
 */

import { afterEach, describe, expect, it, vi } from "vitest";

import catalogJson from "../../contracts/fixtures/catalog/valid/catalog.min.json";
import type { Catalog, CatalogBlock } from "../src/contracts/catalog";
import {
  copyBlockToProjectLibrary,
  forkedSource,
} from "../src/inspector/copyToLibrary";

const catalog = catalogJson as unknown as Catalog;

function motor(): CatalogBlock {
  const block = catalog.blocks.find((entry) => entry.name === "DCMotor");
  if (block === undefined) {
    throw new Error("the catalog has no DCMotor");
  }
  return block;
}

function answer(status: number, body: unknown): Response {
  const text = body === undefined ? "" : JSON.stringify(body);
  return {
    status,
    ok: status >= 200 && status < 300,
    text: async () => text,
    json: async () => JSON.parse(text) as unknown,
  } as unknown as Response;
}

function fetchMock() {
  return vi.fn(async (_input: RequestInfo | URL, _init?: RequestInit) =>
    answer(200, {}),
  );
}

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("forked source", () => {
  it("renames the @block declaration to the new block name", () => {
    const source = forkedSource(motor(), "DCMotorCopy");
    expect(source.startsWith("@block DCMotorCopy begin")).toBe(true);
    expect(source).not.toContain("@block DCMotor begin");
    expect(source).toContain("@equations begin");
  });

  it("refuses to fork source without the block declaration", () => {
    expect(() => forkedSource({ ...motor(), source: "no declaration here" }, "Copy")).toThrow(
      "has no @block DCMotor declaration",
    );
  });
});

describe("copyBlockToProjectLibrary", () => {
  it("writes library/<Name>.jl and reports that the fake catalog has no project block", async () => {
    const project = {
      name: "demo",
      project: { libraryDir: "library" },
      models: [],
      library: [{ name: "DCMotorCopy", modified: 0 }],
    };
    const mock = fetchMock();
    mock
      .mockResolvedValueOnce(answer(200, project))
      .mockResolvedValueOnce(answer(200, { name: "DCMotorCopy2", file: "DCMotorCopy2.jl" }))
      .mockResolvedValueOnce(answer(200, catalog));
    vi.stubGlobal("fetch", mock);

    const outcome = await copyBlockToProjectLibrary("demo", motor());

    expect(outcome.name).toBe("DCMotorCopy2");
    expect(outcome.file).toBe("library/DCMotorCopy2.jl");
    expect(outcome.ref).toBeNull();
    expect(outcome.catalogError).toBeNull();
    expect(outcome.source).toContain("@block DCMotorCopy2 begin");

    const putUrl = String(mock.mock.calls[1]?.[0]);
    expect(putUrl).toContain("/api/projects/demo/library/DCMotorCopy2");
    const put = mock.mock.calls[1]?.[1];
    expect(put?.method).toBe("PUT");
    expect(put?.headers).toMatchObject({ "content-type": "text/plain; charset=utf-8" });
    expect(String(put?.body)).toContain("@block DCMotorCopy2 begin");
  });

  it("re-points when the refreshed catalog publishes project:<name>", async () => {
    const projectBlock: CatalogBlock = {
      ...motor(),
      ref: "project:DCMotorCopy",
      name: "DCMotorCopy",
      path: "library/DCMotorCopy.jl",
    };
    const published: Catalog = {
      ...catalog,
      blocks: [...catalog.blocks, projectBlock],
    };
    const mock = fetchMock();
    mock
      .mockResolvedValueOnce(
        answer(200, {
          name: "demo",
          project: { libraryDir: "library" },
          models: [],
          library: [],
        }),
      )
      .mockResolvedValueOnce(answer(200, { name: "DCMotorCopy", file: "DCMotorCopy.jl" }))
      .mockResolvedValueOnce(answer(200, published));
    vi.stubGlobal("fetch", mock);

    const outcome = await copyBlockToProjectLibrary("demo", motor());
    expect(outcome.name).toBe("DCMotorCopy");
    expect(outcome.ref).toBe("project:DCMotorCopy");
    expect(outcome.catalogError).toBeNull();
    expect(outcome.catalog?.blocks.some((entry) => entry.ref === "project:DCMotorCopy")).toBe(
      true,
    );
  });

  it("reports a catalog refresh failure without claiming the write failed", async () => {
    const mock = fetchMock();
    mock
      .mockResolvedValueOnce(
        answer(200, {
          name: "demo",
          project: { libraryDir: "library" },
          models: [],
          library: [],
        }),
      )
      .mockResolvedValueOnce(answer(200, { name: "DCMotorCopy", file: "DCMotorCopy.jl" }))
      .mockResolvedValueOnce(answer(502, { detail: "the worker is restarting" }));
    vi.stubGlobal("fetch", mock);

    const outcome = await copyBlockToProjectLibrary("demo", motor());
    expect(outcome.ref).toBeNull();
    expect(outcome.catalog).toBeNull();
    expect(outcome.catalogError).toContain("502");
  });

  it("surfaces a project-library write failure", async () => {
    const mock = fetchMock();
    mock
      .mockResolvedValueOnce(
        answer(200, {
          name: "demo",
          project: { libraryDir: "library" },
          models: [],
          library: [],
        }),
      )
      .mockResolvedValueOnce(answer(422, { detail: "the source is not valid" }));
    vi.stubGlobal("fetch", mock);

    await expect(copyBlockToProjectLibrary("demo", motor())).rejects.toThrow(
      "the source is not valid",
    );
  });
});
