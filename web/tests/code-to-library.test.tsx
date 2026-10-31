/**
 * From code to a reusable block (plan 7.7): "Save to project library" of an
 * inline code node (inspector and Code tab), "+ Library block" in the Code
 * tab, the name validation of the shared dialog, re-pointing in one undo step,
 * the fake-worker report path (the fixed catalog never publishes the block),
 * and the library browser showing the new entry.
 */

import { act, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import catalogJson from "../../contracts/fixtures/catalog/valid/catalog.min.json";
import type { Catalog, CatalogBlock } from "../src/contracts/catalog";
import type { Model, ModelNode } from "../src/contracts/model";
import { CodeTab } from "../src/code/CodeTab";
import { openTarget, resetCodeSession, useCodeSessionStore } from "../src/code/codeSession";
import { resetInlineInterfaces } from "../src/code/inlineInterfaces";
import { identicalInlineNodes, inlineNodesOf } from "../src/code/inlineToLibrary";
import { EQUATION_TEMPLATE } from "../src/code/templates";
import { resetDiagnosticsStore } from "../src/diagnostics/store";
import { Inspector } from "../src/inspector/Inspector";
import { resetCatalogStore, useCatalogStore } from "../src/library/catalogStore";
import { LibraryBrowser } from "../src/library/LibraryBrowser";
import { resetLibraryPrefs, useLibraryPrefs } from "../src/library/libraryPrefs";
import { revealLibraryBlock, useLibraryReveal } from "../src/library/libraryReveal";
import {
  blockNameProblem,
  freeBlockName,
  renameBlockDeclaration,
} from "../src/library/projectBlocks";
import { resetRunStore } from "../src/plot/runStore";
import { resetDocumentStore, useDocumentStore } from "../src/state/documentStore";
import { createEmptyModel, createNodeFromBlock } from "../src/state/modelFactory";

// CodeMirror needs layout jsdom does not have; the Code tab's own logic is under test here.
vi.mock("../src/code/CodeEditor", () => ({
  CodeEditor: (props: { source: string; readOnly: boolean }) => (
    <pre data-testid="code-editor" data-read-only={props.readOnly ? "true" : "false"}>
      {props.source}
    </pre>
  ),
}));

const catalog = catalogJson as unknown as Catalog;

const LAG_SOURCE = `@block Equation begin
    @inputs u::Real
    @outputs y::Real
    @parameters begin
        tau::Real = 0.5, [unit = "s", description = "Time constant"]
    end
    @variables x::Real = 0.0
    @equations begin
        ddt(x) ~ (u - x) / tau
        y ~ x
    end
end
`;

function stdlibBlock(name: string): CatalogBlock {
  const entry = catalog.blocks.find((block) => block.name === name);
  if (entry === undefined) {
    throw new Error(`the catalog has no block ${name}`);
  }
  return entry;
}

function projectBlock(name: string, source: string): CatalogBlock {
  return {
    ...stdlibBlock("DCMotor"),
    ref: `project:${name}`,
    name,
    group: "Project",
    description: `${name} (project library)`,
    parameters: [],
    constants: [],
    ports: [],
    inputs: [{ name: "u", type: "Real", size: [], unit: null }],
    outputs: [{ name: "y", type: "Real", size: [], unit: null }],
    variables: [],
    causality: [],
    source,
    path: `library/${name}.jl`,
  } as CatalogBlock;
}

function inlineNode(id: string, name: string, source = LAG_SOURCE): ModelNode {
  return {
    id,
    name,
    block: { inline: { source } },
    position: { x: 120, y: 80 },
    rotation: 90,
    flipX: false,
    params: { tau: "0.25" },
    constants: {},
    starts: { x: "1" },
    ui: { showLabel: true, color: null },
  };
}

function open(nodes: readonly ModelNode[]): Model {
  const doc = createEmptyModel("CodeToLibrary");
  doc.diagram.nodes = [...nodes];
  useDocumentStore.getState().openDocument("demo", "CodeToLibrary", doc);
  return doc;
}

function docNode(id: string): ModelNode | undefined {
  const found = inlineNodesOf(useDocumentStore.getState().doc);
  const inline = found.find((entry) => entry.id === id)?.node;
  if (inline !== undefined) {
    return inline;
  }
  const walk = (nodes: readonly ModelNode[]): ModelNode | undefined => {
    for (const node of nodes) {
      if (node.id === id) {
        return node;
      }
      if ("subsystem" in node.block) {
        const nested = walk(node.block.subsystem.diagram.nodes);
        if (nested !== undefined) {
          return nested;
        }
      }
    }
    return undefined;
  };
  return walk(useDocumentStore.getState().doc?.diagram.nodes ?? []);
}

function answer(status: number, body: unknown): Response {
  const text = typeof body === "string" ? body : JSON.stringify(body);
  return {
    status,
    ok: status >= 200 && status < 300,
    text: async () => text,
    json: async () => JSON.parse(text) as unknown,
  } as unknown as Response;
}

interface Backend {
  library: string[];
  /** The block the catalog publishes after a PUT; null plays the fake worker. */
  publish: boolean;
  puts: { url: string; body: string }[];
  putStatus?: number;
}

function stubBackend(backend: Backend) {
  const mock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
    const url = String(input);
    const method = init?.method ?? "GET";
    if (method === "PUT" && url.includes("/library/")) {
      backend.puts.push({ url, body: String(init?.body) });
      if (backend.putStatus !== undefined) {
        return answer(backend.putStatus, { detail: "the disk is full" });
      }
      const name = decodeURIComponent(url.split("/library/")[1] ?? "");
      backend.library.push(name);
      return answer(200, { project: "demo", name, file: `${name}.jl` });
    }
    if (url.includes("/api/catalog")) {
      const extra = backend.publish
        ? backend.puts.map((put) => {
            const name = decodeURIComponent(put.url.split("/library/")[1] ?? "");
            return projectBlock(name, put.body);
          })
        : [];
      return answer(200, { ...catalog, blocks: [...catalog.blocks, ...extra] });
    }
    if (url.includes("/api/projects/demo")) {
      return answer(200, {
        name: "demo",
        project: { libraryDir: "library" },
        models: [],
        library: backend.library.map((name) => ({ name, modified: 0 })),
      });
    }
    if (url.includes("/api/check/block")) {
      return answer(200, { diagnostics: [], interface: null });
    }
    return answer(404, { detail: `unexpected ${method} ${url}` });
  });
  vi.stubGlobal("fetch", mock);
  return mock;
}

