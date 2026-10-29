import { useEffect, useRef, useState, type ReactNode } from "react";
import type { AbstractEngine } from "@babylonjs/core/Engines/abstractEngine";
import { Engine } from "@babylonjs/core/Engines/engine";
import { Color3 } from "@babylonjs/core/Maths/math.color";
import { hardwareScaling, RenderScheduler, windowClock } from "./renderScheduler";
import { TAP_SLOP_PX } from "./picking";
import { ViewerScene, type CameraPreset, type ViewerColours } from "./viewerScene";
import "./viewer.css";

/** `idle`: nothing to draw. `rendering`: a frame is queued or the view is still moving. `no-webgl`: no engine could be created. */
export type ViewerState = "idle" | "rendering" | "no-webgl";

export interface ViewerProps {
  /** The engine for a canvas (default: WebGL). A test seam: tests inject a NullEngine. */
  readonly createEngine?: ((canvas: HTMLCanvasElement) => AbstractEngine) | undefined;
  /** False while the viewer is on a hidden dock tab: nothing is drawn. */
  readonly active?: boolean | undefined;
  /** Device-pixel-ratio ceiling for the render resolution. */
  readonly dprCap?: number | undefined;
  /** The scene handle once the engine and scene exist, null after they are disposed. */
  readonly onReady?: ((scene: ViewerScene | null) => void) | undefined;
  /** A tap picked an entity (or empty space: null). */
  readonly onSelect?: ((ref: string | null) => void) | undefined;
  /** Entities to outline. */
  readonly selection?: readonly string[] | undefined;
  /** Shown over a corner of the view; the grid and axes are drawn behind it. */
  readonly overlay?: ReactNode;
  /** Appended to the toolbar (the 3D View's Detach / Dock button). */
  readonly toolbarEnd?: ReactNode;
}

const DEFAULT_DPR_CAP = 1.5;
const PRESETS: readonly { readonly id: CameraPreset; readonly label: string }[] = [
  { id: "iso", label: "Iso" },
  { id: "top", label: "Top" },
  { id: "front", label: "Front" },
  { id: "side", label: "Side" },
];
const NO_SELECTION: readonly string[] = [];

function webglEngine(canvas: HTMLCanvasElement): AbstractEngine {
  return new Engine(canvas, true, { useHighPrecisionMatrix: true, stencil: true, preserveDrawingBuffer: false, adaptToDeviceRatio: false, canvasTabIndex: 0 });
}

/** The window an element is shown in: the opener, or a popup the view was detached to. */
function windowOf(el: Element): Window & typeof globalThis {
  return (el.ownerDocument.defaultView as (Window & typeof globalThis) | null) ?? window;
}

