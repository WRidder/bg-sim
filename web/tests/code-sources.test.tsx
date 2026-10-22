/**
 * W2.1 source handling: the read-only stdlib banner (plan 7.7), open-source
 * ref resolution, and the inline-source edit being an undoable document
 * mutation (plan 7.4).
 */

import { fireEvent, render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import catalogJson from "../../contracts/fixtures/catalog/valid/catalog.min.json";
import type { Catalog } from "../src/contracts/catalog";
import type { Model, ModelNode } from "../src/contracts/model";
import { SourceBanner } from "../src/code/SourceBanner";
import { resetCodeSession } from "../src/code/codeSession";
import { resolveOpenDetail } from "../src/code/sources";
import { buildCatalogIndex } from "../src/library/catalogIndex";
import {
  resetDocumentStore,
  useDocumentStore,
} from "../src/state/documentStore";
import { createEmptyModel } from "../src/state/modelFactory";

const catalog = catalogJson as unknown as Catalog;
const index = buildCatalogIndex(catalog);

function inlineNode(source: string, id = "n1", name = "Equation1"): ModelNode {
  return {
    id,
    name,
    block: { inline: { source } },
    position: { x: 40, y: 40 },
    rotation: 0,
    flipX: false,
    params: {},
    constants: {},
    starts: {},
    ui: { showLabel: true, color: null },
  };
}

function modelWith(nodes: ModelNode[]): Model {
  const model = createEmptyModel("CodeModel", "0.1.0");
  model.diagram.nodes = nodes;
  return model;
}

beforeEach(() => {
  resetDocumentStore();
  resetCodeSession();
});

describe("read-only stdlib banner", () => {
  it("says the stdlib source is read-only and offers copy", () => {
    const onCopy = vi.fn();
    render(
      <SourceBanner
        sourceKind="stdlib"
        name="C"
        path="stdlib/bondgraph/C.jl"
        project="demo"
        copyState="idle"
        copyMessage={null}
        onCopy={onCopy}
      />,
    );
    expect(screen.getByTestId("code-readonly-banner")).toBeTruthy();
    expect(screen.getByText("Read-only standard library source")).toBeTruthy();
    const button = screen.getByTestId("code-copy-to-library");
    expect((button as HTMLButtonElement).disabled).toBe(false);
    fireEvent.click(button);
    expect(onCopy).toHaveBeenCalledTimes(1);
  });

  it("disables copying without a project", () => {
    render(
      <SourceBanner
        sourceKind="stdlib"
        name="C"
        path="stdlib/bondgraph/C.jl"
        project={null}
        copyState="idle"
        copyMessage={null}
        onCopy={() => undefined}
      />,
    );
    expect((screen.getByTestId("code-copy-to-library") as HTMLButtonElement).disabled).toBe(true);
    expect(screen.getByText("Open a project to copy this block.")).toBeTruthy();
  });

  it("marks a project-library source as editable and shows its file", () => {
    render(
      <SourceBanner
        sourceKind="project"
        name="MyC"
        path="library/MyC.jl"
        project="demo"
        copyState="idle"
        copyMessage={null}
        onCopy={() => undefined}
      />,
    );
    expect(screen.getByTestId("code-project-banner")).toBeTruthy();
    expect(screen.getByText("Project library source")).toBeTruthy();
    expect(screen.getByTestId("code-project-banner").textContent).toContain("library/MyC.jl");
    expect(screen.queryByTestId("code-copy-to-library")).toBeNull();
  });
});

describe("open-source ref resolution", () => {
  it("resolves inline ids, inline: prefixes and instance names", () => {
    const doc = modelWith([inlineNode("@block Equation begin\nend\n", "n7", "Filter1")]);
    for (const ref of ["n7", "inline:n7", "Filter1"]) {
      const target = resolveOpenDetail({ kind: "inline", ref, line: 3, col: 4 }, doc, index);
      expect(target).toEqual({
        kind: "inline",
        nodeId: "n7",
        ref: "inline:n7",
        line: 3,
        col: 4,
      });
    }
    expect(resolveOpenDetail({ kind: "inline", ref: "missing", line: 1, col: 1 }, doc, index)).toBeNull();
  });

  it("resolves a stdlib ref, a path and a block name", () => {
    for (const ref of ["stdlib:bondgraph/C", "stdlib/bondgraph/C.jl", "C"]) {
      const target = resolveOpenDetail({ kind: "stdlib", ref, line: 1, col: 1 }, null, index);
      expect(target?.kind).toBe("library");
      if (target?.kind === "library") {
        expect(target.blockRef).toBe("stdlib:bondgraph/C");
        expect(target.sourceKind).toBe("stdlib");
        expect(target.path).toBe("stdlib/bondgraph/C.jl");
      }
    }
    expect(resolveOpenDetail({ kind: "stdlib", ref: "nope", line: 1, col: 1 }, null, index)).toBeNull();
  });

  it("resolves a project ref to the editable kind", () => {
    const projectCatalog = {
      ...catalog,
      blocks: [
        ...catalog.blocks,
        {
          ...catalog.blocks[0]!,
          ref: "project:Mine",
          name: "Mine",
          path: "library/Mine.jl",
        },
      ],
    };
    const target = resolveOpenDetail(
      { kind: "project", ref: "project:Mine", line: 2, col: 1 },
      null,
      buildCatalogIndex(projectCatalog),
    );
    expect(target?.kind).toBe("library");
    if (target?.kind === "library") {
      expect(target.sourceKind).toBe("project");
      expect(target.name).toBe("Mine");
    }
  });
});

describe("inline source edits and undo", () => {
  beforeEach(() => {
    useDocumentStore
      .getState()
      .openDocument("demo", "CodeModel", modelWith([inlineNode("old source")]));
  });

  it("commits source edits through the document store", () => {
    const result = useDocumentStore.getState().setInlineSource("n1", "new source");
    expect(result).toEqual({ ok: true });
    const node = useDocumentStore.getState().doc?.diagram.nodes[0];
    expect(node !== undefined && "inline" in node.block ? node.block.inline.source : null).toBe(
      "new source",
    );
  });

  it("coalesces a typing gesture into one undo step", () => {
    const store = useDocumentStore.getState();
    store.beginGesture("inline-source:n1");
    expect(store.setInlineSource("n1", "new ", { coalesce: true }).ok).toBe(true);
    expect(store.setInlineSource("n1", "new source", { coalesce: true }).ok).toBe(true);
    store.endGesture();

    expect(useDocumentStore.getState().past).toHaveLength(1);
    useDocumentStore.getState().undo();
    const node = useDocumentStore.getState().doc?.diagram.nodes[0];
    expect(node !== undefined && "inline" in node.block ? node.block.inline.source : null).toBe(
      "old source",
    );
    useDocumentStore.getState().redo();
    const redone = useDocumentStore.getState().doc?.diagram.nodes[0];
    expect(redone !== undefined && "inline" in redone.block ? redone.block.inline.source : null).toBe(
      "new source",
    );
  });

  it("refuses to edit a node that is not inline", () => {
    useDocumentStore
      .getState()
      .openDocument("demo", "CodeModel", modelWith([
        {
          ...inlineNode("x"),
          block: { ref: "stdlib:bondgraph/C" },
        },
      ]));
    expect(useDocumentStore.getState().setInlineSource("n1", "y")).toEqual({
      ok: false,
      error: "Only inline code nodes have editable embedded source.",
    });
  });
});

describe("new inline nodes", () => {
  beforeEach(() => {
    useDocumentStore.getState().openDocument("demo", "CodeModel", modelWith([]));
  });

  it("adds an Equation node with its source and undoes it", () => {
    const id = useDocumentStore.getState().addInlineBlock("equation", "@block Equation begin\nend\n");
    expect(id).toBe("n1");
    const node = useDocumentStore.getState().doc?.diagram.nodes[0];
    expect(node?.name).toBe("Equation");
    expect(node !== undefined && "inline" in node.block ? node.block.inline.source : null).toBe(
      "@block Equation begin\nend\n",
    );

    useDocumentStore.getState().undo();
    expect(useDocumentStore.getState().doc?.diagram.nodes).toHaveLength(0);
    useDocumentStore.getState().redo();
    expect(useDocumentStore.getState().doc?.diagram.nodes).toHaveLength(1);
  });

  it("names a second node without a clash", () => {
    useDocumentStore.getState().addInlineBlock("discrete", "a");
    useDocumentStore.getState().addInlineBlock("discrete", "b");
    const names = useDocumentStore.getState().doc?.diagram.nodes.map((node) => node.name);
    expect(names).toEqual(["DiscreteCode", "DiscreteCode2"]);
  });
});
