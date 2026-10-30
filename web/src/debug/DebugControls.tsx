/**
 * The debug controls of the run bar (plan 7.9): the Debug button next to Run,
 * and while a debug run is active Continue, Pause, Step statement, Step tick,
 * a menu with Step event / Step solver step, and Run to time. Stop is the run
 * bar's own Stop button (Shift+F5 while debugging).
 *
 * Shortcuts: F5 starts a debug run or continues a paused one, F6 pauses, F10
 * and F11 step (on an idle run bar they start the run paused at its entry),
 * Shift+F5 stops. F9 toggles a breakpoint in the Code tab.
 */

import { useEffect, useRef, useState, type KeyboardEvent as ReactKeyboardEvent } from "react";

import type { StepGranularity } from "../contracts/debug";
import { bindBreakpointsToDocument } from "./breakpointStore";
import { isDebugging, subscribePaused, useDebugStore } from "./debugStore";
import { openPauseLocation } from "./pauseNavigation";
import "./debug.css";

export interface DebugControlsProps {
  /** A model is open and no run is active. */
  canStart: boolean;
}

interface StepButton {
  granularity: StepGranularity;
  label: string;
  short: string;
  keys: string | null;
}

const STEP_STATEMENT: StepButton = {
  granularity: "statement",
  label: "Step statement",
  short: "Stmt",
  keys: "F10",
};
const STEP_TICK: StepButton = { granularity: "tick", label: "Step tick", short: "Tick", keys: "F11" };
const MENU_STEPS: readonly StepButton[] = [
  { granularity: "event", label: "Step event", short: "Event", keys: null },
  { granularity: "solverStep", label: "Step solver step", short: "Solver step", keys: null },
];

function withKeys(label: string, keys: string | null, enabled: boolean, reason: string): string {
  if (!enabled) {
    return reason;
  }
  return keys === null ? label : `${label} (${keys})`;
}