beforeEach(() => {
  resetDocumentStore();
  resetCatalogStore();
  resetDiagnosticsStore();
  resetRunStore();
  resetCodeSession();
  resetInlineInterfaces();
  resetLibraryPrefs();
  useLibraryReveal.getState().consume();
  useCatalogStore.getState().setCatalog(catalog);
});

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("project block names", () => {
  it("accepts a free Julia identifier", () => {
    expect(blockNameProblem("FirstOrderLag", ["Gain2"])).toBeNull();
    expect(blockNameProblem("_lag2", [])).toBeNull();
  });

  it("refuses empty names, non-identifiers, keywords and reserved file names", () => {
    expect(blockNameProblem("  ", [])).toBe("Enter a block name.");
    expect(blockNameProblem("1Lag", [])).toContain("Julia identifier");
    expect(blockNameProblem("first-order", [])).toContain("Julia identifier");
    expect(blockNameProblem("end", [])).toContain("Julia keyword");
    expect(blockNameProblem("NUL", [])).toContain("reserved file name");
  });

  it("refuses a name taken in the project library, ignoring case like the file system", () => {
    expect(blockNameProblem("Lag", ["Lag"])).toBe(
      "The project library already has a block called Lag.",
    );
    expect(blockNameProblem("lag", ["Lag"])).toContain("block file names ignore case");
  });

  it("proposes the first free name, ignoring case", () => {
    expect(freeBlockName("Equation", [])).toBe("Equation");
    expect(freeBlockName("Equation", ["equation"])).toBe("Equation2");
    expect(freeBlockName("Lag2", ["Lag2", "Lag3"])).toBe("Lag4");
  });

  it("renames whatever @block header the source declares", () => {
    expect(renameBlockDeclaration(LAG_SOURCE, "Lag")).toMatch(/^@block Lag begin/);
    expect(renameBlockDeclaration("  @block Foo begin\nend\n", "Bar")).toBe(
      "  @block Bar begin\nend\n",
    );
    expect(() => renameBlockDeclaration("y ~ u", "Bar")).toThrow("no @block <Name> declaration");
  });
});

