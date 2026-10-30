/**
 * F5.1: the CsvSource inspector section. The pure column selection rules, then the component
 * against a stubbed backend: the file picker lists the data folder, picking a file shows the
 * preview and the detected column list and writes the structural size N, the upload button
 * posts the file and selects it.
 */

import { act, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { fetchCsvPreview, uploadDataFile } from "../src/api/data";
import type { Model, ModelNode } from "../src/contracts/model";
import { CsvSourceSection } from "../src/inspector/CsvSourceSection";
import {
  csvOutputs,
  csvSettings,
  isCsvSourceRef,
  outputLabel,
} from "../src/inspector/csvSource";
import { resetDocumentStore, useDocumentStore } from "../src/state/documentStore";
import { createEmptyModel } from "../src/state/modelFactory";

const HEADER = [
  { name: "t", unit: "s" },
  { name: "q1", unit: "rad" },
  { name: "qd1", unit: "rad/s" },
  { name: "tau", unit: "" },
];

describe("csvOutputs", () => {
  it("takes every column but the first when nothing is selected", () => {
    const result = csvOutputs(HEADER, csvSettings({ file: "data/a.csv" }));
    expect(result.outputs.map((o) => o.name)).toEqual(["q1", "qd1", "tau"]);
    expect(result.timeColumn).toBe("t");
    expect(result.missing).toEqual([]);
  });

  it("keeps the order of the columns list and reports unknown names", () => {
    const result = csvOutputs(
      HEADER,
      csvSettings({ file: "data/a.csv", columns: "tau, q1, nope" }),
    );
    expect(result.outputs.map((o) => [o.index, o.name])).toEqual([
      [1, "tau"],
      [2, "q1"],
    ]);
    expect(result.missing).toEqual(["nope"]);
  });

  it("uses another time column and drops it from the outputs", () => {
    const result = csvOutputs(HEADER, csvSettings({ time_column: "tau" }));
    expect(result.timeColumn).toBe("tau");
    expect(result.outputs.map((o) => o.name)).toEqual(["t", "q1", "qd1"]);
    expect(csvOutputs(HEADER, csvSettings({ time_column: "zz" })).missing).toEqual(["zz"]);
  });

  it("labels outputs with their unit and recognises the block refs", () => {
    const [first] = csvOutputs(HEADER, csvSettings({})).outputs;
    expect(outputLabel(first)).toBe("y[1] = q1 [rad]");
    expect(isCsvSourceRef("stdlib:sources/CsvSource")).toBe(true);
    expect(isCsvSourceRef("stdlib:sources/CsvSourceSampled")).toBe(true);
    expect(isCsvSourceRef("stdlib:sources/Step")).toBe(false);
    expect(isCsvSourceRef(null)).toBe(false);
  });
});

function csvNode(constants: ModelNode["constants"] = {}): ModelNode {
  return {
    id: "n1",
    name: "Csv",
    block: { ref: "stdlib:sources/CsvSource" },
    position: { x: 0, y: 0 },
    constants,
  };
}

function openWith(node: ModelNode): void {
  const doc: Model = createEmptyModel("CsvTest");
  doc.diagram.nodes = [node];
  useDocumentStore.getState().openDocument("demo", "CsvTest", doc);
}

function stored(): ModelNode {
  const found = useDocumentStore.getState().doc?.diagram.nodes[0];
  if (found === undefined) throw new Error("no node");
  return found;
}

function respond(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "content-type": "application/json" },
  });
}

const PREVIEW = {
  project: "demo",
  file: "traj.csv",
  path: "data/traj.csv",
  bytes: 100,
  rows: 1001,
  columns: HEADER,
  head: [
    [0, 0, 0, 0.5],
    [0.001, 0.1, 0.2, 0.6],
  ],
  delimiter: ",",
};

