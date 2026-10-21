/**
 * Contract tests (M0.2), the TypeScript half of the pair in
 * backend/tests/test_contracts.py.
 *
 * Every fixture under contracts/fixtures/<name>/valid/ must validate against
 * contracts/schemas/<name>.schema.json with Ajv (2020-12), every fixture under
 * contracts/fixtures/<name>/invalid/ must fail, and the fixtures must cover
 * what the work package asks for (one diagnostic per code, the M1 blocks, the
 * spec's binding examples, the synthetic run's columns).
 */

import { readFileSync, readdirSync } from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

import Ajv2020 from "ajv/dist/2020";
import addFormats from "ajv-formats";
import { describe, expect, it } from "vitest";

import type { Binding, Model, RunManifest, RunStartRequest, RunTime, WorkerRpc } from "../src/contracts";

const here = path.dirname(fileURLToPath(import.meta.url));
const repoRoot = path.resolve(here, "..", "..");
const schemaDir = path.join(repoRoot, "contracts", "schemas");
const fixtureDir = path.join(repoRoot, "contracts", "fixtures");

/** The schema base names of the fixture layout (plan section 3, orchestrator notes 2). */
const schemaNames = [
  "catalog",
  "model",
  "project",
  "diagnostic",
  "run-manifest",
  "worker-rpc",
  "stream-handshake",
  "bindings",
] as const;
type SchemaName = (typeof schemaNames)[number];

function readJson(file: string): unknown {
  return JSON.parse(readFileSync(file, "utf8"));
}

const ajv = new Ajv2020({ allErrors: true, strict: true });
addFormats(ajv);
for (const name of schemaNames) {
  const schema = readJson(path.join(schemaDir, `${name}.schema.json`)) as { $id: string };
  ajv.addSchema(schema, schema.$id);
}

function validator(name: SchemaName) {
  const validate = ajv.getSchema(`https://bgsim.local/schemas/${name}.schema.json`);
  if (!validate) {
    throw new Error(`schema ${name} is not registered`);
  }
  return validate;
}

function fixtureFiles(kind: "valid" | "invalid"): { name: SchemaName; file: string; label: string }[] {
  const cases: { name: SchemaName; file: string; label: string }[] = [];
  for (const name of schemaNames) {
    const base = path.join(fixtureDir, name, kind);
    let entries: string[];
    try {
      entries = readdirSync(base, { recursive: true }) as string[];
    } catch {
      continue;
    }
    for (const entry of entries.filter((e) => e.endsWith(".json")).sort()) {
      cases.push({ name, file: path.join(base, entry), label: `${name}/${entry.split(path.sep).join("/")}` });
    }
  }
  return cases;
}

const validFixtures = fixtureFiles("valid");
const invalidFixtures = fixtureFiles("invalid");

describe("schemas", () => {
  it("registers all eight schemas", () => {
    expect(schemaNames).toHaveLength(8);
    for (const name of schemaNames) {
      expect(validator(name)).toBeTypeOf("function");
    }
  });

  it("has at least one valid and two invalid fixtures per schema", () => {
    for (const name of schemaNames) {
      expect(validFixtures.filter((c) => c.name === name).length).toBeGreaterThanOrEqual(1);
      expect(invalidFixtures.filter((c) => c.name === name).length).toBeGreaterThanOrEqual(2);
    }
  });
});

describe("valid fixtures", () => {
  it.each(validFixtures.map((c) => [c.label, c] as const))("%s validates", (_label, testCase) => {
    const validate = validator(testCase.name);
    const ok = validate(readJson(testCase.file));
    expect(validate.errors, JSON.stringify(validate.errors, null, 2)).toBeNull();
    expect(ok).toBe(true);
  });
});

describe("invalid fixtures", () => {
  it.each(invalidFixtures.map((c) => [c.label, c] as const))("%s is rejected", (_label, testCase) => {
    expect(validator(testCase.name)(readJson(testCase.file))).toBe(false);
  });

  it("explains every rejection in a $comment", () => {
    for (const testCase of invalidFixtures) {
      const document = readJson(testCase.file);
      const comment = Array.isArray(document)
        ? (document as { $comment?: string }[]).find((item) => item.$comment)?.$comment
        : (document as { $comment?: string }).$comment;
      expect(comment, `${testCase.label} needs a $comment`).toBeTruthy();
    }
  });
});

