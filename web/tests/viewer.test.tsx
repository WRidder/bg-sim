import { StrictMode } from "react";
import { act, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { NullEngine } from "@babylonjs/core/Engines/nullEngine";
import { CreateBox } from "@babylonjs/core/Meshes/Builders/boxBuilder";
import { Viewer } from "../src/viewer/Viewer";
import { tagEntity, type ViewerScene } from "../src/viewer/viewerScene";

const SIZE = 64;

function nullEngine(): NullEngine {
  return new NullEngine({
    renderWidth: SIZE,
    renderHeight: SIZE,
    textureSize: SIZE,
    deterministicLockstep: false,
    lockstepMaxSteps: 1,
    useHighPrecisionMatrix: true,
  });
}

const frames = () => Number(screen.getByTestId("viewer").dataset["frames"]);
const state = () => screen.getByTestId("viewer").dataset["state"];

function setHidden(hidden: boolean): void {
  Object.defineProperty(document, "hidden", { configurable: true, get: () => hidden });
  document.dispatchEvent(new Event("visibilitychange"));
}

function pointer(type: string, init: { x: number; y: number; button?: number }): Event {
  const event = new Event(type, { bubbles: true, cancelable: true });
  return Object.assign(event, { pointerId: 1, button: init.button ?? 0, offsetX: init.x, offsetY: init.y });
}

afterEach(() => {
  Reflect.deleteProperty(document, "hidden");
});

describe("Viewer", () => {
  it("creates an engine and a scene, draws an idle first frame, and disposes both on unmount", async () => {
    const engines: NullEngine[] = [];
    const handles: (ViewerScene | null)[] = [];
    const { unmount } = render(
      <Viewer
        createEngine={() => {
          const e = nullEngine();
          engines.push(e);
          return e;
        }}
        onReady={(s) => handles.push(s)}
      />,
    );
    expect(engines).toHaveLength(1);
    expect(engines[0]?.scenes).toHaveLength(1);
    await waitFor(() => expect(frames()).toBeGreaterThanOrEqual(1));
    await waitFor(() => expect(state()).toBe("idle"));
    expect(handles[0]?.root.name).toBe("sdf_root");

    unmount();
    expect(engines[0]?.scenes).toHaveLength(0);
    expect(handles.at(-1)).toBeNull();
  });

  it("leaves no scene behind under StrictMode's double mount", () => {
    const engines: NullEngine[] = [];
    const { unmount } = render(
      <StrictMode>
        <Viewer
          createEngine={() => {
            const e = nullEngine();
            engines.push(e);
            return e;
          }}
        />
      </StrictMode>,
    );
    unmount();
    expect(engines.length).toBeGreaterThanOrEqual(1);
    for (const e of engines) expect(e.scenes).toHaveLength(0);
  });

  it("draws nothing more while stationary", async () => {
    render(<Viewer createEngine={nullEngine} />);
    // the first frames (and the redraw once shaders are ready) settle, then nothing more is drawn
    await waitFor(() => expect(state()).toBe("idle"));
    await new Promise((r) => setTimeout(r, 200));
    const settled = frames();
    await new Promise((r) => setTimeout(r, 300));
    expect(frames()).toBe(settled);
  });

  it("draws again when the scene asks for it", async () => {
    let scene: ViewerScene | null = null;
    render(
      <Viewer
        createEngine={nullEngine}
        onReady={(s) => {
          scene = s;
        }}
      />,
    );
    await waitFor(() => expect(state()).toBe("idle"));
    const before = frames();
    act(() => {
      (scene as ViewerScene | null)?.invalidate();
    });
    await waitFor(() => expect(frames()).toBeGreaterThan(before));
  });

  it("queues one more frame when a frame was drawn before the shaders were ready", async () => {
    let scene: ViewerScene | null = null;
    render(
      <Viewer
        createEngine={nullEngine}
        onReady={(s) => {
          scene = s;
        }}
      />,
    );
    await waitFor(() => expect(state()).toBe("idle"));
    const s = scene as ViewerScene | null;
    if (s === null) throw new Error("the viewer did not hand out its scene");
    vi.spyOn(s.scene, "isReady").mockReturnValueOnce(false);
    const before = frames();
    act(() => {
      s.invalidate();
    });
    // the frame itself, then the redraw once the scene reports ready
    await waitFor(() => expect(frames()).toBeGreaterThanOrEqual(before + 2));
  });

  it("stops drawing while the page is hidden and resumes when it is shown", async () => {
    let scene: ViewerScene | null = null;
    render(
      <Viewer
        createEngine={nullEngine}
        onReady={(s) => {
          scene = s;
        }}
      />,
    );
    await waitFor(() => expect(state()).toBe("idle"));
    act(() => {
      setHidden(true);
    });
    const hiddenAt = frames();
    act(() => {
      (scene as ViewerScene | null)?.invalidate();
    });
    await new Promise((r) => setTimeout(r, 100));
    expect(frames()).toBe(hiddenAt);
    act(() => {
      setHidden(false);
    });
    await waitFor(() => expect(frames()).toBeGreaterThan(hiddenAt));
  });

  it("stops drawing while its dock tab is not active", async () => {
    let scene: ViewerScene | null = null;
    const onReady = (s: ViewerScene | null) => {
      scene = s;
    };
    const { rerender } = render(<Viewer createEngine={nullEngine} onReady={onReady} active />);
    await waitFor(() => expect(state()).toBe("idle"));
    rerender(<Viewer createEngine={nullEngine} onReady={onReady} active={false} />);
    const inactiveAt = frames();
    act(() => {
      (scene as ViewerScene | null)?.invalidate();
    });
    await new Promise((r) => setTimeout(r, 100));
    expect(frames()).toBe(inactiveAt);
    rerender(<Viewer createEngine={nullEngine} onReady={onReady} active />);
    await waitFor(() => expect(frames()).toBeGreaterThan(inactiveAt));
  });

  it("shows the no-3D fallback when no engine can be created", async () => {
    const createEngine = vi.fn(() => {
      throw new Error("WebGL is not supported");
    });
    render(<Viewer createEngine={createEngine} />);
    expect(state()).toBe("no-webgl");
    const failure = await screen.findByTestId("viewer-failure");
    expect(failure.textContent).toContain("No 3D rendering on this device");
    expect(failure.textContent).toContain("WebGL is not supported");
  });

  it("prevents the context menu and the page scroll of the wheel", () => {
    render(<Viewer createEngine={nullEngine} />);
    const canvas = screen.getByTestId("viewer-canvas");
    expect(fireEvent.contextMenu(canvas)).toBe(false);
    expect(fireEvent.wheel(canvas, { deltaY: 100 })).toBe(false);
  });

  it("selects on a tap and not after a drag", async () => {
    let scene: ViewerScene | null = null;
    const onSelect = vi.fn();
    render(
      <Viewer
        createEngine={nullEngine}
        onSelect={onSelect}
        onReady={(s) => {
          scene = s;
        }}
      />,
    );
    const s = scene as ViewerScene | null;
    if (s === null) throw new Error("the viewer did not hand out its scene");
    const box = CreateBox("part", { size: 1 }, s.scene);
    box.parent = s.root;
    box.position.set(0, 0, 0.5);
    tagEntity(box, "body:part");
    s.fit("front");
    await waitFor(() => expect(state()).toBe("idle"));
    s.scene.render();
    const canvas = screen.getByTestId("viewer-canvas");

    canvas.dispatchEvent(pointer("pointerdown", { x: 32, y: 32 }));
    canvas.dispatchEvent(pointer("pointerup", { x: 34, y: 33 }));
    expect(onSelect).toHaveBeenLastCalledWith("body:part");

    canvas.dispatchEvent(pointer("pointerdown", { x: 32, y: 32 }));
    canvas.dispatchEvent(pointer("pointerup", { x: 52, y: 32 }));
    expect(onSelect).toHaveBeenCalledTimes(1);

    canvas.dispatchEvent(pointer("pointerdown", { x: 32, y: 32, button: 2 }));
    canvas.dispatchEvent(pointer("pointerup", { x: 32, y: 32, button: 2 }));
    expect(onSelect).toHaveBeenCalledTimes(1);
  });

  it("outlines the selection it is given", async () => {
    let scene: ViewerScene | null = null;
    const props = {
      createEngine: nullEngine,
      onReady: (s: ViewerScene | null) => {
        scene = s;
      },
    };
    const { rerender } = render(<Viewer {...props} />);
    const s = scene as ViewerScene | null;
    if (s === null) throw new Error("the viewer did not hand out its scene");
    const box = CreateBox("part", { size: 1 }, s.scene);
    tagEntity(box, "body:part");
    rerender(<Viewer {...props} selection={["body:part"]} />);
    expect(box.renderOutline).toBe(true);
    rerender(<Viewer {...props} selection={[]} />);
    expect(box.renderOutline).toBe(false);
  });

  it("switches the projection and presets from its toolbar", async () => {
    let scene: ViewerScene | null = null;
    render(
      <Viewer
        createEngine={nullEngine}
        onReady={(s) => {
          scene = s;
        }}
      />,
    );
    const s = scene as ViewerScene | null;
    if (s === null) throw new Error("the viewer did not hand out its scene");
    fireEvent.click(screen.getByTestId("viewer-ortho"));
    expect(s.orthographic).toBe(true);
    expect(screen.getByTestId("viewer-ortho").getAttribute("aria-pressed")).toBe("true");
    fireEvent.click(screen.getByTestId("viewer-preset-front"));
    const d = s.camera.position.subtract(s.camera.target).normalize();
    expect(d.x).toBeCloseTo(1, 6);
  });
});
