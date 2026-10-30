/**
 * The inspector for one selected node (plan 7.2, 7.4).
 *
 * It renders the declarations of the node's catalog block: parameters as
 * expression strings with units, bounds and descriptions; structural
 * constants; start overrides; and the port list with domain letters and
 * read-only signal ids. Every change calls a document-store command, so the
 * usual Ctrl+Z / Ctrl+Y and autosave apply.
 */

import { useState } from "react";

import type { ConstantDecl, ParameterDecl, VariableDecl } from "../contracts/catalog";
import type { Diagnostic } from "../contracts/diagnostic";
import type { ModelConnection, ModelNode } from "../contracts/model";
import { BlockHelpButton } from "../app/BlockHelp";
import { ExplainButton } from "../debug/explain/ExplainButton";
import { domainLetter } from "../editor/connectionRules";
import { domainColor } from "../editor/geometry";
import { BlockIcon, JunctionGlyph } from "../editor/icons";
import { interfaceForNode, type PortSpec } from "../editor/nodeInterface";
import type { CatalogIndex } from "../library/catalogIndex";
import { useCatalogStore } from "../library/catalogStore";
import { nodeNameIssue, useDocumentStore } from "../state/documentStore";
import { nodeRef } from "../state/modelFactory";
import { copyBlockToProjectLibrary } from "./copyToLibrary";
import { SelectField, TextField, type SelectOption } from "./fields";
import { qualifiedFrame } from "./frames";
import { portComponentUnits, unitArrayText } from "./units";
import {
  arrayConstantIssue,
  constantDefaultText,
  constantIssue,
  parameterIssue,
  parseConstantInput,
  startIssue,
  textValue,
} from "./validation";

export interface NodeInspectorProps {
  node: ModelNode;
  siblings: readonly ModelNode[];
  connections: readonly ModelConnection[];
  index: CatalogIndex;
  project: string | null;
  diagnostics: readonly Diagnostic[];
  /**
   * Instance names of the subsystem path to this diagram, root first. A port
   * frame is shown qualified as `{path}/{node}/{frame}`, matching the
   * display-qualified `model.check.frames` values. Frame identity is face-scoped (FIX-MB-6).
   */
  path?: readonly string[];
}

interface CopyState {
  status: "idle" | "working" | "done" | "error";
  message: string | null;
}

function messageOf(result: { ok: boolean; error?: string }, fallback: string): string | null {
  if (result.ok) {
    return null;
  }
  return result.error !== undefined && result.error.length > 0 ? result.error : fallback;
}

function signalSuffix(size: readonly number[]): string {
  return size.map((count) => `[1..${count}]`).join("");
}

function ParameterField({ node, decl }: { node: ModelNode; decl: ParameterDecl }) {
  const stored = node.params?.[decl.name];
  const value = stored ?? decl.default;
  const onReset =
    stored !== undefined && stored !== decl.default
      ? () => {
          useDocumentStore.getState().setNodeParam(node.id, decl.name, decl.default);
        }
      : undefined;
  const meta = (
    <>
      {decl.tunable ? <span className="inspector-tag">tunable</span> : null}
      <span>
        min <code>{decl.min ?? "—"}</code>
      </span>
      <span className="inspector-dot">·</span>
      <span>
        max <code>{decl.max ?? "—"}</code>
      </span>
      <span className="inspector-dot">·</span>
      <span>
        default <code>{decl.default}</code>
      </span>
    </>
  );
  const badges =
    decl.type === "Real" ? null : <span className="inspector-tag">{decl.type}</span>;
  const resetLabel = `Reset ${decl.name} to its default (${decl.default})`;

  if (decl.options !== null) {
    const options: SelectOption[] = decl.options.map((label, position) => ({
      value: String(position + 1),
      label: `${position + 1} · ${label}`,
    }));
    return (
      <SelectField
        id={`inspector-param-${decl.name}`}
        testId={`inspector-param-${decl.name}`}
        label={decl.name}
        value={value}
        options={options}
        onChange={(next) => {
          const result = useDocumentStore.getState().setNodeParam(node.id, decl.name, next);
          return messageOf(result, "The value was refused.");
        }}
        onReset={onReset}
        resetLabel={resetLabel}
        unit={decl.unit}
        description={decl.description}
        meta={meta}
        badges={badges}
        invalidMessage={`The stored value ${value} is not one of the listed options; choose one.`}
      />
    );
  }

  return (
    <TextField
      id={`inspector-param-${decl.name}`}
      testId={`inspector-param-${decl.name}`}
      label={decl.name}
      value={value}
      issue={(text) => parameterIssue(text, decl)}
      onCommit={(text) => {
        const result = useDocumentStore.getState().setNodeParam(node.id, decl.name, text);
        return messageOf(result, "The value was refused.");
      }}
      onReset={onReset}
      resetLabel={resetLabel}
      unit={decl.unit}
      description={decl.description}
      meta={meta}
      badges={badges}
    />
  );
}

