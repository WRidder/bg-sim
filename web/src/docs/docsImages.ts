/**
 * Image handling of the Docs tab (W5.6): the width syntax, content-hash names, the paste/drop
 * pipeline and the decision about copying assets between models. Everything here is free of
 * React and the DOM so it is unit-tested directly; `docsApi.ts` supplies the network calls.
 */

/** Largest accepted image (bytes); the backend enforces the same limit. */
export const MAX_IMAGE_BYTES = 10 * 1024 * 1024;

/** Image media types the docs accept, and the extension each is stored with. */
export const IMAGE_EXTENSIONS: Readonly<Record<string, string>> = {
  "image/png": "png",
  "image/jpeg": "jpg",
  "image/gif": "gif",
  "image/webp": "webp",
  "image/svg+xml": "svg",
};

/** The custom clipboard type that carries the origin of copied Markdown. */
export const DOCS_CLIP_MIME = "application/x-bgsim-docs";

const ASSET_REF = /assets\/([0-9a-f]{12}\.(?:png|jpg|gif|webp|svg))/g;

export interface ParsedAlt {
  alt: string;
  /** Display width in CSS pixels, or `null`. */
  width: number | null;
}

/** `![alt|300](...)`: a trailing `|<digits>` in the alt text sets the width. */
export function parseImageAlt(raw: string): ParsedAlt {
  const match = /^(.*)\|\s*(\d{1,4})\s*$/.exec(raw);
  if (match === null) {
    return { alt: raw, width: null };
  }
  const width = Number(match[2]);
  if (width < 16 || width > 4000) {
    return { alt: raw, width: null };
  }
  return { alt: (match[1] ?? "").trimEnd(), width };
}

/** The asset names a page text refers to, in order of first appearance. */
export function assetRefs(text: string): string[] {
  const found = new Set<string>();
  for (const match of text.matchAll(ASSET_REF)) {
    const name = match[1];
    if (name !== undefined) {
      found.add(name);
    }
  }
  return [...found];
}

export function assetUrl(project: string, model: string, file: string, base = ""): string {
  const enc = encodeURIComponent;
  return `${base}/api/projects/${enc(project)}/docs/${enc(model)}/assets/${enc(file)}`;
}

/** The Markdown that inserts an uploaded asset. */
export function imageMarkdown(file: string, alt = ""): string {
  return `![${alt}](assets/${file})`;
}

/** The first 12 hex digits of the SHA-256 of `bytes` plus the extension for `mime`. */
export async function contentName(bytes: ArrayBuffer, mime: string): Promise<string> {
  const extension = IMAGE_EXTENSIONS[mime];
  if (extension === undefined) {
    throw new Error(`unsupported image type ${mime}`);
  }
  const digest = await crypto.subtle.digest("SHA-256", bytes);
  const hex = [...new Uint8Array(digest)]
    .slice(0, 6)
    .map((byte) => byte.toString(16).padStart(2, "0"))
    .join("");
  return `${hex}.${extension}`;
}

/** A diagnostic for a file that cannot be added as an image, or `null` when it is fine. */
export function imageProblem(file: { name: string; type: string; size: number }): string | null {
  if (IMAGE_EXTENSIONS[file.type] === undefined) {
    return `"${file.name || "The pasted file"}" is ${file.type || "of an unknown type"}; use a PNG, JPEG, GIF, WebP or SVG image.`;
  }
  if (file.size === 0) {
    return `"${file.name || "The pasted image"}" is empty; copy the image again.`;
  }
  if (file.size > MAX_IMAGE_BYTES) {
    const megabytes = (file.size / (1024 * 1024)).toFixed(1);
    return `"${file.name || "The pasted image"}" is ${megabytes} MB; the limit is ${MAX_IMAGE_BYTES / (1024 * 1024)} MB. Scale it down or save it as JPEG or WebP.`;
  }
  return null;
}

/** The image files of a clipboard or drop payload. */
export function imageFilesOf(data: { files?: ArrayLike<File> | null } | null): File[] {
  return data?.files === undefined || data.files === null
    ? []
    : Array.from(data.files).filter((file) => file.type.startsWith("image/"));
}

