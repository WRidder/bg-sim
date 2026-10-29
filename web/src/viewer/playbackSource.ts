/**
 * Where the 3D View gets its samples from (W5.5): the stream socket, and for a finished run the
 * HTTP data endpoint when the socket fails (Firefox closes some sockets with 1006 where Edge does not).
 * Both paths feed the same handlers with the same decimation, so the timeline does not depend on the path.
 */

import { fetchRunData, RunApiError } from "../plot/runApi";
import type { RunDataFrame } from "../plot/runData";
import type { StreamHandshake } from "../contracts/stream-handshake";
import { isRefusal, openStream, type StreamEnd, type StreamHandlers, type StreamMode } from "./playbackStream";

/** The display rate of the stream (frames per simulated second, the stream's maximum). */
export const PLAYBACK_RATE = 60;

/**
 * Thin recorded rows like the stream endpoint does: keep the first row, then each row at least
 * `1 / rate` after the previously kept one (so rows with equal time, such as the two sides of an
 * event, collapse into the first), and always the last row so the run end is shown.
 *
 * @returns frames `[t, v1 ... vn]` back to back.
 */
export function thinRows(time: ArrayLike<number>, values: readonly ArrayLike<number>[], rate = PLAYBACK_RATE): Float64Array {
  const rows = time.length;
  const width = values.length + 1;
  if (rows === 0) return new Float64Array(0);
  const gap = (1 / rate) * (1 - 1e-9);
  const kept: number[] = [0];
  let lastSent = time[0] ?? 0;
  for (let i = 1; i < rows; i++) {
    const t = time[i] ?? Number.NaN;
    if (t >= lastSent + gap) {
      kept.push(i);
      lastSent = t;
    }
  }
  const last = rows - 1;
  if ((time[last] ?? 0) > lastSent) kept.push(last);
  const frames = new Float64Array(kept.length * width);
  kept.forEach((row, k) => {
    frames[k * width] = time[row] ?? Number.NaN;
    values.forEach((column, c) => {
      frames[k * width + 1 + c] = column[row] ?? Number.NaN;
    });
  });
  return frames;
}

/** Frames of a decoded `/data` answer, decimated like the stream. */
export function framesOf(data: RunDataFrame, rate = PLAYBACK_RATE): Float64Array {
  return thinRows(data.time, data.values, rate);
}

/** What to tell the user when the stream dropped and the run was loaded over HTTP instead. */
export function fallbackNote(code: number | undefined): string {
  return `The 3D stream connection was dropped (${String(code ?? 1006)}) — loaded the run over HTTP instead.`;
}

/** What to tell the user when neither the stream nor HTTP worked. */
export const UNREACHABLE =
  "Cannot reach the backend stream; check that the backend is running and that no proxy/extension blocks WebSockets to this address, then reload.";

function describeHttpFailure(error: unknown): string {
  if (error instanceof RunApiError && error.status > 0) {
    return `The 3D stream connection was dropped and the run could not be loaded over HTTP either: ${error.message}`;
  }
  return UNREACHABLE;
}

export interface SourceHandlers extends StreamHandlers {
  /** The stream failed and the run was loaded over HTTP instead; the text says so. */
  onNote(note: string): void;
}

export interface SourceSeams {
  readonly makeSocket?: (url: string) => WebSocket;
  readonly fetchData?: typeof fetchRunData;
}

/** Load a whole run over HTTP (raw rows, thinned here) and deliver it as one handshake plus one frame block. */
export function loadOverHttp(
  runId: string,
  ids: readonly string[],
  handlers: StreamHandlers,
  fetchData: typeof fetchRunData = fetchRunData,
  onLoaded?: () => void,
): () => void {
  const abort = new AbortController();
  void (async () => {
    try {
      const data = await fetchData(runId, ids, null, 0, abort.signal);
      if (abort.signal.aborted) return;
      const handshake: StreamHandshake = { signals: ids.map((id) => ({ id })), rate: PLAYBACK_RATE, mode: "playback" };
      handlers.onHandshake(handshake);
      handlers.onFrames(framesOf(data));
      onLoaded?.();
      handlers.onEnd({ ok: true, reason: "done" });
    } catch (error) {
      if (abort.signal.aborted) return;
      handlers.onEnd({ ok: false, reason: describeHttpFailure(error) });
    }
  })();
  return () => {
    abort.abort();
  };
}

/**
 * Open the samples of `ids` for a run. A `playback` stream that fails (any close but 1000, except a
 * refusal of the request itself) falls back to HTTP; the outcome reaches `onEnd` as usual and a
 * successful fallback also calls `onNote`. A `live` stream that fails is reported with its code and
 * left to the caller, which loads over HTTP with {@link loadOverHttp} once the run is done.
 */
export function openSamples(
  runId: string,
  ids: readonly string[],
  mode: StreamMode,
  handlers: SourceHandlers,
  seams: SourceSeams = {},
): () => void {
  let cancelHttp: (() => void) | null = null;
  let cancelled = false;
  const closeStream = openStream(
    runId,
    ids,
    mode,
    {
      onHandshake: (h) => {
        handlers.onHandshake(h);
      },
      onFrames: (f) => {
        handlers.onFrames(f);
      },
      onEnd: (end: StreamEnd) => {
        if (cancelled) return;
        if (end.ok || mode === "live" || isRefusal(end.code)) {
          handlers.onEnd(end);
          return;
        }
        // a broken stream may have delivered part of the run: the HTTP handshake starts a fresh buffer
        cancelHttp = loadOverHttp(runId, ids, handlers, seams.fetchData, () => {
          handlers.onNote(fallbackNote(end.code));
        });
      },
    },
    seams.makeSocket,
  );
  return () => {
    cancelled = true;
    closeStream();
    cancelHttp?.();
  };
}
