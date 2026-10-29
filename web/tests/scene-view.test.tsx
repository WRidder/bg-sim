import { readFileSync } from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { act, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { NullEngine } from "@babylonjs/core/Engines/nullEngine";
import type { Mesh } from "@babylonjs/core/Meshes/mesh";
import { resetDiagnosticsStore, useDiagnosticsStore } from "../src/diagnostics/store";
import { SceneView } from "../src/scene/SceneView";
import { resetDocumentStore, useDocumentStore } from "../src/state/documentStore";
import { createEmptyModel } from "../src/state/modelFactory";

const here = path.dirname(fileURLToPath(import.meta.url));
const fixture = (name: string): string => readFileSync(path.join(here, "fixtures", "scenes", name), "utf8");

const engines: NullEngine[] = [];
function createEngine(): NullEngine {
  const e = new NullEngine({
    renderWidth: 64,
    renderHeight: 64,
    textureSize: 64,
    deterministicLockstep: false,
    lockstepMaxSteps: 1,
    useHighPrecisionMatrix: true,
  });
  engines.push(e);
  return e;
}

function openModel(scene: string | null): void {
  const doc = createEmptyModel("M");
  doc.scene = scene === null ? null : { file: scene };
  useDocumentStore.getState().openDocument("p", "M", doc);
}

function serve(files: Record<string, string | number>): void {
  vi.stubGlobal(
    "fetch",
    vi.fn((input: RequestInfo | URL) => {
      const name = decodeURIComponent(String(input).split("/").pop() ?? "");
      const body = files[name];
      if (typeof body === "string") return Promise.resolve(new Response(body, { status: 200 }));
      return Promise.resolve(new Response("not found", { status: typeof body === "number" ? body : 404 }));
    }),
  );
}

beforeEach(() => {
  resetDiagnosticsStore();
  resetDocumentStore();
});

afterEach(() => {
  vi.unstubAllGlobals();
  engines.length = 0;
});

describe("SceneView", () => {
  it("tells how to add a scene when the model has none", () => {
    openModel(null);
    const { unmount } = render(<SceneView active createEngine={createEngine} />);
    expect(screen.getByTestId("scene-view").dataset["state"]).toBe("none");
    expect(screen.getByText("No 3D scene")).toBeTruthy();
    expect(screen.getByText(/scenes\/ folder/)).toBeTruthy();
    expect(screen.queryByTestId("scene-tree")).toBeNull();
    unmount();
    expect(engines.every((e) => e.scenes.length === 0)).toBe(true);
  });

  it("loads the scene, lists it as a tree, fits, and links tree rows with the outline both ways", async () => {
    serve({ "chain.sdf": fixture("chain.sdf") });
    openModel("scenes/chain.sdf");
    const { unmount } = render(<SceneView active createEngine={createEngine} />);
    await waitFor(() => expect(screen.getByTestId("scene-view").dataset["state"]).toBe("loaded"));
    for (const ref of ["model:chain", "link:base", "link:l1", "link:l2", "joint:j1", "joint:j2", "visual:l1_visual"]) {
      expect(screen.getByTestId(`scene-tree-row-${ref}`)).toBeTruthy();
    }
    expect(screen.getByTestId("scene-tree-row-joint:j1").dataset["kind"]).toBe("joint");
    expect(useDiagnosticsStore.getState().viewerDiagnostics).toEqual([]);

    // tree -> 3D: selecting a link outlines its visuals
    const viewerScene = engines.at(-1)?.scenes[0];
    const outlined = () => viewerScene?.meshes.filter((m) => (m as Mesh).renderOutline).map((m) => m.name).sort();
    fireEvent.click(screen.getByTestId("scene-tree-row-link:l1"));
    expect(screen.getByTestId("scene-tree-row-link:l1").getAttribute("aria-pressed")).toBe("true");
    expect(outlined()).toEqual(["visual:l1_visual"]);
    // a joint outlines the link it moves
    fireEvent.click(screen.getByTestId("scene-tree-row-joint:j2"));
    expect(outlined()).toEqual(["visual:l2_visual"]);
    // clicking the selected row again clears it
    fireEvent.click(screen.getByTestId("scene-tree-row-joint:j2"));
    expect(outlined()).toEqual([]);

    unmount();
    expect(engines.every((e) => e.scenes.length === 0)).toBe(true);
  });

  it("selects the tree row of an entity picked in the view", async () => {
    serve({ "chain.sdf": fixture("chain.sdf") });
    openModel("scenes/chain.sdf");
    render(<SceneView active createEngine={createEngine} />);
    await waitFor(() => expect(screen.getByTestId("scene-view").dataset["state"]).toBe("loaded"));
    const canvas = screen.getByTestId("viewer-canvas");
    const pointer = (type: string): Event =>
      Object.assign(new Event(type, { bubbles: true, cancelable: true }), { pointerId: 1, button: 0, offsetX: 32, offsetY: 32 });
    // the fit view looks at the middle of the scene: the nearest entity centre within the touch radius is picked
    act(() => {
      canvas.dispatchEvent(pointer("pointerdown"));
      canvas.dispatchEvent(pointer("pointerup"));
    });
    const pressed = screen.queryAllByRole("button", { pressed: true }).filter((b) => b.getAttribute("data-testid")?.startsWith("scene-tree-row-visual:"));
    expect(pressed).toHaveLength(1);
    expect(pressed[0]?.getAttribute("data-testid")).toMatch(/^scene-tree-row-visual:/);
  });

  it("collapses the tree and its branches", async () => {
    serve({ "chain.sdf": fixture("chain.sdf") });
    openModel("scenes/chain.sdf");
    render(<SceneView active createEngine={createEngine} />);
    await waitFor(() => expect(screen.getByTestId("scene-view").dataset["state"]).toBe("loaded"));
    fireEvent.click(screen.getByLabelText("Collapse l1"));
    expect(screen.queryByTestId("scene-tree-row-visual:l1_visual")).toBeNull();
    fireEvent.click(screen.getByTestId("scene-tree-toggle"));
    expect(screen.queryByTestId("scene-tree-row-link:l1")).toBeNull();
  });

  it("reports a missing scene file as E305 in the diagnostics store", async () => {
    serve({});
    openModel("scenes/gone.sdf");
    render(<SceneView active createEngine={createEngine} />);
    await waitFor(() => expect(screen.getByTestId("scene-view").dataset["state"]).toBe("error"));
    const [d] = useDiagnosticsStore.getState().viewerDiagnostics;
    expect(d).toMatchObject({ code: "E305", severity: "error", path: null });
    expect(d?.message).toContain("gone.sdf");
    expect(d?.hint).toBeTruthy();
    expect(useDiagnosticsStore.getState().counts.error).toBe(1);
    expect(screen.getByText("The scene could not be shown")).toBeTruthy();
  });

  it("publishes E306 for skipped elements, keeps drawing, and clears them on unmount", async () => {
    serve({
      "ball.sdf": '<sdf version="1.7"><model name="m"><link name="a"><visual name="v"><geometry><box><size>1 1 1</size></box></geometry></visual></link><link name="b"/><joint name="s" type="ball"><parent>a</parent><child>b</child></joint></model></sdf>',
    });
    openModel("scenes/ball.sdf");
    const { unmount } = render(<SceneView active createEngine={createEngine} />);
    await waitFor(() => expect(screen.getByTestId("scene-view").dataset["state"]).toBe("loaded"));
    expect(useDiagnosticsStore.getState().viewerDiagnostics.map((d) => d.code)).toEqual(["E306"]);
    expect(useDiagnosticsStore.getState().counts.error).toBe(1);
    unmount();
    expect(useDiagnosticsStore.getState().viewerDiagnostics).toEqual([]);
    expect(useDiagnosticsStore.getState().counts.error).toBe(0);
  });

  it("rebuilds when the model's scene changes, without leaving the old scene behind", async () => {
    serve({ "chain.sdf": fixture("chain.sdf"), "frames.sdf": fixture("frames.sdf") });
    openModel("scenes/chain.sdf");
    render(<SceneView active createEngine={createEngine} />);
    await waitFor(() => expect(screen.getByTestId("scene-tree-row-link:l1")).toBeTruthy());
    const scene = engines.at(-1)?.scenes[0];
    act(() => {
      openModel("scenes/frames.sdf");
    });
    await waitFor(() => expect(screen.getByTestId("scene-tree-row-link:slider")).toBeTruthy());
    expect(screen.queryByTestId("scene-tree-row-link:l1")).toBeNull();
    expect(scene?.getTransformNodeByName("link:l1")).toBeNull();
  });
});