function ConstantField({ node, decl }: { node: ModelNode; decl: ConstantDecl }) {
  const stored = node.constants?.[decl.name];
  const value = stored ?? decl.default;
  const overridden = stored !== undefined;
  const onReset = overridden
    ? () => {
        useDocumentStore.getState().setNodeConstant(node.id, decl.name, null);
      }
    : undefined;
  const badges = decl.structural ? (
    <span
      className="inspector-tag inspector-tag--structural"
      title="A structural constant fixes sizes; changing it triggers a recompile (D13)."
    >
      structural
    </span>
  ) : null;
  const meta = (
    <>
      <span>{decl.type}</span>
      <span className="inspector-dot">·</span>
      <span>
        default <code>{constantDefaultText(decl)}</code>
      </span>
    </>
  );
  const resetLabel = `Remove the override for ${decl.name} and use the default`;
  const testId = `inspector-constant-${decl.name}`;

  if (decl.type === "Bool" && !Array.isArray(decl.default)) {
    return (
      <SelectField
        id={testId}
        testId={testId}
        label={decl.name}
        value={overridden ? String(value) : ""}
        options={[
          { value: "", label: `Default (${String(decl.default)})` },
          { value: "true", label: "true" },
          { value: "false", label: "false" },
        ]}
        onChange={(next) => {
          const nextValue = next.length === 0 ? null : next === "true";
          const result = useDocumentStore.getState().setNodeConstant(node.id, decl.name, nextValue);
          return messageOf(result, "The value was refused.");
        }}
        onReset={onReset}
        resetLabel={resetLabel}
        description={null}
        meta={meta}
        badges={badges}
        invalidMessage="The stored value is not true or false; choose one."
      />
    );
  }

  return (
    <TextField
      id={testId}
      testId={testId}
      label={decl.name}
      value={textValue(value)}
      issue={(text) =>
        Array.isArray(decl.default) ? arrayConstantIssue(text) : constantIssue(text, decl)
      }
      onCommit={(text) => {
        const parsed = parseConstantInput(text, decl);
        if (!parsed.ok) {
          return parsed.message;
        }
        const result = useDocumentStore
          .getState()
          .setNodeConstant(node.id, decl.name, parsed.value);
        return messageOf(result, "The value was refused.");
      }}
      onReset={onReset}
      resetLabel={resetLabel}
      description={null}
      meta={meta}
      badges={badges}
    />
  );
}

function StartField({ node, variable }: { node: ModelNode; variable: VariableDecl }) {
  const stored = node.starts?.[variable.name];
  const onReset =
    stored !== undefined
      ? () => {
          useDocumentStore.getState().setNodeStart(node.id, variable.name, null);
        }
      : undefined;
  const signalId = `${node.name}/${variable.name}`;
  const meta = (
    <>
      <span>
        declared <code>{variable.start}</code>
        {variable.state !== null ? ` · ${variable.state}` : ""}
      </span>
      <span className="inspector-signal" data-testid={`inspector-start-signal-${variable.name}`}>
        {signalId}
      </span>
      <ExplainButton signalId={signalId} testId={`inspector-explain-${variable.name}`} />
    </>
  );
  return (
    <TextField
      id={`inspector-start-${variable.name}`}
      testId={`inspector-start-${variable.name}`}
      label={variable.name}
      value={stored ?? ""}
      placeholder={variable.start}
      issue={startIssue}
      onCommit={(text) => {
        const result = useDocumentStore
          .getState()
          .setNodeStart(node.id, variable.name, text.trim().length === 0 ? null : text);
        return messageOf(result, "The value was refused.");
      }}
      onReset={onReset}
      resetLabel={`Remove the start override for ${variable.name}`}
      unit={variable.unit}
      description={null}
      meta={meta}
      badges={
        variable.state !== null ? <span className="inspector-tag">{variable.state}</span> : null
      }
    />
  );
}

