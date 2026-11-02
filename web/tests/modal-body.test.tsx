/**
 * The FEM flexible body (`stdlib:spatial/ModalBody3D`) in the editor: the summary parsed from a
 * reduced-model file, the inspector section against a stubbed data API (file picker, upload,
 * stiffening switch, summary, error messages), the generic constants editor hiding the
 * file-derived constants, and the reduced-model file as a copy/paste dependency.
 */

import { act, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import catalogJson from "../../contracts/fixtures/catalog/valid/catalog.min.json";
import { dataFileKind, listDataFiles } from "../src/api/data";
import { collectDependencies } from "../src/clipboard/dependencies";
import { buildEnvelope } from "../src/clipboard/envelope";
import { analyse, type PasteIo } from "../src/clipboard/pasteFlow";
import { freeDataName, resolve } from "../src/clipboard/resolve";
import { validateEnvelope } from "../src/clipboard/validate";
import type { Catalog, CatalogBlock } from "../src/contracts/catalog";
import type { Model, ModelNode } from "../src/contracts/model";
import { resetDiagnosticsStore } from "../src/diagnostics/store";
import { Inspector } from "../src/inspector/Inspector";
import { ModalBodySection } from "../src/inspector/ModalBodySection";
import {
  editableConstants,
  formatHz,
  formatPercent,
  isModalBodyRef,
  MODAL_BODY_REF,
  MODAL_FILE_CONSTANTS,
  modalSettings,
  parseModalSummary,
} from "../src/inspector/modalBody";
import { resetCatalogStore, useCatalogStore } from "../src/library/catalogStore";
import { resetDocumentStore, useDocumentStore } from "../src/state/documentStore";
import { createEmptyModel } from "../src/state/modelFactory";

/** A reduced-model file (format bgsim.modal-body 1) with the keys the summary reads. */
function modalDocument(patch: Record<string, unknown> = {}): Record<string, unknown> {
  return {
    format: "bgsim.modal-body",
    version: 1,
    name: "lbar",
    nm: 8,
    fixed_interface_modes: 2,
    mass: 0.023328,
    frequency_hz: [433.036, 738.185, 1634.16, 1784.8, 5387.62, 7876.11, 11324.2, 15054.2],
    interfaces: [
      { name: "root", position: [0, 0, 0], quaternion: [1, 0, 0, 0], nodes: 23 },
      { name: "tip", position: [0.077, 0, -0.043], quaternion: [1, 0, 0, 0], nodes: 23 },
      { name: "mid", position: [0.04, 0, 0.003], quaternion: [1, 0, 0, 0], nodes: 13 },
    ],
    stiffening: { translation: [], inertia: [], rotation: [], interface_force: [] },
    validation: {
      frequencies: {
        band_hz: 16070.18,
        clamped: { max_rel_error_in_band: 0.0309 },
        free: { max_rel_error_in_band: 0.0873 },
      },
    },
    visual: { glb: "lbar.glb", vertices: 179, triangles: 202 },
    ...patch,
  };
}

const MODAL_TEXT = JSON.stringify(modalDocument());

describe("the reduced-model summary", () => {
  it("reads mass, modes, interfaces, frequencies, validation, stiffening and the GLB", () => {
    const parsed = parseModalSummary(MODAL_TEXT);
    expect(parsed.ok).toBe(true);
    if (!parsed.ok) return;
    const summary = parsed.summary;
    expect(summary.name).toBe("lbar");
    expect(summary.mass).toBeCloseTo(0.023328);
    expect([summary.nm, summary.fixedInterfaceModes]).toEqual([8, 2]);
    expect(summary.interfaces.map((entry) => [entry.port, entry.name, entry.nodes])).toEqual([
      ["A", "root", 23],
      ["B", "tip", 23],
      ["C", "mid", 13],
    ]);
    expect(summary.frequencies).toHaveLength(8);
    expect(summary.validation).toEqual({
      bandHz: 16070.18,
      clampedMaxRelError: 0.0309,
      freeMaxRelError: 0.0873,
    });
    expect(summary.hasStiffening).toBe(true);
    expect(summary.glb).toBe("lbar.glb");
    expect(summary.warnings).toEqual([]);
  });

  it("says why a file cannot be read", () => {
    const broken = parseModalSummary("{not json");
    expect(broken.ok ? "" : broken.error).toMatch(/not valid JSON.*bgsim-fem\.jl/);
    const other = parseModalSummary('{"format": "bgsim.model"}');
    expect(other.ok ? "" : other.error).toMatch(/not a reduced-model file/);
    const newer = parseModalSummary(JSON.stringify(modalDocument({ version: 2 })));
    expect(newer.ok ? "" : newer.error).toMatch(/version 2/);
    const noModes = parseModalSummary(JSON.stringify(modalDocument({ nm: 0 })));
    expect(noModes.ok).toBe(false);
    const noInterfaces = parseModalSummary(JSON.stringify(modalDocument({ interfaces: [] })));
    expect(noInterfaces.ok).toBe(false);
  });

  it("warns about more modes than the simulator takes and reads optional keys as absent", () => {
    const big = parseModalSummary(
      JSON.stringify(modalDocument({ nm: 60, stiffening: null, validation: undefined, visual: {} })),
    );
    expect(big.ok).toBe(true);
    if (!big.ok) return;
    expect(big.summary.warnings[0]).toMatch(/at most 48/);
    expect(big.summary.hasStiffening).toBe(false);
    expect(big.summary.validation).toBeNull();
    expect(big.summary.glb).toBeNull();
    expect(big.summary.stress).toBeNull();
    expect(big.summary.rail).toBeNull();
  });

  it("reads the stress points and the rail", () => {
    const parsed = parseModalSummary(
      JSON.stringify(
        modalDocument({
          stress: {
            hotspots: 1,
            points: [
              { name: "root top", kind: "hotspot", sigma: [] },
              { name: "peak 1", kind: "peak", sigma: [] },
              { name: "peak 2", kind: "peak", sigma: [] },
            ],
          },
          rail: { name: "guide", length: 1.2 },
        }),
      ),
    );
    expect(parsed.ok).toBe(true);
    if (!parsed.ok) return;
    expect(parsed.summary.stress).toEqual({ hotspots: ["root top"], points: 3 });
    expect(parsed.summary.rail).toEqual({ name: "guide", length: 1.2 });
  });

  it("formats frequencies and errors, and knows the block and its file-derived constants", () => {
    expect(formatHz(433.0360872)).toBe("433");
    expect(formatHz(12.3456)).toBe("12.35");
    expect(formatHz(16070.18)).toBe("16070");
    expect(formatPercent(0.0309)).toBe("3.1 %");
    expect(isModalBodyRef(MODAL_BODY_REF)).toBe(true);
    expect(isModalBodyRef("stdlib:spatial/RigidBody3D")).toBe(false);
    expect(isModalBodyRef(null)).toBe(false);
    const decls = [{ name: "nm" }, { name: "mass" }, { name: "Gd3" }, { name: "other" }];
    expect(editableConstants(MODAL_BODY_REF, decls).map((decl) => decl.name)).toEqual(["other"]);
    expect(editableConstants("stdlib:sources/Step", decls)).toHaveLength(4);
    expect(MODAL_FILE_CONSTANTS.has("stiffening")).toBe(true);
    for (const name of ["ns", "nh", "Sxx", "Syz", "nr", "nc", "CT1", "CR3"]) {
      expect(MODAL_FILE_CONSTANTS.has(name)).toBe(true);
    }
    expect(modalSettings(undefined)).toEqual({ file: "", stiffening: true });
    expect(modalSettings({ file: "data/a.modal.json", stiffening: 0 })).toEqual({
      file: "data/a.modal.json",
      stiffening: false,
    });
    expect(dataFileKind("a.modal.json")).toBe("modal");
    expect(dataFileKind("A.CSV")).toBe("csv");
    expect(dataFileKind(".modal.json")).toBeNull();
    expect(dataFileKind("a.json")).toBeNull();
  });
});

function modalNode(constants: ModelNode["constants"] = {}): ModelNode {
  return {
    id: "n1",
    name: "Bracket",
    block: { ref: MODAL_BODY_REF },
    position: { x: 0, y: 0 },
    constants,
  };
}

function openWith(node: ModelNode): void {
  const doc: Model = createEmptyModel("ModalTest");
  doc.diagram.nodes = [node];
  useDocumentStore.getState().openDocument("demo", "ModalTest", doc);
}

function stored(): ModelNode {
  const found = useDocumentStore.getState().doc?.diagram.nodes[0];
  if (found === undefined) throw new Error("no node");
  return found;
}

function respond(body: unknown, status = 200): Response {
  return new Response(typeof body === "string" ? body : JSON.stringify(body), {
    status,
    headers: { "content-type": "application/json" },
  });
}

/** A stubbed data API: two reduced-model files (one broken) and an upload. */
function stubData(): ReturnType<typeof vi.fn> {
  const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
    const url = String(input);
    if (init?.method === "POST") {
      return respond({ file: "up.modal.json", path: "data/up.modal.json", kind: "modal" }, 201);
    }
    if (url.endsWith("/data?kind=modal")) {
      return respond([
        { file: "lbar.modal.json", bytes: MODAL_TEXT.length, kind: "modal" },
        { file: "broken.modal.json", bytes: 9, kind: "modal" },
      ]);
    }
    if (url.endsWith("/data/lbar.modal.json") || url.endsWith("/data/up.modal.json")) {
      return respond(MODAL_TEXT);
    }
    if (url.endsWith("/data/broken.modal.json")) return respond("{not json");
    return respond({ detail: "unknown data file" }, 404);
  });
  vi.stubGlobal("fetch", fetchMock);
  return fetchMock;
}

