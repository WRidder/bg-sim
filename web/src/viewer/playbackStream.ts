/**
 * Client of `WS /ws/stream/{runId}` (P5.1, spec "Stream format"): one JSON handshake, then binary
 * messages of whole `[t, v1 ... vn]` Float64 frames, then a close with the run status as reason.
 */

import { API_BASE } from "../api/client";
import type { StreamHandshake } from "../contracts/stream-handshake";
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

/** The URL of a run's stream for the given signal ids, in request order. */
export function streamUrl(runId: string, ids: readonly string[], mode: StreamMode, base?: string): string {
  const root =
    base ?? (API_BASE.length > 0 ? API_BASE : typeof window === "undefined" ? "http://127.0.0.1:8765" : window.location.origin);
  const url = new URL(`${root}/ws/stream/${encodeURIComponent(runId)}`, typeof window === "undefined" ? "http://127.0.0.1:8765" : window.location.href);
  url.protocol = url.protocol === "https:" ? "wss:" : "ws:";
  url.searchParams.set("ids", ids.join(","));
  url.searchParams.set("mode", mode);
  return url.toString();
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

/**
 * Open a stream. Returns a function that closes it (no further handler is called afterwards).
 * `makeSocket` is a test seam.
 */
export function openStream(
  runId: string,
  ids: readonly string[],
  mode: StreamMode,
  handlers: StreamHandlers,
  makeSocket: (url: string) => WebSocket = (url) => new WebSocket(url),
): () => void {
  let closed = false;
  let signalCount = -1;
  let socket: WebSocket;
  try {
    socket = makeSocket(streamUrl(runId, ids, mode));
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
  socket.binaryType = "arraybuffer";
  socket.onmessage = (event: MessageEvent) => {
    if (closed) return;
    try {
      if (typeof event.data === "string") {
        const handshake = JSON.parse(event.data) as StreamHandshake;
        signalCount = handshake.signals.length;
        handlers.onHandshake(handshake);
      } else if (event.data instanceof ArrayBuffer && signalCount >= 0) {
        handlers.onFrames(decodeFrames(event.data, signalCount));
      }
    } catch (error) {
      closed = true;
      socket.close();
      handlers.onEnd({ ok: false, reason: error instanceof Error ? error.message : String(error), code: 1003 });
    }
  };
  socket.onclose = (event: CloseEvent) => {
    if (closed) return;
    closed = true;
    if (event.code === 1000) handlers.onEnd({ ok: true, reason: event.reason });
    else handlers.onEnd({ ok: false, reason: refusal(event.code, event.reason), code: event.code });
  };
  socket.onerror = () => {
    // A close event normally follows and carries the reason. Before the handshake some browsers
    // report only the error (or the close never comes): end the stream here so the caller can fall back.
    if (closed || signalCount >= 0) return;
    closed = true;
    socket.onmessage = null;
    socket.onclose = null;
    socket.close();
    handlers.onEnd({ ok: false, reason: refusal(1006, ""), code: 1006 });
  };
  return () => {
    if (closed) return;
    closed = true;
    socket.onmessage = null;
    socket.onclose = null;
    socket.close();
  };
}
