/**
 * The run and plot store (plan 7.5).
 *
 * One store owns the current run, its manifest, the plotted signal ids, the
 * zoom window, the LRU-backed data and the pinned comparison. The run bar, the
 * signal browser and every uPlot chart read it, so a zoom in one panel is a
 * zoom in all of them and a signal added in the browser appears in the active
 * panel without a second source of truth.
 *
 * `cursorTime` is the global inspect time in seconds (the 3D viewer and the
 * bond hover values read it through `getInspectTime`/`subscribeInspectTime`).
 * `addSignals` plots a whole context-menu selection in one pass, and
 * `splitPanel` moves a forced third unit group to its own panel.
 *
 * Live data arrives through `WS /ws/runs/{id}`. Tails are kept outside React
 * (they can be large) and exposed through `liveSeriesFor` plus a `liveVersion`
 * counter; a finished run replaces them with a fresh `/data` answer. A poll of
 * `GET /api/runs/{id}` is the fallback when the socket cannot connect, and it
 * is what publishes the final manifest stats.
 */

import { create } from "zustand";

import type {
  Diagnostic,
  RunManifest,
  RunSignal,
  RunStatus,
  RunStats,
} from "../contracts/run-manifest";
import { useDocumentStore } from "../state/documentStore";
import {
  cancelRun,
  createRun,
  fetchRunData,
  fetchRunManifest,
  runSocketUrl,
} from "./runApi";
import { runDataCache, type SeriesWindow } from "./runCache";
import {
  assignPanelAxes,
  canAddSignalToPanel,
  groupSignalsByUnit,
} from "./units";

/** `idle` and `starting` extend the contract's run statuses. */
export type RunUiStatus = "idle" | "starting" | RunStatus;
export type SocketState = "off" | "connecting" | "open" | "closed";

export interface PlotPanelState {
  id: string;
  /** Signal ids, in the order they were added. */
  signals: string[];
  /** User-given name; empty means the positional "Panel N" label. */
  name?: string;
}

/** The shown name of a panel: its custom name or "Panel <n>" (1-based). */
export function panelLabel(panel: PlotPanelState, index: number): string {
  const name = panel.name?.trim() ?? "";
  return name.length > 0 ? name : `Panel ${index + 1}`;
}

export interface RunProgress {
  /** Simulation time reached, in seconds. */
  t: number;
  /** Rows written to `stream.f64` so far. */
  rows: number;
}

/** One `/data` answer for the plotted signals of one run. */
export interface RunDataView {
  /** Request signature (run, ids, window, px); used to avoid duplicate work. */
  key: string;
  time: Float64Array;
  /** Signal id -> column. Every column has `time.length` values. */
  values: Record<string, Float64Array>;
}

/** Data shaped for a chart, from `/data` or from a live tail. */
export interface ChartSeriesData {
  time: ArrayLike<number>;
  values: Readonly<Record<string, ArrayLike<number>>>;
}

/** A finished run kept as dashed overlays (plan 7.5, "compare runs"). */
export interface PinnedRun {
  manifest: RunManifest;
}

export interface RunStoreState {
  runId: string | null;
  manifest: RunManifest | null;
  status: RunUiStatus;
  phase: string | null;
  progress: RunProgress | null;
  stats: RunStats | null;
  error: string | null;
  notice: string | null;
  stopping: boolean;
  socketState: SocketState;

  panels: PlotPanelState[];
  activePanelId: string;

  /** The shared x window; null means "show all" (raw, px=0). */
  view: SeriesWindow | null;
  /** Canvas width × devicePixelRatio, supplied by the plot panel. */
  pixelWidth: number;

  data: RunDataView | null;
  dataKey: string | null;
  dataLoading: boolean;
  dataError: string | null;

  compareData: RunDataView | null;
  compareKey: string | null;
  pinned: PinnedRun | null;

  /** The plot cursor time; the future 3D viewer's inspect time (plan 7.5). */
  cursorTime: number | null;
  /** Bumped whenever a live tail is appended. */
  liveVersion: number;

  startRun: () => Promise<void>;
  stopRun: () => Promise<void>;
  addSignal: (
    signalId: string,
    panelId?: string,
    options?: { force?: boolean },
  ) => void;
  /** Add several signals with one data refresh (canvas "Plot all outputs"). */
  addSignals: (signalIds: readonly string[], panelId?: string) => number;
  removeSignal: (panelId: string, signalId: string) => void;
  /** Move a panel's overflow unit groups (third and later) to a new panel. */
  splitPanel: (panelId: string) => boolean;
  addPanel: () => string;
  removePanel: (panelId: string) => void;
  setActivePanel: (panelId: string) => void;
  /** Rename a panel; whitespace or an empty string restores "Panel N". */
  renamePanel: (panelId: string, name: string) => void;
  setView: (view: SeriesWindow | null, px?: number) => void;
  /** Return to the live tail after a zoom (plan 7.5: autoscroll unless zoomed). */
  followLive: () => void;
  ensureData: (px?: number, force?: boolean) => Promise<void>;
  ensureCompareData: (px?: number, force?: boolean) => Promise<void>;
  syncSocketSubscription: () => void;
  setCursorTime: (time: number | null) => void;
  pinRun: () => void;
  unpinRun: () => void;
  setNotice: (message: string | null) => void;
  reset: () => void;
}