describe("ModalBodySection", () => {
  let fetchMock: ReturnType<typeof vi.fn>;

  beforeEach(() => {
    resetDocumentStore();
    fetchMock = stubData();
  });

  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("lists the reduced-model files and selecting one writes constants.file (undoable)", async () => {
    openWith(modalNode());
    const view = render(<ModalBodySection node={stored()} project="demo" />);
    const picker = (await screen.findByTestId("inspector-modal-file")) as HTMLSelectElement;
    await waitFor(() => expect(picker.options.length).toBe(3));
    expect([...picker.options].map((o) => o.textContent)).toEqual([
      "Choose a reduced-model file",
      "lbar.modal.json",
      "broken.modal.json",
    ]);
    expect(String(fetchMock.mock.calls[0]?.[0])).toMatch(/\/api\/projects\/demo\/data\?kind=modal$/);
    expect(screen.getByTestId("inspector-modal-hint").textContent).toContain(
      "julia --project=julia/BGSimFEM julia/BGSimFEM/bin/bgsim-fem.jl <part>.fem.json",
    );

    act(() => {
      fireEvent.change(picker, { target: { value: "data/lbar.modal.json" } });
    });
    expect(stored().constants?.file).toBe("data/lbar.modal.json");
    view.rerender(<ModalBodySection node={stored()} project="demo" />);

    const summary = await screen.findByTestId("inspector-modal-summary");
    expect(summary).toBeTruthy();
    expect(screen.getByTestId("inspector-modal-name").textContent).toBe("lbar");
    expect(screen.getByTestId("inspector-modal-mass").textContent).toBe("0.02333 kg");
    expect(screen.getByTestId("inspector-modal-modes").textContent).toBe(
      "nm = 8 (2 fixed-interface, 6 constraint modes)",
    );
    const interfaces = screen.getByTestId("inspector-modal-interfaces").textContent ?? "";
    expect(interfaces).toContain("port A: root at (0, 0, 0) m (reference frame)");
    expect(interfaces).toContain("port B: tip at (0.077, 0, -0.043) m");
    expect(interfaces).toContain("port C: mid");
    expect(screen.getByTestId("inspector-modal-frequencies").textContent).toBe(
      "433, 738.2, 1634, 1785, 5388, 7876, … Hz",
    );
    expect(screen.getByTestId("inspector-modal-validation").textContent).toBe(
      "band up to 16070 Hz; largest error in band: clamped 3.1 %, free 8.7 %",
    );
    expect(screen.getByTestId("inspector-modal-stiffening-data").textContent).toBe("in the file");
    const glb = screen.getByTestId("inspector-modal-glb").textContent ?? "";
    expect(glb).toContain("lbar.glb");
    expect(glb).toContain("meshes/");
    expect(glb).toContain("Bracket/eta[1..8]");
    expect(screen.queryByTestId("inspector-modal-error")).toBeNull();

    act(() => {
      useDocumentStore.getState().undo();
    });
    expect(stored().constants?.file).toBeUndefined();
  });

  it("writes the stiffening switch as 1 or 0", async () => {
    openWith(modalNode({ file: "data/lbar.modal.json" }));
    const view = render(<ModalBodySection node={stored()} project="demo" />);
    const box = (await screen.findByTestId("inspector-modal-stiffening")) as HTMLInputElement;
    expect(box.checked).toBe(true);
    act(() => {
      fireEvent.click(box);
    });
    expect(stored().constants?.stiffening).toBe(0);
    view.rerender(<ModalBodySection node={stored()} project="demo" />);
    const again = screen.getByTestId("inspector-modal-stiffening") as HTMLInputElement;
    expect(again.checked).toBe(false);
    act(() => {
      fireEvent.click(again);
    });
    expect(stored().constants?.stiffening).toBe(1);
  });

  it("shows why an invalid or missing file cannot be read, without a summary", async () => {
    openWith(modalNode({ file: "data/broken.modal.json" }));
    const view = render(<ModalBodySection node={stored()} project="demo" />);
    const error = await screen.findByTestId("inspector-modal-error");
    expect(error.textContent).toMatch(/not valid JSON/);
    expect(screen.queryByTestId("inspector-modal-summary")).toBeNull();

    act(() => {
      useDocumentStore.getState().setNodeConstant("n1", "file", "data/gone.modal.json");
    });
    view.rerender(<ModalBodySection node={stored()} project="demo" />);
    await waitFor(() =>
      expect(screen.getByTestId("inspector-modal-error").textContent).toMatch(
        /no file data\/gone\.modal\.json/,
      ),
    );
    const picker = screen.getByTestId("inspector-modal-file") as HTMLSelectElement;
    await waitFor(() =>
      expect([...picker.options].map((o) => o.textContent)).toContain(
        "data/gone.modal.json (not found)",
      ),
    );
  });

  it("uploads a file and selects it", async () => {
    openWith(modalNode());
    render(<ModalBodySection node={stored()} project="demo" />);
    const input = (await screen.findByTestId("inspector-modal-upload-input")) as HTMLInputElement;
    const file = new File([MODAL_TEXT], "up.modal.json", { type: "application/json" });
    await act(async () => {
      fireEvent.change(input, { target: { files: [file] } });
    });
    await waitFor(() => expect(stored().constants?.file).toBe("data/up.modal.json"));
    const post = fetchMock.mock.calls.find((call) => (call[1] as RequestInit | undefined)?.method === "POST");
    expect(post).toBeDefined();
  });

  it("works without a project", () => {
    openWith(modalNode());
    render(<ModalBodySection node={stored()} project={null} />);
    expect(screen.getByTestId("inspector-modal-upload")).toHaveProperty("disabled", true);
    expect(
      (screen.getByTestId("inspector-modal-file") as HTMLSelectElement).options[0]?.textContent,
    ).toBe("Open a project to pick a file");
  });
});

