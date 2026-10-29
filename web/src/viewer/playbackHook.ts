/**
 * React glue of the 3D View's bindings and playback: the controller, the stream of the bound signals
 * for the open run, and the binding diagnostics.
 */

import { useEffect, useMemo, useRef, useState, useSyncExternalStore } from "react";

import type { Binding } from "../contracts/model";
import { useDiagnosticsStore } from "../diagnostics/store";
import type { BuiltScene } from "../scene/build";
import { getInspectTime, subscribeInspectTime, useRunStore } from "../plot/runStore";
import { useDocumentStore } from "../state/documentStore";
import { boundSignalIds } from "./bindingsApply";
import { publishBindingDiagnostics } from "./bindingsDiagnostics";
import { validateBindings, type SignalUnits } from "./bindingsValidate";
import { ViewerPlayback, type PlaybackSnapshot } from "./playbackController";
import { openStream } from "./playbackStream";
import { SignalBuffer } from "./timeline";

const NO_BINDINGS: readonly Binding[] = [];

/** The signals the viewer may bind: those of `model.check`, overridden by the open run's manifest. */
export function useBindableSignals(): SignalUnits | null {
  const checked = useDiagnosticsStore((s) => s.signals);
  const manifest = useRunStore((s) => s.manifest);
  return useMemo(() => {
    const map = new Map<string, string | null | undefined>();
    for (const s of checked) map.set(s.id, s.unit);
    for (const s of manifest?.signals ?? []) map.set(s.id, s.unit);
    return map.size === 0 ? null : map;
  }, [checked, manifest]);
}

export function useModelBindings(): readonly Binding[] {
  return useDocumentStore((s) => s.doc?.bindings) ?? NO_BINDINGS;
}

export interface ViewerPlaybackHandle {
  readonly playback: ViewerPlayback | null;
  readonly snapshot: PlaybackSnapshot;
  /** The last stream problem, or null. */
  readonly streamError: string | null;
  /** True while a stream is open and has not ended. */
  readonly streaming: boolean;
}

/**
 * Wires `built` and the model's bindings to a `ViewerPlayback`, validates the bindings (E301-E304) and
 * streams the bound signals of the open run: live while it runs, the whole decimated run once it is done.
 */
export function useViewerPlayback(built: BuiltScene | null, active = true): ViewerPlaybackHandle {
  const bindings = useModelBindings();
  const signals = useBindableSignals();
  const runId = useRunStore((s) => s.runId);
  const runStatus = useRunStore((s) => s.status);
  const [streamError, setStreamError] = useState<string | null>(null);
  const [streaming, setStreaming] = useState(false);

  const [playback, setPlayback] = useState<ViewerPlayback | null>(null);
  useEffect(() => {
    const created = new ViewerPlayback({ get: getInspectTime, set: (t) => { useRunStore.getState().setCursorTime(t); }, subscribe: subscribeInspectTime });
    setPlayback(created);
    return () => {
      created.dispose();
    };
  }, []);

  useEffect(() => {
    playback?.setActive(active);
  }, [playback, active]);

  useEffect(() => {
    playback?.setTarget(built);
    return () => {
      playback?.setTarget(null);
    };
  }, [playback, built]);

  useEffect(() => {
    playback?.setBindings(bindings);
  }, [playback, bindings]);

  // validation
  useEffect(() => {
    if (built === null) {
      publishBindingDiagnostics([]);
      return;
    }
    publishBindingDiagnostics(validateBindings(bindings, built, signals));
    return () => {
      publishBindingDiagnostics([]);
    };
  }, [built, bindings, signals]);

  // the stream of the bound signals of the open run
  const ids = useMemo(() => boundSignalIds(bindings), [bindings]);
  const idsKey = ids.join("\u0000");
  const followable = runStatus === "running" || runStatus === "done" || runStatus === "failed" || runStatus === "cancelled";
  const live = runStatus === "running";
  // read when a stream opens; a run that ends keeps its live stream and finishes it, it must not reopen
  const liveRef = useRef(live);
  useEffect(() => {
    liveRef.current = live;
  });
  const streamRun = followable && built !== null ? runId : null;
  useEffect(() => {
    if (playback === null) return;
    if (streamRun === null || ids.length === 0) {
      playback.setData(null, false);
      setStreamError(null);
      setStreaming(false);
      return;
    }
    let buffer: SignalBuffer | null = null;
    const live = liveRef.current;
    let isLive = live;
    setStreamError(null);
    setStreaming(true);
    const close = openStream(streamRun, ids, live ? "live" : "playback", {
      onHandshake: (handshake) => {
        buffer = new SignalBuffer(handshake.signals.map((s) => s.id));
        isLive = live && handshake.mode !== "playback";
        playback.setData(buffer, isLive);
      },
      onFrames: (frames) => {
        if (buffer === null) return;
        buffer.append(frames);
        playback.dataChanged();
      },
      onEnd: ({ ok, reason }) => {
        setStreaming(false);
        if (ok) {
          if (isLive) playback.finishLive();
        } else {
          setStreamError(reason);
        }
      },
    });
    return () => {
      close();
      setStreaming(false);
      playback.setData(null, false);
    };
  }, [playback, streamRun, ids, idsKey]);

  const idle = useMemo<PlaybackSnapshot>(
    () => ({ mode: "empty", playing: false, time: null, start: 0, end: 0, speed: 1, loop: false, applied: {} }),
    [],
  );
  const snapshot = useSyncExternalStore(
    (listener) => playback?.subscribe(listener) ?? (() => undefined),
    () => playback?.snapshot() ?? idle,
  );
  return { playback, snapshot, streamError, streaming };
}

