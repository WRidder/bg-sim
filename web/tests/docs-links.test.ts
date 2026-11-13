import { describe, expect, it } from "vitest";

import modelJson from "../../contracts/fixtures/model/valid/model.dcmotor.bondgraph.json";
import linkedJson from "../../contracts/fixtures/model/valid/model.linked-subsystem.json";
import type { Model } from "../src/contracts/model";
import {
  describeLink,
  findBlock,
  formatDocsRef,
  modelPagesOf,
  parseDocsRef,
  resolveLink,
  type LinkContext,
} from "../src/docs/docsLinks";
import { hydrateModel } from "../src/library/linkedSubsystems";
import { resetDocumentStore, useDocumentStore } from "../src/state/documentStore";

const model = modelJson as unknown as Model;
const first = model.diagram.nodes[0]!;

const context: LinkContext = {
  pageIds: new Set(["overview", "plant"]),
  model,
  signalIds: new Set(["Body/theta"]),
};

describe("resolveLink", () => {
  it("resolves page links", () => {
    expect(resolveLink("page:plant", context)).toEqual({ kind: "page", id: "plant" });
    const broken = resolveLink("page:ghost", context);
    expect(broken.kind).toBe("broken");
    expect(describeLink(broken)).toContain('no page "ghost"');
    expect(describeLink(broken)).toContain("same docs only");
  });

  it("says that a page link cannot reach another model's docs", () => {
    for (const href of ["page:maglev-bondgraph/overview", "page:other.docs/plant"]) {
      const broken = resolveLink(href, context);
      expect(broken.kind).toBe("broken");
      expect(describeLink(broken)).toContain("not a page id");
      expect(describeLink(broken)).toContain("same docs only");
    }
  });

  it("resolves block links by node name, with the id for selection", () => {
    expect(resolveLink(`block:${first.name}`, context)).toEqual({
      kind: "block",
      path: [],
      nodeId: first.id,
      name: first.name,
    });
    const broken = resolveLink("block:Nope", context);
    expect(broken.kind).toBe("broken");
    expect(describeLink(broken)).toContain("check the block name");
    expect(resolveLink("block:X", { ...context, model: null }).kind).toBe("broken");
  });

  it("finds blocks inside subsystems", () => {
    const nested = structuredClone(model);
    const inner = structuredClone(first);
    inner.id = "inner1";
    inner.name = "Inner";
    const sub = {
      ...structuredClone(first),
      id: "sub1",
      name: "Sub",
      block: { subsystem: { ports: [], diagram: { nodes: [inner], connections: [], annotations: [] } } },
    } as unknown as Model["diagram"]["nodes"][number];
    nested.diagram.nodes.push(sub);
    expect(findBlock(nested, "Sub/Inner")).toEqual({ path: ["sub1"], nodeId: "inner1", name: "Inner" });
    expect(findBlock(nested, "Inner")).toBeNull();
    expect(findBlock(nested, `${first.name}/Inner`)).toBeNull();
  });

  describe("blocks inside an instance of a library subsystem", () => {
    // The saved form: `A` and `B` are `project:Branch` references, the definition alongside.
    const saved = linkedJson as unknown as Model;
    // What the editor holds: every instance as a working copy of the definition.
    const open = hydrateModel({ ...saved, definitions: undefined }, saved.definitions ?? {});
    const linked: LinkContext = { ...context, model: open };

    it("resolves into the instance's own copy of the definition", () => {
      expect(resolveLink("block:A/R1", linked)).toEqual({ kind: "block", path: ["i1"], nodeId: "r", name: "R1" });
      expect(resolveLink("block:B/C1", linked)).toEqual({ kind: "block", path: ["i2"], nodeId: "c", name: "C1" });
      expect(resolveLink("block:A", linked)).toEqual({ kind: "block", path: [], nodeId: "i1", name: "A" });
    });

    it("rejects a name the definition does not have, and a path through a plain block", () => {
      for (const href of ["block:A/Ghost", "block:A/R1/x", "block:Se1/R1", "block:Branch/R1", "block:R1"]) {
        const broken = resolveLink(href, linked);
        expect(broken.kind, href).toBe("broken");
        expect(describeLink(broken)).toContain("instance of a library subsystem");
      }
    });

    it("opens the instance and selects the node, as the breadcrumb does", () => {
      resetDocumentStore();
      useDocumentStore.getState().openDocument("p", "Linked", open);
      const target = findBlock(open, "B/R1")!;
      expect(useDocumentStore.getState().selectNodeAt(target.path, target.nodeId)).toBe(true);
      expect(useDocumentStore.getState().activePath).toEqual(["i2"]);
      expect(useDocumentStore.getState().selection.nodes).toEqual(["r"]);
    });

    it("checks a reference that is not hydrated against the definitions and shows the instance", () => {
      // `saved` keeps the instances as references: they cannot be opened, the path can be checked.
      expect(findBlock(saved, "A/R1")).toEqual({ path: [], nodeId: "i1", name: "R1" });
      expect(findBlock(saved, "A/Ghost")).toBeNull();
      expect(findBlock({ ...saved, definitions: undefined }, "A/R1")).toBeNull();
    });

    it("follows an instance inside another definition", () => {
      const outer = structuredClone(saved.definitions!.Branch!);
      outer.name = "Pair";
      outer.diagram.nodes = [
        { id: "p1", name: "Left", block: { ref: "project:Branch" }, position: { x: 0, y: 0 } },
      ] as Model["diagram"]["nodes"];
      outer.diagram.connections = [];
      const files = { ...saved.definitions, Pair: outer };
      const doc = structuredClone(saved);
      doc.definitions = undefined;
      doc.diagram.nodes.push({
        id: "i3",
        name: "P",
        block: { ref: "project:Pair" },
        position: { x: 0, y: 0 },
      } as Model["diagram"]["nodes"][number]);
      expect(findBlock(hydrateModel(doc, files), "P/Left/C1")).toEqual({ path: ["i3", "p1"], nodeId: "c", name: "C1" });
      expect(findBlock(hydrateModel(doc, files), "P/Left/Ghost")).toBeNull();
      expect(findBlock({ ...doc, definitions: files }, "P/Left/C1")).toEqual({ path: [], nodeId: "i3", name: "C1" });
    });
  });

  it("checks signals against the latest run when there is one", () => {
    expect(resolveLink("signal:Body/theta", context)).toEqual({ kind: "signal", id: "Body/theta" });
    const missing = resolveLink("signal:Body/phi", context);
    expect(missing.kind).toBe("broken");
    expect(describeLink(missing)).toContain("run the model again");
    expect(resolveLink("signal:Body/phi", { ...context, signalIds: null }).kind).toBe("signal");
    expect(resolveLink("signal:", context).kind).toBe("broken");
  });

  it("passes external and anchor links and breaks unsupported ones", () => {
    expect(resolveLink("https://example.org/x", context).kind).toBe("external");
    expect(resolveLink("#fn-1", context).kind).toBe("anchor");
    expect(resolveLink("javascript:alert(1)", context).kind).toBe("broken");
    expect(resolveLink("other/page.md", context).kind).toBe("broken");
    expect(resolveLink(undefined, context).kind).toBe("broken");
  });
});

