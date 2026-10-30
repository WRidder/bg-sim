/**
 * The browser {@link RasterBackend} of the node images: decode with `createImageBitmap`
 * (an `<img>` for SVG, which `createImageBitmap` does not take from a Blob), re-encode on a
 * canvas. The SVG is loaded through an `<img>` and an object URL, so its scripts never run.
 */

import type { DecodedRaster, RasterBackend } from "./nodeImage";

/** The longest side of the copy that is scanned for transparent pixels. */
const ALPHA_PROBE = 256;

function canvasOf(width: number, height: number): HTMLCanvasElement {
  const canvas = document.createElement("canvas");
  canvas.width = width;
  canvas.height = height;
  return canvas;
}

function context2d(canvas: HTMLCanvasElement): CanvasRenderingContext2D {
  const context = canvas.getContext("2d");
  if (context === null) {
    throw new Error("no 2D canvas context");
  }
  return context;
}

function hasTransparency(source: CanvasImageSource, width: number, height: number): boolean {
  const scale = Math.min(1, ALPHA_PROBE / Math.max(width, height, 1));
  const w = Math.max(1, Math.round(width * scale));
  const h = Math.max(1, Math.round(height * scale));
  const context = context2d(canvasOf(w, h));
  context.drawImage(source, 0, 0, w, h);
  const pixels = context.getImageData(0, 0, w, h).data;
  for (let index = 3; index < pixels.length; index += 4) {
    if ((pixels[index] ?? 255) < 255) {
      return true;
    }
  }
  return false;
}

async function loadSvg(blob: Blob): Promise<{ image: HTMLImageElement; release: () => void }> {
  const url = URL.createObjectURL(blob);
  const image = new Image();
  image.decoding = "async";
  image.src = url;
  try {
    await image.decode();
  } catch (error) {
    URL.revokeObjectURL(url);
    throw error;
  }
  return { image, release: () => URL.revokeObjectURL(url) };
}

function encoder(source: CanvasImageSource): DecodedRaster["encode"] {
  return (width, height, mime, quality) => {
    const canvas = canvasOf(width, height);
    const context = context2d(canvas);
    context.imageSmoothingEnabled = true;
    context.imageSmoothingQuality = "high";
    context.drawImage(source, 0, 0, width, height);
    return new Promise((resolve) => canvas.toBlob(resolve, mime, quality));
  };
}

export const browserRasterBackend: RasterBackend = {
  async decode(blob) {
    if (blob.type === "image/svg+xml") {
      const { image, release } = await loadSvg(blob);
      const width = image.naturalWidth > 0 ? image.naturalWidth : 300;
      const height = image.naturalHeight > 0 ? image.naturalHeight : 150;
      return { width, height, hasAlpha: true, encode: encoder(image), release };
    }
    const bitmap = await createImageBitmap(blob);
    const alpha = blob.type === "image/jpeg" ? false : hasTransparency(bitmap, bitmap.width, bitmap.height);
    return {
      width: bitmap.width,
      height: bitmap.height,
      hasAlpha: alpha,
      encode: encoder(bitmap),
      release: () => bitmap.close(),
    };
  },
};
