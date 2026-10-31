/**
 * The Export dialog's tunables editor (W-EX1, J-EX8): the candidates the browser offers, the
 * range checks, "expose all globals", the request and the report's cost line.
 */

import { describe, expect, it } from "vitest";

import catalogJson from "../../contracts/fixtures/catalog/valid/catalog.min.json";
import globalsJson from "../../contracts/fixtures/model/valid/model.global-parameters.json";
import type { Catalog } from "../src/contracts/catalog";
import type { Model } from "../src/contracts/model";
import {
  exposeAllGlobals,
  listTunableCandidates,
  newTunableRow,
  rowOpen,
  rowProblem,
  tunableCostText,
  tunablesRequest,
  type TunableCandidate,
} from "../src/export/exportTunables";
import { buildCatalogIndex } from "../src/library/catalogIndex";

const index = buildCatalogIndex(catalogJson as unknown as Catalog);
const globalsModel = globalsJson as unknown as Model;

function byId(candidates: TunableCandidate[]): Map<string, TunableCandidate> {
  return new Map(candidates.map((c) => [c.id, c]));
}

describe("listTunableCandidates", () => {
  it("lists the globals first; a driven global is blocked", () => {
    const candidates = listTunableCandidates(globalsModel, null, index);
    expect(candidates.slice(0, 3).map((c) => c.id)).toEqual(["global:m", "global:rate", "global:x0"]);
    const m = byId(candidates).get("global:m");
    expect(m).toMatchObject({ kind: "global", value: 2, unit: "kg", blocked: null, min: null, max: null });
    expect(byId(candidates).get("global:rate")?.blocked).toMatch(/equation over m/);
  });

  it("offers block parameters by instance path; one computed from a global is blocked", () => {
    const candidates = byId(listTunableCandidates(globalsModel, null, index));
    const rate = candidates.get("Source/Rate/value");
    expect(rate?.kind).toBe("parameter");
    expect(rate?.value).toBe(8);
    expect(rate?.blocked).toMatch(/expose the global instead/);
    expect(candidates.get("Int1/lower")?.kind).toBe("parameter");
  });

  it("names a subsystem's parameters as the scoped model does, and needs the catalog", () => {
    const scoped = listTunableCandidates(globalsModel, "Source", index).map((c) => c.id);
    expect(scoped).toContain("Source/Rate/value");
    expect(scoped).not.toContain("Int1/lower");
    expect(listTunableCandidates(globalsModel, null, null).every((c) => c.kind === "global")).toBe(true);
  });

  it("blocks a parameter the catalog already makes tunable at runtime", () => {
    const doc: Pick<Model, "diagram" | "parameters"> = {
      diagram: {
        nodes: [{ id: "n1", name: "R1", block: { ref: "stdlib:bondgraph/R" }, position: { x: 0, y: 0 }, params: { r: "2.5" } }],
        connections: [],
      },
    };
    const r = listTunableCandidates(doc, null, index).find((c) => c.id === "R1/r");
    expect(r?.value).toBe(2.5);
    const decl = index.blocksByRef.get("stdlib:bondgraph/R")?.parameters.find((p) => p.name === "r");
    expect(r?.blocked).toBe(decl?.tunable ? "already tunable at runtime" : null);
  });
});

describe("rows", () => {
  const candidate: TunableCandidate = {
    id: "Motor/R", kind: "parameter", value: 2, unit: "Ohm", min: 0.5, max: null, description: "", blocked: null,
  };

  it("start from the catalog range and check it against the model's value", () => {
    const row = newTunableRow(candidate);
    expect(row).toEqual({ id: "Motor/R", minText: "0.5", maxText: "" });
    expect(rowOpen(row)).toBe(true);
    expect(rowProblem(row, candidate)).toBeNull();
    expect(rowProblem({ ...row, maxText: "4" }, candidate)).toBeNull();
    expect(rowProblem({ ...row, maxText: "abc" }, candidate)).toMatch(/must be numbers/);
    expect(rowProblem({ ...row, minText: "3", maxText: "1" }, candidate)).toBe("min is above max");
    expect(rowProblem({ ...row, minText: "3", maxText: "4" }, candidate)).toMatch(/contain the model's value 2/);
  });

  it("build the request: open ends are left out", () => {
    expect(tunablesRequest([
      { id: "Motor/R", minText: "0.5", maxText: "4" },
      { id: "global:m", minText: "", maxText: " 3 " },
    ])).toEqual([{ id: "Motor/R", min: 0.5, max: 4 }, { id: "global:m", max: 3 }]);
  });

  it("expose all globals adds every independent global once", () => {
    const candidates = listTunableCandidates(globalsModel, null, index);
    const rows = exposeAllGlobals([], candidates);
    expect(rows.map((r) => r.id)).toEqual(["global:m"]);
    expect(exposeAllGlobals(rows, candidates)).toEqual(rows);
  });

  it("the report's cost line compares with everything folded", () => {
    expect(tunableCostText(64, 58)).toBe(
      "64 operations per right-hand side with the tunables, 58 with everything folded (+10.3 %)",
    );
    expect(tunableCostText(64, null)).toBeNull();
  });
});
