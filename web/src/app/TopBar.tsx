import { lazy, Suspense, useCallback, useEffect, useState } from "react";

import { useAssistantPanelStore } from "../assistant/panelStore";
import { ExportDialog } from "../export/ExportDialog";
import { useExportDialogStore } from "../export/exportStore";
import { useDocumentStore } from "../state/documentStore";
import { TaskIndicator } from "../tasks/TaskIndicator";
import type { Theme } from "../theme/theme";
import { useHelpStore } from "./helpStore";
import { LeaveProjectDialog } from "./LeaveProjectDialog";
import { requestLeaveModel, requestLeaveProject } from "./leaveProject";
import { ModelMenu } from "./ModelMenu";
import { OpenDialog } from "./OpenDialog";
import { projectUrl, readAppRoute, type AppRoute } from "./route";
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

/** A speech bubble, drawn in the text colour. */
function AssistantIcon() {
  return (
    <svg viewBox="0 0 16 16" width="16" height="16" aria-hidden="true" focusable="false">
      <path
        d="M2.5 3.5h11v7.4H7.2L4.4 13.4v-2.5H2.5z"
        fill="none"
        stroke="currentColor"
        strokeWidth="1.4"
        strokeLinejoin="round"
      />
    </svg>
  );
}

export interface TopBarProps {
  theme: Theme;
  onToggleTheme: () => void;
  /** The screen the URL selects; read from the URL when omitted. */
  route?: AppRoute;
}

/**
 * The top bar of plan 7.2 in three columns: the breadcrumb on the left, Run/Stop,
 * t_end/solver/tol and the run activity centred, Export and the status icons on the right. Run and Stop stay disabled until a model is open (M1
 * wires them); the theme toggle is live. The help icon at the far right opens
 * the user manual (also F1 when no block is selected).
 *
 * The breadcrumb depends on the screen. On the start page it opens the Open
 * dialog (Ctrl+O). In a project it reads `BG-Sim ▸ project ▸ model ▾`: the brand
 * goes back to the start page (the only way to another project), the project
 * name to the project's model picker, and the model menu (Ctrl+O) lists the
 * project's models to switch to.
 */
export function TopBar({ theme, onToggleTheme, route: routeProp }: TopBarProps) {
  const nextTheme = theme === "dark" ? "light" : "dark";
  const [urlRoute] = useState(() => readAppRoute());
  const route = routeProp ?? urlRoute;
  const storeProject = useDocumentStore((state) => state.project);
  const storeModel = useDocumentStore((state) => state.modelName);
  const project = storeProject ?? (route.kind === "start" ? null : route.project);
  const modelName = storeModel ?? (route.kind === "editor" ? route.model : null);
  const hasDoc = useDocumentStore((state) => state.doc !== null);
  const openExport = useExportDialogStore((state) => state.openExport);
  const assistantOpen = useAssistantPanelStore((state) => state.open);
  const toggleAssistant = useAssistantPanelStore((state) => state.toggle);
  const [openDialog, setOpenDialog] = useState(false);
  const [modelMenu, setModelMenu] = useState(false);
  const closeOpenDialog = useCallback(() => setOpenDialog(false), []);
  const closeModelMenu = useCallback(() => setModelMenu(false), []);
  const manualOpen = useHelpStore((state) => state.manualOpen);
  const setManualOpen = useHelpStore((state) => state.setManualOpen);
  const kind = route.kind;

  useEffect(() => {
    const onKeyDown = (event: KeyboardEvent): void => {
      if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === "o") {
        event.preventDefault();
        if (kind === "start") {
          setOpenDialog(true);
        } else if (kind === "editor") {
          setModelMenu(true);
        } else {
          document.querySelector<HTMLElement>('[data-testid="model-grid"] .model-card')?.focus();
        }
      }
    };
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [kind]);

  return (
    <header className="top-bar" data-testid="top-bar">
      <div className="top-bar__left">
        {kind === "start" ? (
          <div className="top-bar__brand">BG-Sim</div>
        ) : (
          <button
            type="button"
            className="top-bar__brand top-bar__brand--link"
            data-testid="brand-home"
            title="Back to the start page (all projects and the examples)"
            onClick={requestLeaveProject}
          >
            BG-Sim
          </button>
        )}
        <LeaveProjectDialog />

        {kind === "start" ? (
          <button
            type="button"
            className="top-bar__project"
            data-testid="open-project"
            aria-haspopup="dialog"
            aria-expanded={openDialog}
            title="Open a project (Ctrl+O)"
            onClick={() => setOpenDialog(true)}
          >
            <span className="top-bar__project-name">No project</span>
            <span className="top-bar__hint">open a project</span>
            <span className="top-bar__chevron" aria-hidden="true">
              ▾
            </span>
          </button>
        ) : (
          <nav className="top-bar__crumbs" aria-label="Project and model">
            <span className="top-bar__crumb-sep" aria-hidden="true">
              ▸
            </span>
            {kind === "picker" ? (
              <span className="top-bar__crumb top-bar__crumb--static" data-testid="project-crumb" aria-current="page">
                {project}
              </span>
            ) : (
              <a
                className="top-bar__crumb"
                href={projectUrl(project ?? "")}
                data-testid="project-crumb"
                title="All models of this project"
                onClick={(event) => {
                  if (event.button === 0 && !event.ctrlKey && !event.metaKey && !event.shiftKey) {
                    event.preventDefault();
                    void requestLeaveModel(projectUrl(project ?? ""), "project");
                  }
                }}
              >
                {project}
              </a>
            )}
            <span className="top-bar__crumb-sep" aria-hidden="true">
              ▸
            </span>
            {kind === "picker" ? (
              <span className="top-bar__crumb top-bar__crumb--hint">choose a model</span>
            ) : (
              <button
                type="button"
                className="top-bar__project top-bar__model"
                data-testid="open-project"
                aria-haspopup="dialog"
                aria-expanded={modelMenu}
                title="Switch to another model of this project (Ctrl+O)"
                onClick={() => setModelMenu(true)}
              >
                <span className="top-bar__model-name">{modelName ?? "No model"}</span>
                <span className="top-bar__chevron" aria-hidden="true">
                  ▾
                </span>
              </button>
            )}
          </nav>
        )}
        {kind === "editor" && project !== null ? (
          <ModelMenu open={modelMenu} project={project} current={modelName} onClose={closeModelMenu} />
        ) : null}
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
            data-testid="assistant-toggle"
            aria-label={assistantOpen ? "Close the assistant" : "Open the assistant"}
            aria-pressed={assistantOpen}
            title="Assistant"
            onClick={toggleAssistant}
          >
            <AssistantIcon />
          </button>
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

      {kind === "start" ? <OpenDialog open={openDialog} onClose={closeOpenDialog} /> : null}
      <ExportDialog />
      {manualOpen ? (
        <Suspense fallback={null}>
          <UserManualDialog />
        </Suspense>
      ) : null}
    </header>
  );
}
