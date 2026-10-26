/**
 * The subsystem breadcrumb bar (plan 7.2/7.4, W2.2).
 *
 * The root crumb is the model; every further crumb is a subsystem node on the
 * active path. Clicking a crumb opens that diagram, and `Up` (or Esc on the
 * canvas) leaves one level.
 */

import { Fragment } from "react";

import { useDocumentStore } from "../state/documentStore";
import { subsystemPathCrumbs } from "./subsystemPath";

export function SubsystemBreadcrumbs() {
  const doc = useDocumentStore((state) => state.doc);
  const modelName = useDocumentStore((state) => state.modelName);
  const activePath = useDocumentStore((state) => state.activePath);

  if (doc === null) {
    return null;
  }
  const crumbs = subsystemPathCrumbs(doc, activePath);

  return (
    <nav
      className="subsystem-breadcrumbs"
      data-testid="subsystem-breadcrumbs"
      aria-label="Diagram path"
    >
      <button
        type="button"
        className="subsystem-breadcrumbs__crumb"
        data-testid="breadcrumb-0"
        data-breadcrumb-name={modelName ?? doc.name}
        aria-current={activePath.length === 0 ? "page" : undefined}
        onClick={() => useDocumentStore.getState().navigateToPath([])}
        title="The model's root diagram"
      >
        {modelName ?? doc.name}
      </button>
      {crumbs.map((crumb, index) => (
        <Fragment key={crumb.id}>
          <span className="subsystem-breadcrumbs__separator" aria-hidden="true">
            ▸
          </span>
          <button
            type="button"
            className="subsystem-breadcrumbs__crumb"
            data-testid={`breadcrumb-${index + 1}`}
            data-breadcrumb-name={crumb.name}
            aria-current={index === crumbs.length - 1 ? "page" : undefined}
            onClick={() =>
              useDocumentStore.getState().navigateToPath(activePath.slice(0, index + 1))
            }
            title={`Open ${crumb.name}`}
          >
            {crumb.name}
          </button>
        </Fragment>
      ))}
      <span className="subsystem-breadcrumbs__spacer" />
      <button
        type="button"
        className="icon-button"
        data-testid="subsystem-back"
        onClick={() => useDocumentStore.getState().leaveSubsystem()}
        disabled={activePath.length === 0}
        aria-label="Leave the subsystem"
        title="Leave the subsystem (Esc)"
      >
        ↑ Up
      </button>
    </nav>
  );
}