describe("re-pointing inline nodes", () => {
  it("replaces inline blocks with the library ref in one undo step, keeping the instance", () => {
    const inner = inlineNode("n3", "Filter");
    const subsystem: ModelNode = {
      id: "n2",
      name: "Plant",
      block: {
        subsystem: {
          diagram: { nodes: [inner], connections: [], subsystemPorts: [], annotations: [] },
          ports: [],
        },
      },
      position: { x: 0, y: 0 },
      rotation: 0,
      flipX: false,
      params: {},
      constants: {},
      starts: {},
      ui: { showLabel: true, color: null },
    } as unknown as ModelNode;
    open([inlineNode("n1", "Lag1"), subsystem, createNodeFromBlock(stdlibBlock("DCMotor"), { x: 0, y: 0 }, "n4", "Motor1")]);
    expect(identicalInlineNodes(useDocumentStore.getState().doc, "n1", LAG_SOURCE).map((e) => e.path)).toEqual([
      "Plant/Filter",
    ]);

    const before = useDocumentStore.getState().past.length;
    const result = useDocumentStore.getState().replaceInlineWithRef(["n1", "n3", "n4"], "project:Lag");
    expect(result).toEqual({ ok: true, replaced: ["n1", "n3"] });
    expect(useDocumentStore.getState().past.length).toBe(before + 1);

    const lag = docNode("n1");
    expect(lag?.block).toEqual({ ref: "project:Lag" });
    expect(lag?.name).toBe("Lag1");
    expect(lag?.position).toEqual({ x: 120, y: 80 });
    expect(lag?.rotation).toBe(90);
    expect(lag?.params).toEqual({ tau: "0.25" });
    expect(lag?.starts).toEqual({ x: "1" });
    expect(docNode("n3")?.block).toEqual({ ref: "project:Lag" });
    expect(docNode("n4")?.block).toEqual({ ref: stdlibBlock("DCMotor").ref });

    useDocumentStore.getState().undo();
    expect(docNode("n1")?.block).toEqual({ inline: { source: LAG_SOURCE } });
    expect(docNode("n3")?.block).toEqual({ inline: { source: LAG_SOURCE } });
  });

  it("refuses when none of the ids is an inline node", () => {
    open([createNodeFromBlock(stdlibBlock("DCMotor"), { x: 0, y: 0 }, "n4", "Motor1")]);
    const result = useDocumentStore.getState().replaceInlineWithRef(["n4"], "project:Lag");
    expect(result.ok).toBe(false);
    expect(useDocumentStore.getState().past.length).toBe(0);
  });
});

describe("inspector library buttons", () => {
  it("offers Save to project library for an inline node instead of Copy", () => {
    open([inlineNode("n1", "Lag1")]);
    useDocumentStore.getState().setSelection(["n1"], []);
    render(<Inspector />);
    const save = screen.getByTestId("inspector-save-library") as HTMLButtonElement;
    expect(save.disabled).toBe(false);
    expect(screen.queryByTestId("inspector-copy-library")).toBeNull();
  });

  it("keeps Copy to project library for a standard block", () => {
    open([createNodeFromBlock(stdlibBlock("DCMotor"), { x: 0, y: 0 }, "n1", "Motor1")]);
    useDocumentStore.getState().setSelection(["n1"], []);
    render(<Inspector />);
    expect((screen.getByTestId("inspector-copy-library") as HTMLButtonElement).disabled).toBe(false);
    expect(screen.queryByTestId("inspector-save-library")).toBeNull();
  });

  it("disables copying a block that already lives in the project library", () => {
    const lag = projectBlock("Lag", LAG_SOURCE);
    useCatalogStore.getState().setCatalog({ ...catalog, blocks: [...catalog.blocks, lag] });
    open([createNodeFromBlock(lag, { x: 0, y: 0 }, "n1", "Lag1")]);
    useDocumentStore.getState().setSelection(["n1"], []);
    render(<Inspector />);
    const copy = screen.getByTestId("inspector-copy-library") as HTMLButtonElement;
    expect(copy.disabled).toBe(true);
    expect(copy.title).toBe("This block already lives in the project library.");
    expect(screen.queryByTestId("inspector-save-library")).toBeNull();
  });

  it("disables saving without a project", () => {
    open([inlineNode("n1", "Lag1")]);
    useDocumentStore.setState({ project: null });
    useDocumentStore.getState().setSelection(["n1"], []);
    render(<Inspector />);
    expect((screen.getByTestId("inspector-save-library") as HTMLButtonElement).disabled).toBe(true);
  });
});

