/**
 * The background tasks indicator of the top bar (Eclipse's "Progress view"): a compact icon
 * button that spins with a count while tasks run, shows a dot for a task that ended while
 * nobody looked (green done, red failed), and is a muted icon when idle. It opens a popover
 * listing the tasks (active first, then the recent finished ones) with their phase, progress
 * and elapsed time, Cancel, "Show details" (the Export dialog attached to that job) and the
 * finished export's download; "Clear finished" empties the list.
 *
 * It also keeps the sources running: it lists the project's export jobs on load, on a
 * project change and when the window regains focus, so a running export comes back after a
 * reload. A task that ends is announced in a polite live region, and a toast offers "Show"
 * while its dialog is closed.
 */

import { useCallback, useEffect, useId, useRef, useState } from "react";

import { useDialogFocus } from "../app/useDialogFocus";
import { useExportDialogStore } from "../export/exportStore";
import { useDocumentStore } from "../state/documentStore";
import { exportJobIdOf, refreshExports } from "./exportTasks";
import {
  cancelTask,
  isActive,
  useTaskStore,
  type Task,
  type TaskAnnouncement,
  type TaskStatus,
} from "./taskStore";
import "./tasks.css";

/** The toast stays this long unless the user acts on it. */
export const TOAST_MS = 8000;

const STATUS_TEXT: Record<TaskStatus, string> = {
  queued: "Queued",
  running: "Running",
  done: "Done",
  failed: "Failed",
  cancelled: "Cancelled",
  refused: "Refused",
};

/** `8 s`, `3 min 04 s`, `1 h 02 min`. */
export function formatElapsed(ms: number): string {
  const seconds = Math.max(0, Math.round(ms / 1000));
  if (seconds < 60) {
    return `${seconds} s`;
  }
  const minutes = Math.floor(seconds / 60);
  if (minutes < 60) {
    return `${minutes} min ${String(seconds % 60).padStart(2, "0")} s`;
  }
  return `${Math.floor(minutes / 60)} h ${String(minutes % 60).padStart(2, "0")} min`;
}

function clockTime(epochMs: number): string {
  const date = new Date(epochMs);
  return `${String(date.getHours()).padStart(2, "0")}:${String(date.getMinutes()).padStart(2, "0")}`;
}

function isFailure(task: Pick<Task, "status">): boolean {
  return task.status === "failed" || task.status === "refused";
}

/** Whether "Show details" applies: an export job re-opens its dialog. */
export function hasDetails(task: Task): boolean {
  return task.kind === "fmu-export" && exportJobIdOf(task.id) !== null;
}

/** Open the details of a task (the Export dialog attached to the job). */
export function showTaskDetails(task: Task): void {
  const jobId = exportJobIdOf(task.id);
  if (task.kind === "fmu-export" && jobId !== null) {
    useTaskStore.getState().markSeen([task.id]);
    useExportDialogStore.getState().showExport(jobId);
  }
}

/** A clock that ticks every second while `running`. */
function useNow(running: boolean): number {
  const [now, setNow] = useState(() => Date.now());
  useEffect(() => {
    if (!running) {
      return;
    }
    setNow(Date.now());
    const timer = window.setInterval(() => setNow(Date.now()), 1000);
    return () => window.clearInterval(timer);
  }, [running]);
  return now;
}

function IndicatorIcon({ state, progress }: { state: string; progress: number | null }) {
  if (state === "running") {
    const circumference = 2 * Math.PI * 7;
    const shown = progress === null ? 0.28 : Math.max(0.04, progress);
    return (
      <svg
        className={`tasks-indicator__ring${progress === null ? " is-spinning" : ""}`}
        width="18"
        height="18"
        viewBox="0 0 18 18"
        aria-hidden="true"
      >
        <circle className="tasks-indicator__track" cx="9" cy="9" r="7" />
        <circle
          className="tasks-indicator__arc"
          cx="9"
          cy="9"
          r="7"
          strokeDasharray={`${shown * circumference} ${circumference}`}
          transform="rotate(-90 9 9)"
        />
      </svg>
    );
  }
  // Idle and finished: three bars of decreasing length, a list of progress bars.
  return (
    <svg className="tasks-indicator__bars" width="18" height="18" viewBox="0 0 18 18" aria-hidden="true">
      <rect x="2" y="3.5" width="14" height="2" rx="1" />
      <rect x="2" y="8" width="10" height="2" rx="1" />
      <rect x="2" y="12.5" width="6" height="2" rx="1" />
    </svg>
  );
}

