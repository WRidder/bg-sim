import { lazy, Suspense, useEffect, useState } from "react";

import { ExportDialog } from "../export/ExportDialog";
import { useExportDialogStore } from "../export/exportStore";
import { useDocumentStore } from "../state/documentStore";
import { TaskIndicator } from "../tasks/TaskIndicator";
import type { Theme } from "../theme/theme";
import { useHelpStore } from "./helpStore";
import { LeaveProjectDialog } from "./LeaveProjectDialog";
import { requestLeaveProject } from "./leaveProject";
import { OpenDialog } from "./OpenDialog";
import { RunBar } from "./RunBar";
import { WorkerStatus } from "./WorkerStatus";

// The manual pulls in the Markdown stack (react-markdown, KaTeX); it loads on first open.
const UserManualDialog = lazy(() => import("../manual/UserManualDialog"));

/** A question mark in a circle, drawn in the text colour. */
function HelpIcon() {
  return (
    <svg
      viewBox="0 0 16 16"
      width="16"
      height="16"
      aria-hidden="true"
      focusable="false"
    >
      <circle
        cx="8"
        cy="8"
        r="6.6"
        fill="none"
        stroke="currentColor"
        strokeWidth="1.4"
      />
      <path
        d="M6.1 6.3a1.95 1.95 0 1 1 2.7 1.8c-.52.24-.8.62-.8 1.18v.35"
        fill="none"
        stroke="currentColor"
        strokeWidth="1.4"
        strokeLinecap="round"
      />
      <circle cx="8" cy="11.45" r="0.85" fill="currentColor" />
    </svg>
  );
}

export interface TopBarProps {
  theme: Theme;
  onToggleTheme: () => void;
}

/**
 * The top bar of plan 7.2 in three columns: the project ▸ model picker on the left, Run/Stop,
 * t_end/solver/tol and the run activity centred, Export and the status icons on the right. Run and Stop stay disabled until a model is open (M1
 * wires them); the theme toggle is live. The help icon at the far right opens
 * the user manual (also F1 when no block is selected).
 */
export function TopBar({ theme, onToggleTheme }: TopBarProps) {
  const nextTheme = theme === "dark" ? "light" : "dark";
  const project = useDocumentStore((state) => state.project);
  const modelName = useDocumentStore((state) => state.modelName);
  const hasDoc = useDocumentStore((state) => state.doc !== null);
  const openExport = useExportDialogStore((state) => state.openExport);
  const [openDialog, setOpenDialog] = useState(false);
  const manualOpen = useHelpStore((state) => state.manualOpen);
  const setManualOpen = useHelpStore((state) => state.setManualOpen);

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
      <div className="top-bar__left">
        {project === null ? (
          <div className="top-bar__brand">BG-Sim</div>
        ) : (
          <button
            type="button"
            className="top-bar__brand top-bar__brand--link"
            data-testid="brand-home"
            title="Back to the library (examples and projects)"
            onClick={requestLeaveProject}
          >
            BG-Sim
          </button>
        )}
        <LeaveProjectDialog />

        <button
          type="button"
          className="top-bar__project"
          data-testid="open-project"
          aria-haspopup="dialog"
          aria-expanded={openDialog}
          title="Open a project or model (Ctrl+O)"
          onClick={() => setOpenDialog(true)}
        >
          <span className="top-bar__project-name">
            {project ?? "No project"}
          </span>
          <span className="top-bar__hint">
            {project === null ? "open a project" : (modelName ?? "No model")}
          </span>
          <span className="top-bar__chevron" aria-hidden="true">
            ▾
          </span>
        </button>
      </div>

      <div className="top-bar__center">
        <RunBar />
      </div>

      <div className="top-bar__right">
        <button
          type="button"
          className="button"
          data-testid="open-export"
          aria-haspopup="dialog"
          disabled={!hasDoc || project === null}
          title="Export the model as a C/FMU (right-click a subsystem to export only that subsystem)"
          onClick={() => openExport(null)}
        >
          Export FMU…
        </button>

        <div className="top-bar__status">
          <TaskIndicator />
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
          <button
            type="button"
            className="icon-button"
            data-testid="open-manual"
            aria-label="User manual"
            aria-haspopup="dialog"
            aria-expanded={manualOpen}
            title="User manual (F1)"
            onClick={() => setManualOpen(true)}
          >
            <HelpIcon />
          </button>
        </div>
      </div>

      <OpenDialog open={openDialog} onClose={() => setOpenDialog(false)} />
      <ExportDialog />
      {manualOpen ? (
        <Suspense fallback={null}>
          <UserManualDialog />
        </Suspense>
      ) : null}
    </header>
  );
}
