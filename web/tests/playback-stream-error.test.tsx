/**
 * A 3D stream that is refused, drops or never answers shows an error in the playback bar instead of
 * a silent "Press Play" (the long-URL 414 of the Beaver and F-16 examples left the view waiting).
 */

import { act, render, screen, waitFor } from "@testing-library/react";
import type { ReactElement } from "react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { resetRunStore, useRunStore } from "../src/plot/runStore";
import type { BuiltScene } from "../src/scene/build";
import { resetDocumentStore, useDocumentStore } from "../src/state/documentStore";
import { createEmptyModel } from "../src/state/modelFactory";
import { PlaybackBar } from "../src/viewer/PlaybackBar";
import { useViewerPlayback } from "../src/viewer/playbackHook";
import type { SourceSeams } from "../src/viewer/playbackSource";

class FakeSocket {
  binaryType = "";
  onopen: (() => void) | null = null;
  onmessage: ((e: MessageEvent) => void) | null = null;
  onclose: ((e: CloseEvent) => void) | null = null;
  onerror: (() => void) | null = null;
  sent: string[] = [];
  send(text: string): void {
    this.sent.push(text);
  }
  close(): void {
    /* nothing to release */
  }
}

const built = new Proxy({}, { get: () => () => true }) as unknown as BuiltScene;

function Harness({ seams }: { seams: SourceSeams }): ReactElement {
  const { playback, snapshot, streamError, streamNote, streaming } = useViewerPlayback(built, true, null, seams);
  return (
    <PlaybackBar
      playback={playback}
      snapshot={snapshot}
      streamError={streamError}
      streamNote={streamNote}
      streaming={streaming}
      hasBindings
      bindingsOpen={false}
      onToggleBindings={() => undefined}
    />
  );
}

/** A model with 300 bound pose components (over 8 KiB of ids) and an open run. */
function openRun(status: "running" | "done"): string[] {
  const doc = createEmptyModel("M");
  const ids: string[] = [];
  doc.bindings = [];
  for (let k = 0; k < 43; k++) {
    const signal = Array.from({ length: 7 }, (_, i) => `ElevatorTrail/d${String(k)}[${String(i + 1)}]`) as [string, ...string[]];
    ids.push(...signal);
    doc.bindings.push({ target: `link:trail_${String(k)}`, property: "pose", signal });
  }
  useDocumentStore.getState().openDocument("p", "M", doc);
  useRunStore.setState({ runId: "r1", status });
  return ids;
}

beforeEach(() => {
  resetDocumentStore();
  resetRunStore();
});

afterEach(() => {
  vi.useRealTimers();
});

describe("3D stream errors in the playback bar", () => {
  it("says the data is loading, sends the ids in the subscribe message, and shows a refusal as an alert", async () => {
    const ids = openRun("done");
    const sockets: { url: string; socket: FakeSocket }[] = [];
    render(
      <Harness
        seams={{
          makeSocket: (url) => {
            const socket = new FakeSocket();
            sockets.push({ url, socket });
            return socket as unknown as WebSocket;
          },
        }}
      />,
    );
    await waitFor(() => expect(sockets).toHaveLength(1));
    expect(screen.getByTestId("playback-note").textContent).toBe("Loading the run into the 3D view…");
    const first = sockets[0];
    expect(first?.url).not.toContain("ids=");
    act(() => {
      first?.socket.onopen?.();
    });
    expect(JSON.parse(first?.socket.sent[0] ?? "{}")).toEqual({ ids });
    act(() => {
      first?.socket.onclose?.({ code: 4400, reason: "unknown signal id 'ElevatorTrail/d0[1]'" } as CloseEvent);
    });
    const note = screen.getByTestId("playback-note");
    expect(note.getAttribute("role")).toBe("alert");
    expect(note.textContent).toMatch(/stream request was refused: unknown signal id 'ElevatorTrail\/d0\[1\]'/);
  });

  it("shows an error when a live stream never connects, instead of waiting at Press Play", async () => {
    openRun("running");
    vi.useFakeTimers({ shouldAdvanceTime: true });
    const fetchData = vi.fn();
    render(
      <Harness
        seams={{
          makeSocket: () => new FakeSocket() as unknown as WebSocket, // the backend never answers the upgrade
          fetchData,
          timing: { openMs: 1500 },
        }}
      />,
    );
    await waitFor(() => expect(screen.getByTestId("playback-note").textContent).toMatch(/Loading the run/));
    act(() => {
      vi.advanceTimersByTime(1500);
    });
    const note = screen.getByTestId("playback-note");
    expect(note.getAttribute("role")).toBe("alert");
    expect(note.textContent).toMatch(/live 3D stream was dropped \(1006\).*loaded over HTTP when the run is done/);
    expect(note.textContent).not.toMatch(/Press Play/);
    expect(fetchData).not.toHaveBeenCalled();
  });

  it("shows an error when a finished run can be loaded neither by stream nor over HTTP", async () => {
    openRun("done");
    vi.useFakeTimers({ shouldAdvanceTime: true });
    render(
      <Harness
        seams={{
          makeSocket: () => new FakeSocket() as unknown as WebSocket,
          fetchData: () => Promise.reject(new TypeError("Failed to fetch")),
          timing: { openMs: 1000 },
        }}
      />,
    );
    act(() => {
      vi.advanceTimersByTime(1000);
    });
    await waitFor(() => expect(screen.getByTestId("playback-note").getAttribute("role")).toBe("alert"));
    expect(screen.getByTestId("playback-note").textContent).toMatch(/Cannot reach the backend stream/);
  });
});
