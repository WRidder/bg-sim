import { useEffect, useState } from "react";

import { useDocumentStore } from "../state/documentStore";
import type { Theme } from "../theme/theme";
import { OpenDialog } from "./OpenDialog";
import { RunBar } from "./RunBar";
import { WorkerStatus } from "./WorkerStatus";

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
  const project = useDocumentStore((state) => state.project);
  const modelName = useDocumentStore((state) => state.modelName);
  const [openDialog, setOpenDialog] = useState(false);

  useEffect(() => {
    const onKeyDown = (event: KeyboardEvent): void => {
      if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === "o") {
        event.preventDefault();
        setOpenDialog(true);
      }
    };
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, []);

  return (
    <header className="top-bar" data-testid="top-bar">
      <div className="top-bar__brand">bg-sim</div>

      <button
        type="button"
        className="top-bar__project"
        data-testid="open-project"
        aria-haspopup="dialog"
        aria-expanded={openDialog}
        title="Open a project or model (Ctrl+O)"
        onClick={() => setOpenDialog(true)}
      >
        <span className="top-bar__project-name">{project ?? "No project"}</span>
        <span className="top-bar__hint">
          {project === null ? "open a project" : (modelName ?? "No model")}
        </span>
        <span className="top-bar__chevron" aria-hidden="true">
          ▾
        </span>
      </button>

      <RunBar />

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

      <OpenDialog open={openDialog} onClose={() => setOpenDialog(false)} />
    </header>
  );
}
