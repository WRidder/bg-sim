/**
 * Play in the 3D view with no run to play starts one (as Run in the top bar); during a run and with no
 * model open it stays disabled.
 */

import { fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { useRunStore } from "../src/plot/runStore";
import { useDocumentStore } from "../src/state/documentStore";
import { PlaybackBar } from "../src/viewer/PlaybackBar";
import type { PlaybackSnapshot } from "../src/viewer/playbackController";

const EMPTY: PlaybackSnapshot = { mode: "empty", playing: false, time: null, start: 0, end: 0, speed: 1, loop: false, applied: {}, pauseTime: null };

const initialRun = useRunStore.getState();
const initialDoc = useDocumentStore.getState();

afterEach(() => {
  useRunStore.setState(initialRun, true);
  useDocumentStore.setState(initialDoc, true);
});

function bar() {
  return render(
    <PlaybackBar playback={null} snapshot={EMPTY} streamError={null} hasBindings bindingsOpen={false} onToggleBindings={() => undefined} />,
  );
}

describe("Play with nothing to play", () => {
  it("starts a run when a model is open", () => {
    const startRun = vi.fn(async () => undefined);
    useRunStore.setState({ status: "idle", startRun });
    useDocumentStore.setState({ project: "p", doc: {} as never });
    bar();
    const play = screen.getByTestId("playback-toggle") as HTMLButtonElement;
    expect(play.disabled).toBe(false);
    expect(play.getAttribute("data-runs")).toBe("true");
    fireEvent.click(play);
    expect(startRun).toHaveBeenCalledTimes(1);
  });

  it("stays disabled while a run is busy or no model is open", () => {
    useRunStore.setState({ status: "running" });
    useDocumentStore.setState({ project: "p", doc: {} as never });
    const { unmount } = bar();
    expect((screen.getByTestId("playback-toggle") as HTMLButtonElement).disabled).toBe(true);
    unmount();
    useRunStore.setState({ status: "idle" });
    useDocumentStore.setState({ project: null, doc: null });
    bar();
    expect((screen.getByTestId("playback-toggle") as HTMLButtonElement).disabled).toBe(true);
  });
});
