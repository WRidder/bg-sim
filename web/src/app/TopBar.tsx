import type { Theme } from "../theme/theme";
import { WorkerStatus } from "./WorkerStatus";

/** Simulation settings shown as read-only placeholders until a model is open. */
const SIMULATION_SETTINGS = [
  { id: "t-end", label: "t_end", value: "1 s" },
  { id: "solver", label: "solver", value: "auto" },
  { id: "tol", label: "tol", value: "1e-6" },
] as const;

export interface TopBarProps {
  theme: Theme;
  onToggleTheme: () => void;
}

/**
 * The top bar of plan 7.2: project ▸ model tabs, Run/Stop, t_end/solver/tol and
 * the worker status. Run and Stop stay disabled until a model is open (M1
 * wires them); the theme toggle is live.
 */
export function TopBar({ theme, onToggleTheme }: TopBarProps) {
  const nextTheme = theme === "dark" ? "light" : "dark";

  return (
    <header className="top-bar" data-testid="top-bar">
      <div className="top-bar__brand">bg-sim</div>

      <div className="top-bar__project" data-testid="project-tabs">
        <span className="top-bar__project-name">No project</span>
        <span className="top-bar__hint">model tabs appear here once a project is open</span>
      </div>

      <div className="top-bar__run" role="group" aria-label="Simulation controls">
        <button
          type="button"
          className="button button--primary"
          disabled
          aria-label="Run simulation"
          title="Run (Ctrl+Enter) becomes available when a model is open"
        >
          <span className="button__glyph" aria-hidden="true">
            ▶
          </span>
          Run
        </button>
        <button
          type="button"
          className="button"
          disabled
          aria-label="Stop simulation"
          title="Stop becomes available while a simulation runs"
        >
          <span className="button__glyph" aria-hidden="true">
            ■
          </span>
          Stop
        </button>
      </div>

      <div className="top-bar__settings">
        {SIMULATION_SETTINGS.map((setting) => (
          <label className="setting" key={setting.id}>
            <span className="setting__label">{setting.label}</span>
            <input
              className="setting__value"
              type="text"
              value={setting.value}
              readOnly
              disabled
              aria-label={setting.label}
              title="Simulation settings become editable when a model is open"
            />
          </label>
        ))}
      </div>

      <div className="top-bar__status">
        <WorkerStatus />
        <button
          type="button"
          className="icon-button"
          data-testid="theme-toggle"
          onClick={onToggleTheme}
          aria-label={`Switch to ${nextTheme} theme`}
          title={`Switch to the ${nextTheme} theme`}
        >
          <span aria-hidden="true">{theme === "dark" ? "☾" : "☀"}</span>
        </button>
      </div>
    </header>
  );
}
