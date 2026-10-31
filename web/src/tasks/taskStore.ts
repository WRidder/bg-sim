/**
 * The background tasks registry (the top bar's tasks indicator, Eclipse's "Progress view").
 *
 * A task is anything that runs longer than a click and goes on while the user works: an
 * FMU export job on the backend (`exportTasks.ts`, which survives closing the dialog and
 * reloading the page) or a CSV download streamed by the browser (`csvTask.ts`). Simulation
 * runs are not tasks: they have the run bar, one per model, and their plots are the progress.
 *
 * The store only holds data. The sources put their tasks with `putTask`, which works out
 * the transitions: a task seen running in this session that ends becomes `unseen` (the
 * indicator's dot) and is announced, unless the user is looking at it (`viewing`, e.g. the
 * Export dialog attached to that job). Cancel functions live beside the store, keyed by task
 * id, because they are not data.
 */

import { create } from "zustand";

import type { ExportJob } from "../contracts/export-job";

export type TaskKind = "fmu-export" | "csv-export";
export type TaskStatus = "queued" | "running" | "done" | "failed" | "cancelled" | "refused";

export interface TaskResult {
  href: string;
  fileName: string;
  /** The link text, e.g. `Download arm.fmu (12 KB)`. */
  label: string;
}

export interface Task {
  /** Unique over kinds: `export:<jobId>`, `csv:<n>`. */
  id: string;
  kind: TaskKind;
  /** E.g. `FMU export · arm`. */
  title: string;
  project: string | null;
  model: string | null;
  status: TaskStatus;
  /** What the task does now, or how it ended (one line). */
  phase: string | null;
  /** 0..1 when known; null shows an indeterminate spinner. */
  progress: number | null;
  /** Epoch milliseconds. */
  started: number;
  finished: number | null;
  error: string | null;
  /** Finished in this session while nobody looked: the indicator shows a dot. */
  unseen: boolean;
  /** Whether Cancel is offered while the task is active. */
  cancellable: boolean;
  result: TaskResult | null;
  /** The backend's job document of an `fmu-export` task. */
  exportJob: ExportJob | null;
}

export interface TaskAnnouncement {
  taskId: string;
  text: string;
  /** Bumped per announcement, so the same text twice is announced twice. */
  seq: number;
}

/** Finished tasks kept in the list; older ones drop off. */
export const MAX_FINISHED = 20;

const DISMISSED_KEY = "bgsim.tasks.dismissed";
const MAX_DISMISSED = 200;

export function isActive(task: Pick<Task, "status">): boolean {
  return task.status === "queued" || task.status === "running";
}

function readDismissed(): string[] {
  try {
    const raw = globalThis.localStorage?.getItem(DISMISSED_KEY);
    const parsed: unknown = raw ? JSON.parse(raw) : [];
    return Array.isArray(parsed) ? parsed.filter((id): id is string => typeof id === "string") : [];
  } catch {
    return [];
  }
}

function writeDismissed(ids: string[]): void {
  try {
    globalThis.localStorage?.setItem(DISMISSED_KEY, JSON.stringify(ids.slice(-MAX_DISMISSED)));
  } catch {
    /* a private window or blocked storage: dismissing then lasts until the reload */
  }
}

const ENDING: Record<TaskStatus, string> = {
  queued: "is waiting",
  running: "is running",
  done: "finished",
  failed: "failed",
  cancelled: "was cancelled",
  refused: "was refused",
};

/** `FMU export · arm finished`, for the live region and the toast. */
export function endingText(task: Pick<Task, "title" | "status">): string {
  return `${task.title} ${ENDING[task.status]}`;
}

interface TaskState {
  /** Active first (newest first), then finished (newest first). */
  tasks: Task[];
  /** The task a dialog shows right now; its end is not "unseen". */
  viewing: string | null;
  announcement: TaskAnnouncement | null;
  /** A source's trouble reaching the backend (shown in the popover; polling retries). */
  connectionError: string | null;
  /** Finished tasks the user cleared; a reload does not bring them back. */
  dismissed: string[];
  putTask: (task: Task) => void;
  updateTask: (id: string, patch: Partial<Task>) => void;
  setViewing: (id: string | null) => void;
  markSeen: (ids?: readonly string[]) => void;
  dismissTask: (id: string) => void;
  clearFinished: () => void;
  setConnectionError: (message: string | null) => void;
}

