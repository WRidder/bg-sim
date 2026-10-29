/**
 * What the example gallery knows about an example beyond its name: a title, a
 * one-line description, whether it ships a 3D scene and a thumbnail.
 *
 * `GET /api/examples` is the authority on which examples exist. This module adds
 * the presentation: `gallery.json` and `thumbnails/<example>.png` are written by
 * `npm run capture-thumbnails` (scripts/capture-thumbnails.mjs), which reads each
 * example's README and renders its diagram and scene in a browser. An example
 * that has not been captured yet still gets a card, with a neutral placeholder.
 *
 * The thumbnails live next to this module (not in `public/`) so Vite fingerprints
 * them and the gallery only ships the images of the examples it lists.
 */

import manifest from "./gallery.json";

export interface ExampleInfo {
  name: string;
  title: string;
  description: string;
  hasScene: boolean;
  models: string[];
  /** The thumbnail URL, or null while the example has none (placeholder card). */
  thumbnail: string | null;
}

interface ManifestEntry {
  title?: string;
  description?: string;
  hasScene?: boolean;
  models?: string[];
}

const thumbnails = import.meta.glob("./thumbnails/*.png", {
  eager: true,
  query: "?url",
  import: "default",
}) as Record<string, string>;

const entries = manifest as Record<string, ManifestEntry>;

/** `dc-motor` -> `Dc motor`, the title of an example without a README. */
export function titleFromName(name: string): string {
  const spaced = name.replace(/[-_]+/g, " ").trim();
  return spaced.length === 0 ? name : spaced.charAt(0).toUpperCase() + spaced.slice(1);
}

export const FALLBACK_DESCRIPTION =
  "A sample project. Open it to import an editable copy; the sample itself never changes.";

export function exampleInfo(name: string): ExampleInfo {
  const entry = entries[name] ?? {};
  return {
    name,
    title: entry.title && entry.title.length > 0 ? entry.title : titleFromName(name),
    description:
      entry.description && entry.description.length > 0 ? entry.description : FALLBACK_DESCRIPTION,
    hasScene: entry.hasScene === true,
    models: entry.models ?? [],
    thumbnail: thumbnails[`./thumbnails/${name}.png`] ?? null,
  };
}

/**
 * The examples that get a card. A directory the tooling leaves in `examples/` (`__pycache__`, a
 * dot-folder) is not an example, even when the backend lists it.
 */
export function galleryExamples(names: readonly string[]): string[] {
  return names.filter((name) => !name.startsWith("_") && !name.startsWith("."));
}
