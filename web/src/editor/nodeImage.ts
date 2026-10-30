/**
 * Node images (`ui.image`, plan 3.3): an image drawn inside a subsystem card.
 *
 * The image is stored in the model document as bare base64 plus its media type and a fit
 * (`contain` keeps the aspect ratio, `stretch` fills the card body). The contract caps the
 * base64 text at 699052 characters, which is 512 KiB decoded. Instead of refusing a larger
 * image, the editor shrinks it until it fits:
 *
 * - an SVG is kept as it is when it fits, minified (comments, metadata, whitespace, long
 *   decimals) when it does not, and rasterized to PNG when the minified text is still too
 *   large;
 * - a raster image is kept when it fits and is PNG, SVG, WebP or JPEG; otherwise it is
 *   decoded, its longest side is capped at 1024 px, and it is re-encoded and halved until
 *   the result fits. An image with transparency stays PNG; an opaque one may fall back to
 *   WebP and then JPEG.
 *
 * Everything here is free of React; the canvas work goes through a {@link RasterBackend}
 * (`nodeImageRaster.ts` in the browser, a fake in the unit tests).
 *
 * Safety: the editor only ever shows the image through `<img src="data:...">`. An SVG in an
 * `<img>` cannot run scripts or load other resources; the markup is never put in the DOM.
 */

import type { CSSProperties } from "react";

import type { Model, ModelDiagram, ModelNodeImage } from "../contracts/model";

/** Largest decoded image, in bytes (512 KiB). */
export const NODE_IMAGE_MAX_BYTES = 512 * 1024;
/** The schema's `maxLength` of `ui.image.data`: the base64 length of 512 KiB. */
export const NODE_IMAGE_MAX_BASE64 = 4 * Math.ceil(NODE_IMAGE_MAX_BYTES / 3);
/** The longest side of a re-encoded raster image before the halving starts. */
export const NODE_IMAGE_RASTER_CAP = 1024;
/** The halving stops below this longest side. */
export const NODE_IMAGE_MIN_SIDE = 8;
/** Quality of the lossy fallbacks (WebP, then JPEG). */
export const NODE_IMAGE_LOSSY_QUALITY = 0.85;

export type NodeImageMime = ModelNodeImage["mime"];
export type NodeImageFit = ModelNodeImage["fit"];

export const NODE_IMAGE_MIMES: readonly NodeImageMime[] = [
  "image/png",
  "image/svg+xml",
  "image/webp",
  "image/jpeg",
];

export const NODE_IMAGE_FITS: readonly NodeImageFit[] = ["contain", "stretch"];

/** What the file input accepts (other raster types are converted when the browser decodes them). */
export const NODE_IMAGE_ACCEPT =
  "image/png,image/svg+xml,image/webp,image/jpeg,image/gif,image/bmp,.png,.svg,.webp,.jpg,.jpeg,.gif,.bmp";

const BASE64_PATTERN = /^(?:[A-Za-z0-9+/]{4})*(?:[A-Za-z0-9+/]{2}==|[A-Za-z0-9+/]{3}=)?$/;

/** A problem the user can act on; the message is shown as it is. */
export class NodeImageError extends Error {
  constructor(message: string) {
    super(message);
    this.name = "NodeImageError";
  }
}

export function isNodeImageMime(value: unknown): value is NodeImageMime {
  return typeof value === "string" && (NODE_IMAGE_MIMES as readonly string[]).includes(value);
}

export function isNodeImageFit(value: unknown): value is NodeImageFit {
  return typeof value === "string" && (NODE_IMAGE_FITS as readonly string[]).includes(value);
}

// --------------------------------------------------------------------------- base64

/** Standard base64 without line breaks. */
export function bytesToBase64(bytes: Uint8Array): string {
  let binary = "";
  const chunk = 0x8000;
  for (let start = 0; start < bytes.length; start += chunk) {
    binary += String.fromCharCode(...bytes.subarray(start, start + chunk));
  }
  return btoa(binary);
}

export function base64ToBytes(text: string): Uint8Array {
  const binary = atob(text);
  const bytes = new Uint8Array(binary.length);
  for (let position = 0; position < binary.length; position += 1) {
    bytes[position] = binary.charCodeAt(position);
  }
  return bytes;
}