describe("the node inspector of a ModalBody3D", () => {
  beforeEach(() => {
    resetDocumentStore();
    resetCatalogStore();
    resetDiagnosticsStore();
    stubData();
  });

  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("shows the reduced-model section and hides the file-derived constants", async () => {
    const catalog = JSON.parse(JSON.stringify(catalogJson)) as Catalog;
    const base = catalog.blocks.find((block) => block.constants.length > 0) as CatalogBlock;
    const modal: CatalogBlock = {
      ...(JSON.parse(JSON.stringify(base)) as CatalogBlock),
      ref: MODAL_BODY_REF,
      name: "ModalBody3D",
      constants: [
        { name: "nm", type: "Int", default: 2, structural: true },
        { name: "stiffening", type: "Int", default: 1, structural: false },
        { name: "mass", type: "Real", default: 1, structural: false },
      ],
    };
    catalog.blocks.push(modal);
    useCatalogStore.getState().setCatalog(catalog);
    openWith(modalNode({ file: "data/lbar.modal.json" }));
    useDocumentStore.getState().setSelection(["n1"], []);
    render(<Inspector />);

    expect(screen.getByTestId("inspector-modal")).toBeTruthy();
    expect(screen.queryByTestId("inspector-constant-mass")).toBeNull();
    expect(screen.queryByTestId("inspector-constant-nm")).toBeNull();
    expect(screen.getByTestId("inspector-constants-none").textContent).toMatch(/reduced-model file/);
    expect(await screen.findByTestId("inspector-modal-summary")).toBeTruthy();
  });
});

