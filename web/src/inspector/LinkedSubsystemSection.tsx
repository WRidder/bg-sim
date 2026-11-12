/**
 * The inspector's side of library subsystems (library/linkedSubsystems.ts):
 *
 * - on an instance: which library subsystem it is, the pinned values with the
 *   ones this instance sets itself marked, reset to the library's value, and
 *   Detach;
 * - on an ordinary subsystem: Make reusable;
 * - on a parameter or start value of a block inside a library subsystem: the
 *   pin that makes it a value of each instance.
 */

import { useState } from "react";

import type { ModelNode } from "../contracts/model";
import {
  enclosingInstance,
  instanceCount,
  instancesWithOwnValue,
  instanceValues,
  linkedDefinition,
  pinsOf,
  suggestedDefinitionName,
  definitionNameProblem,
  type PinKind,
} from "../library/linkedSubsystems";
import { useCatalogStore } from "../library/catalogStore";
import { useDocumentStore } from "../state/documentStore";
import { stripEquationPrefix } from "./expression";
import { TextField } from "./fields";

function projectBlockNames(): string[] {
  return (useCatalogStore.getState().index?.blocks ?? []).map((block) => block.name);
}

/** The section of an instance: its library subsystem and its own values. */
export function LinkedInstanceSection({ node }: { node: ModelNode }) {
  const doc = useDocumentStore((state) => state.doc);
  const [detaching, setDetaching] = useState(false);
  const name = linkedDefinition(node);
  const definition = name === null ? undefined : doc?.definitions?.[name];
  if (doc === null || name === null || definition === undefined || !("subsystem" in node.block)) {
    return null;
  }
  const values = instanceValues(node.block.subsystem, definition);
  const changed = values.filter((entry) => entry.changed);
  const count = instanceCount(doc, name);
  const store = useDocumentStore.getState();
  return (
    <section
      className="inspector-section"
      aria-labelledby="inspector-linked-title"
      data-testid="inspector-linked"
      data-definition={name}
    >
      <h4 className="inspector-section__title" id="inspector-linked-title">
        Library subsystem
        <span className="inspector-section__count">{values.length}</span>
      </h4>
      <p className="inspector-note" data-testid="inspector-linked-summary">
        <strong>{node.name}</strong> is an instance of <strong>{name}</strong> ({count}{" "}
        {count === 1 ? "instance" : "instances"} in this model). Open it to edit {name}: what
        you change inside changes every instance. The pinned values below belong to this
        instance.
      </p>
      {values.length === 0 ? (
        <p className="inspector-none" data-testid="inspector-linked-none">
          {name} has no pinned values. Open it, select a block and pin a parameter to give each
          instance its own value.
        </p>
      ) : (
        <>
          <p
            className={`inspector-linked__state${changed.length > 0 ? " is-changed" : ""}`}
            data-testid="inspector-linked-changed"
            data-changed={changed.length}
          >
            {changed.length === 0
              ? `All ${values.length} pinned values are as in the library.`
              : `${changed.length} of ${values.length} pinned values set on this instance.`}
            {changed.length > 0 ? (
              <button
                type="button"
                className="inspector-linked__reset-all"
                data-testid="inspector-linked-reset-all"
                onClick={() => store.resetInstanceValues(node.id)}
              >
                Reset all
              </button>
            ) : null}
          </p>
          {values.map((entry) => {
            const testId = `inspector-linked-${entry.kind}-${entry.path.replace(/\//g, "-")}`;
            const base = entry.default ?? "";
            return (
              <TextField
                key={`${entry.kind}:${entry.path}`}
                id={testId}
                testId={testId}
                label={entry.kind === "starts" ? `${entry.path} (start)` : entry.path}
                value={entry.value ?? ""}
                placeholder={entry.default === undefined ? "block default" : undefined}
                issue={(text) =>
                  text.trim().length === 0 ? "Enter a value, or reset it to the library's." : null
                }
                onCommit={(text) => {
                  const result = store.setInstanceValue(
                    node.id,
                    entry.kind,
                    entry.path,
                    stripEquationPrefix(text).trim(),
                  );
                  return result.ok ? null : (result.error ?? "The value was refused.");
                }}
                onReset={
                  entry.changed && entry.resolves
                    ? () => store.resetInstanceValues(node.id, { kind: entry.kind, path: entry.path })
                    : undefined
                }
                resetLabel={`Reset ${entry.path} to the value of ${name} (${base.length > 0 ? base : "block default"})`}
                meta={
                  <span>
                    {name} <code>{base.length > 0 ? base : "block default"}</code>
                    {entry.resolves ? "" : " · no longer in the subsystem"}
                  </span>
                }
                badges={
                  entry.changed ? (
                    <span
                      className="inspector-tag inspector-tag--structural"
                      data-testid={`${testId}-changed`}
                    >
                      this instance
                    </span>
                  ) : null
                }
              />
            );
          })}
        </>
      )}
      <div className="inspector-actions">
        {detaching ? (
          <>
            <button
              type="button"
              className="button inspector-button"
              data-testid="inspector-detach-confirm"
              title={`${node.name} keeps its diagram and values, and no longer follows ${name}`}
              onClick={() => {
                setDetaching(false);
                store.detachInstance(node.id);
              }}
            >
              Detach {node.name} from {name}
            </button>
            <button
              type="button"
              className="button inspector-button"
              data-testid="inspector-detach-cancel"
              onClick={() => setDetaching(false)}
            >
              Cancel
            </button>
          </>
        ) : (
          <button
            type="button"
            className="button inspector-button"
            data-testid="inspector-detach"
            title={`Make ${node.name} an ordinary subsystem that no longer follows ${name}`}
            onClick={() => setDetaching(true)}
          >
            Detach…
          </button>
        )}
      </div>
    </section>
  );
}