/** The decoded size of a base64 text, without decoding it. */
export function decodedLength(text: string): number {
  const padding = text.endsWith("==") ? 2 : text.endsWith("=") ? 1 : 0;
  return Math.floor((text.length * 3) / 4) - padding;
}

export function imageDataUrl(image: Pick<ModelNodeImage, "mime" | "data">): string {
  return `data:${image.mime};base64,${image.data}`;
}

/**
 * An SVG that fills any box: `preserveAspectRatio="none"` on the root (and a viewBox from
 * width/height when it has none). An SVG keeps its own aspect ratio inside an `<img>`
 * otherwise, so `object-fit: fill` alone would still letterbox it.
 */
export function stretchSvg(text: string): string {
  return text.replace(/<svg\b[^>]*>/i, (root) => {
    let tag = root.replace(/\spreserveAspectRatio\s*=\s*(?:"[^"]*"|'[^']*')/i, "");
    if (!/\sviewBox\s*=/i.test(tag)) {
      const size = svgSize(tag);
      if (size !== null) {
        tag = tag.replace(/^<svg/i, `<svg viewBox="0 0 ${size.width} ${size.height}"`);
      }
    }
    return tag.replace(/^<svg/i, '<svg preserveAspectRatio="none"');
  });
}

/**
 * The `src` of a node image. A stretched SVG is rewritten with {@link stretchSvg} for the
 * display only; the stored document keeps the SVG as it was.
 */
export function nodeImageSrc(image: Pick<ModelNodeImage, "mime" | "data" | "fit">): string {
  if (image.mime !== "image/svg+xml" || image.fit !== "stretch") {
    return imageDataUrl(image);
  }
  try {
    const text = new TextDecoder().decode(base64ToBytes(image.data));
    return imageDataUrl({ mime: image.mime, data: bytesToBase64(UTF8.encode(stretchSvg(text))) });
  } catch {
    return imageDataUrl(image);
  }
}

/** The `<img>` style of a fit: `contain` letterboxes, `stretch` fills the box. */
export function nodeImageFitStyle(fit: NodeImageFit): CSSProperties {
  return { objectFit: fit === "stretch" ? "fill" : "contain" };
}

export function mimeLabel(mime: string): string {
  switch (mime) {
    case "image/png":
      return "PNG";
    case "image/svg+xml":
      return "SVG";
    case "image/webp":
      return "WebP";
    case "image/jpeg":
      return "JPEG";
    case "image/gif":
      return "GIF";
    case "image/bmp":
      return "BMP";
    default:
      return mime.length > 0 ? mime : "unknown type";
  }
}

/** `812 B`, `410 KB`, `2.3 MB` (1 KB = 1024 bytes, like the 512 KB limit). */
export function formatBytes(bytes: number): string {
  if (bytes < 1024) {
    return `${bytes} B`;
  }
  if (bytes < 1024 * 1024) {
    return `${Math.round(bytes / 1024)} KB`;
  }
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

// --------------------------------------------------------------------------- validation

/** Why a `ui.image` value breaks the contract, or null when it is fine. */
export function nodeImageIssue(image: unknown): string | null {
  if (typeof image !== "object" || image === null || Array.isArray(image)) {
    return "ui.image must be an object with mime, data and fit.";
  }
  const record = image as Record<string, unknown>;
  for (const key of Object.keys(record)) {
    if (key !== "mime" && key !== "data" && key !== "fit" && key !== "$comment") {
      return `ui.image has an unknown field "${key}".`;
    }
  }
  if (!isNodeImageMime(record.mime)) {
    return `ui.image.mime is ${JSON.stringify(record.mime)}; use one of ${NODE_IMAGE_MIMES.join(", ")}.`;
  }
  if (!isNodeImageFit(record.fit)) {
    return `ui.image.fit is ${JSON.stringify(record.fit)}; use contain or stretch.`;
  }
  const data = record.data;
  if (typeof data !== "string" || data.length < 4) {
    return "ui.image.data must be a non-empty base64 text.";
  }
  if (data.length > NODE_IMAGE_MAX_BASE64) {
    return `ui.image.data decodes to ${decodedLength(data)} bytes; the limit is ${NODE_IMAGE_MAX_BYTES} bytes (${formatBytes(NODE_IMAGE_MAX_BYTES)}).`;
  }
  if (!BASE64_PATTERN.test(data)) {
    return "ui.image.data is not standard base64 (no data: prefix, no line breaks).";
  }
  return null;
}

/** Every node of a diagram and its nested subsystems, with its instance path. */
function* walkNodes(
  diagram: ModelDiagram,
  prefix: string,
): Generator<{ path: string; ui: unknown }> {
  // Called on documents straight from disk, so nothing beyond the arrays is trusted.
  for (const node of Array.isArray(diagram.nodes) ? diagram.nodes : []) {
    const path = prefix.length === 0 ? node.name : `${prefix}/${node.name}`;
    yield { path, ui: node.ui };
    const block: unknown = node.block;
    if (typeof block === "object" && block !== null && "subsystem" in block) {
      const inner = (block as { subsystem?: { diagram?: ModelDiagram } }).subsystem?.diagram;
      if (inner !== undefined) {
        yield* walkNodes(inner, path);
      }
    }
  }
}

/** The `ui.image` contract violations of a document, one message per node. */
export function modelImageIssues(doc: Model): string[] {
  const issues: string[] = [];
  for (const { path, ui } of walkNodes(doc.diagram, "")) {
    if (typeof ui !== "object" || ui === null || !("image" in ui)) {
      continue;
    }
    const issue = nodeImageIssue((ui as { image: unknown }).image);
    if (issue !== null) {
      issues.push(`${path}: ${issue}`);
    }
  }
  return issues;
}

// --------------------------------------------------------------------------- SVG

const UTF8 = new TextEncoder();

function stripProlog(text: string): string {
  let rest = (text.charCodeAt(0) === 0xfeff ? text.slice(1) : text).trimStart();
  for (;;) {
    const before = rest;
    rest = rest
      .replace(/^<\?xml[\s\S]*?\?>/i, "")
      .replace(/^<!--[\s\S]*?-->/, "")
      .replace(/^<!DOCTYPE[^>[]*(?:\[[\s\S]*?\])?\s*>/i, "")
      .trimStart();
    if (rest === before) {
      return rest;
    }
  }
}

/** True for SVG markup: an `<svg` root after an optional XML prolog, comments and doctype. */
export function isSvgText(text: string): boolean {
  return /^<svg[\s>/]/i.test(stripProlog(text));
}

/**
 * A smaller SVG with the same drawing: no prolog, comments, metadata, title/desc or editor
 * (Inkscape/Sodipodi) elements, collapsed whitespace and decimals rounded to three places.
 */
export function minifySvg(text: string): string {
  return stripProlog(text)
    .replace(/<!--[\s\S]*?-->/g, "")
    .replace(/<metadata\b[^>]*\/>/gi, "")
    .replace(/<metadata\b[\s\S]*?<\/metadata\s*>/gi, "")
    .replace(/<(title|desc)\b[^>]*>[\s\S]*?<\/\1\s*>/gi, "")
    .replace(/<sodipodi:namedview\b[^>]*\/>/gi, "")
    .replace(/<sodipodi:namedview\b[\s\S]*?<\/sodipodi:namedview\s*>/gi, "")
    .replace(/(\d+\.\d{3})\d+/g, (_match, kept: string) => kept)
    .replace(/>\s+</g, "><")
    .replace(/\s{2,}/g, " ")
    .trim();
}

function svgLength(raw: string | undefined): number | null {
  if (raw === undefined) {
    return null;
  }
  const match = /^\s*([0-9]*\.?[0-9]+)\s*(px)?\s*$/i.exec(raw);
  if (match === null) {
    return null;
  }
  const value = Number(match[1]);
  return value > 0 ? value : null;
}

/** The intrinsic size of an SVG from its width/height or viewBox, or null when it has none. */
export function svgSize(text: string): { width: number; height: number } | null {
  const root = /<svg\b[^>]*>/i.exec(stripProlog(text))?.[0];
  if (root === undefined) {
    return null;
  }
  const attribute = (name: string): string | undefined =>
    new RegExp(`\\s${name}\\s*=\\s*(?:"([^"]*)"|'([^']*)')`, "i").exec(root)?.slice(1).find(
      (value) => value !== undefined,
    );
  const width = svgLength(attribute("width"));
  const height = svgLength(attribute("height"));
  if (width !== null && height !== null) {
    return { width, height };
  }
  const box = attribute("viewBox")
    ?.trim()
    .split(/[\s,]+/)
    .map(Number);
  if (box !== undefined && box.length === 4) {
    const [, , boxWidth = 0, boxHeight = 0] = box;
    if (boxWidth > 0 && boxHeight > 0) {
      return { width: boxWidth, height: boxHeight };
    }
  }
  return null;
}

// --------------------------------------------------------------------------- fitting

/** A decoded image the backend can re-encode at any size. */
export interface DecodedRaster {
  width: number;
  height: number;
  /** True when any pixel is not fully opaque (SVGs are treated as transparent). */
  hasAlpha: boolean;
  /** Draw the image at width x height and encode it; null when the type is not supported. */
  encode: (width: number, height: number, mime: string, quality?: number) => Promise<Blob | null>;
  release?: () => void;
}

export interface RasterBackend {
  decode: (blob: Blob) => Promise<DecodedRaster>;
}

export interface ImageInput {
  bytes: Uint8Array;
  /** The media type the file or clipboard reported; SVG text may come as text/plain. */
  mime: string;
}

export type FitAction = "kept" | "minified" | "compressed" | "rasterized" | "converted";

export interface FittedImage {
  mime: NodeImageMime;
  data: string;
  /** Decoded size of `data`. */
  bytes: number;
  originalBytes: number;
  originalMime: string;
  action: FitAction;
  /** Pixel size after re-encoding; null when the file was stored unchanged. */
  width: number | null;
  height: number | null;
  /** What happened, for the inspector; null when the image was stored as it was. */
  message: string | null;
}

async function blobBytes(blob: Blob): Promise<Uint8Array> {
  if (typeof blob.arrayBuffer === "function") {
    return new Uint8Array(await blob.arrayBuffer());
  }
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => resolve(new Uint8Array(reader.result as ArrayBuffer));
    reader.onerror = () => reject(reader.error ?? new Error("could not read the image"));
    reader.readAsArrayBuffer(blob);
  });
}

/** Scale (width, height) so the longest side is at most `cap`, never up. */
export function capSize(width: number, height: number, cap: number): { width: number; height: number } {
  const longest = Math.max(width, height);
  if (longest <= cap) {
    return { width: Math.max(1, Math.round(width)), height: Math.max(1, Math.round(height)) };
  }
  const scale = cap / longest;
  return {
    width: Math.max(1, Math.round(width * scale)),
    height: Math.max(1, Math.round(height * scale)),
  };
}

function bufferCopy(bytes: Uint8Array): ArrayBuffer {
  const copy = new ArrayBuffer(bytes.byteLength);
  new Uint8Array(copy).set(bytes);
  return copy;
}

/**
 * Re-encode a decoded image until it fits: cap the longest side, then halve it. At each size
 * PNG is tried first; an opaque image then tries WebP and JPEG.
 */
async function shrinkRaster(
  raster: DecodedRaster,
  start: { width: number; height: number },
): Promise<{ mime: NodeImageMime; bytes: Uint8Array; width: number; height: number }> {
  let { width, height } = capSize(start.width, start.height, NODE_IMAGE_RASTER_CAP);
  const encodings: { mime: NodeImageMime; quality?: number }[] = raster.hasAlpha
    ? [{ mime: "image/png" }]
    : [
        { mime: "image/png" },
        { mime: "image/webp", quality: NODE_IMAGE_LOSSY_QUALITY },
        { mime: "image/jpeg", quality: NODE_IMAGE_LOSSY_QUALITY },
      ];
  for (;;) {
    for (const encoding of encodings) {
      const blob = await raster.encode(width, height, encoding.mime, encoding.quality);
      // A canvas that cannot write the type falls back to PNG; only take what was asked for.
      if (blob === null || blob.type !== encoding.mime) {
        continue;
      }
      if (blob.size <= NODE_IMAGE_MAX_BYTES) {
        return { mime: encoding.mime, bytes: await blobBytes(blob), width, height };
      }
    }
    if (Math.max(width, height) / 2 < NODE_IMAGE_MIN_SIDE) {
      throw new NodeImageError(
        `The image does not fit in ${formatBytes(NODE_IMAGE_MAX_BYTES)} even at ${width}×${height}; use a simpler image.`,
      );
    }
    width = Math.max(1, Math.round(width / 2));
    height = Math.max(1, Math.round(height / 2));
  }
}

function result(
  input: ImageInput,
  mime: NodeImageMime,
  bytes: Uint8Array,
  action: FitAction,
  size: { width: number; height: number } | null,
  message: string | null,
): FittedImage {
  return {
    mime,
    data: bytesToBase64(bytes),
    bytes: bytes.length,
    originalBytes: input.bytes.length,
    originalMime: input.mime,
    action,
    width: size?.width ?? null,
    height: size?.height ?? null,
    message,
  };
}

function looksLikeSvg(input: ImageInput): string | null {
  if (input.mime !== "image/svg+xml" && input.mime !== "text/plain" && input.mime !== "") {
    return null;
  }
  const text = new TextDecoder("utf-8", { fatal: false }).decode(input.bytes);
  if (isSvgText(text)) {
    return text;
  }
  if (input.mime === "image/svg+xml") {
    throw new NodeImageError("The SVG file does not start with an <svg> element.");
  }
  return null;
}

/**
 * Turn an image file or clipboard payload into a `ui.image` value within the 512 KiB limit.
 * Throws a {@link NodeImageError} for something that is not an image or cannot be decoded.
 */
export async function fitNodeImage(input: ImageInput, backend: RasterBackend): Promise<FittedImage> {
  if (input.bytes.length === 0) {
    throw new NodeImageError("The image is empty; copy or choose it again.");
  }
  const original = formatBytes(input.bytes.length);
  const svg = looksLikeSvg(input);
  if (svg !== null) {
    if (input.bytes.length <= NODE_IMAGE_MAX_BYTES) {
      return result(input, "image/svg+xml", input.bytes, "kept", null, null);
    }
    const minified = UTF8.encode(minifySvg(svg));
    if (minified.length <= NODE_IMAGE_MAX_BYTES) {
      return result(
        input,
        "image/svg+xml",
        minified,
        "minified",
        null,
        `SVG minified from ${original} to ${formatBytes(minified.length)}.`,
      );
    }
    const blob = new Blob([bufferCopy(minified)], { type: "image/svg+xml" });
    let raster: DecodedRaster;
    try {
      raster = await backend.decode(blob);
    } catch {
      throw new NodeImageError("The SVG could not be drawn, so it cannot be rasterized.");
    }
    try {
      const intrinsic = svgSize(svg) ?? { width: raster.width, height: raster.height };
      // A vector image is drawn at the cap size; it does not get sharper below it.
      const longest = Math.max(intrinsic.width, intrinsic.height, 1);
      const scale = NODE_IMAGE_RASTER_CAP / longest;
      const shrunk = await shrinkRaster(
        { ...raster, hasAlpha: true },
        { width: intrinsic.width * scale, height: intrinsic.height * scale },
      );
      return result(
        input,
        shrunk.mime,
        shrunk.bytes,
        "rasterized",
        shrunk,
        `SVG of ${original} is still ${formatBytes(minified.length)} minified; rasterized to ${mimeLabel(shrunk.mime)} at ${shrunk.width}×${shrunk.height}, ${formatBytes(shrunk.bytes.length)}.`,
      );
    } finally {
      raster.release?.();
    }
  }

  if (!input.mime.startsWith("image/")) {
    throw new NodeImageError(
      `That is ${input.mime.length > 0 ? input.mime : "not an image"}; use a PNG or SVG image (JPEG and WebP work too).`,
    );
  }
  if (isNodeImageMime(input.mime) && input.bytes.length <= NODE_IMAGE_MAX_BYTES) {
    return result(input, input.mime, input.bytes, "kept", null, null);
  }
  let raster: DecodedRaster;
  try {
    raster = await backend.decode(new Blob([bufferCopy(input.bytes)], { type: input.mime }));
  } catch {
    throw new NodeImageError(
      `The ${mimeLabel(input.mime)} image could not be decoded; save it as PNG and try again.`,
    );
  }
  try {
    const shrunk = await shrinkRaster(raster, { width: raster.width, height: raster.height });
    const converted = input.bytes.length <= NODE_IMAGE_MAX_BYTES;
    const label = mimeLabel(shrunk.mime);
    return result(
      input,
      shrunk.mime,
      shrunk.bytes,
      converted ? "converted" : "compressed",
      shrunk,
      converted
        ? `Converted ${mimeLabel(input.mime)} to ${label}: ${formatBytes(shrunk.bytes.length)}, ${shrunk.width}×${shrunk.height}.`
        : `Compressed from ${original} to ${formatBytes(shrunk.bytes.length)}, ${shrunk.width}×${shrunk.height} ${label}.`,
    );
  } finally {
    raster.release?.();
  }
}

// --------------------------------------------------------------------------- clipboard

/** The clipboard image types, in the order they are preferred. */
const CLIPBOARD_IMAGE_TYPES = ["image/svg+xml", "image/png", "image/webp", "image/jpeg"];

/** The shape of an async-Clipboard-API item that this module needs. */
export interface ClipboardItemLike {
  readonly types: readonly string[];
  getType: (type: string) => Promise<Blob>;
}

/** The shape of a paste event's `clipboardData` that this module needs. */
export interface DataTransferLike {
  readonly files?: ArrayLike<File> | null;
  getData: (format: string) => string;
}

function pickType(types: readonly string[]): string | null {
  for (const type of CLIPBOARD_IMAGE_TYPES) {
    if (types.includes(type)) {
      return type;
    }
  }
  return types.find((type) => type.startsWith("image/")) ?? null;
}

/** The image in async-clipboard items: an image type, or SVG markup copied as text. */
export async function imageFromClipboardItems(
  items: readonly ClipboardItemLike[],
): Promise<ImageInput | null> {
  for (const item of items) {
    const type = pickType(item.types);
    if (type !== null) {
      const blob = await item.getType(type);
      return { bytes: await blobBytes(blob), mime: type };
    }
  }
  for (const item of items) {
    if (item.types.includes("text/plain")) {
      const text = await (await item.getType("text/plain")).text();
      if (isSvgText(text)) {
        return { bytes: UTF8.encode(text), mime: "image/svg+xml" };
      }
    }
  }
  return null;
}

/**
 * The image of a paste event, read synchronously (the event's data is gone once the
 * handler returns): an image file, or SVG markup in text/plain. Null when there is none.
 */
export function imageFromDataTransfer(
  data: DataTransferLike | null | undefined,
): (() => Promise<ImageInput>) | null {
  if (data === null || data === undefined) {
    return null;
  }
  const files = data.files === undefined || data.files === null ? [] : Array.from(data.files);
  const images = files.filter((file) => file.type.startsWith("image/"));
  const type = pickType(images.map((file) => file.type));
  const file = images.find((entry) => entry.type === type);
  if (file !== undefined) {
    return async () => ({ bytes: await blobBytes(file), mime: file.type });
  }
  const svgText = data.getData("image/svg+xml");
  const text = svgText.length > 0 ? svgText : data.getData("text/plain");
  if (text.length > 0 && isSvgText(text)) {
    return () => Promise.resolve({ bytes: UTF8.encode(text), mime: "image/svg+xml" });
  }
  return null;
}

/** The minimal async clipboard this module reads from. */
export interface AsyncClipboardLike {
  read?: () => Promise<readonly ClipboardItemLike[]>;
}

/** Read an image with the async Clipboard API (the Paste button). */
export async function readClipboardImage(
  clipboard: AsyncClipboardLike | undefined = typeof navigator === "undefined"
    ? undefined
    : (navigator.clipboard as AsyncClipboardLike | undefined),
): Promise<ImageInput> {
  if (clipboard?.read === undefined) {
    throw new NodeImageError(
      "This browser cannot read images from the clipboard here; click the image area and press Ctrl+V.",
    );
  }
  let items: readonly ClipboardItemLike[];
  try {
    items = await clipboard.read();
  } catch (error) {
    // A DOMException is not an Error in every environment; read its message either way.
    const message =
      typeof error === "object" && error !== null && "message" in error ? String(error.message) : "";
    const reason = message.length > 0 ? ` (${message})` : "";
    throw new NodeImageError(
      `The browser did not allow reading the clipboard${reason}; click the image area and press Ctrl+V.`,
    );
  }
  const image = await imageFromClipboardItems(items);
  if (image === null) {
    throw new NodeImageError("The clipboard holds no PNG or SVG image.");
  }
  return image;
}