export interface ImageDeps {
  /** Upload one file; the backend names it by content hash and dedupes. */
  upload: (file: File) => Promise<{ file: string }>;
  /** Asset names known to exist already; a known hash name is not uploaded again. */
  known: ReadonlySet<string>;
  /** Called after an upload so the caller can extend its known set. */
  onUploaded?: (name: string) => void;
}

export interface ImageResult {
  /** Markdown to insert at the cursor, one image per line. */
  markdown: string;
  /** Diagnostics for the files that were refused or failed. */
  problems: string[];
  /** The asset names that were inserted. */
  names: string[];
}

/** Turn pasted or dropped image files into assets and the Markdown that shows them. */
export async function addImages(files: readonly File[], deps: ImageDeps): Promise<ImageResult> {
  const lines: string[] = [];
  const names: string[] = [];
  const problems: string[] = [];
  for (const file of files) {
    const problem = imageProblem(file);
    if (problem !== null) {
      problems.push(problem);
      continue;
    }
    try {
      let name = await contentName(await file.arrayBuffer(), file.type);
      if (!deps.known.has(name)) {
        const stored = await deps.upload(file);
        name = stored.file;
        deps.onUploaded?.(name);
      }
      names.push(name);
      lines.push(imageMarkdown(name));
    } catch (error) {
      problems.push(error instanceof Error ? error.message : String(error));
    }
  }
  return { markdown: lines.join("\n"), problems, names };
}

// --------------------------------------------------------------------------- cross-model copy

export interface ClipSource {
  project: string;
  model: string;
  text: string;
}

export interface ModelRef {
  project: string;
  model: string;
}

export type PastePlan =
  | { kind: "images"; files: File[] }
  | { kind: "copy-assets"; from: ModelRef; files: string[] }
  | { kind: "default" };

/** Normalise line endings and trailing space so copied and pasted text can be compared. */
function normalised(text: string): string {
  return text.replace(/\r\n?/g, "\n").trim();
}

/**
 * What a paste into `target` has to do. Image files win (they are uploaded, which dedupes by
 * hash). Otherwise pasted Markdown that refers to assets of a different model needs those
 * assets copied; the origin comes from the custom clipboard type or the remembered copy.
 */
export function planPaste(input: {
  files: readonly File[];
  text: string;
  custom: string | null;
  remembered: ClipSource | null;
  target: ModelRef;
}): PastePlan {
  if (input.files.length > 0) {
    return { kind: "images", files: [...input.files] };
  }
  let source: ClipSource | null = null;
  if (input.custom !== null) {
    try {
      const parsed = JSON.parse(input.custom) as Partial<ClipSource>;
      if (typeof parsed.project === "string" && typeof parsed.model === "string") {
        source = { project: parsed.project, model: parsed.model, text: parsed.text ?? input.text };
      }
    } catch {
      source = null;
    }
  }
  if (
    source === null &&
    input.remembered !== null &&
    normalised(input.remembered.text) === normalised(input.text)
  ) {
    source = input.remembered;
  }
  if (source === null) {
    return { kind: "default" };
  }
  if (source.project === input.target.project && source.model === input.target.model) {
    return { kind: "default" };
  }
  const files = assetRefs(input.text);
  if (files.length === 0) {
    return { kind: "default" };
  }
  return {
    kind: "copy-assets",
    from: { project: source.project, model: source.model },
    files,
  };
}

const REMEMBER_KEY = "bgsim.docs.lastCopy";
let lastCopy: ClipSource | null = null;

/** Remember where copied Markdown came from (also across browser tabs of this origin). */
export function rememberCopy(source: ClipSource): void {
  lastCopy = source;
  try {
    localStorage.setItem(REMEMBER_KEY, JSON.stringify(source));
  } catch {
    // Private mode or blocked storage: the in-memory copy still serves this tab.
  }
}

export function recallCopy(): ClipSource | null {
  if (lastCopy !== null) {
    return lastCopy;
  }
  try {
    const raw = localStorage.getItem(REMEMBER_KEY);
    return raw === null ? null : (JSON.parse(raw) as ClipSource);
  } catch {
    return null;
  }
}

export function forgetCopy(): void {
  lastCopy = null;
}