/** On an ordinary subsystem: make it a library subsystem that can be instanced. */
export function MakeReusable({ node }: { node: ModelNode }) {
  const definitions = useDocumentStore((state) => state.doc?.definitions);
  const [name, setName] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  if (!("subsystem" in node.block) || linkedDefinition(node) !== null) {
    return null;
  }
  if (name === null) {
    return (
      <button
        type="button"
        className="button inspector-button"
        data-testid="inspector-make-reusable"
        title="Add this subsystem to the project library. This node becomes its first instance; more instances come from the Project category, and an edit inside any instance changes them all."
        onClick={() => {
          setError(null);
          setName(suggestedDefinitionName(node.name, definitions, projectBlockNames()));
        }}
      >
        Make reusable…
      </button>
    );
  }
  const problem = definitionNameProblem(name.trim(), definitions, projectBlockNames());
  const create = (): void => {
    const result = useDocumentStore
      .getState()
      .makeSubsystemReusable(node.id, name.trim(), projectBlockNames());
    if (result.ok) {
      setName(null);
    } else {
      setError(result.error ?? "The subsystem was not added to the library.");
    }
  };
  return (
    <div className="inspector-linked__make" data-testid="inspector-make-reusable-form">
      <label className="inspector-linked__make-label" htmlFor="inspector-make-reusable-name">
        Library name
      </label>
      <input
        id="inspector-make-reusable-name"
        className="inspector-linked__make-input"
        data-testid="inspector-make-reusable-name"
        value={name}
        autoFocus
        spellCheck={false}
        onChange={(event) => {
          setError(null);
          setName(event.target.value);
        }}
        onKeyDown={(event) => {
          if (event.key === "Enter" && problem === null) {
            create();
          } else if (event.key === "Escape") {
            setName(null);
          }
        }}
      />
      <button
        type="button"
        className="button button--primary inspector-button"
        data-testid="inspector-make-reusable-create"
        disabled={problem !== null}
        onClick={create}
      >
        Add to library
      </button>
      <button
        type="button"
        className="button inspector-button"
        data-testid="inspector-make-reusable-cancel"
        onClick={() => setName(null)}
      >
        Cancel
      </button>
      {(error ?? problem) !== null ? (
        <p className="inspector-copy inspector-copy--error" role="alert" data-testid="inspector-make-reusable-error">
          {error ?? problem}
        </p>
      ) : (
        <p className="inspector-note">
          The file is <code>library/{name.trim()}.bgsub.json</code>. This node becomes its first
          instance.
        </p>
      )}
    </div>
  );
}

/**
 * The pin of one parameter or start value of a block inside a library subsystem.
 * Pinned: each instance has its own value. Not pinned: one value for all.
 * Renders nothing outside a library subsystem.
 */
export function PinToggle({ node, kind, name }: { node: ModelNode; kind: PinKind; name: string }) {
  const doc = useDocumentStore((state) => state.doc);
  const activePath = useDocumentStore((state) => state.activePath);
  const [confirming, setConfirming] = useState(false);
  if (doc === null) {
    return null;
  }
  const enclosing = enclosingInstance(doc, activePath);
  const definition = enclosing === null ? undefined : doc.definitions?.[enclosing.name];
  if (enclosing === null || definition === undefined) {
    return null;
  }
  const path = [...enclosing.inner, node.name, name].join("/");
  const pinned = pinsOf(definition, kind).includes(path);
  const store = useDocumentStore.getState();
  const testId = `inspector-pin-${kind}-${name}`;
  if (!pinned) {
    return (
      <button
        type="button"
        className="inspector-pin"
        data-testid={testId}
        data-pinned="false"
        aria-pressed={false}
        title={`One value for every instance of ${enclosing.name}. Pin it to give each instance its own ${name}.`}
        onClick={() => store.setDefinitionPin(enclosing.name, kind, path, true)}
      >
        pin
      </button>
    );
  }
  const own = instancesWithOwnValue(doc, enclosing.name, kind, path);
  if (confirming) {
    return (
      <span className="inspector-pin__confirm" data-testid={`${testId}-confirm`}>
        {own.length} {own.length === 1 ? "instance has" : "instances have"} a value of their own (
        {own.slice(0, 3).join(", ")}
        {own.length > 3 ? ", …" : ""}); unpinning returns {own.length === 1 ? "it" : "them"} to the
        library&apos;s value.
        <button
          type="button"
          className="inspector-pin"
          data-testid={`${testId}-confirm-yes`}
          onClick={() => {
            setConfirming(false);
            store.setDefinitionPin(enclosing.name, kind, path, false);
          }}
        >
          Unpin
        </button>
        <button
          type="button"
          className="inspector-pin"
          data-testid={`${testId}-confirm-no`}
          onClick={() => setConfirming(false)}
        >
          Keep
        </button>
      </span>
    );
  }
  return (
    <button
      type="button"
      className="inspector-pin is-pinned"
      data-testid={testId}
      data-pinned="true"
      aria-pressed={true}
      title={`Pinned: this is the value of ${enclosing.node.name} only; every instance of ${enclosing.name} has its own. Click to unpin.`}
      onClick={() => {
        if (own.length > 0) {
          setConfirming(true);
        } else {
          store.setDefinitionPin(enclosing.name, kind, path, false);
        }
      }}
    >
      pinned · {enclosing.node.name}
    </button>
  );
}