describe("Save to project library from the inspector", () => {
  async function openDialog(): Promise<HTMLInputElement> {
    useDocumentStore.getState().setSelection(["n1"], []);
    render(<Inspector />);
    fireEvent.click(screen.getByTestId("inspector-save-library"));
    expect(screen.getByTestId("project-block-dialog").getAttribute("data-mode")).toBe("save-inline");
    const name = screen.getByTestId("project-block-name") as HTMLInputElement;
    await waitFor(() => expect(name.disabled).toBe(false));
    return name;
  }

  it("proposes the @block name and validates the name as it is typed", async () => {
    stubBackend({ library: ["Lag", "Equation"], publish: false, puts: [] });
    open([inlineNode("n1", "Lag1")]);
    const name = await openDialog();
    const submit = screen.getByTestId("project-block-submit") as HTMLButtonElement;
    const hint = screen.getByTestId("project-block-name-hint");

    // `@block Equation` is taken, so the proposal is the next free name.
    expect(name.value).toBe("Equation2");
    expect(submit.disabled).toBe(false);
    expect(screen.getByTestId("project-block-rename-note").textContent).toContain(
      "@block Equation",
    );

    fireEvent.change(name, { target: { value: "lag" } });
    expect(hint.textContent).toContain("ignore case");
    expect(submit.disabled).toBe(true);

    fireEvent.change(name, { target: { value: "first order" } });
    expect(hint.textContent).toContain("Julia identifier");
    expect(submit.disabled).toBe(true);

    fireEvent.change(name, { target: { value: "FirstOrderLag" } });
    expect(hint.textContent).toBe("Saved as library/FirstOrderLag.jl, used as project:FirstOrderLag.");
    expect(screen.getByTestId("project-block-rename-note").textContent).toContain(
      "@block FirstOrderLag",
    );
    expect(submit.disabled).toBe(false);

    fireEvent.click(screen.getByTestId("project-block-cancel"));
    expect(screen.queryByTestId("project-block-dialog")).toBeNull();
  });

  it("reports the fake-worker case instead of re-pointing", async () => {
    const backend: Backend = { library: [], publish: false, puts: [] };
    stubBackend(backend);
    open([inlineNode("n1", "Lag1")]);
    const name = await openDialog();
    fireEvent.change(name, { target: { value: "FirstOrderLag" } });
    fireEvent.click(screen.getByTestId("project-block-submit"));

    await waitFor(() => expect(screen.queryByTestId("project-block-dialog")).toBeNull());
    expect(backend.puts).toHaveLength(1);
    expect(backend.puts[0]?.url).toContain("/api/projects/demo/library/FirstOrderLag");
    expect(backend.puts[0]?.body).toMatch(/^@block FirstOrderLag begin/);
    expect(screen.getByTestId("inspector-copy-status").textContent).toContain(
      "The catalog does not list project:FirstOrderLag yet, so Lag1 stays an inline block",
    );
    expect(docNode("n1")?.block).toEqual({ inline: { source: LAG_SOURCE } });
    expect(useDocumentStore.getState().past.length).toBe(0);
  });

  it("re-points the node (and its identical copies on request) in one undo step", async () => {
    const backend: Backend = { library: [], publish: true, puts: [] };
    stubBackend(backend);
    open([inlineNode("n1", "Lag1"), inlineNode("n2", "Lag2"), inlineNode("n3", "Other", EQUATION_TEMPLATE)]);
    const name = await openDialog();
    expect(screen.getByTestId("project-block-identical").textContent).toContain(
      "1 other inline block with the same source (Lag2)",
    );
    fireEvent.click(screen.getByTestId("project-block-identical-check"));
    fireEvent.change(name, { target: { value: "FirstOrderLag" } });
    fireEvent.click(screen.getByTestId("project-block-submit"));

    await waitFor(() => expect(docNode("n1")?.block).toEqual({ ref: "project:FirstOrderLag" }));
    expect(docNode("n2")?.block).toEqual({ ref: "project:FirstOrderLag" });
    expect(docNode("n3")?.block).toEqual({ inline: { source: EQUATION_TEMPLATE } });
    expect(docNode("n1")?.params).toEqual({ tau: "0.25" });
    expect(useDocumentStore.getState().past.length).toBe(1);
    expect(screen.getByTestId("inspector-copy-status").textContent).toContain(
      "Lag1 (and 1 other identical inline block) now uses project:FirstOrderLag",
    );
    expect(useCatalogStore.getState().index?.blocksByRef.has("project:FirstOrderLag")).toBe(true);
    expect(useLibraryReveal.getState().pending).toBe("project:FirstOrderLag");

    act(() => useDocumentStore.getState().undo());
    expect(docNode("n1")?.block).toEqual({ inline: { source: LAG_SOURCE } });
    expect(docNode("n2")?.block).toEqual({ inline: { source: LAG_SOURCE } });
  });

  it("keeps the dialog open with the error when the write fails", async () => {
    stubBackend({ library: [], publish: true, puts: [], putStatus: 507 });
    open([inlineNode("n1", "Lag1")]);
    await openDialog();
    fireEvent.click(screen.getByTestId("project-block-submit"));
    await waitFor(() =>
      expect(screen.getByTestId("project-block-error").textContent).toContain("the disk is full"),
    );
    expect(docNode("n1")?.block).toEqual({ inline: { source: LAG_SOURCE } });
  });
});

