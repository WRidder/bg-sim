/**
 * Node images (`ui.image`, plan 3.3): base64, the 512 KiB contract limit, the fit styles,
 * the automatic shrinking of large PNG and SVG images, the clipboard paths (mocked), the
 * store commands with undo, the canvas rendering and the inspector's Image section.
 */

import { readFileSync } from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

import { act, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { ReactFlowProvider, type NodeProps } from "@xyflow/react";
import { afterEach, beforeEach, describe, expect, it } from "vitest";

import catalogJson from "../../contracts/fixtures/catalog/valid/catalog.min.json";
import imagesFixture from "../../contracts/fixtures/model/valid/model.subsystem-images.json";
import type { Catalog } from "../src/contracts/catalog";
import type { Model, ModelNode, ModelNodeImage } from "../src/contracts/model";
import { buildDiagram } from "../src/editor/buildFlow";
import {
  base64ToBytes,
  bytesToBase64,
  capSize,
  decodedLength,
  fitNodeImage,
  formatBytes,
  imageDataUrl,
  imageFromClipboardItems,
  imageFromDataTransfer,
  isSvgText,
  minifySvg,
  modelImageIssues,
  NODE_IMAGE_MAX_BASE64,
  NODE_IMAGE_MAX_BYTES,
  NODE_IMAGE_RASTER_CAP,
  NodeImageError,
  nodeImageFitStyle,
  nodeImageIssue,
  nodeImageSrc,
  readClipboardImage,
  stretchSvg,
  svgSize,
  type ClipboardItemLike,
  type DecodedRaster,
  type RasterBackend,
} from "../src/editor/nodeImage";
import { applyNodeImage, setNodeImageBackend, useNodeImageStatus } from "../src/editor/nodeImageApply";
import { BlockNode, type BlockNodeType } from "../src/editor/nodes/BlockNode";
import { Inspector } from "../src/inspector/Inspector";
import { NodeImageSection } from "../src/inspector/NodeImageSection";
import { buildCatalogIndex } from "../src/library/catalogIndex";
import { resetCatalogStore, useCatalogStore } from "../src/library/catalogStore";
import { resetDocumentStore, selectIsDirty, useDocumentStore } from "../src/state/documentStore";
import { createEmptyModel } from "../src/state/modelFactory";

const catalog = catalogJson as unknown as Catalog;
const here = path.dirname(fileURLToPath(import.meta.url));
const modelSchema = JSON.parse(
  readFileSync(path.join(here, "..", "..", "contracts", "schemas", "model.schema.json"), "utf8"),
) as { $defs: { nodeImage: { properties: { data: { maxLength: number }; mime: { enum: string[] } } } } };

const TINY_PNG = imagesFixture.diagram.nodes[0]!.ui.image!.data;
const TINY_SVG = imagesFixture.diagram.nodes[1]!.ui.image!.data;

// ------------------------------------------------------------------ fakes

interface FakeOptions {
  width: number;
  height: number;
  hasAlpha: boolean;
  /** Encoded bytes per pixel, by media type. */
  density?: Partial<Record<string, number>>;
  /** Media types the fake canvas cannot write (it answers with PNG, as browsers do). */
  unsupported?: readonly string[];
}

interface FakeBackend extends RasterBackend {
  calls: { width: number; height: number; mime: string }[];
  decoded: string[];
}

/** A canvas stand-in whose encoded size is proportional to the pixel count. */
function fakeBackend(options: FakeOptions): FakeBackend {
  const density: Partial<Record<string, number>> = {
    "image/png": 1.5,
    "image/webp": 0.25,
    "image/jpeg": 0.3,
    ...options.density,
  };
  const backend: FakeBackend = {
    calls: [],
    decoded: [],
    decode: (blob) => {
      backend.decoded.push(blob.type);
      const raster: DecodedRaster = {
        width: options.width,
        height: options.height,
        hasAlpha: options.hasAlpha,
        encode: (width, height, mime) => {
          backend.calls.push({ width, height, mime });
          const type = options.unsupported?.includes(mime) ? "image/png" : mime;
          const size = Math.ceil(width * height * (density[type] ?? 1));
          return Promise.resolve(new Blob([new Uint8Array(size)], { type }));
        },
      };
      return Promise.resolve(raster);
    },
  };
  return backend;
}

function bigBytes(size: number): Uint8Array<ArrayBuffer> {
  const bytes = new Uint8Array(size);
  for (let index = 0; index < size; index += 1) {
    bytes[index] = (index * 7919) % 251;
  }
  return bytes;
}

const UTF8 = new TextEncoder();

function blobItem(type: string, content: BlobPart): ClipboardItemLike {
  return {
    types: [type],
    getType: (requested) =>
      requested === type
        ? Promise.resolve(new Blob([content], { type }))
        : Promise.reject(new Error(`no ${requested}`)),
  };
}

// ------------------------------------------------------------------ model helpers

const index = buildCatalogIndex(catalog);

function subsystemNode(id: string, name: string, image?: ModelNodeImage): ModelNode {
  return {
    id,
    name,
    block: { subsystem: { ports: [], diagram: { nodes: [], connections: [] } } },
    position: { x: 100, y: 100 },
    rotation: 0,
    flipX: false,
    params: {},
    constants: {},
    starts: {},
    ui: image === undefined ? { showLabel: true, color: null } : { showLabel: true, color: null, image },
  };
}

function openModel(nodes: ModelNode[]): void {
  const doc = createEmptyModel("Images");
  doc.diagram.nodes = nodes;
  useDocumentStore.getState().openDocument("demo", "Images", doc);
}

function docNode(id: string): ModelNode | undefined {
  return useDocumentStore.getState().doc?.diagram.nodes.find((entry) => entry.id === id);
}

const PNG_IMAGE: ModelNodeImage = { mime: "image/png", data: TINY_PNG, fit: "contain" };

beforeEach(() => {
  resetDocumentStore();
  resetCatalogStore();
  useCatalogStore.getState().setCatalog(catalog);
  useNodeImageStatus.getState().setStatus(null);
});

afterEach(() => {
  setNodeImageBackend(null);
});

// ------------------------------------------------------------------ tests

describe("base64 and the size limit", () => {
  it("round-trips bytes through base64 and computes the decoded size", () => {
    const bytes = bigBytes(70_001);
    const text = bytesToBase64(bytes);
    expect(text).not.toContain("\n");
    expect(base64ToBytes(text)).toEqual(bytes);
    expect(decodedLength(text)).toBe(70_001);
    expect(decodedLength(bytesToBase64(bigBytes(3)))).toBe(3);
    expect(decodedLength(bytesToBase64(bigBytes(4)))).toBe(4);
    expect(decodedLength(bytesToBase64(bigBytes(5)))).toBe(5);
    expect(imageDataUrl(PNG_IMAGE)).toBe(`data:image/png;base64,${TINY_PNG}`);
  });

  it("matches the schema's limit and mime list", () => {
    expect(NODE_IMAGE_MAX_BYTES).toBe(524_288);
    expect(NODE_IMAGE_MAX_BASE64).toBe(modelSchema.$defs.nodeImage.properties.data.maxLength);
    expect(modelSchema.$defs.nodeImage.properties.mime.enum).toEqual([
      "image/png",
      "image/svg+xml",
      "image/webp",
      "image/jpeg",
    ]);
    expect(formatBytes(NODE_IMAGE_MAX_BYTES)).toBe("512 KB");
    expect(formatBytes(2.3 * 1024 * 1024)).toBe("2.3 MB");
  });

  it("accepts an image of exactly 512 KiB and refuses one byte-quad more", () => {
    const atLimit = bytesToBase64(bigBytes(NODE_IMAGE_MAX_BYTES));
    expect(atLimit.length).toBe(NODE_IMAGE_MAX_BASE64);
    expect(nodeImageIssue({ mime: "image/png", data: atLimit, fit: "contain" })).toBeNull();
    const over = bytesToBase64(bigBytes(NODE_IMAGE_MAX_BYTES + 3));
    expect(nodeImageIssue({ mime: "image/png", data: over, fit: "contain" })).toMatch(
      "ui.image.data decodes to 524291 bytes; the limit is 524288 bytes (512 KB).",
    );
  });

  it("names a bad mime, fit or encoding", () => {
    expect(nodeImageIssue(PNG_IMAGE)).toBeNull();
    expect(nodeImageIssue({ ...PNG_IMAGE, mime: "image/gif" })).toMatch(/mime/);
    expect(nodeImageIssue({ ...PNG_IMAGE, fit: "cover" })).toMatch(/fit/);
    expect(nodeImageIssue({ ...PNG_IMAGE, data: `data:image/png;base64,${TINY_PNG}` })).toMatch(
      /not standard base64/,
    );
    expect(nodeImageIssue({ ...PNG_IMAGE, extra: 1 })).toMatch(/unknown field/);
    expect(nodeImageIssue({ ...PNG_IMAGE, data: "" })).toMatch(/non-empty/);
  });

  it("reports an oversize image on load with the node path", () => {
    const doc = JSON.parse(JSON.stringify(imagesFixture)) as Model;
    expect(modelImageIssues(doc)).toEqual([]);
    const iconic = doc.diagram.nodes[0]!;
    iconic.ui!.image!.data = bytesToBase64(bigBytes(NODE_IMAGE_MAX_BYTES + 1024));
    const issues = modelImageIssues(doc);
    expect(issues).toHaveLength(1);
    expect(issues[0]).toBe(
      "Iconic: ui.image.data decodes to 525312 bytes; the limit is 524288 bytes (512 KB).",
    );
  });
});

describe("fit styles", () => {
  it("contain keeps the aspect ratio and stretch fills", () => {
    expect(nodeImageFitStyle("contain")).toEqual({ objectFit: "contain" });
    expect(nodeImageFitStyle("stretch")).toEqual({ objectFit: "fill" });
  });

  it("drops the SVG's own aspect ratio for stretch, in the displayed copy only", () => {
    expect(stretchSvg('<svg viewBox="0 0 40 40" preserveAspectRatio="xMinYMin"><g/></svg>')).toBe(
      '<svg preserveAspectRatio="none" viewBox="0 0 40 40"><g/></svg>',
    );
    expect(stretchSvg('<?xml version="1.0"?><svg width="64" height="32"><g/></svg>')).toBe(
      '<?xml version="1.0"?><svg preserveAspectRatio="none" viewBox="0 0 64 32" width="64" height="32"><g/></svg>',
    );
    const contain = { mime: "image/svg+xml" as const, data: TINY_SVG, fit: "contain" as const };
    expect(nodeImageSrc(contain)).toBe(`data:image/svg+xml;base64,${TINY_SVG}`);
    const stretched = nodeImageSrc({ ...contain, fit: "stretch" });
    const text = new TextDecoder().decode(base64ToBytes(stretched.split(",")[1] ?? ""));
    expect(text.startsWith('<svg preserveAspectRatio="none" xmlns=')).toBe(true);
    expect(nodeImageSrc({ ...PNG_IMAGE, fit: "stretch" })).toBe(`data:image/png;base64,${TINY_PNG}`);
  });

  it("caps the longest side without changing the aspect ratio", () => {
    expect(capSize(4000, 3000, 1024)).toEqual({ width: 1024, height: 768 });
    expect(capSize(300, 900, 1024)).toEqual({ width: 300, height: 900 });
  });
});

describe("SVG text", () => {
  const messy = `<?xml version="1.0" encoding="UTF-8"?>
<!-- Generator: an editor -->
<!DOCTYPE svg PUBLIC "-//W3C//DTD SVG 1.1//EN" "http://www.w3.org/Graphics/SVG/1.1/DTD/svg11.dtd">
<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 400 200">
  <title>Pump</title>
  <metadata><rdf:RDF>lots of data</rdf:RDF></metadata>
  <sodipodi:namedview id="base" pagecolor="#ffffff"/>
  <!-- a comment -->
  <path d="M 10.123456 20.987654   L 30.5 40.25" />
</svg>`;

  it("recognises SVG markup behind a prolog, and nothing else", () => {
    expect(isSvgText(messy)).toBe(true);
    expect(isSvgText("  <svg/>")).toBe(true);
    expect(isSvgText("<svgx>")).toBe(false);
    expect(isSvgText("hello <svg>")).toBe(false);
    expect(isSvgText("<html><svg></svg></html>")).toBe(false);
  });

  it("minifies comments, metadata, whitespace and long decimals", () => {
    const small = minifySvg(messy);
    expect(small).toBe(
      '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 400 200"><path d="M 10.123 20.987 L 30.5 40.25" /></svg>',
    );
    expect(isSvgText(small)).toBe(true);
  });

  it("reads the intrinsic size from width/height or the viewBox", () => {
    expect(svgSize(messy)).toEqual({ width: 400, height: 200 });
    expect(svgSize('<svg width="64px" height="32" viewBox="0 0 1 1"/>')).toEqual({
      width: 64,
      height: 32,
    });
    expect(svgSize('<svg width="100%"/>')).toBeNull();
  });
});

describe("fitting an image into 512 KB", () => {
  it("keeps a small PNG and a small SVG byte for byte", async () => {
    const backend = fakeBackend({ width: 16, height: 8, hasAlpha: true });
    const png = await fitNodeImage({ bytes: base64ToBytes(TINY_PNG), mime: "image/png" }, backend);
    expect(png).toMatchObject({ mime: "image/png", data: TINY_PNG, action: "kept", message: null });
    const svg = await fitNodeImage({ bytes: base64ToBytes(TINY_SVG), mime: "image/svg+xml" }, backend);
    expect(svg).toMatchObject({ mime: "image/svg+xml", data: TINY_SVG, action: "kept" });
    expect(backend.decoded).toEqual([]);
  });

  it("shrinks a large transparent PNG below the limit as PNG, keeping the aspect ratio", async () => {
    const backend = fakeBackend({ width: 4000, height: 3000, hasAlpha: true });
    const fitted = await fitNodeImage({ bytes: bigBytes(2_400_000), mime: "image/png" }, backend);
    expect(fitted.mime).toBe("image/png");
    expect(fitted.bytes).toBeLessThanOrEqual(NODE_IMAGE_MAX_BYTES);
    expect(fitted.data.length).toBeLessThanOrEqual(NODE_IMAGE_MAX_BASE64);
    expect(fitted.action).toBe("compressed");
    // 1024x768 (1.1 MB at 1.5 B/px) is too large; halving gives 512x384.
    expect([fitted.width, fitted.height]).toEqual([512, 384]);
    expect((fitted.width ?? 0) / (fitted.height ?? 1)).toBeCloseTo(4000 / 3000, 2);
    expect(backend.calls.every((call) => call.mime === "image/png")).toBe(true);
    expect(backend.calls[0]).toEqual({ width: NODE_IMAGE_RASTER_CAP, height: 768, mime: "image/png" });
    expect(fitted.message).toBe("Compressed from 2.3 MB to 288 KB, 512×384 PNG.");
    expect(nodeImageIssue({ mime: fitted.mime, data: fitted.data, fit: "contain" })).toBeNull();
  });

  it("falls back to WebP for an opaque image, and to JPEG when WebP cannot be written", async () => {
    const opaque = fakeBackend({ width: 3000, height: 2000, hasAlpha: false });
    const webp = await fitNodeImage({ bytes: bigBytes(900_000), mime: "image/png" }, opaque);
    expect(webp.mime).toBe("image/webp");
    expect([webp.width, webp.height]).toEqual([1024, 683]);
    expect(webp.message).toMatch(/^Compressed from 879 KB to \d+ KB, 1024×683 WebP\.$/);

    const noWebp = fakeBackend({ width: 3000, height: 2000, hasAlpha: false, unsupported: ["image/webp"] });
    const jpeg = await fitNodeImage({ bytes: bigBytes(900_000), mime: "image/jpeg" }, noWebp);
    expect(jpeg.mime).toBe("image/jpeg");
    expect(jpeg.bytes).toBeLessThanOrEqual(NODE_IMAGE_MAX_BYTES);
  });

  it("converts a small GIF to PNG", async () => {
    const backend = fakeBackend({ width: 40, height: 20, hasAlpha: true });
    const fitted = await fitNodeImage({ bytes: bigBytes(1000), mime: "image/gif" }, backend);
    expect(fitted).toMatchObject({ mime: "image/png", action: "converted", width: 40, height: 20 });
    expect(fitted.message).toMatch(/^Converted GIF to PNG/);
  });

  it("minifies a large SVG when that is enough", async () => {
    const backend = fakeBackend({ width: 400, height: 200, hasAlpha: true });
    const padding = `<!-- ${"x".repeat(NODE_IMAGE_MAX_BYTES)} -->`;
    const text = `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 400 200">${padding}<rect width="10" height="10"/></svg>`;
    const fitted = await fitNodeImage({ bytes: UTF8.encode(text), mime: "image/svg+xml" }, backend);
    expect(fitted.mime).toBe("image/svg+xml");
    expect(fitted.action).toBe("minified");
    expect(new TextDecoder().decode(base64ToBytes(fitted.data))).toBe(
      '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 400 200"><rect width="10" height="10"/></svg>',
    );
    expect(fitted.message).toBe("SVG minified from 512 KB to 98 B.");
    expect(backend.decoded).toEqual([]);
  });

  it("rasterizes a large SVG to PNG when minifying is not enough", async () => {
    const backend = fakeBackend({ width: 300, height: 150, hasAlpha: true });
    const paths = Array.from({ length: 30_000 }, (_, k) => `<path d="M${k} ${k}L${k + 7} ${k + 3}"/>`).join("");
    const text = `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 800 400">${paths}</svg>`;
    expect(text.length).toBeGreaterThan(NODE_IMAGE_MAX_BYTES);
    const fitted = await fitNodeImage({ bytes: UTF8.encode(text), mime: "image/svg+xml" }, backend);
    expect(fitted.action).toBe("rasterized");
    expect(fitted.mime).toBe("image/png");
    expect(backend.decoded).toEqual(["image/svg+xml"]);
    expect(fitted.bytes).toBeLessThanOrEqual(NODE_IMAGE_MAX_BYTES);
    // The viewBox aspect (2:1) is kept: 1024x512 is 768 KB at 1.5 B/px, so 512x256.
    expect([fitted.width, fitted.height]).toEqual([512, 256]);
    expect(fitted.message).toMatch(/^SVG of \d+ KB is still \d+ KB minified; rasterized to PNG at 512×256, 192 KB\.$/);
  });

  it("refuses something that is not an image", async () => {
    const backend = fakeBackend({ width: 1, height: 1, hasAlpha: false });
    await expect(
      fitNodeImage({ bytes: UTF8.encode("hello"), mime: "text/plain" }, backend),
    ).rejects.toThrow(NodeImageError);
    await expect(
      fitNodeImage({ bytes: UTF8.encode("<html/>"), mime: "image/svg+xml" }, backend),
    ).rejects.toThrow(/does not start with an <svg> element/);
    await expect(fitNodeImage({ bytes: new Uint8Array(), mime: "image/png" }, backend)).rejects.toThrow(
      /empty/,
    );
  });
});

describe("clipboard", () => {
  it("takes a PNG item, then SVG markup copied as text, and nothing else", async () => {
    const png = await imageFromClipboardItems([blobItem("image/png", base64ToBytes(TINY_PNG).slice())]);
    expect(png?.mime).toBe("image/png");
    expect(png?.bytes.length).toBe(decodedLength(TINY_PNG));

    const svgSource = new TextDecoder().decode(base64ToBytes(TINY_SVG));
    const svg = await imageFromClipboardItems([blobItem("text/plain", svgSource)]);
    expect(svg?.mime).toBe("image/svg+xml");
    expect(new TextDecoder().decode(svg?.bytes)).toBe(svgSource);

    const native = await imageFromClipboardItems([
      { types: ["text/html", "image/svg+xml"], getType: () => Promise.resolve(new Blob([svgSource], { type: "image/svg+xml" })) },
    ]);
    expect(native?.mime).toBe("image/svg+xml");

    expect(await imageFromClipboardItems([blobItem("text/plain", "just words")])).toBeNull();
  });

  it("reads the async clipboard and explains a refusal", async () => {
    const image = await readClipboardImage({
      read: () => Promise.resolve([blobItem("image/png", base64ToBytes(TINY_PNG).slice())]),
    });
    expect(image.mime).toBe("image/png");
    await expect(readClipboardImage({})).rejects.toThrow(/press Ctrl\+V/);
    await expect(
      readClipboardImage({ read: () => Promise.reject(new DOMException("Read permission denied.", "NotAllowedError")) }),
    ).rejects.toThrow(/did not allow reading the clipboard \(Read permission denied\.\)/);
    await expect(
      readClipboardImage({ read: () => Promise.resolve([blobItem("text/plain", "words")]) }),
    ).rejects.toThrow("The clipboard holds no PNG or SVG image.");
  });

  it("reads a paste event's files or SVG text synchronously", async () => {
    const file = new File([base64ToBytes(TINY_PNG).slice()], "shot.png", { type: "image/png" });
    const fromFile = imageFromDataTransfer({ files: [file], getData: () => "" });
    expect(fromFile).not.toBeNull();
    expect((await fromFile!()).mime).toBe("image/png");

    const svgSource = new TextDecoder().decode(base64ToBytes(TINY_SVG));
    const fromText = imageFromDataTransfer({
      files: [],
      getData: (format) => (format === "text/plain" ? svgSource : ""),
    });
    expect((await fromText!()).mime).toBe("image/svg+xml");

    expect(imageFromDataTransfer({ files: [], getData: () => "Motor1" })).toBeNull();
    expect(imageFromDataTransfer(null)).toBeNull();
  });
});

describe("store commands", () => {
  it("sets, refits and removes an image as undoable edits", () => {
    openModel([subsystemNode("s1", "Plant")]);
    const store = useDocumentStore.getState();
    expect(selectIsDirty(useDocumentStore.getState())).toBe(false);

    expect(store.setNodeImage("s1", PNG_IMAGE)).toEqual({ ok: true });
    expect(docNode("s1")?.ui?.image).toEqual(PNG_IMAGE);
    expect(selectIsDirty(useDocumentStore.getState())).toBe(true);

    expect(store.setNodeImageFit("s1", "stretch")).toEqual({ ok: true });
    expect(docNode("s1")?.ui?.image?.fit).toBe("stretch");

    store.setNodeImage("s1", null);
    expect(docNode("s1")?.ui?.image).toBeUndefined();
    expect(docNode("s1")?.ui).toEqual({ showLabel: true, color: null });

    store.undo();
    expect(docNode("s1")?.ui?.image?.fit).toBe("stretch");
    store.undo();
    expect(docNode("s1")?.ui?.image?.fit).toBe("contain");
    store.undo();
    expect(docNode("s1")?.ui?.image).toBeUndefined();
    store.redo();
    expect(docNode("s1")?.ui?.image).toEqual(PNG_IMAGE);
  });

  it("refuses an image on a library block, an invalid image and a fit without image", () => {
    const doc = createEmptyModel("Images");
    const plain = { ...subsystemNode("n1", "R1"), block: { ref: "stdlib:electrical/Resistor" } };
    doc.diagram.nodes = [plain, subsystemNode("s1", "Plant")];
    useDocumentStore.getState().openDocument("demo", "Images", doc);
    const store = useDocumentStore.getState();
    expect(store.setNodeImage("n1", PNG_IMAGE).error).toMatch(/Only subsystem blocks/);
    expect(store.setNodeImage("s1", { ...PNG_IMAGE, data: "!!!!" }).error).toMatch(/base64/);
    expect(store.setNodeImageFit("s1", "stretch").error).toMatch(/no image/);
    expect(useDocumentStore.getState().past).toHaveLength(0);
  });
});

describe("canvas rendering", () => {
  function renderNode(model: Model, id: string) {
    const flow = buildDiagram(model, index, { nodes: [], connections: [] });
    const node = flow.nodes.find((entry) => entry.id === id);
    const props = { id, data: node?.data, selected: false } as unknown as NodeProps<BlockNodeType>;
    return render(
      <ReactFlowProvider>
        <BlockNode {...props} />
      </ReactFlowProvider>,
    );
  }

  it("draws the image with its fit as a data: URL <img>, never as inline SVG", () => {
    const model = imagesFixture as unknown as Model;
    const { container } = renderNode(model, "bondgraph");
    const image = screen.getByTestId("node-image-bondgraph") as HTMLImageElement;
    expect(image.tagName).toBe("IMG");
    // A stretched SVG is shown with preserveAspectRatio="none"; still a data: URL.
    expect(image.getAttribute("src")).toBe(nodeImageSrc({ mime: "image/svg+xml", data: TINY_SVG, fit: "stretch" }));
    expect(image.getAttribute("src")).toMatch(/^data:image\/svg\+xml;base64,[A-Za-z0-9+/]+=*$/);
    expect(image.dataset.fit).toBe("stretch");
    expect(image.style.objectFit).toBe("fill");
    // The SVG markup itself is not in the DOM: only the <img>.
    expect(container.querySelector("svg rect")).toBeNull();
    expect(container.querySelector(".block-node__header")?.textContent).toContain("Bondgraph");
  });

  it("contains a PNG and draws the icon when there is no image", () => {
    const model = imagesFixture as unknown as Model;
    renderNode(model, "iconic");
    const image = screen.getByTestId("node-image-iconic") as HTMLImageElement;
    expect(image.style.objectFit).toBe("contain");
    expect(image.dataset.mime).toBe("image/png");

    const plain = createEmptyModel("Plain");
    plain.diagram.nodes = [subsystemNode("s1", "Plant")];
    renderNode(plain, "s1");
    expect(screen.queryByTestId("node-image-s1")).toBeNull();
  });
});

describe("the inspector's Image section", () => {
  it("is shown for subsystems only", () => {
    const doc = createEmptyModel("Images");
    const plain = { ...subsystemNode("n1", "R1"), block: { ref: "stdlib:electrical/Resistor" } };
    doc.diagram.nodes = [plain, subsystemNode("s1", "Plant")];
    useDocumentStore.getState().openDocument("demo", "Images", doc);
    useDocumentStore.getState().setSelection(["n1"], []);
    const { unmount } = render(<Inspector />);
    expect(screen.queryByTestId("inspector-image")).toBeNull();
    unmount();
    useDocumentStore.getState().setSelection(["s1"], []);
    render(<Inspector />);
    expect(screen.getByTestId("inspector-image")).toBeTruthy();
  });

  it("pastes a large image from a mocked clipboard, shows the compression and toggles the fit", async () => {
    openModel([subsystemNode("s1", "Plant")]);
    setNodeImageBackend(fakeBackend({ width: 2048, height: 1536, hasAlpha: true }));
    const clipboard = {
      read: () => Promise.resolve([blobItem("image/png", bigBytes(2_400_000))]),
    };
    const view = () => docNode("s1")!;
    const { rerender } = render(<NodeImageSection node={view()} clipboard={clipboard} />);

    fireEvent.click(screen.getByTestId("inspector-image-paste"));
    await waitFor(() =>
      expect(screen.getByTestId("inspector-image-status").textContent).toBe(
        "Compressed from 2.3 MB to 288 KB, 512×384 PNG.",
      ),
    );
    const image = view().ui?.image;
    expect(image?.mime).toBe("image/png");
    expect(image?.fit).toBe("contain");
    expect(decodedLength(image?.data ?? "")).toBeLessThanOrEqual(NODE_IMAGE_MAX_BYTES);

    rerender(<NodeImageSection node={view()} clipboard={clipboard} />);
    expect(screen.getByTestId("inspector-image-preview").dataset.fit).toBe("contain");
    expect(screen.getByTestId("inspector-image-meta").textContent).toBe("PNG · 288 KB of 512 KB");

    fireEvent.change(screen.getByTestId("inspector-image-fit"), { target: { value: "stretch" } });
    expect(view().ui?.image?.fit).toBe("stretch");
    rerender(<NodeImageSection node={view()} clipboard={clipboard} />);
    expect((screen.getByTestId("inspector-image-preview") as HTMLImageElement).style.objectFit).toBe("fill");

    fireEvent.click(screen.getByTestId("inspector-image-remove"));
    expect(view().ui?.image).toBeUndefined();
  });

  it("takes SVG text pasted with Ctrl+V into the image area", async () => {
    openModel([subsystemNode("s1", "Plant")]);
    render(<NodeImageSection node={docNode("s1")!} />);
    const svgSource = new TextDecoder().decode(base64ToBytes(TINY_SVG));
    fireEvent.paste(screen.getByTestId("inspector-image-drop"), {
      clipboardData: { files: [], getData: (format: string) => (format === "text/plain" ? svgSource : "") },
    });
    await waitFor(() => expect(docNode("s1")?.ui?.image?.mime).toBe("image/svg+xml"));
    expect(docNode("s1")?.ui?.image?.data).toBe(TINY_SVG);
    expect(screen.getByTestId("inspector-image-status").textContent).toBe("Image set.");
  });

  it("says so when the clipboard has no image", async () => {
    openModel([subsystemNode("s1", "Plant")]);
    render(
      <NodeImageSection
        node={docNode("s1")!}
        clipboard={{ read: () => Promise.resolve([blobItem("text/plain", "Motor1")]) }}
      />,
    );
    fireEvent.click(screen.getByTestId("inspector-image-paste"));
    await waitFor(() =>
      expect(screen.getByRole("alert").textContent).toBe("The clipboard holds no PNG or SVG image."),
    );
    expect(docNode("s1")?.ui?.image).toBeUndefined();
  });

  it("keeps the current fit when a new image replaces the old one", async () => {
    openModel([subsystemNode("s1", "Plant", { ...PNG_IMAGE, fit: "stretch" })]);
    await act(async () => {
      await applyNodeImage("s1", () =>
        Promise.resolve({ bytes: base64ToBytes(TINY_SVG), mime: "image/svg+xml" }),
      );
    });
    expect(docNode("s1")?.ui?.image).toEqual({ mime: "image/svg+xml", data: TINY_SVG, fit: "stretch" });
  });
});
