/**
 * The Export dialog (plan/EXPORT_PLAN.md W-EX1): export the open model, or one subsystem
 * of it (J-EX11), as a C/FMU.
 *
 * One column, top to bottom: the scope, the interface the export will publish (with the
 * effort/flow choice of each power port), the settings (method and dt, Auto by default;
 * damping, Jacobian and linear solver under Advanced), the Export button with progress, and
 * the backend's report with the Download button. A refused export (E110, E112, ...) is a
 * message with its diagnostics, never a crash.
 *
 * The job is a background task (`tasks/exportTasks.ts` polls it): closing the dialog does
 * not cancel it, and the top bar's tasks indicator re-opens the dialog on it ("Show
 * details"), also after a reload and also for another model's export (progress and report
 * only, without the form).
 */

import { useCallback, useEffect, useMemo, useRef, useState, type ReactNode } from "react";

import { useDialogFocus } from "../app/useDialogFocus";
import type { ExportJob } from "../contracts/export-job";
import type { Diagnostic, ExportReport } from "../contracts/export-report";
import type {
  ExportJacobian,
  ExportLinearSolver,
  ExportMethod,
  ExportRequest,
  ExportSettings,
} from "../contracts/export-request";
import { useCatalogStore } from "../library/catalogStore";
import { useDocumentStore } from "../state/documentStore";
import { exportTaskId, trackExportJob } from "../tasks/exportTasks";
import { cancelTask, useTaskStore } from "../tasks/taskStore";
import { ExportApiError, fmuUrl, getExport, isFinished, startExport } from "./exportApi";
import {
  buildLines,
  defaultStep,
  formatBytes,
  formatCost,
  formatStep,
  METHOD_LABELS,
  methodLabel,
  parseOptionalPositive,
  progressLabel,
  timingParts,
} from "./exportFormat";
import {
  defaultPowerInputs,
  findSubsystem,
  isEmptyInterface,
  listSubsystems,
  previewInterface,
  type PowerChoice,
} from "./exportInterface";
import { useExportDialogStore } from "./exportStore";
import {
  exposeAllGlobals,
  listTunableCandidates,
  newTunableRow,
  rowOpen,
  rowProblem,
  tunableCostText,
  tunablesRequest,
  type TunableCandidate,
  type TunableRow,
} from "./exportTunables";
import "./export.css";

/** The elapsed seconds of a running job tick this often. */
const TICK_MS = 500;
const METHODS = Object.keys(METHOD_LABELS) as ExportMethod[];

function errorText(cause: unknown): string {
  return cause instanceof Error ? cause.message : String(cause);
}

/** Diagnostics shown in full per code; the rest of a long run (14 × W203) folds away. */
const SHOWN_PER_CODE = 2;

function DiagnosticItem({ d }: { d: Diagnostic }) {
  return (
    <li
      className={`export-dialog__diagnostic is-${d.severity}`}
      data-testid={`export-diagnostic-${d.code}`}
    >
      <span className="export-dialog__code">{d.code}</span>
      <span className="export-dialog__message">
        {d.message}
        {d.path ? <span className="export-dialog__path"> at {d.path}</span> : null}
        {d.hint ? <span className="export-dialog__hint">{d.hint}</span> : null}
      </span>
    </li>
  );
}

function DiagnosticList({ diagnostics }: { diagnostics: Diagnostic[] }) {
  if (diagnostics.length === 0) {
    return null;
  }
  const groups = new Map<string, Diagnostic[]>();
  for (const d of diagnostics) {
    groups.set(d.code, [...(groups.get(d.code) ?? []), d]);
  }
  return (
    <ul className="export-dialog__diagnostics" data-testid="export-diagnostics">
      {[...groups.entries()].map(([code, items]) => (
        <li key={code} className="export-dialog__group">
          <ul className="export-dialog__diagnostics">
            {items.slice(0, SHOWN_PER_CODE).map((d, index) => (
              <DiagnosticItem key={index} d={d} />
            ))}
          </ul>
          {items.length > SHOWN_PER_CODE ? (
            <details className="export-dialog__more" data-testid={`export-more-${code}`}>
              <summary>
                {items.length - SHOWN_PER_CODE} more {code}
              </summary>
              <ul className="export-dialog__diagnostics">
                {items.slice(SHOWN_PER_CODE).map((d, index) => (
                  <DiagnosticItem key={index} d={d} />
                ))}
              </ul>
            </details>
          ) : null}
        </li>
      ))}
    </ul>
  );
}

