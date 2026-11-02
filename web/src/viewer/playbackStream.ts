/**
 * Client of `WS /ws/stream/{runId}` (P5.1, spec "Stream format"): the socket opens with `?subscribe=1`, the
 * first client message names the signal ids (the `stream-subscribe` contract), then the server sends one JSON
 * handshake, binary messages of whole `[t, v1 ... vn]` Float64 frames, and a close with the run status as reason.
 *
 * The ids travel in the message and not in the URL: the 3D view binds hundreds of signals, and an upgrade
 * request line over 8 KiB is refused by the backend (414), or never answered, which the browser cannot tell
 * from a silent wait.
 */

import { API_BASE } from "../api/client";
import type { StreamHandshake } from "../contracts/stream-handshake";
import type { StreamSubscribe } from "../contracts/stream-subscribe";
import { decodeFrames } from "./timeline";

export type StreamMode = "live" | "playback";

/** How a stream ended. `code` is the WebSocket close code of a failure (1006 when the connection never opened or broke). */
export interface StreamEnd {
  readonly ok: boolean;
  readonly reason: string;
  readonly code?: number;
}

export interface StreamHandlers {
  /** The handshake arrived; signals are in frame order. */
  onHandshake(handshake: StreamHandshake): void;
  /** Whole decoded frames, `[t, v1 ... vn]` each. */
  onFrames(frames: Float64Array): void;
  /** The stream ended: a normal close carries the run status (`done`, `cancelled`, `failed`), anything else an error text. */
  onEnd(end: StreamEnd): void;
}

/** How long a stream may take to connect, and (playback only) to send its handshake once connected. */
export interface StreamTiming {
  /** Milliseconds until the socket must be open; 0 waits forever. */
  readonly openMs?: number;
  /** Milliseconds from the open until a playback handshake; 0 waits forever. A live handshake waits for the run. */
  readonly handshakeMs?: number;
}

/** Default timing: a backend that accepts no connection or never answers is reported, not waited for. */
export const STREAM_TIMING: Required<StreamTiming> = { openMs: 10_000, handshakeMs: 20_000 };

/** The URL of a run's stream. The signal ids are not in it: they go in the subscribe message ({@link subscribeMessage}). */
export function streamUrl(runId: string, mode: StreamMode, base?: string): string {
  const root =
    base ?? (API_BASE.length > 0 ? API_BASE : typeof window === "undefined" ? "http://127.0.0.1:8765" : window.location.origin);
  const url = new URL(`${root}/ws/stream/${encodeURIComponent(runId)}`, typeof window === "undefined" ? "http://127.0.0.1:8765" : window.location.href);
  url.protocol = url.protocol === "https:" ? "wss:" : "ws:";
  url.searchParams.set("subscribe", "1");
  url.searchParams.set("mode", mode);
  return url.toString();
}

/** The first client message of a stream: the ids in frame order. */
export function subscribeMessage(ids: readonly string[]): string {
  const message: StreamSubscribe = { ids: [...ids] };
  return JSON.stringify(message);
}

/** The request itself is wrong (bad ids, gone run, run not finished): the HTTP path would fail the same way. */
export function isRefusal(code: number | undefined): boolean {
  return code === 4400 || code === 4404 || code === 4409;
}

/** Refusal codes of the stream endpoint and what to do about them. */
export function refusal(code: number, reason: string): string {
  switch (code) {
    case 4400:
      return `the stream request was refused: ${reason}`;
    case 4404:
      return `the run is gone (${reason}); run the model again`;
    case 4409:
      return `the run cannot be followed yet (${reason}); wait for it to finish`;
    default:
      return `the 3D stream connection was dropped (${String(code)}${reason.length > 0 ? ` ${reason}` : ""})`;
  }
}

/** What to say when the stream did not connect, or connected and sent no handshake, in time. */
export function timedOut(stage: "open" | "handshake", ms: number): string {
  const seconds = `${String(Math.round(ms / 100) / 10)} s`;
  return stage === "open"
    ? `the 3D stream did not connect within ${seconds}; the backend did not answer the connection`
    : `the 3D stream connected but sent no data within ${seconds}`;
}

