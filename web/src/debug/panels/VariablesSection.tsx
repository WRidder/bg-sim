/**
 * Variables (plan 7.9): the frame of a statement pause (locals, held outputs,
 * `previous` values; vectors and matrices expand) and, at any pause, the
 * signals of the selected instance plus the signals the watch breakpoints and
 * watch expressions read (`GET /values`).
 */

import { useEffect, useMemo, useState } from "react";

import type { Frame, FrameValue, PausedInfo } from "../../contracts/debug";
import type { Model } from "../../contracts/model";
import type { RunSignal } from "../../contracts/run-manifest";
import { useRunStore } from "../../plot/runStore";
import { useDocumentStore } from "../../state/documentStore";
import { useBreakpointStore } from "../breakpointStore";
import { useDebugStore } from "../debugStore";
import { formatPauseTime } from "../format";
import { signalIdsOfExpression, watchBreakpoints } from "./breakWhen";
import { formatFrameValue, frameElements, frameTypeText } from "./frameFormat";
import { useWatchExpressionStore } from "./watchExpressionStore";

/** The signal ids shown per pause; a model with hundreds of signals per instance is capped. */
const SIGNAL_LIMIT = 64;

/** The instance path of the selected node (`Rig/Motor1`), or null. */
export function selectedInstancePath(
  doc: Model | null,
  activePath: readonly string[],
  selectedNodes: readonly string[],
): string | null {
  if (doc === null || selectedNodes.length === 0) {
    return null;
  }
  const names: string[] = [];
  let diagram = doc.diagram;
  for (const id of activePath) {
    const node = diagram.nodes.find((entry) => entry.id === id);
    if (node === undefined || !("subsystem" in node.block)) {
      return null;
    }
    names.push(node.name);
    diagram = node.block.subsystem.diagram;
  }
  const selected = diagram.nodes.find((entry) => entry.id === selectedNodes[0]);
  return selected === undefined ? null : [...names, selected.name].join("/");
}

function ValueRow({ item, testId }: { item: FrameValue; testId: string }) {
  const isArray = Array.isArray(item.value);
  const summary = (
    <>
      <span className="debug-var__name">{item.name}</span>
      <span className="debug-var__type">{frameTypeText(item.type, item.size)}</span>
      <span className="debug-var__value" data-testid={`${testId}-value`}>
        {formatFrameValue(item.value, item.size)}
      </span>
    </>
  );
  if (!isArray) {
    return (
      <li className="debug-var" data-testid={testId}>
        {summary}
      </li>
    );
  }
  return (
    <li className="debug-var debug-var--array" data-testid={testId}>
      <details>
        <summary aria-label={`${item.name}, ${frameTypeText(item.type, item.size)}, expand`}>{summary}</summary>
        <ElementList value={item.value} size={item.size} />
      </details>
    </li>
  );
}

function ElementList({ value, size }: { value: unknown; size: readonly number[] }) {
  return (
    <ul className="debug-var__elements">
      {frameElements(value).map((element) => (
        <li key={element.label} className="debug-var">
          {Array.isArray(element.value) ? (
            <details>
              <summary>
                <span className="debug-var__name">{element.label}</span>
                <span className="debug-var__value">
                  {formatFrameValue(element.value, size.slice(1))}
                </span>
              </summary>
              <ElementList value={element.value} size={size.slice(1)} />
            </details>
          ) : (
            <>
              <span className="debug-var__name">{element.label}</span>
              <span className="debug-var__value">{formatFrameValue(element.value)}</span>
            </>
          )}
        </li>
      ))}
    </ul>
  );
}

function FrameGroup({ title, items, group }: { title: string; items: readonly FrameValue[]; group: string }) {
  if (items.length === 0) {
    return null;
  }
  return (
    <div className="debug-var-group" data-testid={`variables-${group}`}>
      <h4 className="debug-var-group__title">{title}</h4>
      <ul className="debug-var-list">
        {items.map((item) => (
          <ValueRow key={item.name} item={item} testId={`var-${group}-${item.name}`} />
        ))}
      </ul>
    </div>
  );
}

export function FrameView({ frame }: { frame: Frame }) {
  return (
    <>
      <FrameGroup title="Locals" items={frame.locals} group="locals" />
      <FrameGroup title="Held outputs" items={frame.held} group="held" />
      <FrameGroup title="Previous values" items={frame.previous} group="previous" />
    </>
  );
}

/** Signal ids the panel reads at a pause: the selected instance first, then the watched ones. */
export function variableSignalIds(
  signals: readonly RunSignal[],
  instance: string | null,
  watchedIds: readonly string[],
): { instanceIds: string[]; watchedIds: string[] } {
  const instanceIds =
    instance === null
      ? []
      : signals.filter((signal) => signal.path === instance).map((signal) => signal.id);
  const taken = new Set(instanceIds);
  return {
    instanceIds: instanceIds.slice(0, SIGNAL_LIMIT),
    watchedIds: watchedIds.filter((id) => !taken.has(id)).slice(0, SIGNAL_LIMIT),
  };
}