function ReportView({ job, report }: { job: ExportJob; report: ExportReport }) {
  const spectrum = report.spectrum;
  const timings = timingParts(job.timings);
  return (
    <section className="export-dialog__section" data-testid="export-report" aria-label="Report">
      <h3 className="export-dialog__heading">Report</h3>
      <dl className="export-dialog__summary">
        <dt>Method</dt>
        <dd data-testid="export-report-method">{methodLabel(report.method)}</dd>
        <dt>Internal step dt</dt>
        <dd data-testid="export-report-dt">{formatStep(report.dt)}</dd>
        <dt>Substeps</dt>
        <dd data-testid="export-report-substeps">
          {report.substeps} per communication step of {formatStep(report.step)}
        </dd>
        <dt>States</dt>
        <dd>
          {report.states}
          {report.algebraic ? ` (${report.algebraic} algebraic)` : ""}
        </dd>
        <dt>Spectrum</dt>
        <dd>
          max |λ| {spectrum.maxAbsLambda === null ? "—" : formatCost(spectrum.maxAbsLambda)} 1/s
          {spectrum.stableStep ? `, stable step ${formatStep(spectrum.stableStep)}` : ""}
          {spectrum.accurateStep ? `, accurate step ${formatStep(spectrum.accurateStep)}` : ""}
          {` (${spectrum.points} points`}
          {spectrum.relaxedDamping ? `, relaxed damping ${spectrum.damping ?? ""}` : ""})
        </dd>
        <dt>Interface</dt>
        <dd>
          {report.inputs.length} input{report.inputs.length === 1 ? "" : "s"},{" "}
          {report.outputs.length} output{report.outputs.length === 1 ? "" : "s"},{" "}
          {report.parameters.length} parameter{report.parameters.length === 1 ? "" : "s"}
        </dd>
        {timings.length > 0 ? (
          <>
            <dt>Timings</dt>
            <dd data-testid="export-timings">
              {timings.join(" · ")}
              {typeof job.timings?.totalS === "number"
                ? ` · total ${job.timings.totalS.toFixed(1)} s`
                : ""}
            </dd>
          </>
        ) : null}
      </dl>

      {(report.selection ?? []).length > 0 ? (
        <table className="export-dialog__table" data-testid="export-candidates">
          <caption>Candidates (cost: estimated flops per communication step)</caption>
          <thead>
            <tr>
              <th scope="col">Method</th>
              <th scope="col">dt</th>
              <th scope="col">Substeps</th>
              <th scope="col">Cost</th>
              <th scope="col">Within budget</th>
              <th scope="col">Damped modes</th>
            </tr>
          </thead>
          <tbody>
            {(report.selection ?? []).map((row) => (
              <tr
                key={row.method}
                className={row.method === report.method ? "is-chosen" : undefined}
                data-testid={`export-candidate-${row.method}`}
              >
                <td>
                  {methodLabel(row.method)}
                  {row.method === report.method ? " (chosen)" : ""}
                </td>
                <td>{formatStep(row.dt)}</td>
                <td>{row.substeps}</td>
                <td>{formatCost(row.cost)}</td>
                <td>{row.withinBudget ? "yes" : "no"}</td>
                <td>{row.numericallyDamped ?? 0}</td>
              </tr>
            ))}
          </tbody>
        </table>
      ) : null}

      <TunablesReport report={report} />

      <ul className="export-dialog__lines" data-testid="export-build">
        {buildLines(report.build).map((line) => (
          <li key={line}>{line}</li>
        ))}
      </ul>
      {(job.notes ?? [])
        .filter((note) => !note.startsWith("Source-only FMU"))
        .map((note) => (
          <p key={note} className="export-dialog__note">
            {note}
          </p>
        ))}
      <DiagnosticList diagnostics={report.diagnostics} />
      {job.fmu ? (
        <a
          className="button button--primary export-dialog__download"
          href={fmuUrl(job.id)}
          download={job.fmu.file}
          data-testid="export-download"
        >
          Download {job.fmu.file} ({formatBytes(job.fmu.bytes)})
        </a>
      ) : null}
    </section>
  );
}

function formatValue(value: number | null): string {
  return value === null ? "—" : String(Number(value.toPrecision(6)));
}

/**
 * The tunables editor (W-EX1, J-EX8): nothing by default (every parameter folded), a picker
 * over the scope's block parameters and global parameters, "Expose all globals", and a range
 * per pick (D-EX16).
 */
