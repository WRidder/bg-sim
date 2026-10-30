/**
 * The data-file section of a CsvSource node (F5.1): a picker over the data files of the
 * project with an upload button, the interpolation settings, a preview of the header and
 * the first rows, and the output list. The settings are the node constants; the compiler
 * reads them (src/library/csvdata.jl). Choosing a file or columns also writes the structural
 * constant `N`, so the output vector has the right size for connections and checks.
 */

import { useCallback, useEffect, useRef, useState } from "react";

import {
  fetchCsvPreview,
  listDataFiles,
  uploadDataFile,
  type CsvPreview,
  type DataFile,
} from "../api/data";
import type { ModelNode } from "../contracts/model";
import { useDocumentStore } from "../state/documentStore";
import { SelectField, TextField } from "./fields";
import {
  CSV_EXTRAPOLATION,
  CSV_METHODS,
  csvOutputs,
  csvSettings,
  outputLabel,
} from "./csvSource";

function numberOf(value: unknown, fallback: number): number {
  return typeof value === "number" ? value : fallback;
}

function realIssue(text: string): string | null {
  return text.length === 0 || Number.isFinite(Number(text)) ? null : "Enter a number.";
}

export function CsvSourceSection({ node, project }: { node: ModelNode; project: string | null }) {
  const settings = csvSettings(node.constants);
  const [files, setFiles] = useState<DataFile[]>([]);
  const [preview, setPreview] = useState<CsvPreview | null>(null);
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
      setFiles(await listDataFiles(project));
    } catch (error) {
      setMessage(error instanceof Error ? error.message : String(error));
    }
  }, [project]);

  useEffect(() => {
    void refreshFiles();
  }, [refreshFiles]);

  useEffect(() => {
    if (project === null || settings.file.length === 0) {
      setPreview(null);
      return undefined;
    }
    const controller = new AbortController();
    const name = settings.file.split("/").pop() ?? settings.file;
    fetchCsvPreview(project, name, 8, controller.signal)
      .then((result) => {
        setPreview(result);
        setMessage(null);
      })
      .catch((error: unknown) => {
        if (controller.signal.aborted) return;
        setPreview(null);
        setMessage(error instanceof Error ? error.message : String(error));
      });
    return () => controller.abort();
  }, [project, settings.file]);

  const columnsKey = settings.columns.join(",");
  const result = preview === null ? null : csvOutputs(preview.columns, settings);
  const outputCount = result === null ? 0 : result.outputs.length;

  // keep the structural size N equal to the number of selected columns
  useEffect(() => {
    if (outputCount > 0 && numberOf(node.constants?.N, 1) !== outputCount) {
      setConstant("N", outputCount);
    }
  }, [outputCount, columnsKey, node.constants?.N, setConstant]);

  const onUpload = async (file: File | undefined): Promise<void> => {
    if (file === undefined || project === null) return;
    setBusy(true);
    try {
      const stored = await uploadDataFile(project, file);
      await refreshFiles();
      setConstant("file", stored.path);
      setConstant("columns", null);
      setConstant("time_column", null);
      setMessage(null);
    } catch (error) {
      setMessage(error instanceof Error ? error.message : String(error));
    } finally {
      setBusy(false);
      if (upload.current !== null) upload.current.value = "";
    }
  };

  const fileOptions = [
    { value: "", label: project === null ? "Open a project to pick a file" : "Choose a data file" },
    ...files.map((entry) => ({ value: `data/${entry.file}`, label: entry.file })),
  ];
  if (settings.file.length > 0 && !fileOptions.some((option) => option.value === settings.file)) {
    fileOptions.push({ value: settings.file, label: `${settings.file} (not found)` });
  }
  const method = numberOf(node.constants?.method, 2);
  const extrapolation = numberOf(node.constants?.extrapolation, 0);

  return (
    <section
      className="inspector-section"
      aria-labelledby="inspector-csv-title"
      data-testid="inspector-csv"
    >
      <h4 className="inspector-section__title" id="inspector-csv-title">
        Data file
      </h4>
      <SelectField
        id="inspector-csv-file"
        testId="inspector-csv-file"
        label="file"
        value={settings.file}
        options={fileOptions}
        onChange={(next) => {
          setConstant("file", next.length === 0 ? null : next);
          setConstant("columns", null);
          setConstant("time_column", null);
          return null;
        }}
        description="A CSV file in the data folder of the project: a header row, then numeric rows."
        invalidMessage="The stored file is not in the data folder of the project; pick another or upload it."
      />
      <div className="inspector-field">
        <input
          ref={upload}
          type="file"
          accept=".csv,text/csv"
          hidden
          data-testid="inspector-csv-upload-input"
          onChange={(event) => void onUpload(event.target.files?.[0])}
        />
        <button
          type="button"
          className="inspector-button"
          data-testid="inspector-csv-upload"
          disabled={project === null || busy}
          onClick={() => upload.current?.click()}
        >
          {busy ? "Uploading…" : "Upload CSV…"}
        </button>
      </div>
      {message !== null ? (
        <p className="inspector-note" role="alert" data-testid="inspector-csv-message">
          {message}
        </p>
      ) : null}
      <SelectField
        id="inspector-csv-method"
        testId="inspector-csv-method"
        label="method"
        value={String(method)}
        options={CSV_METHODS.map((name, position) => ({ value: String(position), label: name }))}
        onChange={(next) => {
          setConstant("method", Number(next));
          return null;
        }}
        description="hold and linear stop the solver at every data row; cubic is a C2 spline with smooth derivatives."
        invalidMessage="Choose hold, linear or cubic."
      />
      <SelectField
        id="inspector-csv-extrapolation"
        testId="inspector-csv-extrapolation"
        label="extrapolation"
        value={String(extrapolation)}
        options={CSV_EXTRAPOLATION.map((name, position) => ({
          value: String(position),
          label: name === "hold" ? "hold the end values" : "error past the data",
        }))}
        onChange={(next) => {
          setConstant("extrapolation", Number(next));
          return null;
        }}
        description="What happens before the first and after the last time stamp."
        invalidMessage="Choose hold or error."
      />
      <TextField
        id="inspector-csv-time-column"
        testId="inspector-csv-time-column"
        label="time_column"
        value={settings.timeColumn}
        placeholder={preview?.columns[0]?.name ?? "first column"}
        issue={() => null}
        onCommit={(text) => {
          setConstant("time_column", text.length === 0 ? null : text);
          return null;
        }}
        description="Header name of the time column; empty means the first column."
      />
      <TextField
        id="inspector-csv-columns"
        testId="inspector-csv-columns"
        label="columns"
        value={settings.columns.join(", ")}
        placeholder="all other columns"
        issue={() => null}
        onCommit={(text) => {
          setConstant("columns", text.length === 0 ? null : text);
          return null;
        }}
        description="Comma separated header names of the outputs, in output order; empty means all other columns."
      />
      <TextField
        id="inspector-csv-time-offset"
        testId="inspector-csv-time-offset"
        label="time_offset"
        value={String(numberOf(node.constants?.time_offset, 0))}
        issue={realIssue}
        onCommit={(text) => {
          setConstant("time_offset", text.length === 0 ? null : Number(text));
          return null;
        }}
        unit="s"
        description="Seconds added to the time column of the file."
      />
      <TextField
        id="inspector-csv-scale"
        testId="inspector-csv-scale"
        label="scale"
        value={String(numberOf(node.constants?.scale, 1))}
        issue={realIssue}
        onCommit={(text) => {
          setConstant("scale", text.length === 0 ? null : Number(text));
          return null;
        }}
        description="Factor applied to every value."
      />
      {preview !== null && result !== null ? (
        <div className="inspector-csv-preview" data-testid="inspector-csv-preview">
          <p className="inspector-note" data-testid="inspector-csv-summary">
            {preview.rows} rows × {preview.columns.length} columns, time column{" "}
            <code>{result.timeColumn ?? "?"}</code>
          </p>
          <div className="inspector-csv-scroll">
            <table>
              <thead>
                <tr>
                  {preview.columns.map((column) => (
                    <th key={column.name}>
                      {column.name}
                      {column.unit.length > 0 ? ` [${column.unit}]` : ""}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {preview.head.map((row, rowIndex) => (
                  <tr key={rowIndex}>
                    {row.map((cell, cellIndex) => (
                      <td key={cellIndex}>{String(cell)}</td>
                    ))}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          {result.missing.length > 0 ? (
            <p className="inspector-note" role="alert" data-testid="inspector-csv-missing">
              The file has no column {result.missing.map((name) => `"${name}"`).join(", ")}; check
              the spelling against the header above.
            </p>
          ) : null}
          <ul className="inspector-csv-outputs" data-testid="inspector-csv-outputs">
            {result.outputs.map((output) => (
              <li key={output.index}>
                <code>{outputLabel(output)}</code>
              </li>
            ))}
          </ul>
        </div>
      ) : null}
    </section>
  );
}