export function DebugControls({ canStart }: DebugControlsProps) {
  const status = useDebugStore((state) => state.status);
  const error = useDebugStore((state) => state.error);
  const debugging = isDebugging({ status });
  const paused = status === "paused";
  const running = status === "running";

  const [menuOpen, setMenuOpen] = useState(false);
  const [runToDraft, setRunToDraft] = useState("");
  const [runToInvalid, setRunToInvalid] = useState(false);
  const menu = useRef<HTMLDivElement>(null);

  useEffect(() => {
    bindBreakpointsToDocument();
    return subscribePaused((info) => {
      openPauseLocation(info);
    });
  }, []);

  // Leaving the paused state closes the step menu.
  useEffect(() => {
    if (!paused) {
      setMenuOpen(false);
    }
  }, [paused]);

  useEffect(() => {
    if (!menuOpen) {
      return;
    }
    const onPointerDown = (event: MouseEvent): void => {
      if (menu.current !== null && !menu.current.contains(event.target as Node)) {
        setMenuOpen(false);
      }
    };
    window.addEventListener("mousedown", onPointerDown);
    return () => window.removeEventListener("mousedown", onPointerDown);
  }, [menuOpen]);

  // F5, Shift+F5, F6, F10 and F11 work anywhere in the editor.
  useEffect(() => {
    const onKeyDown = (event: KeyboardEvent): void => {
      if (event.ctrlKey || event.metaKey || event.altKey) {
        return;
      }
      const store = useDebugStore.getState();
      const active = isDebugging(store);
      switch (event.key) {
        case "F5":
          if (event.shiftKey) {
            if (active) {
              event.preventDefault();
              void store.stop();
            }
          } else if (active) {
            event.preventDefault();
            if (store.status === "paused") {
              void store.continueRun();
            }
          } else if (canStart) {
            event.preventDefault();
            void store.startDebug();
          }
          break;
        case "F6":
          if (active) {
            event.preventDefault();
            if (store.status === "running") {
              void store.pause();
            }
          }
          break;
        case "F10":
        case "F11":
          if (event.shiftKey) {
            break;
          }
          if (active) {
            event.preventDefault();
            if (store.status === "paused") {
              void store.step(event.key === "F10" ? "statement" : "tick");
            }
          } else if (canStart) {
            event.preventDefault();
            void store.startDebug({ pauseOnEntry: true });
          }
          break;
        default:
          break;
      }
    };
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [canStart]);

  const store = useDebugStore.getState;
  const notPaused = "Available while the run is paused";

  const submitRunTo = (): void => {
    const value = Number(runToDraft.trim());
    if (runToDraft.trim().length === 0 || !Number.isFinite(value) || value < 0) {
      setRunToInvalid(true);
      return;
    }
    setRunToInvalid(false);
    void store().runTo(value);
  };

  const onRunToKeyDown = (event: ReactKeyboardEvent<HTMLInputElement>): void => {
    if (event.key === "Enter") {
      event.preventDefault();
      submitRunTo();
    }
  };

  const stepButton = (step: StepButton) => (
    <button
      key={step.granularity}
      type="button"
      className="button debug-controls__button"
      disabled={!paused}
      aria-label={step.label}
      data-testid={`debug-step-${step.granularity}`}
      title={withKeys(step.label, step.keys, paused, notPaused)}
      onClick={() => void store().step(step.granularity)}
    >
      <span className="button__glyph" aria-hidden="true">
        ⤓
      </span>
      {step.short}
    </button>
  );

  return (
    <>
      <button
        type="button"
        className="button debug-controls__start"
        onClick={() => void store().startDebug()}
        disabled={!canStart}
        aria-label="Debug the model"
        data-testid="debug-button"
        title={
          canStart
            ? "Run the model in the debugger: pause at breakpoints (F5)"
            : debugging
              ? "A debug run is already active"
              : "Open a model, and wait for the active run to end, to debug it"
        }
      >
        <span className="button__glyph" aria-hidden="true">
          ⏵
        </span>
        Debug
      </button>

      {debugging ? (
        <div
          className="debug-controls"
          role="group"
          aria-label="Debug controls"
          data-testid="debug-controls"
          data-debug-status={status}
        >
          <button
            type="button"
            className="button debug-controls__button"
            disabled={!paused}
            aria-label="Continue"
            data-testid="debug-continue"
            title={withKeys("Continue", "F5", paused, notPaused)}
            onClick={() => void store().continueRun()}
          >
            <span className="button__glyph" aria-hidden="true">
              ⏵⏵
            </span>
            Continue
          </button>
          <button
            type="button"
            className="button debug-controls__button"
            disabled={!running}
            aria-label="Pause"
            data-testid="debug-pause"
            title={withKeys("Pause", "F6", running, "Available while the run is going")}
            onClick={() => void store().pause()}
          >
            <span className="button__glyph" aria-hidden="true">
              ⏸
            </span>
            Pause
          </button>
          {stepButton(STEP_STATEMENT)}
          {stepButton(STEP_TICK)}
          <div className="debug-controls__menu" ref={menu}>
            <button
              type="button"
              className="button debug-controls__button"
              disabled={!paused}
              aria-label="More step commands"
              aria-haspopup="menu"
              aria-expanded={menuOpen}
              data-testid="debug-step-menu"
              title={paused ? "Step event, step solver step" : notPaused}
              onClick={() => setMenuOpen((open) => !open)}
            >
              More ▾
            </button>
            {menuOpen && paused ? (
              <div className="debug-controls__popup" role="menu" aria-label="More step commands">
                {MENU_STEPS.map((step) => (
                  <button
                    key={step.granularity}
                    type="button"
                    role="menuitem"
                    className="debug-controls__item"
                    data-testid={`debug-step-${step.granularity}`}
                    onClick={() => {
                      setMenuOpen(false);
                      void store().step(step.granularity);
                    }}
                  >
                    {step.label}
                  </button>
                ))}
              </div>
            ) : null}
          </div>
          <label className="debug-controls__runto" title={paused ? "Run to this simulation time and pause (s)" : notPaused}>
            <input
              className={`setting__value${runToInvalid ? " is-invalid" : ""}`}
              type="text"
              inputMode="decimal"
              value={runToDraft}
              placeholder="run to t"
              disabled={!paused}
              aria-label="Run to time (s)"
              aria-invalid={runToInvalid}
              data-testid="debug-runto-input"
              onChange={(event) => {
                setRunToDraft(event.target.value);
                setRunToInvalid(false);
              }}
              onKeyDown={onRunToKeyDown}
            />
          </label>
          <button
            type="button"
            className="button debug-controls__button"
            disabled={!paused}
            aria-label="Run to time"
            data-testid="debug-runto"
            title={paused ? "Run to the time and pause" : notPaused}
            onClick={submitRunTo}
          >
            Go
          </button>
        </div>
      ) : null}

      {error !== null ? (
        <span className="debug-controls__error" role="alert" data-testid="debug-error" title={error}>
          {error}
          <button
            type="button"
            className="icon-button"
            aria-label="Dismiss the debug message"
            onClick={() => useDebugStore.getState().clearError()}
          >
            ×
          </button>
        </span>
      ) : null}
    </>
  );
}