interface SignalLine {
  key: string;
  id: string;
  unit: string | null;
  title: string;
}

function signalLines(node: ModelNode, port: PortSpec, index: CatalogIndex): SignalLine[] {
  const prefix = `${node.name}/${port.name}`;
  const suffix = signalSuffix(port.size);
  if (port.kind !== "power") {
    return [
      {
        key: port.name,
        id: `${prefix}${suffix}`,
        unit: port.unit,
        title: `${port.kind} ${port.type}`,
      },
    ];
  }
  const components = portComponentUnits(port, index);
  if (components !== null && components.effort.length > 1) {
    // A multibond is recorded per component: each e[k]/f[k] carries its own
    // unit (D-MB10), and P is the scalar power sum in W.
    const lines: SignalLine[] = [];
    const count = components.effort.length;
    components.effort.forEach((unit, position) => {
      const k = position + 1;
      lines.push({
        key: `e${k}`,
        id: `${prefix}.e[${k}]`,
        unit,
        title: `effort component ${k} of ${count} (${unit})`,
      });
    });
    components.flow.forEach((unit, position) => {
      const k = position + 1;
      lines.push({
        key: `f${k}`,
        id: `${prefix}.f[${k}]`,
        unit,
        title: `flow component ${k} of ${count} (${unit})`,
      });
    });
    lines.push({
      key: "P",
      id: `${prefix}.P`,
      unit: "W",
      title: "derived power sum, Σ e[k]·f[k]",
    });
    return lines;
  }
  const domain = index.domains.get(port.domain);
  return [
    {
      key: "e",
      id: `${prefix}.e${suffix}`,
      unit: domain?.effort.unit ?? null,
      title: domain === undefined ? "effort" : `effort (${domain.effort.name})`,
    },
    {
      key: "f",
      id: `${prefix}.f${suffix}`,
      unit: domain?.flow.unit ?? null,
      title: domain === undefined ? "flow" : `flow (${domain.flow.name})`,
    },
    {
      key: "P",
      id: `${prefix}.P${suffix}`,
      unit: null,
      title: "derived power, e·f",
    },
  ];
}

function PortRow({
  node,
  port,
  index,
  path = [],
}: {
  node: ModelNode;
  port: PortSpec;
  index: CatalogIndex;
  path?: readonly string[];
}) {
  const lines = signalLines(node, port, index);
  const components = portComponentUnits(port, index);
  const declared =
    port.frame === null || port.frame === undefined ? "" : port.frame.trim();
  const qualified = qualifiedFrame([...path, node.name], declared);
  return (
    <div
      className="inspector-port"
      data-testid={`inspector-port-${port.name}`}
      data-domain={port.domain}
      data-multibond={components !== null ? components.effort.length : undefined}
      role="group"
      aria-label={
        components === null
          ? `${port.name} port, ${port.domain}`
          : `${port.name} port, ${port.domain} multibond, ${components.effort.length} components`
      }
    >
      <div className="inspector-port__head">
        <span
          className="inspector-port__letter"
          style={{ color: domainColor(port.domain) }}
          data-testid={`inspector-port-${port.name}-letter`}
          title={`${port.domain} domain`}
          role="img"
          aria-label={`${port.domain} domain`}
        >
          {domainLetter(port.domain)}
        </span>
        <span className="inspector-port__name">{port.name}</span>
        <span className="inspector-port__kind">{port.kind}</span>
        {port.size.length > 0 ? (
          <span className="inspector-tag" title="Vector size">
            {port.size.join("×")}
          </span>
        ) : null}
        <span className="inspector-port__domain">{port.domain}</span>
      </div>
      {port.kind === "power" ? (
        <p
          className={`inspector-port__frame${declared.length === 0 ? " is-neutral" : ""}`}
          data-testid={`inspector-port-${port.name}-frame`}
          data-frame={declared.length === 0 ? null : declared}
        >
          {declared.length === 0 ? (
            "frame-neutral"
          ) : (
            <>
              <span className="inspector-port__frame-label">frame</span>
              <code>{declared}</code>
              {qualified !== null && qualified !== declared ? (
                <span className="inspector-port__frame-qualified">{qualified}</span>
              ) : null}
            </>
          )}
        </p>
      ) : null}
      {components !== null ? (
        <dl
          className="inspector-units"
          data-testid={`inspector-port-${port.name}-units`}
          aria-label={`${port.domain} component units`}
        >
          <div className="inspector-units__row">
            <dt>effort</dt>
            <dd>
              <code>{unitArrayText(components.effort)}</code>
            </dd>
          </div>
          <div className="inspector-units__row">
            <dt>flow</dt>
            <dd>
              <code>{unitArrayText(components.flow)}</code>
            </dd>
          </div>
        </dl>
      ) : null}
      <ul className="inspector-signals">
        {lines.map((line) => (
          <li key={line.key} title={line.title} data-testid={`inspector-signal-${line.id}`}>
            <code>{line.id}</code>
            {line.unit !== null ? <span className="inspector-signals__unit">{line.unit}</span> : null}
          </li>
        ))}
      </ul>
    </div>
  );
}

