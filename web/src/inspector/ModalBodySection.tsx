/**
 * The reduced-model section of a FEM flexible body (`stdlib:spatial/ModalBody3D`): a picker over
 * the project's `data/*.modal.json` files with an upload button, the geometric-stiffening switch,
 * and a read-only summary of the chosen file (mass, modes, interfaces and ports, the first modal
 * frequencies, the validation numbers, the GLB of the mode shapes). The settings are the node
 * constants `file` and `stiffening`; the compiler reads the file (src/library/modaldata.jl) and
 * sets every other constant of the block from it.
 */

import { useCallback, useEffect, useRef, useState } from "react";

import { fetchDataText, listDataFiles, uploadDataFile, type DataFile } from "../api/data";
import type { ModelNode } from "../contracts/model";
import { useDocumentStore } from "../state/documentStore";
import { SelectField } from "./fields";
import {
  formatHz,
  formatNumber,
  formatPercent,
  MODAL_CLI,
  modalSettings,
  parseModalSummary,
  type ModalParse,
} from "./modalBody";

/** How many modal frequencies the summary lists before it abbreviates. */
const SHOWN_FREQUENCIES = 6;

function errorText(error: unknown): string {
  return error instanceof Error ? error.message : String(error);
}

export function ModalBodySection({ node, project }: { node: ModelNode; project: string | null }) {
  const settings = modalSettings(node.constants);
  const [files, setFiles] = useState<DataFile[]>([]);
  const [parsed, setParsed] = useState<ModalParse | null>(null);
  const [message, setMessage] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const upload = useRef<HTMLInputElement>(null);

  const setConstant = useCallback(
    (name: string, value: string | number | null) => {
      useDocumentStore.getState().setNodeConstant(node.id, name, value);
    },
    [node.id],
  );

  const refreshFiles = useCallback(async () => {
    if (project === null) return;
    try {
      setFiles(await listDataFiles(project, undefined, "modal"));
    } catch (error) {
      setMessage(errorText(error));
    }
  }, [project]);

  useEffect(() => {
    void refreshFiles();
  }, [refreshFiles]);

  useEffect(() => {
    if (project === null || settings.file.length === 0) {
      setParsed(null);
      return undefined;
    }
    const controller = new AbortController();
    const name = settings.file.split("/").pop() ?? settings.file;
    fetchDataText(project, name, controller.signal)
      .then((text) => {
        if (controller.signal.aborted) return;
        setParsed(
          text === null
            ? {
                ok: false,
                error: `The project has no file ${settings.file}; pick another or upload it.`,
              }
            : parseModalSummary(text),
        );
        setMessage(null);
      })
      .catch((error: unknown) => {
        if (controller.signal.aborted) return;
        setParsed({ ok: false, error: errorText(error) });
      });
    return () => controller.abort();
  }, [project, settings.file]);

  const onUpload = async (file: File | undefined): Promise<void> => {
    if (file === undefined || project === null) return;
    setBusy(true);
    try {
      const stored = await uploadDataFile(project, file);
      await refreshFiles();
      setConstant("file", stored.path);
      setMessage(null);
    } catch (error) {
      setMessage(errorText(error));
    } finally {
      setBusy(false);
      if (upload.current !== null) upload.current.value = "";
    }
  };

  const fileOptions = [
    {
      value: "",
      label: project === null ? "Open a project to pick a file" : "Choose a reduced-model file",
    },
    ...files.map((entry) => ({ value: `data/${entry.file}`, label: entry.file })),
  ];
  if (settings.file.length > 0 && !fileOptions.some((option) => option.value === settings.file)) {
    fileOptions.push({ value: settings.file, label: `${settings.file} (not found)` });
  }
  const summary = parsed?.ok === true ? parsed.summary : null;

  return (
    <section
      className="inspector-section"
      aria-labelledby="inspector-modal-title"
      data-testid="inspector-modal"
    >
      <h4 className="inspector-section__title" id="inspector-modal-title">
        Reduced model
      </h4>
      <SelectField
        id="inspector-modal-file"
        testId="inspector-modal-file"
        label="file"
        value={settings.file}
        options={fileOptions}
        onChange={(next) => {
          setConstant("file", next.length === 0 ? null : next);
          return null;
        }}
        description="A reduced-model file (.modal.json) in the data folder of the project. The compiler sets the block's mass, modes and matrices from it."
        invalidMessage="The stored file is not in the data folder of the project; pick another or upload it."
      />
      <div className="inspector-field">
        <input
          ref={upload}
          type="file"
          accept=".json,application/json"
          hidden
          data-testid="inspector-modal-upload-input"
          onChange={(event) => void onUpload(event.target.files?.[0])}
        />
        <button
          type="button"
          className="inspector-button"
          data-testid="inspector-modal-upload"
          disabled={project === null || busy}
          onClick={() => upload.current?.click()}
        >
          {busy ? "Uploading…" : "Upload .modal.json…"}
        </button>
      </div>
      {message !== null ? (
        <p className="inspector-note" role="alert" data-testid="inspector-modal-message">
          {message}
        </p>
      ) : null}
      <div className="inspector-field">
        <label className="inspector-modal-check">
          <input
            type="checkbox"
            data-testid="inspector-modal-stiffening"
            checked={settings.stiffening}
            onChange={(event) => setConstant("stiffening", event.target.checked ? 1 : 0)}
          />
          Geometric stiffening
        </label>
        <p className="inspector-field__description">
          Adds the stiffening by centrifugal and inertia loads and by interface forces (when the
          file has the terms). Off saves equations.
        </p>
      </div>
      {parsed !== null && !parsed.ok ? (
        <p className="inspector-note" role="alert" data-testid="inspector-modal-error">
          {parsed.error}
        </p>
      ) : null}
      {summary !== null ? (
        <dl className="inspector-modal-summary" data-testid="inspector-modal-summary">
          {summary.name !== null ? (
            <>
              <dt>Part</dt>
              <dd data-testid="inspector-modal-name">{summary.name}</dd>
            </>
          ) : null}
          {summary.mass !== null ? (
            <>
              <dt>Mass</dt>
              <dd data-testid="inspector-modal-mass">{formatNumber(summary.mass)} kg</dd>
            </>
          ) : null}
          <dt>Modes</dt>
          <dd data-testid="inspector-modal-modes">
            nm = {summary.nm}
            {summary.fixedInterfaceModes !== null
              ? ` (${String(summary.fixedInterfaceModes)} fixed-interface, ${String(Math.max(summary.nm - summary.fixedInterfaceModes, 0))} constraint modes)`
              : ""}
          </dd>
          <dt>Interfaces</dt>
          <dd data-testid="inspector-modal-interfaces">
            {summary.interfaces.map((entry, position) => (
              <span key={position} className="inspector-modal-line">
                port {entry.port}: {entry.name}
                {entry.position !== null
                  ? ` at (${entry.position.map(formatNumber).join(", ")}) m`
                  : ""}
                {position === 0 ? " (reference frame)" : ""}
              </span>
            ))}
          </dd>
          {summary.frequencies.length > 0 ? (
            <>
              <dt>Frequencies (A clamped)</dt>
              <dd data-testid="inspector-modal-frequencies">
                {summary.frequencies.slice(0, SHOWN_FREQUENCIES).map(formatHz).join(", ")}
                {summary.frequencies.length > SHOWN_FREQUENCIES ? ", …" : ""} Hz
              </dd>
            </>
          ) : null}
          {summary.validation !== null ? (
            <>
              <dt>Validation</dt>
              <dd data-testid="inspector-modal-validation">
                {summary.validation.bandHz !== null
                  ? `band up to ${formatHz(summary.validation.bandHz)} Hz; `
                  : ""}
                largest error in band: clamped{" "}
                {summary.validation.clampedMaxRelError !== null
                  ? formatPercent(summary.validation.clampedMaxRelError)
                  : "—"}
                , free{" "}
                {summary.validation.freeMaxRelError !== null
                  ? formatPercent(summary.validation.freeMaxRelError)
                  : "—"}
              </dd>
            </>
          ) : null}
          <dt>Stiffening data</dt>
          <dd data-testid="inspector-modal-stiffening-data">
            {summary.hasStiffening
              ? "in the file"
              : "not in the file (the switch has no effect)"}
          </dd>
          <dt>Stress</dt>
          <dd data-testid="inspector-modal-stress">
            {summary.stress !== null ? (
              <>
                {summary.stress.points} points
                {summary.stress.hotspots.length > 0 ? (
                  <>
                    ; hotspots{" "}
                    {summary.stress.hotspots.map((name, index) => (
                      <span key={`${name}-${String(index)}`}>
                        {index > 0 ? ", " : ""}
                        <code>
                          sigma_vm[{index + 1}]
                        </code>{" "}
                        {name}
                      </span>
                    ))}
                  </>
                ) : null}
                ; peak estimate <code>sigma_max</code>
              </>
            ) : (
              "none in the file (sigma_vm and sigma_max read 0)"
            )}
          </dd>
          <dt>Rail</dt>
          <dd data-testid="inspector-modal-rail">
            {summary.rail !== null ? (
              <>
                {summary.rail.name}
                {summary.rail.length !== null ? `, ${formatNumber(summary.rail.length)} m` : ""}: ports{" "}
                <code>E</code> (carriage frame) and <code>S</code> (slide)
              </>
            ) : (
              "none (ports E and S stay open)"
            )}
          </dd>
          <dt>Mode-shape mesh</dt>
          <dd data-testid="inspector-modal-glb">
            {summary.glb !== null ? (
              <>
                <code>{summary.glb}</code>: put it in the project&apos;s <code>meshes/</code> folder
                and show it in the 3D viewer with a mode-shapes binding to{" "}
                <code>
                  {node.name}/eta[1..{summary.nm}]
                </code>
                .
              </>
            ) : (
              "none in the file"
            )}
          </dd>
        </dl>
      ) : null}
      {summary !== null && summary.warnings.length > 0 ? (
        <ul className="inspector-modal-warnings" role="alert" data-testid="inspector-modal-warnings">
          {summary.warnings.map((warning) => (
            <li key={warning}>{warning}</li>
          ))}
        </ul>
      ) : null}
      <p className="inspector-note" data-testid="inspector-modal-hint">
        Write the file from a part spec with <code>{MODAL_CLI}</code>, then upload it here (or
        copy it into the project&apos;s <code>data/</code> folder) and the GLB next to it into{" "}
        <code>meshes/</code>.
      </p>
    </section>
  );
}