/** Poll fallback interval while a run is active. */
export const RUN_POLL_INTERVAL_MS = 400;
/** A tail is decimated, but a long live session must still bound memory. */
export const LIVE_POINT_LIMIT = 200_000;
/** Fallback request width before the canvas has been measured. */
export const DEFAULT_PIXEL_WIDTH = 1600;

let panelSequence = 0;
function makePanel(signals: string[] = []): PlotPanelState {
  panelSequence += 1;
  return { id: `panel-${panelSequence}`, signals: [...signals] };
}

function initialPanels(): { panels: PlotPanelState[]; activePanelId: string } {
  const panel = makePanel();
  return { panels: [panel], activePanelId: panel.id };
}

/** The unique signal ids of every panel, in first-added order. */
export function plottedSignalIds(panels: readonly PlotPanelState[]): string[] {
  const seen = new Set<string>();
  const ids: string[] = [];
  for (const panel of panels) {
    for (const id of panel.signals) {
      if (!seen.has(id)) {
        seen.add(id);
        ids.push(id);
      }
    }
  }
  return ids;
}

/** The manifest entries of a panel's signal ids, in panel order. */
export function panelSignals(
  panel: PlotPanelState,
  manifest: RunManifest | null,
): RunSignal[] {
  if (manifest === null) {
    return [];
  }
  const byId = new Map(manifest.signals.map((signal) => [signal.id, signal]));
  return panel.signals
    .map((id) => byId.get(id))
    .filter((signal): signal is RunSignal => signal !== undefined);
}

/** The result of placing one signal into the panel layout. */
interface Placement {
  panels: PlotPanelState[];
  activePanelId: string;
  /** 1-based number of the panel that received (or would receive) the signal. */
  panelNumber: number;
  /** True when the signal could not join the target and started a new panel. */
  createdPanel: boolean;
  /** How many unit groups the receiving panel has after the placement. */
  groups: number;
}

/**
 * Put one signal into `targetPanelId` (or the active panel). A third unit
 * group starts a new panel unless `force` is set; the drag-and-drop path can
 * deliberately target a panel, and the header then offers "Split panel".
 */
function placeSignal(
  panels: readonly PlotPanelState[],
  activePanelId: string,
  manifest: RunManifest,
  signal: RunSignal,
  targetPanelId: string | null,
  force: boolean,
): Placement | null {
  const target =
    panels.find((panel) => panel.id === (targetPanelId ?? activePanelId)) ??
    panels[0];
  if (target === undefined) {
    return null;
  }
  const panelIndex = panels.findIndex((panel) => panel.id === target.id);
  const panelNumber = panelIndex + 1;
  if (target.signals.includes(signal.id)) {
    return {
      panels: [...panels],
      activePanelId: target.id,
      panelNumber,
      createdPanel: false,
      groups: groupSignalsByUnit(panelSignals(target, manifest)).length,
    };
  }
  const existing = panelSignals(target, manifest);
  const groups = groupSignalsByUnit([...existing, signal]).length;
  if (force || canAddSignalToPanel(existing, signal)) {
    return {
      panels: panels.map((panel) =>
        panel.id === target.id
          ? { ...panel, signals: [...panel.signals, signal.id] }
          : panel,
      ),
      activePanelId: target.id,
      panelNumber,
      createdPanel: false,
      groups,
    };
  }
  const created = makePanel([signal.id]);
  return {
    panels: [
      ...panels.slice(0, panelIndex + 1),
      created,
      ...panels.slice(panelIndex + 1),
    ],
    activePanelId: created.id,
    panelNumber: panelIndex + 2,
    createdPanel: true,
    groups: 1,
  };
}

function requestWidth(view: SeriesWindow | null, width: number): number {
  if (view === null) {
    return 0;
  }
  const pixels =
    Number.isFinite(width) && width > 0 ? Math.round(width) : DEFAULT_PIXEL_WIDTH;
  return Math.max(1, pixels);
}

function windowKey(view: SeriesWindow | null): string {
  return view === null ? "*" : `${view.t0}:${view.t1}`;
}