function TaskItem({
  task,
  now,
  project,
  onDetails,
}: {
  task: Task;
  now: number;
  project: string | null;
  onDetails: (task: Task) => void;
}) {
  const active = isActive(task);
  const titleId = useId();
  const [cancelling, setCancelling] = useState(false);
  const time = active
    ? formatElapsed(now - task.started)
    : `${clockTime(task.finished ?? task.started)} · took ${formatElapsed(
        (task.finished ?? task.started) - task.started,
      )}`;
  return (
    <li
      className={`tasks__item${task.unseen ? " is-unseen" : ""}`}
      data-testid="task-item"
      data-task-id={task.id}
      data-status={task.status}
      aria-labelledby={titleId}
    >
      <div className="tasks__row">
        <span className="tasks__title" id={titleId}>
          {task.title}
        </span>
        <span className={`tasks__status is-${task.status}`} data-testid="task-status">
          {STATUS_TEXT[task.status]}
        </span>
      </div>
      {task.phase !== null ? (
        <div className={`tasks__phase${isFailure(task) ? " is-error" : ""}`} data-testid="task-phase">
          {task.phase}
        </div>
      ) : null}
      {active ? (
        task.progress === null ? (
          <div
            className="tasks__bar is-indeterminate"
            role="progressbar"
            aria-labelledby={titleId}
            aria-valuetext={task.phase ?? STATUS_TEXT[task.status]}
          >
            <span />
          </div>
        ) : (
          <div
            className="tasks__bar"
            role="progressbar"
            aria-labelledby={titleId}
            aria-valuemin={0}
            aria-valuemax={100}
            aria-valuenow={Math.round(task.progress * 100)}
          >
            <span style={{ width: `${Math.round(task.progress * 100)}%` }} />
          </div>
        )
      ) : null}
      <div className="tasks__meta">
        <span data-testid="task-time">{time}</span>
        {task.project !== null && task.project !== project ? <span>project {task.project}</span> : null}
      </div>
      <div className="tasks__actions">
        {hasDetails(task) ? (
          <button
            type="button"
            className="button"
            data-testid="task-details"
            aria-describedby={titleId}
            onClick={() => onDetails(task)}
          >
            Show details
          </button>
        ) : null}
        {task.result !== null ? (
          <a
            className="button"
            href={task.result.href}
            download={task.result.fileName}
            data-testid="task-download"
            aria-label={task.result.label}
            title={task.result.label}
          >
            Download
          </a>
        ) : null}
        {active && task.cancellable ? (
          <button
            type="button"
            className="button"
            data-testid="task-cancel"
            aria-describedby={titleId}
            disabled={cancelling}
            onClick={() => {
              setCancelling(true);
              void cancelTask(task.id).finally(() => setCancelling(false));
            }}
          >
            {cancelling ? "Cancelling…" : "Cancel"}
          </button>
        ) : null}
        {!active ? (
          <button
            type="button"
            className="icon-button tasks__dismiss"
            data-testid="task-dismiss"
            aria-label={`Remove ${task.title} from the list`}
            title="Remove from the list"
            onClick={() => useTaskStore.getState().dismissTask(task.id)}
          >
            ✕
          </button>
        ) : null}
      </div>
    </li>
  );
}

function TaskToast({
  toast,
  task,
  onShow,
  onClose,
}: {
  toast: TaskAnnouncement;
  task: Task | undefined;
  onShow: () => void;
  onClose: () => void;
}) {
  return (
    <div
      className={`tasks-toast${task !== undefined && isFailure(task) ? " is-error" : ""}`}
      data-testid="task-toast"
    >
      <span className="tasks-toast__text">{toast.text}</span>
      <button type="button" className="button" data-testid="task-toast-show" onClick={onShow}>
        Show
      </button>
      <button
        type="button"
        className="icon-button"
        aria-label="Dismiss the notification"
        title="Dismiss"
        onClick={onClose}
      >
        ✕
      </button>
    </div>
  );
}