function TunablesSection({
  candidates,
  candidateById,
  rows,
  problems,
  pick,
  onPick,
  onRows,
}: {
  candidates: readonly TunableCandidate[];
  candidateById: ReadonlyMap<string, TunableCandidate>;
  rows: readonly TunableRow[];
  problems: readonly (string | null)[];
  pick: string;
  onPick: (next: string) => void;
  onRows: (next: TunableRow[]) => void;
}) {
  const picked = new Set(rows.map((row) => row.id));
  const pickable = candidates.filter((c) => c.blocked === null && !picked.has(c.id));
  const chosen = candidateById.get(pick.trim());
  const pickProblem = pick.trim() === ""
    ? null
    : chosen === undefined
      ? "not a parameter of this export"
      : chosen.blocked ?? (picked.has(chosen.id) ? "already picked" : null);
  const exposable = candidates.filter((c) => c.kind === "global" && c.blocked === null);
  const add = () => {
    if (chosen !== undefined && pickProblem === null) {
      onRows([...rows, newTunableRow(chosen)]);
      onPick("");
    }
  };
  const update = (index: number, patch: Partial<TunableRow>) =>
    onRows(rows.map((row, k) => (k === index ? { ...row, ...patch } : row)));
  const open = rows.filter(rowOpen).length;
  return (
    <section className="export-dialog__section" aria-label="Tunable parameters" data-testid="export-tunables">
      <h3 className="export-dialog__heading">Tunable parameters</h3>
      <p className="export-dialog__note">
        {rows.length === 0
          ? "None: every parameter is folded into the generated code, which gives the fastest step. "
          : ""}
        A tunable stays an FMU parameter that the host sets before initialization. The values
        computed from it (and, for a DAE, the algebraic start) are recomputed once at
        initialization, never per step. Keeping a value open can cost operations per step; the
        report compares.
      </p>
      <div className="export-dialog__row">
        <input
          className="open-dialog__input export-dialog__pick"
          list="export-tunable-candidates"
          data-testid="export-tunable-pick"
          aria-label="Parameter or global to keep tunable"
          aria-invalid={pickProblem !== null}
          placeholder={pickable[0] ? `e.g. ${pickable[0].id}` : "no parameter to pick"}
          value={pick}
          onChange={(event) => onPick(event.target.value)}
          onKeyDown={(event) => {
            if (event.key === "Enter") {
              event.preventDefault();
              add();
            }
          }}
        />
        <datalist id="export-tunable-candidates">
          {pickable.map((c) => (
            <option key={c.id} value={c.id}>
              {`${formatValue(c.value)}${c.unit ? ` ${c.unit}` : ""}${c.description ? ` · ${c.description}` : ""}`}
            </option>
          ))}
        </datalist>
        <button
          type="button"
          className="button"
          data-testid="export-tunable-add"
          disabled={chosen === undefined || pickProblem !== null}
          onClick={add}
        >
          Add
        </button>
        {exposable.length > 0 ? (
          <button
            type="button"
            className="button"
            data-testid="export-expose-globals"
            disabled={exposable.every((c) => picked.has(c.id))}
            title="Make every global parameter that is not an equation an FMU parameter"
            onClick={() => onRows(exposeAllGlobals(rows, candidates))}
          >
            Expose all globals ({exposable.length})
          </button>
        ) : null}
      </div>
      {pickProblem !== null ? (
        <p className="export-dialog__warning" data-testid="export-tunable-pick-problem">
          {pick.trim()}: {pickProblem}.
        </p>
      ) : null}
      {rows.length > 0 ? (
        <table className="export-dialog__table" data-testid="export-tunable-table">
          <thead>
            <tr>
              <th scope="col">Tunable</th>
              <th scope="col">Value</th>
              <th scope="col">Unit</th>
              <th scope="col">Min</th>
              <th scope="col">Max</th>
              <th scope="col">
                <span className="visually-hidden">Remove</span>
              </th>
            </tr>
          </thead>
          <tbody>
            {rows.map((row, index) => {
              const candidate = candidateById.get(row.id);
              const problem = problems[index];
              return (
                <tr key={row.id} data-testid={`export-tunable-row-${row.id}`}>
                  <td>
                    <code>{row.id}</code>
                    {problem ? (
                      <span className="export-dialog__row-problem" role="alert"> {problem}</span>
                    ) : null}
                  </td>
                  <td>{formatValue(candidate?.value ?? null)}</td>
                  <td>{candidate?.unit ?? ""}</td>
                  <td>
                    <input
                      className="open-dialog__input export-dialog__range"
                      data-testid={`export-tunable-min-${row.id}`}
                      aria-label={`Minimum of ${row.id}`}
                      aria-invalid={problem !== null}
                      placeholder="open"
                      value={row.minText}
                      onChange={(event) => update(index, { minText: event.target.value })}
                    />
                  </td>
                  <td>
                    <input
                      className="open-dialog__input export-dialog__range"
                      data-testid={`export-tunable-max-${row.id}`}
                      aria-label={`Maximum of ${row.id}`}
                      aria-invalid={problem !== null}
                      placeholder="open"
                      value={row.maxText}
                      onChange={(event) => update(index, { maxText: event.target.value })}
                    />
                  </td>
                  <td>
                    <button
                      type="button"
                      className="icon-button"
                      data-testid={`export-tunable-remove-${row.id}`}
                      aria-label={`Remove ${row.id}`}
                      title="Fold it again"
                      onClick={() => onRows(rows.filter((_, k) => k !== index))}
                    >
                      ✕
                    </button>
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      ) : null}
      {open > 0 ? (
        <p className="export-dialog__faint" data-testid="export-tunable-open">
          {open} tunable{open === 1 ? " has" : "s have"} an open range: the step is proven stable
          only at the model's value there (W210). With a min and a max the export scans the
          range, and the FMU refuses values outside it.
        </p>
      ) : null}
    </section>
  );
}

/** The report's tunables: what the FMU lets the host set, what it recomputes, the cost. */
function TunablesReport({ report }: { report: ExportReport }) {
  const tunables = report.tunables;
  const fixed = report.parameters.filter((p) => p.variability === "fixed" || p.causality === "calculatedParameter");
  if (tunables === undefined || fixed.length === 0) {
    return null;
  }
  const cost = tunableCostText(tunables.rhsOps, tunables.rhsOpsFolded);
  const recomputed = [
    tunables.calculated ? `${tunables.calculated} calculated parameter${tunables.calculated === 1 ? "" : "s"}` : null,
    tunables.starts ? `${tunables.starts} start value${tunables.starts === 1 ? "" : "s"}` : null,
    tunables.heldValues ? `${tunables.heldValues} held value${tunables.heldValues === 1 ? "" : "s"}` : null,
    tunables.newton ? "the algebraic unknowns (Newton)" : null,
  ].filter((part) => part !== null);
  return (
    <div className="export-dialog__tunables-report" data-testid="export-report-tunables">
      <table className="export-dialog__table">
        <caption>Parameters set before initialization</caption>
        <thead>
          <tr>
            <th scope="col">Name</th>
            <th scope="col">Kind</th>
            <th scope="col">Start</th>
            <th scope="col">Range</th>
            <th scope="col">Unit</th>
          </tr>
        </thead>
        <tbody>
          {fixed.map((p) => (
            <tr key={p.name} data-testid={`export-report-parameter-${p.name}`}>
              <td>
                <code>{p.name}</code>
              </td>
              <td>
                {p.causality === "calculatedParameter"
                  ? `calculated from ${(p.dependsOn ?? []).join(", ")}`
                  : p.id.startsWith("global:")
                    ? "global"
                    : "fixed"}
              </td>
              <td>{p.start === undefined ? "—" : formatValue(p.start)}</td>
              <td>
                {p.causality === "calculatedParameter"
                  ? ""
                  : `${p.min === undefined ? "open" : formatValue(p.min)} … ${p.max === undefined ? "open" : formatValue(p.max)}`}
              </td>
              <td>{p.unit ?? ""}</td>
            </tr>
          ))}
        </tbody>
      </table>
      <ul className="export-dialog__lines">
        {recomputed.length > 0 ? (
          <li data-testid="export-report-recomputed">
            Recomputed once in fmi2ExitInitializationMode: {recomputed.join(", ")}.
          </li>
        ) : null}
        {cost !== null ? <li data-testid="export-report-tunable-cost">{cost}.</li> : null}
      </ul>
    </div>
  );
}

export function ExportDialog() {
  const open = useExportDialogStore((state) => state.open);
  const openScope = useExportDialogStore((state) => state.scope);
  const openCount = useExportDialogStore((state) => state.openCount);
  const closeExport = useExportDialogStore((state) => state.closeExport);
  const jobId = useExportDialogStore((state) => state.jobId);
  const setJobId = useExportDialogStore((state) => state.setJobId);
  const task = useTaskStore((state) =>
    jobId === null ? undefined : state.tasks.find((entry) => entry.id === exportTaskId(jobId)),
  );
  const connectionError = useTaskStore((state) => state.connectionError);
  const setViewing = useTaskStore((state) => state.setViewing);
  const job = task?.exportJob ?? null;
  const doc = useDocumentStore((state) => state.doc);
  const project = useDocumentStore((state) => state.project);
  const modelName = useDocumentStore((state) => state.modelName);
  const dialog = useRef<HTMLDivElement>(null);

  const [scope, setScope] = useState<string | null>(null);
  const [powerInputs, setPowerInputs] = useState<Record<string, PowerChoice>>({});
  const [method, setMethod] = useState<ExportMethod>("auto");
  const [dtText, setDtText] = useState("");
  const [stepText, setStepText] = useState("");
  const [dampingText, setDampingText] = useState("");
  const [jacobian, setJacobian] = useState<ExportJacobian>("auto");
  const [linearSolver, setLinearSolver] = useState<ExportLinearSolver>("auto");
  const [exposeAll, setExposeAll] = useState(false);
  const [tunableRows, setTunableRows] = useState<TunableRow[]>([]);
  const [tunablePick, setTunablePick] = useState("");
  const catalogIndex = useCatalogStore((state) => state.index);
  const [requestError, setRequestError] = useState<string | null>(null);
  const [starting, setStarting] = useState(false);
  const [now, setNow] = useState(() => Date.now());

  const subsystems = useMemo(() => (doc === null ? [] : listSubsystems(doc)), [doc]);
  const running = job !== null && !isFinished(job);
  // An attached job of another model (or project) shows its progress and report only.
  const foreign = job !== null && (job.project !== project || job.model !== modelName);

  // A new open resets the form to the opener's scope and keeps a running job on screen;
  // "Show details" (attached) shows its job, with the job's scope when it is this model's.
  useEffect(() => {
    if (openCount === 0) {
      return;
    }
    const dialogState = useExportDialogStore.getState();
    const current = useDocumentStore.getState().doc;
    const shown = dialogState.jobId === null
      ? undefined
      : useTaskStore.getState().tasks.find((entry) => entry.id === exportTaskId(dialogState.jobId as string));
    const shownJob = shown?.exportJob ?? null;
    let wanted = openScope;
    const documentState = useDocumentStore.getState();
    if (dialogState.attached) {
      wanted = shownJob?.scope ?? null;
    } else if (
      shownJob !== null &&
      (isFinished(shownJob) ||
        shownJob.project !== documentState.project ||
        shownJob.model !== documentState.modelName)
    ) {
      // A fresh form; another model's running job stays in the tasks indicator.
      dialogState.setJobId(null);
    }
    const valid = wanted !== null && current !== null && findSubsystem(current, wanted);
    const next = valid ? wanted : null;
    setScope(next);
    setPowerInputs(current === null ? {} : defaultPowerInputs(current, next));
    setRequestError(null);
  }, [openCount, openScope]);

  useDialogFocus(open, dialog, closeExport);

  // The job the open dialog shows is "being watched": its end is no unseen task.
  useEffect(() => {
    if (!open || jobId === null) {
      return;
    }
    setViewing(exportTaskId(jobId));
    return () => setViewing(null);
  }, [jobId, open, setViewing]);

  // The elapsed seconds tick while the job runs (the task registry polls the job).
  useEffect(() => {
    if (!open || !running) {
      return;
    }
    setNow(Date.now());
    const timer = window.setInterval(() => setNow(Date.now()), TICK_MS);
    return () => window.clearInterval(timer);
  }, [open, running]);

  const preview = useMemo(
    () => (doc === null ? null : previewInterface(doc, scope, powerInputs)),
    [doc, scope, powerInputs],
  );

  // The tunables editor (W-EX1, J-EX8): candidates of the scope, the picked rows.
  const candidates = useMemo(
    () => (doc === null ? [] : listTunableCandidates(doc, scope, catalogIndex)),
    [doc, scope, catalogIndex],
  );
  const candidateById = useMemo(
    () => new Map<string, TunableCandidate>(candidates.map((c) => [c.id, c])),
    [candidates],
  );
  const tunableProblems = tunableRows.map((row) => rowProblem(row, candidateById.get(row.id)));

  const dt = parseOptionalPositive(dtText);
  const step = parseOptionalPositive(stepText);
  const damping = parseOptionalPositive(dampingText);
  const dampingInvalid = damping !== null && (Number.isNaN(damping) || damping >= 1);
  const invalid = Number.isNaN(dt) || Number.isNaN(step) || dampingInvalid ||
    tunableProblems.some((problem) => problem !== null);

  const onScopeChange = useCallback(
    (next: string | null) => {
      setScope(next);
      setPowerInputs(doc === null ? {} : defaultPowerInputs(doc, next));
      // Instance paths change with the scope; a pick of the old scope means nothing there.
      setTunableRows([]);
    },
    [doc],
  );

  const onExport = useCallback(async () => {
    const current = useDocumentStore.getState().doc;
    if (current === null || project === null || modelName === null) {
      return;
    }
    const settings: ExportSettings = { method, dt, step, damping, jacobian, linearSolver };
    if (exposeAll) {
      settings.exposeAll = true;
    }
    if (tunableRows.length > 0) {
      settings.tunables = tunablesRequest(tunableRows);
    }
    const request: ExportRequest = { model: current, settings };
    if (scope !== null) {
      request.scope = scope;
      request.powerInputs = powerInputs;
    }
    setStarting(true);
    setRequestError(null);
    try {
      const id = await startExport(project, modelName, request);
      setNow(Date.now());
      // The job is a background task from here on: closing the dialog does not stop it.
      trackExportJob(await getExport(id));
      setJobId(id);
    } catch (cause) {
      setRequestError(
        cause instanceof ExportApiError ? cause.message : `The export could not start: ${errorText(cause)}`,
      );
    } finally {
      setStarting(false);
    }
  }, [damping, dt, exposeAll, jacobian, linearSolver, method, modelName, powerInputs, project, scope, setJobId, step, tunableRows]);

  const onCancel = useCallback(async () => {
    if (jobId === null) {
      return;
    }
    try {
      await cancelTask(exportTaskId(jobId));
    } catch (cause) {
      setRequestError(errorText(cause));
    }
  }, [jobId]);

  if (!open) {
    return null;
  }
  const elapsed = Math.max(0, Math.round((now - (task?.started ?? now)) / 1000));
  const shownModel = foreign ? job.model : modelName;
  const pollError = running ? connectionError : null;

  /** The Export button (when given), the progress with Cancel, errors and the report. */
  const jobStatus = (startButton: ReactNode) => (
    <>
      <div className="export-dialog__actions">
        {startButton}
        {running ? (
          <>
            <span className="export-dialog__progress" data-testid="export-progress" role="status">
              <span className="export-dialog__spinner" aria-hidden="true" />
              {progressLabel(job.status, job.phase)}… {elapsed} s
            </span>
            <button
              type="button"
              className="button"
              data-testid="export-cancel"
              onClick={() => void onCancel()}
            >
              Cancel
            </button>
          </>
        ) : null}
        {job?.status === "cancelled" ? (
          <span className="export-dialog__faint" data-testid="export-cancelled">
            The export was cancelled.
          </span>
        ) : null}
      </div>
      {running ? (
        <p className="export-dialog__faint" data-testid="export-background-note">
          You can close this dialog: the export goes on in the background, and the tasks
          indicator in the top bar brings it back.
        </p>
      ) : null}

      {requestError !== null || pollError !== null ? (
        <p className="export-dialog__error" role="alert" data-testid="export-error">
          {requestError ?? pollError}
        </p>
      ) : null}

      {job?.status === "refused" ? (
        <section className="export-dialog__section" data-testid="export-refused" role="alert">
          <p className="export-dialog__error">
            The model cannot be exported as it is: {job.error ?? "see the diagnostics"}.
          </p>
          <DiagnosticList diagnostics={job.diagnostics} />
        </section>
      ) : null}
      {job?.status === "failed" ? (
        <section className="export-dialog__section" data-testid="export-failed" role="alert">
          <p className="export-dialog__error">The export failed.</p>
          <pre className="export-dialog__log">{job.error}</pre>
        </section>
      ) : null}
      {job?.status === "done" && job.report ? <ReportView job={job} report={job.report} /> : null}
    </>
  );

  return (
    <div
      className="dialog-backdrop"
      onMouseDown={(event) => {
        if (event.target === event.currentTarget) {
          closeExport();
        }
      }}
    >
      <div
        className="export-dialog"
        role="dialog"
        aria-modal="true"
        aria-labelledby="export-dialog-title"
        data-testid="export-dialog"
        ref={dialog}
        tabIndex={-1}
      >
        <header className="open-dialog__header">
          <h2 className="open-dialog__title" id="export-dialog-title">
            Export FMU{shownModel ? ` · ${shownModel}` : ""}
          </h2>
          <button
            type="button"
            className="icon-button"
            data-testid="export-dialog-close"
            aria-label="Close"
            title="Close (Esc)"
            onClick={closeExport}
          >
            ✕
          </button>
        </header>

        <div className="export-dialog__body">
          {foreign ? (
            <>
              <p className="export-dialog__note" data-testid="export-foreign">
                This export is of {job.scope ? `${job.scope} in ` : ""}
                {job.model} (project {job.project}). Open that model to export it again.
              </p>
              {jobStatus(null)}
            </>
          ) : doc === null || preview === null ? (
            <p className="open-dialog__empty">Open a model to export it.</p>
          ) : (
            <>
              <section className="export-dialog__section" aria-label="Scope">
                <h3 className="export-dialog__heading">Scope</h3>
                <div className="export-dialog__row">
                  <label className="export-dialog__choice">
                    <input
                      type="radio"
                      name="export-scope"
                      data-testid="export-scope-model"
                      checked={scope === null}
                      onChange={() => onScopeChange(null)}
                    />
                    Whole model
                  </label>
                  <label className="export-dialog__choice">
                    <input
                      type="radio"
                      name="export-scope"
                      data-testid="export-scope-subsystem"
                      checked={scope !== null}
                      disabled={subsystems.length === 0}
                      onChange={() => onScopeChange(subsystems[0]?.path ?? null)}
                    />
                    Subsystem
                  </label>
                  <select
                    className="export-dialog__select"
                    aria-label="Subsystem to export"
                    data-testid="export-scope-select"
                    value={scope ?? ""}
                    disabled={subsystems.length === 0}
                    onChange={(event) => onScopeChange(event.target.value || null)}
                  >
                    {scope === null ? <option value="">(choose a subsystem)</option> : null}
                    {subsystems.map((entry) => (
                      <option key={entry.path} value={entry.path}>
                        {entry.path}
                      </option>
                    ))}
                  </select>
                </div>
                <p className="export-dialog__note">
                  {scope === null
                    ? "The Export markers (ExportInput, ExportOutput, ExportParameter) are the interface."
                    : "The subsystem's ports are the interface; everything outside it is left out."}
                </p>
              </section>

              <section className="export-dialog__section" aria-label="Interface" data-testid="export-interface">
                <h3 className="export-dialog__heading">Interface</h3>
                {preview.powerPorts.length > 0 ? (
                  <div className="export-dialog__power" data-testid="export-power-ports">
                    {preview.powerPorts.map((port) => (
                      <label key={port.name} className="export-dialog__field">
                        <span>
                          {port.name} <span className="export-dialog__faint">({port.domain})</span>: the
                          host imposes
                        </span>
                        <select
                          className="export-dialog__select"
                          data-testid={`export-power-${port.name}`}
                          value={port.choice}
                          onChange={(event) =>
                            setPowerInputs((previous) => ({
                              ...previous,
                              [port.name]: event.target.value as PowerChoice,
                            }))
                          }
                        >
                          <option value="effort">effort</option>
                          <option value="flow">flow</option>
                        </select>
                      </label>
                    ))}
                  </div>
                ) : null}
                {isEmptyInterface(preview) ? (
                  <p className="export-dialog__warning" data-testid="export-w209">
                    W209: nothing is published. The FMU would have no inputs or outputs. Place
                    ExportInput blocks where the controller supplies a signal and ExportOutput
                    blocks on the signals to publish, or export a subsystem with ports.
                  </p>
                ) : (
                  <div className="export-dialog__columns">
                    {(
                      [
                        ["Inputs", preview.inputs, "export-inputs"],
                        ["Outputs", preview.outputs, "export-outputs"],
                        ["Parameters", preview.parameters, "export-parameters"],
                      ] as const
                    ).map(([title, entries, testId]) =>
                      entries.length === 0 && title === "Parameters" ? null : (
                        <div key={title}>
                          <h4 className="export-dialog__subheading">
                            {title} ({entries.length})
                          </h4>
                          <ul className="export-dialog__vars" data-testid={testId}>
                            {entries.map((entry) => (
                              <li key={entry.name}>
                                <code>{entry.name}</code>
                                <span className="export-dialog__faint"> {entry.detail}</span>
                              </li>
                            ))}
                          </ul>
                        </div>
                      ),
                    )}
                  </div>
                )}
                {preview.problems.map((problem) => (
                  <p key={problem} className="export-dialog__warning">
                    {problem}
                  </p>
                ))}
              </section>

              <TunablesSection
                candidates={candidates}
                candidateById={candidateById}
                rows={tunableRows}
                problems={tunableProblems}
                pick={tunablePick}
                onPick={setTunablePick}
                onRows={setTunableRows}
              />

              <section className="export-dialog__section" aria-label="Settings">
                <h3 className="export-dialog__heading">Settings</h3>
                <div className="export-dialog__row">
                  <label className="export-dialog__field">
                    <span>Method</span>
                    <select
                      className="export-dialog__select"
                      data-testid="export-method"
                      value={method}
                      onChange={(event) => setMethod(event.target.value as ExportMethod)}
                    >
                      {METHODS.map((m) => (
                        <option key={m} value={m}>
                          {METHOD_LABELS[m]}
                        </option>
                      ))}
                    </select>
                  </label>
                  <label className="export-dialog__field">
                    <span>Internal step dt [s]</span>
                    <input
                      className="open-dialog__input export-dialog__number"
                      data-testid="export-dt"
                      placeholder="Auto"
                      aria-invalid={Number.isNaN(dt)}
                      value={dtText}
                      onChange={(event) => setDtText(event.target.value)}
                    />
                  </label>
                </div>
                <details className="export-dialog__advanced" data-testid="export-advanced">
                  <summary>Advanced</summary>
                  <div className="export-dialog__grid">
                    <label className="export-dialog__field">
                      <span>Communication step [s]</span>
                      <input
                        className="open-dialog__input export-dialog__number"
                        data-testid="export-step"
                        placeholder={`Auto (${formatStep(defaultStep(doc.settings.t_end))})`}
                        aria-invalid={Number.isNaN(step)}
                        value={stepText}
                        onChange={(event) => setStepText(event.target.value)}
                      />
                    </label>
                    <label className="export-dialog__field">
                      <span>Damping (Rosenbrock)</span>
                      <input
                        className="open-dialog__input export-dialog__number"
                        data-testid="export-damping"
                        placeholder="Auto (0.05, else 0.5)"
                        aria-invalid={dampingInvalid}
                        value={dampingText}
                        onChange={(event) => setDampingText(event.target.value)}
                      />
                    </label>
                    <label className="export-dialog__field">
                      <span>Jacobian</span>
                      <select
                        className="export-dialog__select"
                        data-testid="export-jacobian"
                        value={jacobian}
                        onChange={(event) => setJacobian(event.target.value as ExportJacobian)}
                      >
                        <option value="auto">Auto</option>
                        <option value="symbolic">Symbolic</option>
                        <option value="fd">Finite differences</option>
                      </select>
                    </label>
                    <label className="export-dialog__field">
                      <span>Linear solver</span>
                      <select
                        className="export-dialog__select"
                        data-testid="export-linear-solver"
                        value={linearSolver}
                        onChange={(event) => setLinearSolver(event.target.value as ExportLinearSolver)}
                      >
                        <option value="auto">Auto</option>
                        <option value="dense">Dense LU</option>
                        <option value="sparse">Sparse LU</option>
                      </select>
                    </label>
                    <label className="export-dialog__choice">
                      <input
                        type="checkbox"
                        data-testid="export-expose-all"
                        checked={exposeAll}
                        onChange={(event) => setExposeAll(event.target.checked)}
                      />
                      Expose all signals (debug, read-only)
                    </label>
                  </div>
                </details>
                {invalid ? (
                  <p className="export-dialog__warning" role="alert">
                    Steps must be positive numbers in seconds, the damping between 0 and 1, and
                    each tunable range must contain the model's value. Leave a field empty for
                    Auto.
                  </p>
                ) : null}
              </section>

              {jobStatus(
                <button
                  type="button"
                  className="button button--primary"
                  data-testid="export-start"
                  disabled={running || starting || invalid || preview.missingScope}
                  onClick={() => void onExport()}
                >
                  {job !== null && isFinished(job) ? "Export again" : "Export"}
                </button>,
              )}
            </>
          )}
        </div>
      </div>
    </div>
  );
}