export function NodeInspector({
  node,
  siblings,
  connections,
  index,
  project,
  diagnostics,
  path = [],
}: NodeInspectorProps) {
  const iface = interfaceForNode(node, index);
  const ref = nodeRef(node);
  const block = ref === null ? undefined : index.blocksByRef.get(ref);
  const inlineSource = "inline" in node.block ? node.block.inline.source : null;
  const source = block?.source ?? inlineSource;
  const sourcePath = block?.path ?? (inlineSource !== null ? "inline source" : null);
  const [sourceOpen, setSourceOpen] = useState(false);
  const [copy, setCopy] = useState<CopyState>({ status: "idle", message: null });

  const displayRef =
    ref ??
    ("junction" in node.block
      ? `junction:${node.block.junction}`
      : "inline" in node.block
        ? `inline:${node.id}`
        : "subsystem");

  const description =
    block?.description ??
    ("junction" in node.block
      ? `A ${node.block.junction} junction: the across variables are equal and the through variables sum to zero.`
      : "inline" in node.block
        ? "The block source is embedded in this model."
        : "A nested diagram; its exposed ports are listed below.");

  const nodeDiagnostics = diagnostics.filter((entry) => {
    if (entry.node === node.id) {
      return true;
    }
    const path = entry.path ?? null;
    return path !== null && (path === node.name || path.startsWith(`${node.name}/`));
  });

  const junctionConnections = iface.isJunction
    ? connections.filter(
        (connection) =>
          connection.from.node === node.id || connection.to.node === node.id,
      )
    : [];
  const nameOf = (id: string): string =>
    siblings.find((entry) => entry.id === id)?.name ?? id;

  const copyDisabled =
    block === undefined ||
    project === null ||
    block.ref.startsWith("project:") ||
    copy.status === "working";
  const copyHint =
    block === undefined
      ? "Only library blocks have source that can be copied."
      : block.ref.startsWith("project:")
        ? "This block already lives in the project library."
        : project === null
          ? "Open a project before copying a block."
          : "Fork the block into library/<Name>.jl and re-point this instance.";

  const onCopy = async (): Promise<void> => {
    if (block === undefined || project === null) {
      return;
    }
    setCopy({ status: "working", message: null });
    try {
      const outcome = await copyBlockToProjectLibrary(project, block);
      if (outcome.catalog !== null) {
        useCatalogStore.getState().setCatalog(outcome.catalog);
      }
      if (outcome.ref !== null) {
        const result = useDocumentStore.getState().setNodeBlockRef(node.id, outcome.ref);
        if (!result.ok) {
          throw new Error(result.error ?? "The instance could not be re-pointed.");
        }
        setCopy({
          status: "done",
          message: `Copied to ${outcome.file} and re-pointed ${node.name} to ${outcome.ref}.`,
        });
      } else if (outcome.catalogError !== null) {
        setCopy({
          status: "done",
          message: `Copied to ${outcome.file}, but the catalog could not be refreshed (${outcome.catalogError}). Reopen the project to use the fork.`,
        });
      } else {
        setCopy({
          status: "done",
          message: `Copied to ${outcome.file}. The catalog does not list project:${outcome.name} yet; reopen the project to use the fork.`,
        });
      }
    } catch (error) {
      setCopy({
        status: "error",
        message: error instanceof Error ? error.message : String(error),
      });
    }
  };

  const helpRef = iface.isJunction ? `junction:${iface.junction ?? "0"}` : ref;

  return (
    <div className="inspector-body" data-testid="inspector-node" data-node-id={node.id}>
      <header className="inspector-header">
        <div className="inspector-header__icon" aria-hidden="true">
          {iface.isJunction ? (
            <JunctionGlyph kind={iface.junction ?? "0"} size={26} />
          ) : (
            <BlockIcon icon={iface.icon} name={iface.title} size={26} />
          )}
        </div>
        <div className="inspector-header__text">
          <p className="inspector-header__kicker">
            {block?.group ?? (iface.isJunction ? "Power junction" : "Model element")}
          </p>
          <h3 className="inspector-header__title" data-testid="inspector-title">
            {iface.title}
          </h3>
          <p className="inspector-header__ref" data-testid="inspector-ref">
            {displayRef}
          </p>
          <p className="inspector-header__description" data-testid="inspector-description">
            {description}
          </p>
        </div>
        {helpRef !== null ? <BlockHelpButton blockRef={helpRef} label={iface.title} /> : null}
      </header>

      {ref !== null && block === undefined ? (
        <p className="inspector-warning" role="alert" data-testid="inspector-unknown-ref">
          The block <code>{ref}</code> is not in the current catalog, so its declarations and
          units cannot be shown. Check the project library or re-add the block.
        </p>
      ) : null}

      <section className="inspector-section" aria-labelledby="inspector-name-title">
        <h4 className="inspector-section__title" id="inspector-name-title">
          Name
        </h4>
        <TextField
          id="inspector-name"
          testId="inspector-name"
          label="Instance name"
          value={node.name}
          issue={(text) => nodeNameIssue(siblings, node.id, text.trim())}
          onCommit={(text) => {
            const result = useDocumentStore.getState().renameNode(node.id, text);
            return messageOf(result, "The name was refused.");
          }}
          description={
            iface.isJunction
              ? "Junction names follow the same identifier rules as blocks."
              : "Signal ids start with this name; it must be unique in the diagram."
          }
          meta={
            iface.isJunction ? undefined : (
              <span className="inspector-signal">
                signals <code>{node.name}/…</code>
              </span>
            )
          }
        />
      </section>

      {block !== undefined ? (
        <>
          <section className="inspector-section" aria-labelledby="inspector-params-title">
            <h4 className="inspector-section__title" id="inspector-params-title">
              Parameters
              <span className="inspector-section__count">{block.parameters.length}</span>
            </h4>
            {block.parameters.length === 0 ? (
              <p className="inspector-none">This block has no parameters.</p>
            ) : (
              block.parameters.map((decl) => (
                <ParameterField key={decl.name} node={node} decl={decl} />
              ))
            )}
          </section>

          <section className="inspector-section" aria-labelledby="inspector-constants-title">
            <h4 className="inspector-section__title" id="inspector-constants-title">
              Constants
              <span className="inspector-section__count">{block.constants.length}</span>
            </h4>
            {block.constants.length === 0 ? (
              <p className="inspector-none">This block has no constants.</p>
            ) : (
              <>
                {block.constants.map((decl) => (
                  <ConstantField key={decl.name} node={node} decl={decl} />
                ))}
                {block.constants.some((decl) => decl.structural) ? (
                  <p className="inspector-note" data-testid="inspector-structural-note">
                    Structural constants set the block&apos;s sizes; changing one triggers a
                    recompile (D13).
                  </p>
                ) : null}
              </>
            )}
          </section>

          <section className="inspector-section" aria-labelledby="inspector-starts-title">
            <h4 className="inspector-section__title" id="inspector-starts-title">
              Start values
              <span className="inspector-section__count">{block.variables.length}</span>
            </h4>
            {block.variables.length === 0 ? (
              <p className="inspector-none">This block has no state variables.</p>
            ) : (
              <>
                {block.variables.map((variable) => (
                  <StartField key={variable.name} node={node} variable={variable} />
                ))}
                <p className="inspector-note">
                  An empty field uses the declared start; clear a field to remove the override.
                </p>
              </>
            )}
          </section>
        </>
      ) : null}

      <section className="inspector-section" aria-labelledby="inspector-ports-title">
        <h4 className="inspector-section__title" id="inspector-ports-title">
          Ports
          <span className="inspector-section__count">{iface.ports.length}</span>
        </h4>
        {iface.isJunction ? (
          <p className="inspector-note">
            A {iface.junction} junction creates one port per bond, numbered p1…pn in model
            check order. Bonds attach to the circle edge.
          </p>
        ) : iface.ports.length === 0 ? (
          <p className="inspector-none">This element has no ports.</p>
        ) : (
          iface.ports.map((port) => (
            <PortRow key={port.name} node={node} port={port} index={index} path={path} />
          ))
        )}
        {iface.isJunction ? (
          junctionConnections.length === 0 ? (
            <p className="inspector-none">No bonds are connected to this junction.</p>
          ) : (
            <ul className="inspector-connections" data-testid="inspector-junction-connections">
              {junctionConnections.map((connection) => (
                <li key={connection.id} data-testid={`inspector-connection-${connection.id}`}>
                  <span className="inspector-tag">{connection.kind}</span>
                  <code>
                    {nameOf(connection.from.node)}
                    {connection.from.port !== undefined ? `.${connection.from.port}` : ""} →{" "}
                    {nameOf(connection.to.node)}
                    {connection.to.port !== undefined ? `.${connection.to.port}` : ""}
                  </code>
                </li>
              ))}
            </ul>
          )
        ) : null}
      </section>

      {nodeDiagnostics.length > 0 ? (
        <section className="inspector-section" aria-labelledby="inspector-check-title">
          <h4 className="inspector-section__title" id="inspector-check-title">
            Model check
            <span className="inspector-section__count">{nodeDiagnostics.length}</span>
          </h4>
          <ul className="inspector-diagnostics">
            {nodeDiagnostics.map((entry, position) => (
              <li
                key={`${entry.code}-${position}`}
                className={`inspector-diagnostic inspector-diagnostic--${entry.severity}`}
                data-testid={`inspector-diagnostic-${entry.code}`}
              >
                <div className="inspector-diagnostic__head">
                  <span className="inspector-diagnostic__code">{entry.code}</span>
                  <span className="inspector-diagnostic__severity">{entry.severity}</span>
                </div>
                <p className="inspector-diagnostic__message">{entry.message}</p>
                {entry.hint !== null && entry.hint !== undefined ? (
                  <p className="inspector-diagnostic__hint">{entry.hint}</p>
                ) : null}
              </li>
            ))}
          </ul>
        </section>
      ) : null}

      <section className="inspector-section inspector-section--last" aria-labelledby="inspector-library-title">
        <h4 className="inspector-section__title" id="inspector-library-title">
          Library
        </h4>
        <div className="inspector-actions">
          <button
            type="button"
            className="button inspector-button"
            data-testid="inspector-open-source"
            aria-expanded={sourceOpen}
            disabled={source === null}
            title={source === null ? "This element has no source." : "Show the block source"}
            onClick={() => setSourceOpen((open) => !open)}
          >
            {sourceOpen ? "Hide source" : "Open source"}
          </button>
          <button
            type="button"
            className="button inspector-button"
            data-testid="inspector-copy-library"
            disabled={copyDisabled}
            title={copyHint}
            onClick={() => void onCopy()}
          >
            {copy.status === "working" ? "Copying…" : "Copy to project library"}
          </button>
        </div>
        {copy.status !== "idle" && copy.message !== null ? (
          <p
            className={`inspector-copy inspector-copy--${copy.status}`}
            role={copy.status === "error" ? "alert" : "status"}
            data-testid="inspector-copy-status"
          >
            {copy.message}
          </p>
        ) : null}
        {sourceOpen && source !== null ? (
          <div className="inspector-source" data-testid="inspector-source">
            <div className="inspector-source__head">
              <span className="inspector-source__path">{sourcePath}</span>
              <button
                type="button"
                className="inspector-reset"
                aria-label="Close the source"
                title="Close the source"
                onClick={() => setSourceOpen(false)}
              >
                ×
              </button>
            </div>
            <pre className="inspector-source__text" data-testid="inspector-source-text">
              {source}
            </pre>
          </div>
        ) : null}
      </section>
    </div>
  );
}