/**
 * Open a stream. Returns a function that closes it (no further handler is called afterwards).
 * `makeSocket` is a test seam; `timing` overrides {@link STREAM_TIMING}.
 */
export function openStream(
  runId: string,
  ids: readonly string[],
  mode: StreamMode,
  handlers: StreamHandlers,
  makeSocket: (url: string) => WebSocket = (url) => new WebSocket(url),
  timing: StreamTiming = {},
): () => void {
  const openMs = timing.openMs ?? STREAM_TIMING.openMs;
  const handshakeMs = timing.handshakeMs ?? STREAM_TIMING.handshakeMs;
  let closed = false;
  let signalCount = -1;
  let timer: ReturnType<typeof setTimeout> | null = null;
  const clearTimer = (): void => {
    if (timer !== null) clearTimeout(timer);
    timer = null;
  };
  let socket: WebSocket;
  try {
    socket = makeSocket(streamUrl(runId, mode));
  } catch (error) {
    // some browsers refuse the constructor itself (mixed content, blocked ports): same as a dropped connection
    queueMicrotask(() => {
      if (closed) return;
      closed = true;
      handlers.onEnd({ ok: false, reason: refusal(1006, error instanceof Error ? error.message : String(error)), code: 1006 });
    });
    return () => {
      closed = true;
    };
  }
  /** End the stream from this side: no socket callback reaches the handlers afterwards. */
  const fail = (end: StreamEnd): void => {
    if (closed) return;
    closed = true;
    clearTimer();
    socket.onopen = null;
    socket.onmessage = null;
    socket.onclose = null;
    socket.onerror = null;
    socket.close();
    handlers.onEnd(end);
  };
  const arm = (ms: number, stage: "open" | "handshake"): void => {
    clearTimer();
    if (ms > 0) {
      timer = setTimeout(() => {
        fail({ ok: false, reason: timedOut(stage, ms), code: 1006 });
      }, ms);
    }
  };
  socket.binaryType = "arraybuffer";
  arm(openMs, "open");
  socket.onopen = () => {
    if (closed) return;
    if (mode === "playback") arm(handshakeMs, "handshake");
    else clearTimer();
    try {
      socket.send(subscribeMessage(ids));
    } catch (error) {
      fail({ ok: false, reason: refusal(1006, error instanceof Error ? error.message : String(error)), code: 1006 });
    }
  };
  socket.onmessage = (event: MessageEvent) => {
    if (closed) return;
    try {
      if (typeof event.data === "string") {
        const handshake = JSON.parse(event.data) as StreamHandshake;
        signalCount = handshake.signals.length;
        clearTimer();
        handlers.onHandshake(handshake);
      } else if (event.data instanceof ArrayBuffer && signalCount >= 0) {
        handlers.onFrames(decodeFrames(event.data, signalCount));
      }
    } catch (error) {
      fail({ ok: false, reason: error instanceof Error ? error.message : String(error), code: 1003 });
    }
  };
  socket.onclose = (event: CloseEvent) => {
    if (closed) return;
    closed = true;
    clearTimer();
    if (event.code === 1000) handlers.onEnd({ ok: true, reason: event.reason });
    else handlers.onEnd({ ok: false, reason: refusal(event.code, event.reason), code: event.code });
  };
  socket.onerror = () => {
    // A close event normally follows and carries the reason. Before the handshake some browsers
    // report only the error (or the close never comes): end the stream here so the caller can fall back.
    if (closed || signalCount >= 0) return;
    fail({ ok: false, reason: refusal(1006, ""), code: 1006 });
  };
  return () => {
    if (closed) return;
    closed = true;
    clearTimer();
    socket.onopen = null;
    socket.onmessage = null;
    socket.onclose = null;
    socket.close();
  };
}
