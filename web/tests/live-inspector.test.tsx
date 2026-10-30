/**
 * W4.3 (plan 7.9, "At a pause"): the inspector in live mode. A parameter change maps to
 * `POST /api/runs/{id}/debug/setParameter { name: "<instance path>/<param>", value }`, refusals are shown inline,
 * and the model document, its undo stack and the dirty flag are not touched. Not paused, the inspector is as before.
 */

import { act, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import catalogJson from "../../contracts/fixtures/catalog/valid/catalog.min.json";
import type { Catalog } from "../src/contracts/catalog";
import type { PausedInfo } from "../src/contracts/debug";
import { resetBreakpointStore } from "../src/debug/breakpointStore";
import { resetDebugStore, useDebugStore } from "../src/debug/debugStore";
import { Inspector } from "../src/inspector/Inspector";
import {
  latestLiveValue,
  liveModeOf,
  liveParameterName,
  parseLiveValue,
  sendLiveParameter,
} from "../src/inspector/liveEdit";
import { resetCatalogStore, useCatalogStore } from "../src/library/catalogStore";
import { resetRunStore, useRunStore } from "../src/plot/runStore";
import { resetDocumentStore, useDocumentStore } from "../src/state/documentStore";
import { createEmptyModel, createNodeFromBlock } from "../src/state/modelFactory";

const catalog = catalogJson as unknown as Catalog;

describe("live edit request mapping", () => {
  it("qualifies the parameter with the instance path", () => {
    expect(liveParameterName([], "Motor1", "R")).toBe("Motor1/R");
    expect(liveParameterName(["Rig", "Drive"], "Motor1", "R")).toBe("Rig/Drive/Motor1/R");
  });

  it("parses numbers and literal arithmetic, and refuses names with a hint", () => {
    expect(parseLiveValue("2.5")).toEqual({ ok: true, value: 2.5 });
    expect(parseLiveValue(" 1e-3 ")).toEqual({ ok: true, value: 0.001 });
    expect(parseLiveValue("2*pi")).toEqual({ ok: true, value: 2 * Math.PI });
    const named = parseLiveValue("Rbase * 2");
    expect(named.ok).toBe(false);
    expect(named.ok === false && named.message).toContain("Live edits take a number");
    expect(parseLiveValue("").ok).toBe(false);
    expect(parseLiveValue("1 +").ok).toBe(false);
    expect(parseLiveValue("1/0").ok).toBe(false);
  });

  it("is live only while the shown run is the paused debug run", () => {
    const paused = { status: "paused", runId: "r1", pausedInfo: { t: 0.084 } };
    expect(liveModeOf(paused, "r1")).toEqual({ runId: "r1", t: 0.084 });
    expect(liveModeOf(paused, "r2")).toBeNull();
    expect(liveModeOf({ ...paused, status: "running" }, "r1")).toBeNull();
    expect(liveModeOf({ ...paused, status: "done" }, "r1")).toBeNull();
  });

  it("reads the latest live value of a target from the edits", () => {
    const edits = [
      { t: 0.1, kind: "parameter" as const, target: "Motor1/R", value: 3 },
      { t: 0.2, kind: "state" as const, target: "Motor1/R", value: 9 },
      { t: 0.3, kind: "parameter" as const, target: "Motor1/R", value: 4 },
    ];
    expect(latestLiveValue(edits, "Motor1/R")).toBe(4);
    expect(latestLiveValue(edits, "Motor1/L")).toBeNull();
    expect(latestLiveValue(undefined, "Motor1/R")).toBeNull();
  });
});

interface Call {
  url: string;
  method: string;
  body: unknown;
}

function mockFetch(answer: (call: Call) => { status?: number; body: unknown }): Call[] {
  const calls: Call[] = [];
  vi.stubGlobal(
    "fetch",
    vi.fn((url: string, init?: RequestInit) => {
      const call: Call = {
        url,
        method: init?.method ?? "GET",
        body: typeof init?.body === "string" ? (JSON.parse(init.body) as unknown) : null,
      };
      calls.push(call);
      const { status = 200, body } = answer(call);
      return Promise.resolve(
        new Response(JSON.stringify(body), {
          status,
          headers: { "content-type": "application/json" },
        }),
      );
    }),
  );
  return calls;
}

describe("sending a live edit", () => {
  afterEach(() => {
    vi.unstubAllGlobals();
    resetRunStore();
  });

  it("posts the qualified name and the number, and returns the recorded edit", async () => {
    const edit = { t: 0.084, kind: "parameter", target: "Motor1/R", value: 3.5 };
    const calls = mockFetch((call) =>
      call.method === "POST"
        ? { body: { ok: true, edit, diagnostics: [] } }
        : { status: 404, body: { detail: "no manifest" } },
    );
    const result = await sendLiveParameter("r1", "Motor1/R", "3.5");
    expect(result).toEqual({ ok: true, edit });
    const post = calls.find((call) => call.method === "POST");
    expect(post?.url).toContain("/api/runs/r1/debug/setParameter");
    expect(post?.body).toEqual({ name: "Motor1/R", value: 3.5 });
  });

  it("shows the server's refusal with its code and hint, and sends nothing for a non-number", async () => {
    const calls = mockFetch(() => ({
      body: {
        ok: false,
        edit: null,
        diagnostics: [
          {
            code: "E003",
            severity: "error",
            message: "unknown parameter 'R'",
            hint: "write the instance path and the parameter, for example Motor1/R",
          },
        ],
      },
    }));
    const refused = await sendLiveParameter("r1", "R", "3");
    expect(refused.ok).toBe(false);
    expect(refused.ok === false && refused.message).toContain("E003");
    expect(refused.ok === false && refused.message).toContain("Motor1/R");

    calls.length = 0;
    const text = await sendLiveParameter("r1", "Motor1/R", "Rbase");
    expect(text.ok).toBe(false);
    expect(calls).toHaveLength(0);
  });
});

function paused(runId = "r1"): PausedInfo {
  return {
    runId,
    t: 0.084,
    tick: null,
    reason: "breakpoint",
    breakpointId: null,
    location: null,
    frame: null,
    diagnostics: [],
  };
}

function openMotor(): void {
  const motor = catalog.blocks.find((entry) => entry.name === "DCMotor");
  if (motor === undefined) {
    throw new Error("the catalog has no DCMotor");
  }
  const doc = createEmptyModel("LiveTest");
  doc.diagram.nodes = [createNodeFromBlock(motor, { x: 0, y: 0 }, "n1", "Motor1")];
  useDocumentStore.getState().openDocument("demo", "LiveTest", doc);
  useDocumentStore.getState().setSelection(["n1"], []);
}

describe("the inspector in live mode", () => {
  beforeEach(() => {
    resetDocumentStore();
    resetCatalogStore();
    resetRunStore();
    resetDebugStore();
    resetBreakpointStore();
    useCatalogStore.getState().setCatalog(catalog);
    openMotor();
  });

  afterEach(() => {
    vi.unstubAllGlobals();
  });

  function pause(): void {
    useRunStore.setState({ runId: "r1", status: "running" });
    useDebugStore.getState().begin("r1");
    useDebugStore.getState().applyPaused(paused());
  }

  it("shows no banner and edits the model when the run is not paused", () => {
    render(<Inspector />);
    expect(screen.queryByTestId("inspector-live-banner")).toBeNull();
    const field = screen.getByTestId("inspector-param-R") as HTMLInputElement;
    expect(field.dataset.live).toBeUndefined();
    fireEvent.change(field, { target: { value: "5.0" } });
    fireEvent.blur(field);
    expect(useDocumentStore.getState().doc?.diagram.nodes[0]?.params?.R).toBe("5.0");
  });

  it("shows the banner, sends the edit, lists it and leaves the document, undo stack and saved revision alone", async () => {
    pause();
    const before = useDocumentStore.getState();
    const docBefore = before.doc;
    const revisionBefore = before.revision;
    const pastBefore = before.past.length;
    const savedBefore = before.savedRevision;
    const edit = { t: 0.084, kind: "parameter", target: "Motor1/R", value: 5 };
    const calls = mockFetch((call) =>
      call.method === "POST"
        ? { body: { ok: true, edit, diagnostics: [] } }
        : { status: 404, body: { detail: "n/a" } },
    );
    render(<Inspector />);
    expect(screen.getByTestId("inspector-live-banner").textContent).toContain(
      "changes apply to the paused run",
    );

    const field = screen.getByTestId("inspector-param-R") as HTMLInputElement;
    expect(field.dataset.live).toBe("true");
    fireEvent.change(field, { target: { value: "5" } });
    await act(async () => {
      fireEvent.keyDown(field, { key: "Enter" });
    });
    await waitFor(() => {
      expect(calls.some((call) => call.method === "POST")).toBe(true);
    });
    const post = calls.find((call) => call.method === "POST");
    expect(post?.url).toContain("/api/runs/r1/debug/setParameter");
    expect(post?.body).toEqual({ name: "Motor1/R", value: 5 });

    const after = useDocumentStore.getState();
    expect(after.doc).toBe(docBefore);
    expect(after.revision).toBe(revisionBefore);
    expect(after.past.length).toBe(pastBefore);
    expect(after.savedRevision).toBe(savedBefore);
    expect(after.doc?.diagram.nodes[0]?.params?.R).not.toBe("5");
  });

  it("shows the server's refusal inline and refuses a non-number with a hint", async () => {
    pause();
    mockFetch(() => ({
      body: {
        ok: false,
        edit: null,
        diagnostics: [{ code: "E003", severity: "error", message: "unknown parameter 'Motor1/R'" }],
      },
    }));
    render(<Inspector />);
    const field = screen.getByTestId("inspector-param-R") as HTMLInputElement;

    fireEvent.change(field, { target: { value: "Rbase" } });
    expect(screen.getByTestId("inspector-param-R-error").textContent).toContain("Live edits take a number");

    fireEvent.change(field, { target: { value: "7" } });
    await act(async () => {
      fireEvent.keyDown(field, { key: "Enter" });
    });
    await waitFor(() => {
      expect(screen.getByTestId("inspector-param-R-error").textContent).toContain("E003");
    });
  });

  it("returns to the normal fields on resume", () => {
    pause();
    render(<Inspector />);
    expect(screen.getByTestId("inspector-live-banner")).toBeTruthy();
    act(() => {
      useDebugStore.getState().applyResumed("r1");
    });
    expect(screen.queryByTestId("inspector-live-banner")).toBeNull();
    expect((screen.getByTestId("inspector-param-R") as HTMLInputElement).dataset.live).toBeUndefined();
  });
});
