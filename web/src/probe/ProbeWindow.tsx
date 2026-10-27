import { useRef, useState } from "react";

import type { Model, ModelProbe } from "../contracts/model";
import { useDocumentStore } from "../state/documentStore";
import { ProbeGlyph } from "./ProbeGlyph";
import { ProbePlot } from "./ProbePlot";
import "./probe.css";

interface Frame {
  x: number;
  y: number;
  width: number;
  height: number;
}

function initialFrame(probe: ModelProbe): Frame {
  return {
    x: probe.panelPosition?.x ?? 80,
    y: probe.panelPosition?.y ?? 80,
    width: probe.size?.width ?? 380,
    height: probe.size?.height ?? 240,
  };
}

export function ProbeWindow({ model, probe }: { model: Model; probe: ModelProbe }) {
  const [frame, setFrame] = useState<Frame>(() => initialFrame(probe));
  const latestFrame = useRef(frame);
  latestFrame.current = frame;
  const dragRef = useRef<{ mode: "move" | "resize"; startX: number; startY: number; frame: Frame } | null>(
    null,
  );

  if (!(probe.open ?? true)) {
    return null;
  }

  const start = (
    mode: "move" | "resize",
    event: React.PointerEvent<HTMLElement>,
  ): void => {
    if (event.button !== 0) {
      return;
    }
    event.preventDefault();
    event.stopPropagation();
    const current = initialFrame(probe);
    setFrame(current);
    dragRef.current = {
      mode,
      startX: event.clientX,
      startY: event.clientY,
      frame: current,
    };
    const move = (moveEvent: PointerEvent): void => {
      const drag = dragRef.current;
      if (drag === null) {
        return;
      }
      const dx = moveEvent.clientX - drag.startX;
      const dy = moveEvent.clientY - drag.startY;
      if (drag.mode === "move") {
        setFrame({
          ...drag.frame,
          x: Math.max(0, drag.frame.x + dx),
          y: Math.max(0, drag.frame.y + dy),
        });
      } else {
        setFrame({
          ...drag.frame,
          width: Math.max(240, drag.frame.width + dx),
          height: Math.max(140, drag.frame.height + dy),
        });
      }
    };
    const finish = (): void => {
      window.removeEventListener("pointermove", move, true);
      window.removeEventListener("pointerup", finish, true);
      window.removeEventListener("pointercancel", finish, true);
      const drag = dragRef.current;
      dragRef.current = null;
      if (drag !== null) {
        useDocumentStore.getState().setProbeFrame(probe.id, latestFrame.current);
      }
    };
    window.addEventListener("pointermove", move, true);
    window.addEventListener("pointerup", finish, true);
    window.addEventListener("pointercancel", finish, true);
  };

  return (
    <section
      className={`probe-window probe-window--${probe.kind}`}
      data-testid={`probe-window-${probe.id}`}
      style={{
        left: frame.x,
        top: frame.y,
        width: frame.width,
        height: frame.height,
      }}
      onPointerDown={(event) => event.stopPropagation()}
    >
      <header
        className="probe-window__header"
        onPointerDown={(event) => start("move", event)}
      >
        <ProbeGlyph size={15} />
        <span className="probe-window__name">{probe.name}</span>
        <span className="probe-window__kind">
          {probe.kind === "block" ? "scope block" : "probe plot"}
        </span>
        <button
          type="button"
          className="probe-window__close"
          aria-label={`Close ${probe.name}`}
          title="Close this probe plot (reopen it from the probe inspector)"
          onPointerDown={(event) => event.stopPropagation()}
          onClick={(event) => {
            event.stopPropagation();
            useDocumentStore.getState().setProbeOpen(probe.id, false);
          }}
        >
          ×
        </button>
      </header>
      <div className="probe-window__body">
        <ProbePlot model={model} probe={probe} />
      </div>
      <span
        className="probe-window__resize"
        aria-hidden="true"
        onPointerDown={(event) => start("resize", event)}
      />
    </section>
  );
}