describe("CsvSourceSection", () => {
  let fetchMock: ReturnType<typeof vi.fn>;

  beforeEach(() => {
    resetDocumentStore();
    fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input);
      if (init?.method === "POST") return respond({ file: "up.csv", path: "data/up.csv" }, 201);
      if (url.endsWith("/data")) {
        return respond([
          { file: "traj.csv", bytes: 100 },
          { file: "other.csv", bytes: 10 },
        ]);
      }
      if (url.includes("/preview")) return respond(PREVIEW);
      return respond({ detail: "unexpected" }, 404);
    });
    vi.stubGlobal("fetch", fetchMock);
  });

  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("lists the data files, previews the chosen file and writes N", async () => {
    openWith(csvNode());
    render(<CsvSourceSection node={stored()} project="demo" />);
    const picker = (await screen.findByTestId("inspector-csv-file")) as HTMLSelectElement;
    await waitFor(() => expect(picker.options.length).toBe(3));
    expect([...picker.options].map((o) => o.textContent)).toEqual([
      "Choose a data file",
      "traj.csv",
      "other.csv",
    ]);
    await act(async () => {
      fireEvent.change(picker, { target: { value: "data/traj.csv" } });
    });
    expect(stored().constants?.file).toBe("data/traj.csv");
  });

  it("shows the preview and the detected columns and keeps N in step", async () => {
    openWith(csvNode({ file: "data/traj.csv", columns: "qd1, tau" }));
    const view = render(<CsvSourceSection node={stored()} project="demo" />);
    expect((await screen.findByTestId("inspector-csv-summary")).textContent).toContain("1001 rows × 4 columns");
    const outputs = screen.getByTestId("inspector-csv-outputs");
    expect(outputs.textContent).toContain("y[1] = qd1 [rad/s]");
    expect(outputs.textContent).toContain("y[2] = tau");
    await waitFor(() => expect(stored().constants?.N).toBe(2));
    // the table body shows the first rows
    expect((screen.getByTestId("inspector-csv-preview")).textContent).toContain("0.001");
    view.unmount();
    expect(fetchMock).toHaveBeenCalled();
  });

  it("explains an unknown column", async () => {
    openWith(csvNode({ file: "data/traj.csv", columns: "q1, nope" }));
    render(<CsvSourceSection node={stored()} project="demo" />);
    expect((await screen.findByTestId("inspector-csv-missing")).textContent).toContain('"nope"');
  });

  it("uploads a file and selects it", async () => {
    openWith(csvNode());
    render(<CsvSourceSection node={stored()} project="demo" />);
    const input = (await screen.findByTestId("inspector-csv-upload-input")) as HTMLInputElement;
    const file = new File(["t,x\n0,1\n"], "up.csv", { type: "text/csv" });
    await act(async () => {
      fireEvent.change(input, { target: { files: [file] } });
    });
    await waitFor(() => expect(stored().constants?.file).toBe("data/up.csv"));
    const post = fetchMock.mock.calls.find(([, init]) => (init as RequestInit)?.method === "POST");
    expect(post).toBeDefined();
    expect(String(post?.[0])).toContain("/api/projects/demo/data");
    expect((post?.[1] as RequestInit).body).toBeInstanceOf(FormData);
  });

  it("reports a refused file with the backend message", async () => {
    fetchMock.mockImplementation(async (input: RequestInfo | URL) => {
      const url = String(input);
      if (url.endsWith("/data")) return respond([]);
      return respond({ detail: "data row 2 has 1 cells but the header has 3 columns" }, 422);
    });
    openWith(csvNode({ file: "data/bad.csv" }));
    render(<CsvSourceSection node={stored()} project="demo" />);
    expect((await screen.findByTestId("inspector-csv-message")).textContent).toContain("data row 2 has 1 cells");
  });
});

describe("data api", () => {
  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("turns a backend refusal into an error with the message", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async () => respond({ detail: "the data file is 5 bytes; the limit is 1" }, 413)),
    );
    await expect(uploadDataFile("demo", new File(["x"], "a.csv"))).rejects.toThrow(/limit is 1/);
    await expect(fetchCsvPreview("demo", "a.csv")).rejects.toThrow(/cannot read a.csv/);
  });
});
