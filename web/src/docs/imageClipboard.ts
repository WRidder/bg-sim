/**
 * "Copy image" of the Docs tab: puts the picture on the clipboard as image/png together with
 * its Markdown text, so it can be pasted into another application, into the image-aware editor
 * of another model, or as plain text.
 */

import { rememberCopy } from "./docsImages";

/** Draw any browser-decodable image (also SVG) on a canvas and return it as PNG. */
export async function toPngBlob(blob: Blob): Promise<Blob> {
  if (blob.type === "image/png") {
    return blob;
  }
  const url = URL.createObjectURL(blob);
  try {
    const image = new Image();
    image.decoding = "async";
    image.src = url;
    await image.decode();
    const width = image.naturalWidth > 0 ? image.naturalWidth : 512;
    const height = image.naturalHeight > 0 ? image.naturalHeight : 512;
    const canvas = document.createElement("canvas");
    canvas.width = width;
    canvas.height = height;
    const context = canvas.getContext("2d");
    if (context === null) {
      throw new Error("This browser cannot convert the image to PNG for the clipboard.");
    }
    context.drawImage(image, 0, 0, width, height);
    return await new Promise<Blob>((resolve, reject) => {
      canvas.toBlob(
        (png) => (png === null ? reject(new Error("The image could not be converted to PNG.")) : resolve(png)),
        "image/png",
      );
    });
  } finally {
    URL.revokeObjectURL(url);
  }
}

/** Copy the image at `url` (PNG plus the Markdown `markdown`) to the clipboard. */
export async function copyImageToClipboard(
  url: string,
  markdown: string,
  origin: { project: string; model: string },
): Promise<void> {
  if (typeof ClipboardItem === "undefined" || navigator.clipboard === undefined) {
    throw new Error("This browser does not allow copying images; open the app over https or localhost.");
  }
  const response = await fetch(url);
  if (!response.ok) {
    throw new Error(`The image could not be loaded (${response.status}); paste it again to restore it.`);
  }
  const png = await toPngBlob(await response.blob());
  await navigator.clipboard.write([
    new ClipboardItem({
      "image/png": png,
      "text/plain": new Blob([markdown], { type: "text/plain" }),
    }),
  ]);
  // Pasting the Markdown text into another model must bring the image along.
  rememberCopy({ ...origin, text: markdown });
}
