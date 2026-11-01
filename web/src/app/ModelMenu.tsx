import { useCallback, useEffect, useRef, useState, type KeyboardEvent } from "react";

import { listModelCards, type ModelCardInfo } from "../state/modelApi";
import { requestLeaveModel, requestLeaveProject } from "./leaveProject";
import { ModelCardGrid } from "./ModelCardGrid";
import { errorMessage } from "./openSession";
import { modelUrl, projectUrl } from "./route";
import { useDialogFocus } from "./useDialogFocus";

export interface ModelMenuProps {
  open: boolean;
  project: string;
  /** The model open in the editor; its card is marked. */
  current: string | null;
  onClose: () => void;
}

const ARROWS: Record<string, number> = { ArrowRight: 1, ArrowDown: 1, ArrowLeft: -1, ArrowUp: -1 };

/**
 * The model menu under `project ▸ model ▾` in the top bar: the models of the
 * open project as compact cards (the same cards as the project's model picker),
 * the open one marked. Another project is not offered here: the menu links to
 * the start page instead. Escape or a click outside closes it; arrow keys move
 * between the cards and Enter opens one.
 */
export function ModelMenu({ open, project, current, onClose }: ModelMenuProps) {
  const [cards, setCards] = useState<ModelCardInfo[]>([]);
  const [status, setStatus] = useState<"loading" | "ready" | "error">("loading");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState<string | null>(null);
  const panel = useRef<HTMLDivElement>(null);

  useDialogFocus(open, panel, onClose);

  useEffect(() => {
    if (!open) {
      return;
    }
    const controller = new AbortController();
    setStatus("loading");
    setError(null);
    setBusy(null);
    listModelCards(project, controller.signal)
      .then((list) => {
        setCards(list);
        setStatus("ready");
      })
      .catch((cause: unknown) => {
        if (!controller.signal.aborted) {
          setStatus("error");
          setError(errorMessage(cause));
        }
      });
    return () => controller.abort();
  }, [open, project]);

  // Once the cards are in, focus the open model's card (else the first).
  useEffect(() => {
    if (!open || status !== "ready") {
      return;
    }
    const root = panel.current;
    const target =
      root?.querySelector<HTMLElement>('.model-card[aria-current="page"]') ??
      root?.querySelector<HTMLElement>(".model-card");
    target?.focus();
  }, [open, status]);

  const choose = useCallback(
    async (model: string) => {
      if (model === current) {
        onClose();
        return;
      }
      setBusy(model);
      await requestLeaveModel(modelUrl(project, model), "model");
      // Still here: the leave prompt asks about unsaved work; it takes over from the menu.
      setBusy(null);
      onClose();
    },
    [current, onClose, project],
  );

  const onKeyDown = (event: KeyboardEvent<HTMLDivElement>): void => {
    const step = ARROWS[event.key];
    if (step === undefined || panel.current === null) {
      return;
    }
    const items = [...panel.current.querySelectorAll<HTMLElement>(".model-card")];
    const index = items.indexOf(document.activeElement as HTMLElement);
    if (index < 0) {
      return;
    }
    event.preventDefault();
    items[(index + step + items.length) % items.length]?.focus();
  };

  if (!open) {
    return null;
  }

  return (
    <>
      <div className="model-menu__backdrop" data-testid="model-menu-backdrop" onMouseDown={onClose} />
      <div
        className="model-menu"
        role="dialog"
        aria-modal="true"
        aria-labelledby="model-menu-title"
        data-testid="model-menu"
        data-state={status}
        ref={panel}
        tabIndex={-1}
        onKeyDown={onKeyDown}
      >
        <header className="model-menu__header">
          <h2 className="model-menu__title" id="model-menu-title">
            Models in {project}
          </h2>
          <a
            className="model-menu__link"
            href={projectUrl(project)}
            data-testid="model-menu-all"
            onClick={(event) => {
              if (event.button === 0 && !event.ctrlKey && !event.metaKey && !event.shiftKey) {
                event.preventDefault();
                onClose();
                void requestLeaveModel(projectUrl(project), "project");
              }
            }}
          >
            Project overview
          </a>
        </header>

        {status === "loading" ? <p className="model-menu__note">Loading the models…</p> : null}
        {status === "error" ? (
          <p className="model-menu__note model-menu__note--error" role="alert">
            {error}
          </p>
        ) : null}
        {status === "ready" && cards.length === 0 ? (
          <p className="model-menu__note">This project has no saved models yet.</p>
        ) : null}
        {status === "ready" && cards.length > 0 ? (
          <ModelCardGrid
            project={project}
            cards={cards}
            current={current}
            compact
            testIdPrefix="model-option"
            busy={busy}
            onOpen={(model) => void choose(model)}
          />
        ) : null}

        <footer className="model-menu__footer">
          <span>Another project?</span>
          <button
            type="button"
            className="button"
            data-testid="model-menu-home"
            onClick={() => {
              onClose();
              requestLeaveProject();
            }}
          >
            Back to all projects
          </button>
        </footer>
      </div>
    </>
  );
}
