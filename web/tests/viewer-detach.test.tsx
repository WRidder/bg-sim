import { act, render, renderHook, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { NullEngine } from "@babylonjs/core/Engines/nullEngine";

import { useRunStore, resetRunStore } from "../src/plot/runStore";
import type { RunDataFrame } from "../src/plot/runData";
import type { BuiltScene } from "../src/scene/build";
import { resetDocumentStore, useDocumentStore } from "../src/state/documentStore";
import { createEmptyModel } from "../src/state/modelFactory";
import { DetachedViewerWindow } from "../src/viewer/DetachedViewerWindow";
import { useViewerDetachStore } from "../src/viewer/detachStore";
import { useViewerPlayback } from "../src/viewer/playbackHook";

/** A real, separate window and document: an iframe stands in for the popup. */
function fakePopup(): Window {
  const frame = document.createElement("iframe");
  document.body.appendChild(frame);
  const win = frame.contentWindow;
  if (win === null) throw new Error("no iframe window");
  win.focus = () => undefined; // jsdom does not implement focus()
  return win;
}

function stubOpen(win: Window | null): ReturnType<typeof vi.fn> {
  const open = vi.fn(() => win);
  vi.stubGlobal("open", open);
  return open;
}

beforeEach(() => {
  useViewerDetachStore.getState().attach();
  resetDocumentStore();
  resetRunStore();
});

afterEach(() => {
  useViewerDetachStore.getState().attach();
  vi.unstubAllGlobals();
  document.querySelectorAll("iframe").forEach((f) => {
    f.remove();
  });
});

describe("the 3D View detach store", () => {
  it("opens a popup with a portal root, the page theme and the cloned styles", () => {
    document.documentElement.dataset["theme"] = "dark";
    const style = document.createElement("style");
    style.textContent = ".x{color:red}";
    document.head.appendChild(style);
    const popup = fakePopup();
    const open = stubOpen(popup);
    expect(useViewerDetachStore.getState().detach()).toBe(true);
    expect(open).toHaveBeenCalledWith("", "bgsim-3d-view", expect.stringContaining("popup=yes"));
    const state = useViewerDetachStore.getState();
    expect(state.detached).toBe(true);
    expect(state.popup).toBe(popup);
    expect(popup.document.getElementById("bgsim-detached-root")).not.toBeNull();
    expect(popup.document.documentElement.dataset["theme"]).toBe("dark");
    expect(popup.document.head.querySelectorAll("style").length).toBeGreaterThan(0);
    style.remove();
    delete document.documentElement.dataset["theme"];
  });

  it("follows a theme switch of the main window while detached", async () => {
    const popup = fakePopup();
    stubOpen(popup);
    useViewerDetachStore.getState().detach();
    document.documentElement.dataset["theme"] = "light";
    await waitFor(() => expect(popup.document.documentElement.dataset["theme"]).toBe("light"));
    delete document.documentElement.dataset["theme"];
  });

  it("reports a blocked popup and stays docked", () => {
    stubOpen(null);
    expect(useViewerDetachStore.getState().detach()).toBe(false);
    const state = useViewerDetachStore.getState();
    expect(state.detached).toBe(false);
    expect(state.error).toMatch(/blocked the 3D view window.*Allow pop-ups/);
  });

  it("docks again when the popup closes or when attach is called", () => {
    const popup = fakePopup();
    stubOpen(popup);
    useViewerDetachStore.getState().detach();
    act(() => {
      popup.dispatchEvent(new Event("pagehide"));
    });
    expect(useViewerDetachStore.getState().detached).toBe(false);

    const again = fakePopup();
    stubOpen(again);
    useViewerDetachStore.getState().detach();
    expect(useViewerDetachStore.getState().detached).toBe(true);
    useViewerDetachStore.getState().attach();
    expect(useViewerDetachStore.getState().detached).toBe(false);
    expect(useViewerDetachStore.getState().popup).toBeNull();
  });
});

function nullEngine(): NullEngine {
  return new NullEngine({ renderWidth: 64, renderHeight: 64, textureSize: 64, deterministicLockstep: false, lockstepMaxSteps: 1, useHighPrecisionMatrix: true });
}

describe("DetachedViewerWindow", () => {
  it("renders into the popup with the popup's frame clock and disposes the engine on dock", async () => {
    const popup = fakePopup();
    const popupFrames = vi.fn((cb: FrameRequestCallback) => window.setTimeout(() => { cb(0); }, 0));
    Object.assign(popup, { requestAnimationFrame: popupFrames, cancelAnimationFrame: (id: number) => { window.clearTimeout(id); } });
    const mainFrames = vi.spyOn(window, "requestAnimationFrame");
    stubOpen(popup);
    const engines: NullEngine[] = [];
    const { container } = render(
      <DetachedViewerWindow
        createEngine={() => {
          const e = nullEngine();
          engines.push(e);
          return e;
        }}
      />,
    );
    expect(container.querySelector("canvas")).toBeNull(); // nothing in the main window
    act(() => {
      useViewerDetachStore.getState().detach();
    });
    const popupDocument = popup.document; // a closed window has no document any more
    const canvas = popupDocument.querySelector("canvas");
    expect(canvas).not.toBeNull();
    expect(canvas?.ownerDocument).toBe(popupDocument);
    expect(popup.document.querySelector('[data-testid="dock-viewer-button"]')?.textContent).toBe("Dock");
    expect(engines).toHaveLength(1);
    expect(engines[0]?.scenes).toHaveLength(1);
    await waitFor(() => expect(Number((popup.document.querySelector('[data-testid="viewer"]') as HTMLElement).dataset["frames"])).toBeGreaterThanOrEqual(1));
    expect(popupFrames).toHaveBeenCalled();
    expect(mainFrames).not.toHaveBeenCalled();

    act(() => {
      useViewerDetachStore.getState().attach();
    });
    expect(popupDocument.querySelector("canvas")).toBeNull();
    expect(engines[0]?.scenes).toHaveLength(0);
    mainFrames.mockRestore();
  });

  it("closing the popup also disposes the engine", () => {
    const popup = fakePopup();
    stubOpen(popup);
    const engines: NullEngine[] = [];
    render(
      <DetachedViewerWindow
        createEngine={() => {
          const e = nullEngine();
          engines.push(e);
          return e;
        }}
      />,
    );
    act(() => {
      useViewerDetachStore.getState().detach();
    });
    expect(engines[0]?.scenes).toHaveLength(1);
    act(() => {
      popup.dispatchEvent(new Event("pagehide"));
    });
    expect(engines[0]?.scenes).toHaveLength(0);
  });
});

describe("useViewerPlayback over a failing stream", () => {
  class FakeSocket {
    binaryType = "";
    onmessage: ((e: MessageEvent) => void) | null = null;
    onclose: ((e: CloseEvent) => void) | null = null;
    onerror: (() => void) | null = null;
    close(): void {
      /* nothing to release */
    }
  }

  const built = new Proxy({}, { get: () => () => true }) as unknown as BuiltScene;
  const data: RunDataFrame = {
    nSignals: 1,
    nPoints: 3,
    time: Float64Array.from([0, 0.5, 1]),
    values: [Float64Array.from([0, 1, 2])],
  };

  function openRun(status: "running" | "done"): void {
    const doc = createEmptyModel("M");
    doc.bindings = [{ target: "joint:j1", property: "position", signal: "A/x" }];
    useDocumentStore.getState().openDocument("p", "M", doc);
    useRunStore.setState({ runId: "r1", status });
  }

  it("keeps a failed live stream's error, then loads the finished run over HTTP", async () => {
    openRun("running");
    const sockets: FakeSocket[] = [];
    const fetchData = vi.fn(() => Promise.resolve(data));
    const { result } = renderHook(() =>
      useViewerPlayback(built, true, null, {
        makeSocket: () => {
          const s = new FakeSocket();
          sockets.push(s);
          return s as unknown as WebSocket;
        },
        fetchData,
      }),
    );
    await waitFor(() => expect(sockets).toHaveLength(1));
    act(() => {
      sockets[0]?.onclose?.({ code: 1006, reason: "" } as CloseEvent);
    });
    expect(result.current.streamError).toMatch(/live 3D stream was dropped \(1006\).*HTTP when the run is done/);
    expect(fetchData).not.toHaveBeenCalled();

    act(() => {
      useRunStore.setState({ status: "done" });
    });
    await waitFor(() => expect(result.current.snapshot.mode).toBe("playback"));
    expect(fetchData).toHaveBeenCalledWith("r1", ["A/x"], null, 0, expect.anything());
    expect(result.current.snapshot.end).toBe(1);
    expect(result.current.streamError).toBeNull();
    expect(result.current.streamNote).toMatch(/loaded the finished run over HTTP/);
  });

  it("loads a finished run over HTTP at once when its stream closes with 1006", async () => {
    openRun("done");
    const fetchData = vi.fn(() => Promise.resolve(data));
    const { result } = renderHook(() =>
      useViewerPlayback(built, true, null, {
        makeSocket: () => {
          const s = new FakeSocket();
          queueMicrotask(() => s.onclose?.({ code: 1006, reason: "" } as CloseEvent));
          return s as unknown as WebSocket;
        },
        fetchData,
      }),
    );
    await waitFor(() => expect(result.current.snapshot.mode).toBe("playback"));
    expect(result.current.snapshot.end).toBe(1);
    expect(result.current.streamNote).toMatch(/dropped \(1006\).*over HTTP/);
    expect(result.current.streamError).toBeNull();
  });
});