function SignalValues({
  ids,
  title,
  group,
  values,
  signals,
  hint,
}: {
  ids: readonly string[];
  title: string;
  group: string;
  values: Record<string, number> | null;
  signals: readonly RunSignal[];
  hint: string;
}) {
  return (
    <div className="debug-var-group" data-testid={`variables-${group}`}>
      <h4 className="debug-var-group__title">{title}</h4>
      {ids.length === 0 ? (
        <p className="debug-panel__hint">{hint}</p>
      ) : (
        <ul className="debug-var-list">
          {ids.map((id) => {
            const unit = signals.find((signal) => signal.id === id)?.unit ?? null;
            const value = values?.[id];
            return (
              <li className="debug-var" key={id} data-testid="var-signal" data-signal-id={id}>
                <span className="debug-var__name">{id}</span>
                <span className="debug-var__type">{unit ?? ""}</span>
                <span className="debug-var__value" data-testid="var-signal-value">
                  {value === undefined ? (values === null ? "…" : "not recorded") : formatFrameValue(value)}
                </span>
              </li>
            );
          })}
        </ul>
      )}
    </div>
  );
}

function pauseSummary(info: PausedInfo): string {
  return `Paused at t = ${formatPauseTime(info.t)} (${info.reason})`;
}

export function VariablesSection() {
  const status = useDebugStore((state) => state.status);
  const info = useDebugStore((state) => state.pausedInfo);
  const pauseCount = useDebugStore((state) => state.pauseCount);
  const signals = useRunStore((state) => state.manifest?.signals);
  const doc = useDocumentStore((state) => state.doc);
  const activePath = useDocumentStore((state) => state.activePath);
  const selectedNodes = useDocumentStore((state) => state.selection.nodes);
  const breakpoints = useBreakpointStore((state) => state.breakpoints);
  const watchExprs = useWatchExpressionStore((state) => state.items);
  const [values, setValues] = useState<Record<string, number> | null>(null);
  const [valuesError, setValuesError] = useState<string | null>(null);

  const instance = selectedInstancePath(doc, activePath, selectedNodes);
  const ids = useMemo(() => {
    const watched = new Set<string>();
    for (const entry of watchBreakpoints(breakpoints)) {
      if (entry.enabled) {
        signalIdsOfExpression(entry.watch.expr).forEach((id) => watched.add(id));
      }
    }
    for (const entry of watchExprs) {
      signalIdsOfExpression(entry.expr).forEach((id) => watched.add(id));
    }
    return variableSignalIds(signals ?? [], instance, [...watched]);
  }, [signals, instance, breakpoints, watchExprs]);
  const key = [...ids.instanceIds, ...ids.watchedIds].join(",");

  useEffect(() => {
    if (status !== "paused" || key.length === 0) {
      setValues(null);
      setValuesError(null);
      return;
    }
    let live = true;
    setValues(null);
    useDebugStore
      .getState()
      .values(key.split(","))
      .then((result) => {
        if (live) {
          setValues(result.values);
          setValuesError(null);
        }
      })
      .catch((error: unknown) => {
        if (live) {
          setValuesError(error instanceof Error ? error.message : String(error));
        }
      });
    return () => {
      live = false;
    };
  }, [status, pauseCount, key]);

  if (status === "idle" || status === "done") {
    return (
      <p className="debug-panel__hint" data-testid="variables-empty">
        Start a debug run (F5) to see variables. At a statement breakpoint the frame is shown here; at
        any pause the signals of the selected block are.
      </p>
    );
  }
  if (status === "running" || info === null) {
    return (
      <p className="debug-panel__hint" data-testid="variables-empty">
        The run is running. Pause it (F6) or set a breakpoint, and the variables appear here.
      </p>
    );
  }
  return (
    <div data-testid="variables">
      <p className="debug-panel__pause" data-testid="variables-pause">
        {pauseSummary(info)}
      </p>
      {info.frame !== null ? (
        <FrameView frame={info.frame} />
      ) : (
        <p className="debug-panel__hint" data-testid="variables-no-frame">
          This pause is not inside a statement, so there is no frame. Pause at a line breakpoint to see
          locals and held outputs.
        </p>
      )}
      <SignalValues
        ids={ids.instanceIds}
        title={instance === null ? "Selected block" : `Signals of ${instance}`}
        group="instance"
        values={values}
        signals={signals ?? []}
        hint={
          instance === null
            ? "Select a block on the canvas to see its signals at this pause."
            : "The run recorded no signals for this block."
        }
      />
      {ids.watchedIds.length > 0 ? (
        <SignalValues
          ids={ids.watchedIds}
          title="Watched signals"
          group="watched"
          values={values}
          signals={signals ?? []}
          hint=""
        />
      ) : null}
      {valuesError !== null ? (
        <p className="debug-panel__error" role="alert" data-testid="variables-error">
          {valuesError}
        </p>
      ) : null}
    </div>
  );
}