export function TaskIndicator() {
  const tasks = useTaskStore((state) => state.tasks);
  const announcement = useTaskStore((state) => state.announcement);
  const connectionError = useTaskStore((state) => state.connectionError);
  const project = useDocumentStore((state) => state.project);
  const [open, setOpen] = useState(false);
  const [toast, setToast] = useState<TaskAnnouncement | null>(null);
  const root = useRef<HTMLDivElement>(null);
  const panel = useRef<HTMLDivElement>(null);
  const panelId = useId();

  const active = tasks.filter(isActive);
  const unseen = tasks.filter((task) => task.unseen);
  const finishedCount = tasks.length - active.length;
  const state = active.length > 0 ? "running" : unseen.length > 0 ? "attention" : "idle";
  const attention = unseen.some(isFailure) ? "error" : "ok";
  const progress = active.length === 1 ? (active[0]?.progress ?? null) : null;
  const now = useNow(open && active.length > 0);

  // The export jobs of the project: on load, on a project change, on focus.
  useEffect(() => {
    if (project !== null) {
      void refreshExports(project);
    }
  }, [project]);
  useEffect(() => {
    const onFocus = (): void => {
      const current = useDocumentStore.getState().project;
      if (current !== null) {
        void refreshExports(current);
      }
    };
    window.addEventListener("focus", onFocus);
    return () => window.removeEventListener("focus", onFocus);
  }, []);

  const close = useCallback(() => setOpen(false), []);
  useDialogFocus(open, panel, close);

  // Looking at the list is seeing its finished tasks.
  useEffect(() => {
    if (open) {
      useTaskStore.getState().markSeen();
    }
  }, [open, tasks]);

  // A click outside the indicator closes the popover.
  useEffect(() => {
    if (!open) {
      return;
    }
    const onPointerDown = (event: MouseEvent): void => {
      if (root.current !== null && !root.current.contains(event.target as Node)) {
        setOpen(false);
      }
    };
    window.addEventListener("mousedown", onPointerDown);
    return () => window.removeEventListener("mousedown", onPointerDown);
  }, [open]);

  // A task that ended while unwatched: a toast, unless the list is open anyway.
  const toasted = useRef(0);
  useEffect(() => {
    if (announcement === null || announcement.seq === toasted.current) {
      return;
    }
    toasted.current = announcement.seq;
    if (!open) {
      setToast(announcement);
    }
  }, [announcement, open]);
  useEffect(() => {
    if (toast === null) {
      return;
    }
    const timer = window.setTimeout(() => setToast(null), TOAST_MS);
    return () => window.clearTimeout(timer);
  }, [toast]);

  const onDetails = useCallback((task: Task) => {
    setOpen(false);
    showTaskDetails(task);
  }, []);

  const toastTask = toast === null ? undefined : tasks.find((task) => task.id === toast.taskId);
  const label =
    active.length > 0
      ? `Background tasks: ${active.length} running`
      : unseen.length > 0
        ? `Background tasks: ${unseen.length} finished${attention === "error" ? ", with errors" : ""}`
        : "Background tasks: none running";

  return (
    <div className="tasks" ref={root} data-testid="tasks">
      <button
        type="button"
        className={`icon-button tasks-indicator is-${state}${open ? " is-active" : ""}`}
        data-testid="tasks-indicator"
        data-state={state}
        data-count={active.length}
        aria-haspopup="dialog"
        aria-expanded={open}
        aria-controls={open ? panelId : undefined}
        aria-label={label}
        title={label}
        onClick={() => setOpen((value) => !value)}
      >
        <IndicatorIcon state={state} progress={progress} />
        {active.length > 0 ? (
          <span className="tasks-indicator__count" data-testid="tasks-count" aria-hidden="true">
            {active.length}
          </span>
        ) : null}
        {state === "attention" ? (
          <span className={`tasks-indicator__dot is-${attention}`} data-testid="tasks-dot" aria-hidden="true" />
        ) : null}
      </button>

      {open ? (
        <div
          className="tasks__panel"
          id={panelId}
          role="dialog"
          aria-labelledby={`${panelId}-title`}
          data-testid="tasks-panel"
          ref={panel}
          tabIndex={-1}
        >
          <header className="tasks__header">
            <h2 className="tasks__heading" id={`${panelId}-title`}>
              Background tasks
            </h2>
            <span className="tasks__summary">
              {active.length > 0 ? `${active.length} running` : "none running"}
            </span>
          </header>
          {connectionError !== null && active.length > 0 ? (
            <p className="tasks__warning" role="alert">
              {connectionError} Retrying…
            </p>
          ) : null}
          {tasks.length === 0 ? (
            <p className="tasks__empty" data-testid="tasks-empty">
              No background tasks. FMU and CSV exports show up here, so you can close their
              dialog and keep working.
            </p>
          ) : (
            <ul className="tasks__list" data-testid="tasks-list">
              {tasks.map((task) => (
                <TaskItem key={task.id} task={task} now={now} project={project} onDetails={onDetails} />
              ))}
            </ul>
          )}
          <footer className="tasks__footer">
            <button
              type="button"
              className="button"
              data-testid="tasks-clear"
              disabled={finishedCount === 0}
              onClick={() => useTaskStore.getState().clearFinished()}
            >
              Clear finished
            </button>
          </footer>
        </div>
      ) : null}

      <div className="visually-hidden" role="status" aria-live="polite" data-testid="tasks-live">
        {announcement === null ? "" : <span key={announcement.seq}>{announcement.text}</span>}
      </div>

      {toast !== null && !open ? (
        <TaskToast
          toast={toast}
          task={toastTask}
          onClose={() => setToast(null)}
          onShow={() => {
            setToast(null);
            if (toastTask !== undefined && hasDetails(toastTask)) {
              showTaskDetails(toastTask);
            } else {
              setOpen(true);
            }
          }}
        />
      ) : null}
    </div>
  );
}