describe("fixture coverage", () => {
  const m1Blocks = [
    "stdlib:bondgraph/Se",
    "stdlib:bondgraph/Sf",
    "stdlib:bondgraph/MSe",
    "stdlib:bondgraph/C",
    "stdlib:bondgraph/I",
    "stdlib:bondgraph/R",
    "stdlib:bondgraph/TF",
    "stdlib:bondgraph/GY",
    "stdlib:bondgraph/De",
    "stdlib:bondgraph/Df",
    "stdlib:sources/Constant",
    "stdlib:sources/Step",
    "stdlib:sources/Sine",
    "stdlib:continuous/Gain",
    "stdlib:continuous/Sum",
    "stdlib:continuous/Integrator",
    "stdlib:continuous/PIController",
    "stdlib:electrical/Resistor",
    "stdlib:electrical/Capacitor",
    "stdlib:electrical/Inductor",
    "stdlib:electrical/Ground",
    "stdlib:electrical/VoltageSource",
    "stdlib:translation/Mass",
    "stdlib:translation/Spring",
    "stdlib:translation/Damper",
    "stdlib:translation/Fixed",
    "stdlib:translation/ForceSource",
    "stdlib:rotation/Inertia",
    "stdlib:rotation/TorsionSpring",
    "stdlib:rotation/RotationalDamper",
    "stdlib:rotation/FixedShaft",
    "stdlib:rotation/TorqueSource",
    "stdlib:rotation/IdealGear",
    "stdlib:converters/DCMotor",
    "stdlib:converters/SpeedSensor",
    "stdlib:converters/AngleSensor",
  ];

  it("catalog.min.json has every M1 block, both junctions and five domains", () => {
    const catalog = readJson(path.join(fixtureDir, "catalog", "valid", "catalog.min.json")) as {
      blocks: { ref: string; source: string }[];
      junctions: { ref: string }[];
      domains: { name: string }[];
    };
    const refs = catalog.blocks.map((block) => block.ref);
    for (const ref of m1Blocks) {
      expect(refs, `missing ${ref}`).toContain(ref);
    }
    for (const block of catalog.blocks) {
      expect(block.source.startsWith("@block "), `${block.ref} has no @block source`).toBe(true);
    }
    expect(catalog.junctions.map((j) => j.ref)).toEqual(["junction:0", "junction:1"]);
    expect(catalog.domains.map((d) => d.name)).toEqual([
      "Electrical",
      "Translation",
      "Rotation",
      "Hydraulic",
      "Generic",
    ]);
  });

  it("diagnostics.sample.json has one instance of every code", () => {
    const codes = [
      "E000", "E001", "E002", "E003", "E004", "E005", "E006",
      "E101", "E102", "E103", "E104", "E105", "E106",
      "E900", "E901",
      "W201", "W202", "W203", "W204", "W205", "W206",
      "E301", "E302", "E303", "E304",
    ];
    const sample = readJson(path.join(fixtureDir, "diagnostic", "valid", "diagnostics.sample.json")) as {
      code: string;
      path: string | null;
      message: string;
    }[];
    expect(sample.map((item) => item.code).sort()).toEqual([...codes].sort());
    for (const item of sample) {
      expect(item.message, `${item.code} has no message`).toBeTruthy();
      expect(item.path, `${item.code} has no path`).not.toBeNull();
    }
  });

  it("bindings.robot.json has the five spec examples", () => {
    const { bindings } = readJson(path.join(fixtureDir, "bindings", "valid", "bindings.robot.json")) as {
      bindings: { target: string; property: string; signal: string | string[] }[];
    };
    expect(bindings.map((binding) => binding.property)).toEqual([
      "position",
      "pose",
      "scale.z",
      "color",
      "visible",
    ]);
    const pose = bindings.find((binding) => binding.property === "pose");
    expect(Array.isArray(pose?.signal) ? pose.signal.length : 0).toBe(7);
  });

  it("the synthetic run manifest lists the generated columns in order", () => {
    const manifest = readJson(
      path.join(fixtureDir, "run-manifest", "valid", "run.synthetic", "manifest.json"),
    ) as { layout: string; signals: { id: string }[]; time: { n: number } };
    expect(manifest.layout).toBe("columnar-f64-v1");
    expect(manifest.signals.map((signal) => signal.id)).toEqual([
      "Synthetic/sine",
      "Synthetic/step",
      "Synthetic/counter",
      "Synthetic/flag",
    ]);
    expect(manifest.time.n).toBe(1001);
  });
});

describe("generated TypeScript", () => {
  it("types a manifest and a worker message the way the schemas describe them", () => {
    const manifest = readJson(
      path.join(fixtureDir, "run-manifest", "valid", "run.synthetic", "manifest.json"),
    ) as RunManifest;
    const time: RunTime = manifest.time;
    expect(time.n).toBe(1001);
    expect(manifest.signals[0].kind).toBe("output");

    const message: WorkerRpc = {
      id: 1,
      method: "ping",
      params: {},
    };
    expect(message.method).toBe("ping");

    const request: RunStartRequest = {
      id: 43,
      method: "run.start",
      params: {
        runId: "run-1",
        model: manifest as unknown as Model,
        projectDir: "C:/p",
        runDir: "C:/p/runs/run-1",
      },
    };
    expect(request.method).toBe("run.start");

    const binding: Binding = { target: "joint:shoulder", property: "position", signal: "A/B/phi" };
    expect(binding.property).toBe("position");
  });
});