function messageOf(error: unknown): string {
  return error instanceof Error ? error.message : String(error);
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

/** The first error diagnostic as a user-facing message (plan 3.4 style). */
function failureMessage(diagnostics: readonly Diagnostic[]): string | null {
  const first =
    diagnostics.find((diagnostic) => diagnostic.severity === "error") ??
    diagnostics[0];
  if (first === undefined) {
    return null;
  }
  const hint = first.hint?.trim() ?? "";
  return hint.length > 0
    ? `${first.code}: ${first.message} ${hint}`
    : `${first.code}: ${first.message}`;
}

// --------------------------------------------------------------- module state

interface LiveSeries {
  runId: string;
  time: number[];
  values: Record<string, number[]>;
}

let live: LiveSeries | null = null;
let socket: WebSocket | null = null;
let subscribedKey: string | null = null;
let pollTimer: ReturnType<typeof setTimeout> | null = null;
let pollToken = 0;
let noticeTimer: ReturnType<typeof setTimeout> | null = null;
let dataAbort: AbortController | null = null;
let compareAbort: AbortController | null = null;
let dataGeneration = 0;
let compareGeneration = 0;
/** `${runId}@${rows}` of the last final-data refresh (avoids duplicate full fetches). */
let finalDataKey: string | null = null;

/** The live tail of a run, or null when there is nothing to draw yet. */
export function liveSeriesFor(
  runId: string | null | undefined,
): ChartSeriesData | null {
  if (runId === null || runId === undefined || live === null) {
    return null;
  }
  if (live.runId !== runId || live.time.length === 0) {
    return null;
  }
  return { time: live.time, values: live.values };
}

function resetLive(): void {
  live = null;
  useRunStore.setState((state) => ({ liveVersion: state.liveVersion + 1 }));
}

function stopPolling(): void {
  pollToken += 1;
  if (pollTimer !== null) {
    clearTimeout(pollTimer);
    pollTimer = null;
  }
}

function closeSocket(): void {
  const current = socket;
  socket = null;
  subscribedKey = null;
  if (current !== null) {
    current.onopen = null;
    current.onmessage = null;
    current.onerror = null;
    current.onclose = null;
    try {
      current.close();
    } catch {
      /* already closing */
    }
  }
  useRunStore.setState((state) =>
    state.socketState === "off" ? {} : { socketState: "off" },
  );
}

function showNotice(message: string | null): void {
  if (noticeTimer !== null) {
    clearTimeout(noticeTimer);
    noticeTimer = null;
  }
  useRunStore.setState({ notice: message });
  if (message !== null) {
    noticeTimer = setTimeout(() => {
      noticeTimer = null;
      useRunStore.setState({ notice: null });
    }, 6000);
  }
}

/** Push the plotted ids to the socket, resetting the tail cursor on a change. */
function syncSubscription(force: boolean): void {
  const state = useRunStore.getState();
  const available = new Set(
    (state.manifest?.signals ?? []).map((signal) => signal.id),
  );
  const ids = plottedSignalIds(state.panels).filter((id) => available.has(id));
  const key = ids.join(",");
  if (!force && key === subscribedKey) {
    return;
  }
  subscribedKey = key;
  resetLive();
  const current = socket;
  if (current === null || current.readyState !== 1) {
    return;
  }
  try {
    current.send(JSON.stringify({ subscribe: ids }));
  } catch {
    /* the close handler will report the socket as closed */
  }
}

/** Merge one `run.tail` payload into the live series. */
function mergeTail(params: Record<string, unknown>): void {
  const runId = params.runId;
  const ids = params.ids;
  const time = params.time;
  const columns = params.values;
  if (
    typeof runId !== "string" ||
    !Array.isArray(ids) ||
    !ids.every((id) => typeof id === "string") ||
    !Array.isArray(time) ||
    !time.every((value) => typeof value === "number" && Number.isFinite(value)) ||
    !Array.isArray(columns) ||
    columns.length !== ids.length
  ) {
    return;
  }
  const state = useRunStore.getState();
  if (state.runId !== runId) {
    return;
  }
  if (state.status !== "running" && state.status !== "starting") {
    // A message already in flight when run.done closed the socket must not
    // extend the series after the final `/data` refresh.
    return;
  }
  const validColumns: number[][] = [];
  for (const column of columns) {
    if (
      !Array.isArray(column) ||
      column.length !== time.length ||
      !column.every((value) => typeof value === "number")
    ) {
      return;
    }
    validColumns.push(column as number[]);
  }

  if (live === null || live.runId !== runId) {
    live = { runId, time: [], values: {} };
  }
  live.time.push(...(time as number[]));
  for (let index = 0; index < ids.length; index += 1) {
    const id = ids[index] as string;
    const column = validColumns[index] as number[];
    const target = live.values[id] ?? [];
    live.values[id] = target;
    target.push(...column);
  }
  if (live.time.length > LIVE_POINT_LIMIT) {
    const drop = live.time.length - LIVE_POINT_LIMIT;
    live.time.splice(0, drop);
    for (const column of Object.values(live.values)) {
      column.splice(0, drop);
    }
  }
  useRunStore.setState((current) => ({
    liveVersion: current.liveVersion + 1,
  }));
}

/**
 * Apply a manifest. A running fake run already lists its signals; a real
 * worker publishes the final manifest at the end, so an empty running signal
 * list must not wipe the panels.
 */
function ingestManifest(manifest: RunManifest): void {
  const state = useRunStore.getState();
  if (state.runId !== null && manifest.id !== state.runId) {
    return;
  }
  let panels = state.panels;
  if (manifest.signals.length > 0) {
    const available = new Set(manifest.signals.map((signal) => signal.id));
    panels = panels.map((panel) => ({
      ...panel,
      signals: panel.signals.filter((id) => available.has(id)),
    }));
  }
  const activePanelId = panels.some((panel) => panel.id === state.activePanelId)
    ? state.activePanelId
    : (panels[0]?.id ?? "");

  useRunStore.setState({
    manifest,
    panels,
    activePanelId,
    stats: manifest.stats ?? state.stats,
  });

  if (manifest.status === "running") {
    if (manifest.time.n > 0) {
      const current = useRunStore.getState();
      if (
        current.progress === null ||
        manifest.time.t1 > current.progress.t ||
        manifest.time.n !== current.progress.rows
      ) {
        useRunStore.setState({
          progress: { t: manifest.time.t1, rows: manifest.time.n },
        });
      }
    }
    syncSubscription(false);
    return;
  }
  finishRun(manifest.status, manifest.stats, manifest.id, manifest.diagnostics);
}

/** Settle a finished run: stop follow-ups and fetch the final decimated data. */
function finishRun(
  status: RunStatus,
  stats: RunStats | undefined,
  runId: string,
  diagnostics: readonly Diagnostic[] = [],
): void {
  const state = useRunStore.getState();
  if (state.runId !== runId) {
    return;
  }
  const manifest = state.manifest;
  stopPolling();
  closeSocket();
  const diagnosticsMessage =
    status === "failed" ? failureMessage(diagnostics) : null;
  useRunStore.setState({
    status,
    stats: stats ?? manifest?.stats ?? state.stats,
    phase: null,
    stopping: false,
    error: diagnosticsMessage ?? state.error,
    progress:
      manifest !== null
        ? { t: manifest.time.t1, rows: manifest.time.n }
        : state.progress,
  });
  // The socket and the poll can both report completion, and a real worker
  // publishes the final manifest just after `run.done`. Refresh once per
  // (run, row count); partial live columns and raw responses for the same run
  // are invalidated so the plots show the final file, not a running prefix.
  const key = `${runId}@${manifest?.time.n ?? 0}`;
  if (finalDataKey !== key) {
    finalDataKey = key;
    runDataCache.invalidateRun(runId);
    void state.ensureData(undefined, true);
    void state.ensureCompareData(undefined, true);
  }
}

async function refreshManifest(runId: string): Promise<void> {
  try {
    const manifest = await fetchRunManifest(runId);
    if (useRunStore.getState().runId === runId) {
      ingestManifest(manifest);
    }
  } catch {
    /* the poll or a later refresh will try again */
  }
}

function startPolling(runId: string): void {
  stopPolling();
  const token = pollToken;
  const tick = async (): Promise<void> => {
    if (token !== pollToken || useRunStore.getState().runId !== runId) {
      return;
    }
    try {
      const manifest = await fetchRunManifest(runId);
      if (token !== pollToken || useRunStore.getState().runId !== runId) {
        return;
      }
      ingestManifest(manifest);
      if (manifest.status !== "running") {
        return;
      }
    } catch {
      /* transient; keep polling until done or cancelled */
    }
    if (token === pollToken) {
      pollTimer = setTimeout(() => void tick(), RUN_POLL_INTERVAL_MS);
    }
  };
  pollTimer = setTimeout(() => void tick(), RUN_POLL_INTERVAL_MS);
}

function handleSocketMessage(raw: unknown): void {
  if (typeof raw !== "string") {
    return;
  }
  let message: unknown;
  try {
    message = JSON.parse(raw) as unknown;
  } catch {
    return;
  }
  if (!isRecord(message) || typeof message.method !== "string") {
    return;
  }
  const params = isRecord(message.params) ? message.params : {};
  const state = useRunStore.getState();

  switch (message.method) {
    case "run.phase": {
      if (params.runId !== state.runId) {
        return;
      }
      const phase = typeof params.phase === "string" ? params.phase : null;
      useRunStore.setState({ phase });
      break;
    }
    case "run.progress": {
      if (params.runId !== state.runId) {
        return;
      }
      if (typeof params.t === "number" && Number.isFinite(params.t)) {
        useRunStore.setState({
          progress: {
            t: params.t,
            rows:
              typeof params.rows === "number" && Number.isFinite(params.rows)
                ? params.rows
                : 0,
          },
          status:
            state.status === "starting" || state.status === "idle"
              ? "running"
              : state.status,
        });
      }
      break;
    }
    case "run.tail":
      mergeTail(params);
      break;
    case "run.done": {
      if (params.runId !== state.runId || state.runId === null) {
        return;
      }
      const status = params.status;
      if (
        status !== "done" &&
        status !== "failed" &&
        status !== "cancelled" &&
        status !== "running"
      ) {
        return;
      }
      const stats = isRecord(params.stats)
        ? (params.stats as unknown as RunStats)
        : undefined;
      const diagnostics = Array.isArray(params.diagnostics)
        ? (params.diagnostics as unknown as Diagnostic[])
        : [];
      finishRun(status, stats, state.runId, diagnostics);
      void refreshManifest(state.runId);
      break;
    }
    case "run.error": {
      const text =
        typeof params.message === "string" ? params.message : "run socket error";
      // A failed subscription (for example before a real worker publishes its
      // signal list) is not a failed run; surface it in the console only.
      console.warn(`bg-sim run socket: ${text}`);
      break;
    }
    default:
      break;
  }
}

function openSocket(runId: string): void {
  if (typeof WebSocket === "undefined") {
    useRunStore.setState({ socketState: "off" });
    return;
  }
  closeSocket();
  let next: WebSocket;
  try {
    next = new WebSocket(runSocketUrl(runId));
  } catch {
    useRunStore.setState({ socketState: "closed" });
    return;
  }
  socket = next;
  subscribedKey = null;
  useRunStore.setState({ socketState: "connecting" });

  next.onopen = () => {
    if (socket !== next) {
      return;
    }
    useRunStore.setState({ socketState: "open" });
    syncSubscription(true);
  };
  next.onmessage = (event: MessageEvent) => {
    if (socket === next) {
      handleSocketMessage(event.data);
    }
  };
  next.onerror = () => {
    if (socket === next) {
      useRunStore.setState({ socketState: "closed" });
    }
  };
  next.onclose = () => {
    if (socket !== next) {
      return;
    }
    socket = null;
    subscribedKey = null;
    useRunStore.setState({ socketState: "closed" });
  };
}

// -------------------------------------------------------------------- store

const firstPanels = initialPanels();

export const useRunStore = create<RunStoreState>()((set, get) => ({
  runId: null,
  manifest: null,
  status: "idle",
  phase: null,
  progress: null,
  stats: null,
  error: null,
  notice: null,
  stopping: false,
  socketState: "off",

  panels: firstPanels.panels,
  activePanelId: firstPanels.activePanelId,

  view: null,
  pixelWidth: 0,

  data: null,
  dataKey: null,
  dataLoading: false,
  dataError: null,

  compareData: null,
  compareKey: null,
  pinned: null,

  cursorTime: null,
  liveVersion: 0,

  startRun: async () => {
    if (get().status === "starting" || get().status === "running") {
      return;
    }
    const { project, doc } = useDocumentStore.getState();
    if (project === null || doc === null) {
      set({ status: "failed", error: "Open a model before running it." });
      return;
    }

    stopPolling();
    closeSocket();
    resetLive();
    subscribedKey = null;
    finalDataKey = null;
    dataAbort?.abort();
    dataAbort = null;
    dataGeneration += 1;
    set({
      runId: null,
      manifest: null,
      status: "starting",
      phase: null,
      progress: null,
      stats: null,
      error: null,
      notice: null,
      stopping: false,
      view: null,
      data: null,
      dataKey: null,
      dataLoading: false,
      dataError: null,
      compareData: null,
      compareKey: null,
      cursorTime: null,
    });

    try {
      const runId = await createRun(project, doc);
      if (get().status !== "starting") {
        // The model changed while the POST was in flight: do not leave an
        // untracked run growing in the background.
        void cancelRun(runId).catch(() => undefined);
        return;
      }
      set({ runId, status: "running" });
      openSocket(runId);
      startPolling(runId);
      try {
        const manifest = await fetchRunManifest(runId);
        if (get().runId === runId) {
          ingestManifest(manifest);
        }
      } catch {
        /* the poll will publish the manifest */
      }
      void get().ensureData(undefined, true);
    } catch (error) {
      if (get().status !== "starting") {
        return;
      }
      set({ status: "failed", error: messageOf(error), stopping: false });
      stopPolling();
    }
  },

  stopRun: async () => {
    const runId = get().runId;
    if (runId === null) {
      return;
    }
    set({ stopping: true });
    try {
      await cancelRun(runId);
      set({ phase: "cancelling" });
    } catch (error) {
      set({ stopping: false, error: messageOf(error) });
    }
  },

  addSignal: (signalId, panelId, options) => {
    const state = get();
    const manifest = state.manifest;
    const signal = manifest?.signals.find((entry) => entry.id === signalId);
    if (signal === undefined || manifest === null) {
      showNotice(
        state.manifest === null
          ? "Run the model before adding a signal."
          : `This run has no signal ${signalId}.`,
      );
      return;
    }
    const target =
      state.panels.find((panel) => panel.id === (panelId ?? state.activePanelId)) ??
      state.panels[0];
    const targetSignals = target === undefined ? [] : panelSignals(target, manifest);
    const placement = placeSignal(
      state.panels,
      state.activePanelId,
      manifest,
      signal,
      panelId ?? null,
      options?.force === true,
    );
    if (placement === null) {
      const panel = makePanel([signalId]);
      set({ panels: [panel], activePanelId: panel.id });
      return;
    }
    if (target !== undefined && target.signals.includes(signalId)) {
      set({ activePanelId: target.id });
      showNotice(`${signalId} is already in this panel.`);
      return;
    }
    set({
      panels: placement.panels,
      activePanelId: placement.activePanelId,
    });
    if (placement.createdPanel) {
      const groups = groupSignalsByUnit([...targetSignals, signal]);
      showNotice(
        `Panel ${placement.panelNumber - 1} already shows two unit groups; ` +
          `${signalId} (${groups[groups.length - 1]?.label ?? "its unit"}) ` +
          `started Panel ${placement.panelNumber}.`,
      );
    } else if (placement.groups > 2) {
      showNotice(
        `Added ${signalId} to Panel ${placement.panelNumber}; ` +
          `${placement.groups} unit groups now share it — use Split panel.`,
      );
    } else {
      showNotice(`Added ${signalId} to Panel ${placement.panelNumber}.`);
    }
    const updated = get();
    updated.syncSocketSubscription();
    void updated.ensureData();
    void updated.ensureCompareData();
  },

  addSignals: (signalIds, panelId) => {
    const state = get();
    const manifest = state.manifest;
    if (manifest === null) {
      showNotice("Run the model before adding signals.");
      return 0;
    }
    const byId = new Map(manifest.signals.map((signal) => [signal.id, signal]));
    const seen = new Set(plottedSignalIds(state.panels));
    const panelCount = state.panels.length;
    let panels = state.panels;
    let active = panelId ?? state.activePanelId;
    let added = 0;
    let unknown = 0;
    let already = 0;
    for (const id of signalIds) {
      const signal = byId.get(id);
      if (signal === undefined) {
        unknown += 1;
        continue;
      }
      if (seen.has(id)) {
        already += 1;
        continue;
      }
      const placement = placeSignal(panels, active, manifest, signal, active, false);
      if (placement === null) {
        break;
      }
      panels = placement.panels;
      active = placement.activePanelId;
      added += 1;
      seen.add(id);
    }
    if (added === 0) {
      showNotice(
        unknown > 0 && already === 0
          ? "This run has none of those signals."
          : "Those signals are already plotted.",
      );
      return 0;
    }
    set({ panels, activePanelId: active });
    const updated = get();
    updated.syncSocketSubscription();
    void updated.ensureData();
    void updated.ensureCompareData();
    const newPanels = panels.length - panelCount;
    const parts = [`Plotted ${added} signal${added === 1 ? "" : "s"}`];
    if (newPanels > 0) {
      parts.push(`in ${newPanels + 1} panels`);
    }
    if (already > 0) {
      parts.push(`${already} already plotted`);
    }
    if (unknown > 0) {
      parts.push(`${unknown} not in this run`);
    }
    showNotice(`${parts.join("; ")}.`);
    return added;
  },

  splitPanel: (panelId) => {
    const state = get();
    const index = state.panels.findIndex((panel) => panel.id === panelId);
    const panel = state.panels[index];
    if (panel === undefined) {
      return false;
    }
    const axes = assignPanelAxes(panelSignals(panel, state.manifest));
    if (axes.overflow.length === 0) {
      showNotice(
        `Panel ${index + 1} has at most two unit groups; there is nothing to split.`,
      );
      return false;
    }
    const moved = new Set(
      axes.overflow.flatMap((group) => group.signals.map((signal) => signal.id)),
    );
    const created = makePanel([...moved]);
    const panels = [...state.panels];
    panels[index] = {
      ...panel,
      signals: panel.signals.filter((id) => !moved.has(id)),
    };
    panels.splice(index + 1, 0, created);
    set({ panels, activePanelId: created.id });
    const updated = get();
    updated.syncSocketSubscription();
    void updated.ensureData();
    void updated.ensureCompareData();
    showNotice(
      `Moved ${moved.size} signal${moved.size === 1 ? "" : "s"} from ` +
        `Panel ${index + 1} to Panel ${index + 2}.`,
    );
    return true;
  },


  removeSignal: (panelId, signalId) => {
    const state = get();
    const panel = state.panels.find((entry) => entry.id === panelId);
    if (panel === undefined || !panel.signals.includes(signalId)) {
      return;
    }
    set({
      panels: state.panels.map((entry) =>
        entry.id === panelId
          ? { ...entry, signals: entry.signals.filter((id) => id !== signalId) }
          : entry,
      ),
    });
    get().syncSocketSubscription();
    void get().ensureData();
    void get().ensureCompareData();
  },

  addPanel: () => {
    const panel = makePanel();
    set((state) => ({
      panels: [...state.panels, panel],
      activePanelId: panel.id,
    }));
    return panel.id;
  },

  setActivePanel: (panelId) => {
    if (get().panels.some((panel) => panel.id === panelId)) {
      set({ activePanelId: panelId });
    }
  },

  renamePanel: (panelId, name) => {
    const trimmed = name.trim();
    set((state) => ({
      panels: state.panels.map((panel) =>
        panel.id === panelId
          ? trimmed.length > 0
            ? { ...panel, name: trimmed }
            : { ...panel, name: undefined }
          : panel,
      ),
    }));
  },

  removePanel: (panelId) => {
    const state = get();
    if (state.panels.length <= 1) {
      set({
        panels: state.panels.map((panel) =>
          panel.id === panelId ? { ...panel, signals: [] } : panel,
        ),
      });
    } else {
      const index = state.panels.findIndex((panel) => panel.id === panelId);
      const panels = state.panels.filter((panel) => panel.id !== panelId);
      const activePanelId =
        state.activePanelId === panelId
          ? (panels[Math.max(0, index - 1)]?.id ?? panels[0]?.id ?? "")
          : state.activePanelId;
      set({ panels, activePanelId });
    }
    get().syncSocketSubscription();
    void get().ensureData();
    void get().ensureCompareData();
  },

  setView: (view, px) => {
    set({
      view,
      ...(px !== undefined && Number.isFinite(px) && px > 0
        ? { pixelWidth: px }
        : {}),
    });
    void get().ensureData(px, true);
    void get().ensureCompareData(px, true);
  },

  followLive: () => {
    if (get().status !== "running") {
      return;
    }
    // The live series is already in memory; a `/data` round trip for the whole
    // partial stream would fetch far more than the tail that is already here.
    set({ view: null });
  },

  ensureData: async (px, force = false) => {
    const state = get();
    const manifest = state.manifest;
    if (manifest === null || manifest.signals.length === 0) {
      if (state.data !== null || state.dataKey !== null) {
        set({ data: null, dataKey: null, dataLoading: false });
      }
      return;
    }
    const available = new Set(manifest.signals.map((signal) => signal.id));
    const ids = plottedSignalIds(state.panels).filter((id) => available.has(id));
    if (ids.length === 0) {
      if (state.data !== null || state.dataKey !== null) {
        set({ data: null, dataKey: null, dataLoading: false, dataError: null });
      }
      return;
    }

    const width = requestWidth(state.view, px ?? state.pixelWidth);
    const key = `${manifest.id}|${ids.join(",")}|${windowKey(state.view)}|${width}`;
    if (!force && key === state.dataKey) {
      return;
    }

    dataAbort?.abort();
    dataAbort = null;
    const generation = ++dataGeneration;

    // While a run is writing, the same (run, window, px) key describes a
    // growing stream; caching it would serve yesterday's prefix after a later
    // fetch. The LRU is for finished runs (zoom, pan, panels, pinned overlays).
    const cacheable = state.status !== "running" && state.status !== "starting";
    const cached = cacheable
      ? ids.map((id) =>
          runDataCache.get(manifest.id, id, state.view, width),
        )
      : [];
    const first = cached[0];
    const allCached =
      cached.length === ids.length &&
      cached.every((frame) => frame !== undefined);
    const sameTime =
      first !== undefined &&
      allCached &&
      cached.every((frame) => {
        if (frame === undefined) {
          return false;
        }
        return (
          frame.time === first.time ||
          (frame.time.length === first.time.length &&
            frame.time[0] === first.time[0] &&
            frame.time[frame.time.length - 1] ===
              first.time[first.time.length - 1])
        );
      });
    if (first !== undefined && allCached && sameTime) {
      const values: Record<string, Float64Array> = {};
      ids.forEach((id, index) => {
        const frame = cached[index];
        if (frame !== undefined) {
          values[id] = frame.values;
        }
      });
      set({
        data: { key, time: first.time, values },
        dataKey: key,
        dataLoading: false,
        dataError: null,
      });
      return;
    }

    const controller = new AbortController();
    dataAbort = controller;
    set({ dataLoading: true, dataError: null, dataKey: key });
    try {
      const frame = await fetchRunData(
        manifest.id,
        ids,
        state.view,
        width,
        controller.signal,
      );
      if (generation !== dataGeneration || controller.signal.aborted) {
        return;
      }
      const values: Record<string, Float64Array> = {};
      ids.forEach((id, index) => {
        const column = frame.values[index] ?? new Float64Array(0);
        values[id] = column;
        if (cacheable && frame.nPoints > 0) {
          runDataCache.set(manifest.id, id, state.view, width, {
            time: frame.time,
            values: column,
          });
        }
      });
      set({
        data: { key, time: frame.time, values },
        dataKey: key,
        dataLoading: false,
        dataError: null,
      });
    } catch (error) {
      if (controller.signal.aborted || generation !== dataGeneration) {
        return;
      }
      set({
        dataLoading: false,
        dataError: messageOf(error),
        dataKey: null,
      });
    } finally {
      if (dataAbort === controller) {
        dataAbort = null;
      }
    }
  },

  ensureCompareData: async (px, force = false) => {
    const state = get();
    const pinned = state.pinned;
    if (pinned === null) {
      if (state.compareData !== null || state.compareKey !== null) {
        set({ compareData: null, compareKey: null });
      }
      return;
    }
    const available = new Set(
      pinned.manifest.signals.map((signal) => signal.id),
    );
    const ids = plottedSignalIds(state.panels).filter((id) => available.has(id));
    if (ids.length === 0) {
      if (state.compareData !== null || state.compareKey !== null) {
        set({ compareData: null, compareKey: null });
      }
      return;
    }

    const width = requestWidth(state.view, px ?? state.pixelWidth);
    const key = `${pinned.manifest.id}|${ids.join(",")}|${windowKey(state.view)}|${width}`;
    if (!force && key === state.compareKey) {
      return;
    }

    compareAbort?.abort();
    compareAbort = null;
    const generation = ++compareGeneration;

    const cached = ids.map((id) =>
      runDataCache.get(pinned.manifest.id, id, state.view, width),
    );
    const first = cached[0];
    const allCached =
      cached.length === ids.length &&
      cached.every((frame) => frame !== undefined);
    const sameTime =
      first !== undefined &&
      allCached &&
      cached.every((frame) => {
        if (frame === undefined) {
          return false;
        }
        return (
          frame.time === first.time ||
          (frame.time.length === first.time.length &&
            frame.time[0] === first.time[0] &&
            frame.time[frame.time.length - 1] ===
              first.time[first.time.length - 1])
        );
      });
    if (first !== undefined && allCached && sameTime) {
      const values: Record<string, Float64Array> = {};
      ids.forEach((id, index) => {
        const frame = cached[index];
        if (frame !== undefined) {
          values[id] = frame.values;
        }
      });
      set({
        compareData: { key, time: first.time, values },
        compareKey: key,
      });
      return;
    }

    const controller = new AbortController();
    compareAbort = controller;
    try {
      const frame = await fetchRunData(
        pinned.manifest.id,
        ids,
        state.view,
        width,
        controller.signal,
      );
      if (generation !== compareGeneration || controller.signal.aborted) {
        return;
      }
      const values: Record<string, Float64Array> = {};
      ids.forEach((id, index) => {
        const column = frame.values[index] ?? new Float64Array(0);
        values[id] = column;
        if (frame.nPoints > 0) {
          runDataCache.set(pinned.manifest.id, id, state.view, width, {
            time: frame.time,
            values: column,
          });
        }
      });
      set({
        compareData: { key, time: frame.time, values },
        compareKey: key,
      });
    } catch (error) {
      if (controller.signal.aborted || generation !== compareGeneration) {
        return;
      }
      console.warn(`bg-sim pinned run data: ${messageOf(error)}`);
    } finally {
      if (compareAbort === controller) {
        compareAbort = null;
      }
    }
  },

  syncSocketSubscription: () => {
    syncSubscription(false);
  },

  setCursorTime: (time) => set({ cursorTime: time }),

  pinRun: () => {
    const state = get();
    if (state.manifest === null) {
      showNotice("Run the model before pinning a run.");
      return;
    }
    if (state.status === "running" || state.status === "starting") {
      showNotice("A run can be pinned when it has finished.");
      return;
    }
    set({ pinned: { manifest: state.manifest } });
    showNotice(
      `Pinned ${state.manifest.id}; the next run overlays it as dashed lines.`,
    );
    void get().ensureCompareData(undefined, true);
  },

  unpinRun: () => {
    set({ pinned: null, compareData: null, compareKey: null });
    showNotice("The comparison run is no longer shown.");
  },

  setNotice: (message) => {
    showNotice(message);
  },

  reset: () => {
    stopPolling();
    closeSocket();
    resetLive();
    if (noticeTimer !== null) {
      clearTimeout(noticeTimer);
      noticeTimer = null;
    }
    dataAbort?.abort();
    dataAbort = null;
    compareAbort?.abort();
    compareAbort = null;
    dataGeneration += 1;
    compareGeneration += 1;
    subscribedKey = null;
    finalDataKey = null;
    runDataCache.clear();
    const panels = initialPanels();
    set({
      runId: null,
      manifest: null,
      status: "idle",
      phase: null,
      progress: null,
      stats: null,
      error: null,
      notice: null,
      stopping: false,
      socketState: "off",
      panels: panels.panels,
      activePanelId: panels.activePanelId,
      view: null,
      pixelWidth: 0,
      data: null,
      dataKey: null,
      dataLoading: false,
      dataError: null,
      compareData: null,
      compareKey: null,
      pinned: null,
      cursorTime: null,
      liveVersion: get().liveVersion + 1,
    });
  },
}));

/** Reset every run/plot field; used by tests and when the model changes. */
export function resetRunStore(): void {
  useRunStore.getState().reset();
}

// ------------------------------------------------------- global inspect time

/**
 * The plot cursor as the global inspect time (plan 7.5), in seconds. The 3D
 * viewer playback head and the bond hover values read this instead of keeping
 * their own cursor, and `setCursorTime` is the single writer.
 */
export function getInspectTime(): number | null {
  return useRunStore.getState().cursorTime;
}

/** React hook form of {@link getInspectTime}. */
export function useInspectTime(): number | null {
  return useRunStore((state) => state.cursorTime);
}

/**
 * Observe changes of the global inspect time outside React (viewer, hover
 * values). Returns an unsubscribe function. The listener also fires for
 * `null` (no cursor yet).
 */
export function subscribeInspectTime(
  listener: (time: number | null) => void,
): () => void {
  return useRunStore.subscribe((state, previous) => {
    if (state.cursorTime !== previous.cursorTime) {
      listener(state.cursorTime);
    }
  });
}

/** True while live tails are being followed (running and not zoomed). */
export function isLiveFollowing(
  state: Pick<RunStoreState, "status" | "view"> = useRunStore.getState(),
): boolean {
  return state.status === "running" && state.view === null;
}

/** Points currently buffered from the live tail (0 when no tail is active). */
export function livePointCount(): number {
  return live?.time.length ?? 0;
}