describe("Code tab", () => {
  it("saves the open inline block and then shows the library block", async () => {
    stubBackend({ library: [], publish: true, puts: [] });
    open([inlineNode("n1", "Lag1")]);
    act(() => openTarget({ kind: "inline", nodeId: "n1", ref: "inline:n1", line: 1, col: 1 }));
    render(<CodeTab />);

    fireEvent.click(screen.getByTestId("code-save-to-library"));
    const name = screen.getByTestId("project-block-name") as HTMLInputElement;
    await waitFor(() => expect(name.disabled).toBe(false));
    expect(name.value).toBe("Equation");
    fireEvent.change(name, { target: { value: "Lag" } });
    fireEvent.click(screen.getByTestId("project-block-submit"));

    await waitFor(() =>
      expect(useCodeSessionStore.getState().target).toMatchObject({
        kind: "library",
        sourceKind: "project",
        blockRef: "project:Lag",
      }),
    );
    expect(docNode("n1")?.block).toEqual({ ref: "project:Lag" });
    expect(screen.getByTestId("code-notice").textContent).toContain(
      "Saved to library/Lag.jl; Lag1 now uses project:Lag.",
    );
    expect(screen.getByTestId("code-project-banner")).toBeTruthy();
    expect(screen.getByTestId("code-editor").textContent).toContain("@block Lag begin");
  });

  it("keeps the inline block open when the catalog does not publish the block", async () => {
    stubBackend({ library: [], publish: false, puts: [] });
    open([inlineNode("n1", "Lag1")]);
    act(() => openTarget({ kind: "inline", nodeId: "n1", ref: "inline:n1", line: 1, col: 1 }));
    render(<CodeTab />);
    fireEvent.click(screen.getByTestId("code-save-to-library"));
    await waitFor(() =>
      expect((screen.getByTestId("project-block-name") as HTMLInputElement).disabled).toBe(false),
    );
    fireEvent.click(screen.getByTestId("project-block-submit"));
    await waitFor(() =>
      expect(screen.getByTestId("code-notice").textContent).toContain("stays an inline block"),
    );
    expect(useCodeSessionStore.getState().target).toMatchObject({ kind: "inline", nodeId: "n1" });
    expect(docNode("n1")?.block).toEqual({ inline: { source: LAG_SOURCE } });
  });

  it("creates a new library block from the discrete template and can place it", async () => {
    const backend: Backend = { library: ["DiscreteCode"], publish: true, puts: [] };
    stubBackend(backend);
    open([]);
    render(<CodeTab />);

    fireEvent.click(screen.getByTestId("code-new-library-block"));
    expect(screen.getByTestId("project-block-dialog").getAttribute("data-mode")).toBe("new");
    const name = screen.getByTestId("project-block-name") as HTMLInputElement;
    await waitFor(() => expect(name.disabled).toBe(false));
    expect(name.value).toBe("Equation");
    fireEvent.click(screen.getByTestId("project-block-kind-discrete"));
    // The proposal follows the template until the user types a name.
    expect(name.value).toBe("DiscreteCode2");
    fireEvent.change(name, { target: { value: "Integrator" } });
    fireEvent.click(screen.getByTestId("project-block-submit"));

    await waitFor(() =>
      expect(useCodeSessionStore.getState().target).toMatchObject({
        kind: "library",
        sourceKind: "project",
        blockRef: "project:Integrator",
        path: "library/Integrator.jl",
      }),
    );
    expect(backend.puts[0]?.url).toContain("/library/Integrator");
    expect(backend.puts[0]?.body).toMatch(/^@block Integrator begin/);
    expect(backend.puts[0]?.body).toContain("@discrete Ts = 0.01");
    // Nothing is placed on the diagram by creating the block.
    expect(useDocumentStore.getState().doc?.diagram.nodes).toHaveLength(0);
    expect(screen.getByTestId("code-notice").textContent).toContain(
      "Created library/Integrator.jl. Integrator is in the library's Project category",
    );
    expect(useLibraryReveal.getState().pending).toBe("project:Integrator");

    fireEvent.click(screen.getByTestId("code-place-on-diagram"));
    const nodes = useDocumentStore.getState().doc?.diagram.nodes ?? [];
    expect(nodes).toHaveLength(1);
    expect(nodes[0]?.block).toEqual({ ref: "project:Integrator" });
    expect(screen.getByTestId("code-notice").textContent).toContain("Placed Integrator");
    expect(screen.queryByTestId("code-place-on-diagram")).toBeNull();
  });

  it("opens the new file from its seed when the fake catalog does not publish it", async () => {
    stubBackend({ library: [], publish: false, puts: [] });
    open([]);
    render(<CodeTab />);
    fireEvent.click(screen.getByTestId("code-new-library-block"));
    const name = screen.getByTestId("project-block-name") as HTMLInputElement;
    await waitFor(() => expect(name.disabled).toBe(false));
    fireEvent.change(name, { target: { value: "Lag" } });
    fireEvent.click(screen.getByTestId("project-block-submit"));
    await waitFor(() =>
      expect(screen.getByTestId("code-notice").textContent).toContain(
        "The catalog does not list project:Lag yet",
      ),
    );
    expect(screen.queryByTestId("code-place-on-diagram")).toBeNull();
    expect(screen.getByTestId("code-editor").textContent).toContain("@block Lag begin");
    expect(useLibraryReveal.getState().pending).toBeNull();
  });

  it("disables + Library block without a project", () => {
    open([]);
    useDocumentStore.setState({ project: null });
    render(<CodeTab />);
    expect((screen.getByTestId("code-new-library-block") as HTMLButtonElement).disabled).toBe(true);
  });
});