describe("the reduced-model file as a clipboard dependency", () => {
  function sourceDoc(): Model {
    const doc = createEmptyModel("arm");
    doc.diagram.nodes = [
      modalNode({ file: "data/lbar.modal.json", stiffening: 1 }),
      {
        id: "n2",
        name: "Sub",
        position: { x: 200, y: 0 },
        block: {
          subsystem: {
            ports: [],
            diagram: {
              nodes: [
                { ...modalNode({ file: "data/inner.modal.json" }), id: "n3", name: "Inner" },
                {
                  id: "n4",
                  name: "Csv",
                  block: { ref: "stdlib:sources/CsvSource" },
                  position: { x: 0, y: 0 },
                  constants: { file: "data/profile.csv" },
                },
                // a .modal.json on another block is not a dependency
                {
                  id: "n5",
                  name: "Other",
                  block: { ref: "stdlib:sources/Step" },
                  position: { x: 0, y: 0 },
                  constants: { file: "data/x.modal.json" },
                },
              ],
              connections: [],
            },
          },
        },
      },
    ];
    return doc;
  }

  it("collects the modal files of copied ModalBody3D nodes, nested ones included", () => {
    const deps = collectDependencies({ nodes: sourceDoc().diagram.nodes, annotations: [], globals: [] });
    expect(deps.dataFiles).toEqual(["lbar.modal.json", "inner.modal.json", "profile.csv"]);
    const envelope = buildEnvelope({
      doc: sourceDoc(),
      path: [],
      selection: ["n1", "n2"],
      project: "lab",
      model: "arm",
    });
    expect(envelope).not.toBeNull();
    expect(validateEnvelope(envelope).ok).toBe(true);
  });

  it("copies the file into another project and renames it on a conflict", async () => {
    const envelope = buildEnvelope({
      doc: sourceDoc(),
      path: [],
      selection: ["n1"],
      project: "lab",
      model: "arm",
    });
    if (envelope === null) throw new Error("nothing copied");
    const data: Record<string, Record<string, string>> = {
      lab: { "lbar.modal.json": MODAL_TEXT },
      other: { "lbar.modal.json": JSON.stringify(modalDocument({ mass: 2 })) },
    };
    const io: PasteIo = {
      libraryNames: async () => [],
      librarySource: async () => null,
      writeLibrary: async () => undefined,
      refreshCatalog: async () => null,
      dataFileNames: async (project) => Object.keys(data[project] ?? {}),
      dataText: async (project, file) => data[project]?.[file] ?? null,
      writeData: async () => undefined,
      copyAssets: async () => ({ copied: [], existing: [], missing: [] }),
      ask: async () => ({}),
    };
    const analysis = await analyse(
      envelope,
      { project: "other", model: "bench", path: [], globals: [] },
      io,
    );
    expect(analysis.conflicts.map((conflict) => [conflict.key, conflict.renameTo])).toEqual([
      ["dataFile:lbar.modal.json", "lbar2.modal.json"],
    ]);
    const resolution = resolve(envelope, analysis, { "dataFile:lbar.modal.json": "rename" });
    expect(resolution.dataWrites.map((write) => write.file)).toEqual(["lbar2.modal.json"]);
    expect(resolution.rewrites.dataFiles).toEqual({
      "data/lbar.modal.json": "data/lbar2.modal.json",
    });

    useDocumentStore.getState().openDocument("other", "bench", createEmptyModel("bench"));
    useDocumentStore
      .getState()
      .pasteClip(envelope, { at: { x: 0, y: 0 }, rewrites: resolution.rewrites, addGlobals: [] });
    const pasted = useDocumentStore.getState().doc?.diagram.nodes[0];
    expect(pasted?.constants).toEqual({ file: "data/lbar2.modal.json", stiffening: 1 });
  });

  it("proposes free modal file names and lists every data file for the paste", async () => {
    expect(freeDataName("lbar.modal.json", ["LBAR.modal.json", "lbar2.modal.json"])).toBe(
      "lbar3.modal.json",
    );
    expect(freeDataName("free.modal.json", ["lbar.modal.json"])).toBe("free.modal.json");
    const fetchMock = vi.fn(async () => respond([]));
    vi.stubGlobal("fetch", fetchMock);
    await listDataFiles("demo", undefined, "all");
    await listDataFiles("demo");
    expect(fetchMock.mock.calls.map((call) => String((call as unknown[])[0]))).toEqual([
      expect.stringMatching(/\/data\?kind=all$/),
      expect.stringMatching(/\/data$/),
    ]);
    vi.unstubAllGlobals();
  });
});
