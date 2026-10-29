import { describe, expect, it } from "vitest";

import modelJson from "../../contracts/fixtures/model/valid/model.dcmotor.bondgraph.json";
import type { Model } from "../src/contracts/model";
import { describeLink, findBlock, resolveLink, type LinkContext } from "../src/docs/docsLinks";

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
