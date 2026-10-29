/**
 * Client of `WS /ws/stream/{runId}` (P5.1, spec "Stream format"): one JSON handshake, then binary
 * messages of whole `[t, v1 ... vn]` Float64 frames, then a close with the run status as reason.
 */

import { API_BASE } from "../api/client";
import type { StreamHandshake } from "../contracts/stream-handshake";
import { decodeFrames } from "./timeline";

export type StreamMode = "live" | "playback";

export interface StreamHandlers {
  /** The handshake arrived; signals are in frame order. */
  onHandshake(handshake: StreamHandshake): void;
  /** Whole decoded frames, `[t, v1 ... vn]` each. */
  onFrames(frames: Float64Array): void;
  /** The stream ended: a normal close carries the run status (`done`, `cancelled`, `failed`), anything else an error text. */
  onEnd(end: { readonly ok: boolean; readonly reason: string }): void;
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

/** Refusal codes of the stream endpoint and what to do about them. */
function refusal(code: number, reason: string): string {
  switch (code) {
    case 4400:
      return `the stream request was refused: ${reason}`;
    case 4404:
      return `the run is gone (${reason}); run the model again`;
    case 4409:
      return `the run cannot be followed yet (${reason}); wait for it to finish`;
    default:
      return `the stream closed with ${String(code)} ${reason}`;
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
  const socket = makeSocket(streamUrl(runId, ids, mode));
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
      handlers.onEnd({ ok: false, reason: error instanceof Error ? error.message : String(error) });
    }
  };
  socket.onclose = (event: CloseEvent) => {
    if (closed) return;
    closed = true;
    if (event.code === 1000) handlers.onEnd({ ok: true, reason: event.reason });
    else handlers.onEnd({ ok: false, reason: refusal(event.code, event.reason) });
  };
  socket.onerror = () => {
    // a close event follows; it carries the reason
  };
  return () => {
    if (closed) return;
    closed = true;
    socket.onmessage = null;
    socket.onclose = null;
    socket.close();
  };
}