function tokenColour(el: Element, name: string, fallback: Color3): Color3 {
  const v = windowOf(el).getComputedStyle(el).getPropertyValue(name).trim();
  if (/^#[0-9a-f]{6}$/i.test(v)) return Color3.FromHexString(v);
  const m = /^rgba?\((\d+),\s*(\d+),\s*(\d+)/.exec(v);
  return m ? new Color3(Number(m[1]) / 255, Number(m[2]) / 255, Number(m[3]) / 255) : fallback;
}

function themeColours(host: Element): ViewerColours {
  return {
    grid: tokenColour(host, "--color-border-strong", Color3.Gray()),
    axisX: tokenColour(host, "--color-error", Color3.Red()),
    axisY: tokenColour(host, "--color-ok", Color3.Green()),
    axisZ: tokenColour(host, "--color-accent", Color3.Blue()),
    selection: tokenColour(host, "--color-focus", Color3.White()),
  };
}

interface Shown {
  page: boolean;
  inView: boolean;
  active: boolean;
  apply: () => void;
}

/**
 * The 3D view (plan 7.6): a Babylon engine and scene per mount, drawn on demand by a
 * `RenderScheduler` and paused while the page, the canvas or the dock tab is hidden.
 * `data-state` and `data-frames` on the root expose the state for e2e tests.
 */
export function Viewer(props: ViewerProps) {
  const hostRef = useRef<HTMLDivElement>(null);
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const sceneRef = useRef<ViewerScene | null>(null);
  const propsRef = useRef(props);
  useEffect(() => {
    propsRef.current = props;
  });
  const shownRef = useRef<Shown>({ page: true, inView: true, active: props.active !== false, apply: () => undefined });
  const [failure, setFailure] = useState<string | null>(null);
  const [ortho, setOrtho] = useState(false);

  // One effect per scene: engine, scene and scheduler are created and disposed together.
  useEffect(() => {
    const canvas = canvasRef.current;
    const host = hostRef.current;
    if (!canvas || !host) return;
    let disposed = false;
    let engine: AbstractEngine;
    try {
      engine = (propsRef.current.createEngine ?? webglEngine)(canvas);
    } catch (e) {
      host.dataset["state"] = "no-webgl";
      const why = `no 3D rendering on this device: ${e instanceof Error ? e.message : String(e)}`;
      queueMicrotask(() => {
        if (!disposed) setFailure(why);
      });
      return () => {
        disposed = true;
      };
    }
    const cap = propsRef.current.dprCap ?? DEFAULT_DPR_CAP;
    // Everything that belongs to the screen is the hosting window's: after a detach that is the popup.
    const doc = canvas.ownerDocument;
    const win = windowOf(canvas);
    engine.setHardwareScalingLevel(hardwareScaling(win.devicePixelRatio, cap));

    // Shaders compile asynchronously: a frame drawn before they are ready lacks those meshes, and an
    // on-demand scheduler would never draw another. One redraw is queued for when the scene is ready.
    let waitingForShaders = false;
    const scheduler: RenderScheduler = new RenderScheduler(() => {
      scene.scene.render();
      if (!waitingForShaders && !scene.scene.isReady()) {
        waitingForShaders = true;
        scene.scene.executeWhenReady(() => {
          waitingForShaders = false;
          if (!disposed) scheduler.invalidate();
        });
      }
      const moving = scene.cameraMoving;
      host.dataset["state"] = moving ? "rendering" : "idle";
      host.dataset["frames"] = String(scheduler.frames);
      return moving;
    }, windowClock(win));
    const scene = new ViewerScene(engine, () => {
      if (disposed) return;
      host.dataset["state"] = "rendering";
      scheduler.invalidate();
    });
    scene.setColours(themeColours(host));
    // Babylon tab-indexes the canvas at 1, which jumps the focus order (axe: tabindex); 0 keeps DOM order.
    engine.canvasTabIndex = 0;
    scene.attachControl();
    sceneRef.current = scene;
    host.dataset["state"] = "rendering";
    host.dataset["frames"] = "0";

    const shown = shownRef.current;
    shown.apply = () => {
      scheduler.setVisible(shown.page && shown.inView && shown.active);
    };
    shown.page = !doc.hidden;
    shown.apply();

    const wake = () => {
      scheduler.invalidate();
    };
    const onVisibility = () => {
      shown.page = !doc.hidden;
      shown.apply();
    };
    doc.addEventListener("visibilitychange", onVisibility);
    const io =
      typeof win.IntersectionObserver !== "undefined"
        ? new win.IntersectionObserver((entries) => {
            const e = entries[entries.length - 1];
            if (disposed || !e) return;
            shown.inView = e.isIntersecting;
            shown.apply();
          })
        : null;
    io?.observe(canvas);
    const ro =
      typeof win.ResizeObserver !== "undefined"
        ? new win.ResizeObserver(() => {
            if (disposed) return;
            engine.setHardwareScalingLevel(hardwareScaling(win.devicePixelRatio, cap));
            engine.resize();
            wake();
          })
        : null;
    ro?.observe(canvas);
    // A theme switch changes the token colours of the grid, axes and outline.
    const themeWatch =
      typeof win.MutationObserver !== "undefined"
        ? new win.MutationObserver(() => {
            if (disposed) return;
            scene.setColours(themeColours(host));
          })
        : null;
    themeWatch?.observe(doc.documentElement, { attributes: true, attributeFilter: ["data-theme"] });

    const noMenu = (e: Event) => {
      e.preventDefault();
    };
    // Non-passive: the wheel zooms the view, it must not scroll the page.
    const onWheel = (e: WheelEvent) => {
      e.preventDefault();
      wake();
    };
    let down: { id: number; x: number; y: number } | null = null;
    const onDown = (e: PointerEvent) => {
      down = e.button === 0 ? { id: e.pointerId, x: e.offsetX, y: e.offsetY } : null;
      wake();
    };
    const onUp = (e: PointerEvent) => {
      wake();
      if (!down || e.pointerId !== down.id) return;
      const moved = Math.hypot(e.offsetX - down.x, e.offsetY - down.y);
      down = null;
      if (moved > TAP_SLOP_PX) return;
      propsRef.current.onSelect?.(scene.pickEntity(e.offsetX, e.offsetY));
    };
    const onCancel = () => {
      down = null;
    };
    canvas.addEventListener("contextmenu", noMenu);
    canvas.addEventListener("wheel", onWheel, { passive: false });
    canvas.addEventListener("pointerdown", onDown);
    canvas.addEventListener("pointermove", wake, { passive: true });
    canvas.addEventListener("pointerup", onUp);
    canvas.addEventListener("pointercancel", onCancel);

    propsRef.current.onReady?.(scene);
    scene.highlight(propsRef.current.selection ?? NO_SELECTION);

    return () => {
      disposed = true;
      propsRef.current.onReady?.(null);
      doc.removeEventListener("visibilitychange", onVisibility);
      io?.disconnect();
      ro?.disconnect();
      themeWatch?.disconnect();
      canvas.removeEventListener("contextmenu", noMenu);
      canvas.removeEventListener("wheel", onWheel);
      canvas.removeEventListener("pointerdown", onDown);
      canvas.removeEventListener("pointermove", wake);
      canvas.removeEventListener("pointerup", onUp);
      canvas.removeEventListener("pointercancel", onCancel);
      scene.detachControl();
      scheduler.dispose();
      scene.dispose();
      engine.dispose();
      sceneRef.current = null;
    };
  }, []);

  // The dock (or whoever hosts the viewer) shows and hides it.
  const active = props.active !== false;
  useEffect(() => {
    const shown = shownRef.current;
    shown.active = active;
    shown.apply();
  }, [active]);

  useEffect(() => {
    sceneRef.current?.highlight(props.selection ?? NO_SELECTION);
  }, [props.selection]);

  function toggleOrtho() {
    const next = !ortho;
    setOrtho(next);
    sceneRef.current?.setOrthographic(next);
  }

  return (
    <div className="viewer" data-testid="viewer" ref={hostRef} data-state="rendering">
      <canvas className="viewer__canvas" data-testid="viewer-canvas" ref={canvasRef} />
      {failure === null ? (
        <>
          <div className="viewer__toolbar" role="toolbar" aria-label="3D view">
            {PRESETS.map((p) => (
              <button
                key={p.id}
                type="button"
                className="viewer__button"
                data-testid={`viewer-preset-${p.id}`}
                onClick={() => sceneRef.current?.fit(p.id)}
              >
                {p.label}
              </button>
            ))}
            <button type="button" className="viewer__button" data-testid="viewer-fit" onClick={() => sceneRef.current?.fit()}>
              Fit
            </button>
            <button type="button" className="viewer__button" data-testid="viewer-ortho" aria-pressed={ortho} onClick={toggleOrtho}>
              Ortho
            </button>
            {props.toolbarEnd}
          </div>
          {props.overlay ? <div className="viewer__overlay">{props.overlay}</div> : null}
        </>
      ) : (
        <div className="viewer__failure" role="alert" data-testid="viewer-failure">
          <p className="empty-state__title">No 3D rendering on this device</p>
          <p className="empty-state__hint">{failure}. Try a browser with WebGL enabled; the rest of the editor works without the 3D view.</p>
        </div>
      )}
    </div>
  );
}
