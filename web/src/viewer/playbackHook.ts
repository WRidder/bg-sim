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
import type { StreamHandshake } from "../contracts/stream-handshake";
import { isRefusal, type StreamEnd } from "./playbackStream";
import { loadOverHttp, openSamples, type SourceSeams } from "./playbackSource";
import { windowClock } from "./renderScheduler";
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
  /** The stream failed but the run was loaded over HTTP instead (what happened, in words), or null. */
  readonly streamNote: string | null;
  /** True while a stream is open and has not ended. */
  readonly streaming: boolean;
}

/**
 * Wires `built` and the model's bindings to a `ViewerPlayback`, validates the bindings (E301-E304) and
 * streams the bound signals of the open run: live while it runs, the whole decimated run once it is done.
 */
export function useViewerPlayback(
  built: BuiltScene | null,
  active = true,
  hostWindow: Window | null = null,
  seams: SourceSeams = {},
): ViewerPlaybackHandle {
  const bindings = useModelBindings();
  const signals = useBindableSignals();
  const runId = useRunStore((s) => s.runId);
  const runStatus = useRunStore((s) => s.status);
  const [streamError, setStreamError] = useState<string | null>(null);
  const [streamNote, setStreamNote] = useState<string | null>(null);
  // a live stream that failed: the run is loaded over HTTP once it is done
  const [liveFailedFor, setLiveFailedFor] = useState<string | null>(null);
  const seamsRef = useRef(seams);
  useEffect(() => {
    seamsRef.current = seams;
  });
  const [streaming, setStreaming] = useState(false);

  const [playback, setPlayback] = useState<ViewerPlayback | null>(null);
  useEffect(() => {
    // the frame clock is the window that shows the view: a popup draws and throttles on its own
    const created = new ViewerPlayback(
      { get: getInspectTime, set: (t) => { useRunStore.getState().setCursorTime(t); }, subscribe: subscribeInspectTime },
      hostWindow === null ? {} : { frames: windowClock(hostWindow) },
    );
    setPlayback(created);
    return () => {
      created.dispose();
    };
  }, [hostWindow]);

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
  // a live stream failed and the run has ended since: load it over HTTP
  const httpRun = liveFailedFor !== null && liveFailedFor === streamRun && !live ? streamRun : null;
  useEffect(() => {
    if (playback === null) return;
    if (streamRun === null || ids.length === 0) {
      playback.setData(null, false);
      setStreamError(null);
      setStreamNote(null);
      setStreaming(false);
      return;
    }
    let buffer: SignalBuffer | null = null;
    const live = liveRef.current && httpRun === null;
    let isLive = live;
    setStreamError(null);
    setStreamNote(null);
    setStreaming(true);
    const handlers = {
      onHandshake: (handshake: StreamHandshake) => {
        buffer = new SignalBuffer(handshake.signals.map((s) => s.id));
        isLive = live && handshake.mode !== "playback";
        playback.setData(buffer, isLive);
      },
      onFrames: (frames: Float64Array) => {
        if (buffer === null) return;
        buffer.append(frames);
        playback.dataChanged();
      },
      onNote: (note: string) => {
        setStreamNote(note);
      },
    };
    const end = ({ ok, reason }: StreamEnd) => {
      setStreaming(false);
      if (ok) {
        if (isLive) playback.finishLive();
      } else {
        setStreamError(reason);
      }
    };
    const close =
      httpRun !== null
        ? loadOverHttp(streamRun, ids, { ...handlers, onEnd: end }, seamsRef.current.fetchData, () => {
            setStreamNote("The 3D stream connection was dropped during the live run — loaded the finished run over HTTP instead.");
          })
        : openSamples(
            streamRun,
            ids,
            live ? "live" : "playback",
            {
              ...handlers,
              onEnd: (e) => {
                if (!e.ok && live && !isRefusal(e.code)) {
                  // keep what arrived, say what happened, and load the whole run when it is done
                  setLiveFailedFor(streamRun);
                  end({ ...e, reason: `The live 3D stream was dropped (${String(e.code ?? 1006)}); the finished run will be loaded over HTTP when the run is done.` });
                  return;
                }
                end(e);
              },
            },
            seamsRef.current,
          );
    return () => {
      close();
      setStreaming(false);
      playback.setData(null, false);
    };
  }, [playback, streamRun, ids, idsKey, httpRun]);

  const idle = useMemo<PlaybackSnapshot>(
    () => ({ mode: "empty", playing: false, time: null, start: 0, end: 0, speed: 1, loop: false, applied: {} }),
    [],
  );
  const snapshot = useSyncExternalStore(
    (listener) => playback?.subscribe(listener) ?? (() => undefined),
    () => playback?.snapshot() ?? idle,
  );
  return { playback, snapshot, streamError, streamNote, streaming };
}