function finishedAt(task: Task): number {
  return task.finished ?? task.started;
}

/** Active tasks first, then finished ones; newest first in each; at most MAX_FINISHED finished. */
function ordered(tasks: Task[]): Task[] {
  const active = tasks.filter(isActive).sort((a, b) => b.started - a.started);
  const finished = tasks
    .filter((task) => !isActive(task))
    .sort((a, b) => finishedAt(b) - finishedAt(a))
    .slice(0, MAX_FINISHED);
  return [...active, ...finished];
}

let announcementSeq = 0;

function merge(state: TaskState, next: Task): Partial<TaskState> {
  const previous = state.tasks.find((task) => task.id === next.id);
  if (previous === undefined && !isActive(next) && state.dismissed.includes(next.id)) {
    return {};
  }
  let task = next;
  let announcement = state.announcement;
  if (previous !== undefined && isActive(previous) && !isActive(next)) {
    // Seen running in this session and now ended: tell the user unless they are watching.
    const watched = state.viewing === next.id;
    task = { ...next, unseen: !watched };
    if (!watched) {
      announcementSeq += 1;
      announcement = { taskId: next.id, text: endingText(next), seq: announcementSeq };
    }
  } else if (previous !== undefined) {
    task = { ...next, unseen: previous.unseen && !isActive(next) };
  }
  const tasks = previous === undefined
    ? [...state.tasks, task]
    : state.tasks.map((entry) => (entry.id === next.id ? task : entry));
  return { tasks: ordered(tasks), announcement };
}

export const useTaskStore = create<TaskState>((set) => ({
  tasks: [],
  viewing: null,
  announcement: null,
  connectionError: null,
  dismissed: readDismissed(),
  putTask: (task) => set((state) => merge(state, task)),
  updateTask: (id, patch) =>
    set((state) => {
      const previous = state.tasks.find((task) => task.id === id);
      return previous === undefined ? {} : merge(state, { ...previous, ...patch });
    }),
  setViewing: (id) =>
    set((state) => ({
      viewing: id,
      tasks: state.tasks.some((task) => task.id === id && task.unseen)
        ? state.tasks.map((task) => (task.id === id ? { ...task, unseen: false } : task))
        : state.tasks,
    })),
  markSeen: (ids) =>
    set((state) => {
      const seen = (task: Task): boolean => task.unseen && (ids === undefined || ids.includes(task.id));
      return state.tasks.some(seen)
        ? { tasks: state.tasks.map((task) => (seen(task) ? { ...task, unseen: false } : task)) }
        : {};
    }),
  dismissTask: (id) =>
    set((state) => {
      const task = state.tasks.find((entry) => entry.id === id);
      if (task === undefined || isActive(task)) {
        return {};
      }
      const dismissed = [...state.dismissed.filter((entry) => entry !== id), id];
      writeDismissed(dismissed);
      cancellers.delete(id);
      return { tasks: state.tasks.filter((entry) => entry.id !== id), dismissed };
    }),
  clearFinished: () =>
    set((state) => {
      const finished = state.tasks.filter((task) => !isActive(task)).map((task) => task.id);
      const dismissed = [...state.dismissed.filter((id) => !finished.includes(id)), ...finished];
      writeDismissed(dismissed);
      for (const id of finished) {
        cancellers.delete(id);
      }
      return { tasks: state.tasks.filter(isActive), dismissed };
    }),
  setConnectionError: (message) =>
    set((state) => (state.connectionError === message ? {} : { connectionError: message })),
}));

/** How each active task is cancelled (an HTTP DELETE, an AbortController). */
const cancellers = new Map<string, () => Promise<void> | void>();

export function registerCanceller(id: string, cancel: () => Promise<void> | void): void {
  cancellers.set(id, cancel);
}

/** Cancel an active task; false when it cannot be cancelled. */
export async function cancelTask(id: string): Promise<boolean> {
  const task = useTaskStore.getState().tasks.find((entry) => entry.id === id);
  const cancel = cancellers.get(id);
  if (task === undefined || !isActive(task) || !task.cancellable || cancel === undefined) {
    return false;
  }
  await cancel();
  return true;
}

/** Tests: an empty registry (the dismissed list in localStorage is kept). */
export function resetTaskStore(): void {
  cancellers.clear();
  useTaskStore.setState({
    tasks: [],
    viewing: null,
    announcement: null,
    connectionError: null,
    dismissed: readDismissed(),
  });
}
