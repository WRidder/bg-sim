/**
 * The subsystem breadcrumb bar (plan 7.2/7.4, W2.2).
 *
 * The root crumb is the model; every further crumb is a subsystem node on the
 * active path. Clicking a crumb opens that diagram, and `Up` (or Esc on the
 * canvas) leaves one level.
 */

import { Fragment } from "react";

import { enclosingInstance, instanceCount, linkedDefinition } from "../library/linkedSubsystems";
import { useDocumentStore } from "../state/documentStore";
import { activeDiagram, subsystemPathCrumbs } from "./subsystemPath";

export function SubsystemBreadcrumbs() {
  const doc = useDocumentStore((state) => state.doc);
  const modelName = useDocumentStore((state) => state.modelName);
  const activePath = useDocumentStore((state) => state.activePath);
  const editNotice = useDocumentStore((state) => state.editNotice);

  if (doc === null) {
    return null;
  }
  const crumbs = subsystemPathCrumbs(doc, activePath);
  // The library subsystem each crumb is an instance of, and the one an edit here changes.
  const definitions = crumbs.map((_, index) => {
    const parent = activeDiagram(doc, activePath.slice(0, index));
    const node = parent?.nodes.find((entry) => entry.id === activePath[index]);
    return node === undefined ? null : linkedDefinition(node);
  });
  const shared = enclosingInstance(doc, activePath);
  const sharedCount = shared === null ? 0 : instanceCount(doc, shared.name);

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
            {definitions[index] !== null && definitions[index] !== undefined ? (
              <span className="subsystem-breadcrumbs__definition"> ({definitions[index]})</span>
            ) : null}
          </button>
        </Fragment>
      ))}
      {shared !== null ? (
        <span
          className="subsystem-breadcrumbs__shared"
          data-testid="breadcrumb-shared"
          data-definition={shared.name}
          title={`This is the library subsystem ${shared.name}. What you change here changes every instance, in this model and in the other models of the project. Only a pinned value stays with ${shared.node.name}.`}
        >
          Library subsystem {shared.name} · {sharedCount}{" "}
          {sharedCount === 1 ? "instance" : "instances"} · changes apply to all
        </span>
      ) : null}
      {editNotice !== null ? (
        <span className="subsystem-breadcrumbs__notice" role="alert" data-testid="edit-notice">
          {editNotice}
          <button
            type="button"
            className="icon-button"
            aria-label="Dismiss"
            onClick={() => useDocumentStore.getState().clearEditNotice()}
          >
            ×
          </button>
        </span>
      ) : null}
      <span className="subsystem-breadcrumbs__spacer" />
      <button
        type="button"
        className="icon-button"
        data-testid="subsystem-back"
        onClick={() => useDocumentStore.getState().leaveSubsystem()}
        disabled={activePath.length === 0}
        aria-label="Up: leave the subsystem"
        title="Leave the subsystem (Esc)"
      >
        ↑ Up
      </button>
    </nav>
  );
}