describe("library browser reveal", () => {
  it("expands the Project category and highlights the new block", () => {
    const lag = projectBlock("Lag", LAG_SOURCE);
    useCatalogStore.getState().setCatalog({ ...catalog, blocks: [...catalog.blocks, lag] });
    useLibraryPrefs.getState().setHidden("Project", true);
    render(<LibraryBrowser />);
    expect(screen.queryByTestId("library-group-Project")).toBeNull();

    act(() => revealLibraryBlock("project:Lag"));

    expect(screen.getByTestId("library-group-Project").getAttribute("data-expanded")).toBe("true");
    const entry = screen.getByTestId("library-item-Lag");
    expect(entry.getAttribute("data-new")).toBe("true");
    expect(entry.getAttribute("draggable")).toBe("true");
    expect(useLibraryReveal.getState().pending).toBeNull();
    expect(useLibraryPrefs.getState().expanded.has("Project")).toBe(true);
  });

  it("waits until the catalog lists the block", () => {
    render(<LibraryBrowser />);
    act(() => revealLibraryBlock("project:Later"));
    expect(useLibraryReveal.getState().pending).toBe("project:Later");
    act(() =>
      useCatalogStore
        .getState()
        .setCatalog({ ...catalog, blocks: [...catalog.blocks, projectBlock("Later", LAG_SOURCE)] }),
    );
    expect(screen.getByTestId("library-item-Later").getAttribute("data-new")).toBe("true");
  });
});