describe("links between the project docs and the docs of other models", () => {
  const wikis: LinkContext = {
    ...context,
    projectPageIds: new Set(["rig", "safety"]),
    modelPages: modelPagesOf([
      { name: "Plant", docs: { pages: [{ id: "overview", children: [{ id: "tuning", children: [] }] }] } },
      { name: "Bare", docs: { pages: [] } },
    ]),
  };

  it("resolves project: links to pages of the project docs", () => {
    expect(resolveLink("project:rig", wikis)).toEqual({ kind: "project-page", id: "rig" });
    expect(describeLink(resolveLink("project:rig", wikis))).toBe("Open page rig of the project docs");
    const missing = resolveLink("project:ghost", wikis);
    expect(missing.kind).toBe("broken");
    expect(describeLink(missing)).toContain('no page "ghost" in the project docs');
    const none = resolveLink("project:rig", { ...wikis, projectPageIds: new Set() });
    expect(describeLink(none)).toContain("no project docs yet");
    expect(describeLink(resolveLink("project:rig", context))).toContain("docs pages only");
  });

  it("resolves model: links to a page or the first page of another model's docs", () => {
    expect(resolveLink("model:Plant/tuning", wikis)).toEqual({ kind: "model-page", model: "Plant", id: "tuning" });
    expect(resolveLink("model:Plant", wikis)).toEqual({ kind: "model-page", model: "Plant", id: "overview" });
    expect(describeLink(resolveLink("model:Plant", wikis))).toBe("Open page overview of the docs of Plant");
  });

  it("breaks model: links to unknown models, models without docs and unknown pages", () => {
    const reasons = ["model:Ghost/x", "model:Bare", "model:Plant/ghost", "model:", "model:/x"].map((href) => {
      const target = resolveLink(href, wikis);
      expect(target.kind).toBe("broken");
      return describeLink(target);
    });
    expect(reasons[0]).toContain('no model "Ghost"');
    expect(reasons[1]).toContain("has no docs yet");
    expect(reasons[2]).toContain('no page "ghost"');
    expect(reasons[3]).toContain("Name the model");
    expect(reasons[4]).toContain("Name the model");
    expect(describeLink(resolveLink("model:Plant", context))).toContain("docs pages only");
  });

  it("keeps page: links inside the docs they are in", () => {
    const inProject: LinkContext = { ...wikis, wiki: "project", pageIds: new Set(["rig", "safety"]) };
    expect(resolveLink("page:safety", inProject)).toEqual({ kind: "page", id: "safety" });
    expect(resolveLink("page:plant", inProject).kind).toBe("broken");
    expect(describeLink(resolveLink("page:plant", inProject))).toContain("project:<id>");
  });

  it("breaks block: and signal: links in the project docs, with the way out", () => {
    const inProject: LinkContext = { ...wikis, wiki: "project" };
    for (const href of [`block:${first.name}`, "signal:Body/theta"]) {
      const target = resolveLink(href, inProject);
      expect(target.kind).toBe("broken");
      expect(describeLink(target)).toContain("model:<name>/<id>");
    }
  });

  it("overrides a model's tree with its live state", () => {
    const pages = modelPagesOf(
      [{ name: "Plant", docs: { pages: [{ id: "old", children: [] }] } }],
      { Plant: [{ id: "new", children: [] }] },
    );
    expect(pages.get("Plant")).toEqual(["new"]);
  });
});

describe("page references in URLs", () => {
  it("reads and writes the link syntax", () => {
    expect(parseDocsRef("project:rig")).toEqual({ wiki: "project", id: "rig" });
    expect(parseDocsRef("model:Plant/tuning")).toEqual({ wiki: "model", model: "Plant", id: "tuning" });
    expect(parseDocsRef("model:Plant")).toEqual({ wiki: "model", model: "Plant", id: null });
    expect(parseDocsRef("overview")).toEqual({ wiki: "model", model: null, id: "overview" });
    for (const bad of [null, "", "project:", "model:", "Bad Id", "../x"]) {
      expect(parseDocsRef(bad)).toBeNull();
    }
    for (const text of ["project:rig", "model:Plant/tuning", "model:Plant", "overview"]) {
      expect(formatDocsRef(parseDocsRef(text)!)).toBe(text);
    }
  });
});
