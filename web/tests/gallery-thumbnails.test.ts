/**
 * The committed gallery assets (W5.4): every thumbnail is a PNG well under the 100 kB budget and has
 * a manifest entry with a title and a one-line description; every example the manifest knows is
 * resolved to its thumbnail URL by `exampleInfo`.
 */

import { readdirSync, readFileSync, statSync } from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

import { describe, expect, it } from "vitest";

import { exampleInfo } from "../src/examples/gallery";

const here = path.dirname(fileURLToPath(import.meta.url));
const thumbnails = path.join(here, "..", "src", "examples", "thumbnails");
const manifest = JSON.parse(
  readFileSync(path.join(here, "..", "src", "examples", "gallery.json"), "utf8"),
) as Record<string, { title?: string; description?: string; hasScene?: boolean; models?: string[] }>;

const files = readdirSync(thumbnails).filter((name) => name.endsWith(".png"));

describe("gallery thumbnails", () => {
  it("has a thumbnail for the examples captured so far", () => {
    expect(files.length).toBeGreaterThan(10);
  });

  it("keeps every thumbnail a PNG under 100 kB", () => {
    for (const file of files) {
      const full = path.join(thumbnails, file);
      expect(statSync(full).size, file).toBeLessThan(100 * 1024);
      const signature = readFileSync(full).subarray(0, 8).toString("hex");
      expect(signature, `${file} is a PNG`).toBe("89504e470d0a1a0a");
    }
  });

  it("describes every captured example with a title and a one-line description", () => {
    for (const file of files) {
      const name = file.replace(/\.png$/, "");
      const entry = manifest[name];
      expect(entry, `${name} in gallery.json`).toBeDefined();
      expect(entry?.title?.length ?? 0).toBeGreaterThan(0);
      const description = entry?.description ?? "";
      expect(description.length).toBeGreaterThan(10);
      expect(description.length).toBeLessThanOrEqual(171);
      expect(description).not.toContain("\n");
    }
  });

  it("resolves each captured example to its thumbnail and the manifest text", () => {
    for (const file of files) {
      const name = file.replace(/\.png$/, "");
      const info = exampleInfo(name);
      expect(info.thumbnail, name).not.toBeNull();
      expect(info.title).toBe(manifest[name]?.title);
    }
  });
});
