import { describe, expect, it, vi } from "vitest";

import {
  MAX_IMAGE_BYTES,
  addImages,
  assetRefs,
  assetUrl,
  contentName,
  forgetCopy,
  imageMarkdown,
  imageProblem,
  parseImageAlt,
  planPaste,
  recallCopy,
  rememberCopy,
} from "../src/docs/docsImages";

const PNG_BYTES = new Uint8Array([0x89, 0x50, 0x4e, 0x47, 1, 2, 3]);

function file(name: string, type: string, bytes: Uint8Array = PNG_BYTES): File {
  return new File([bytes as BlobPart], name, { type });
}

describe("width syntax", () => {
  it("reads alt|width", () => {
    expect(parseImageAlt("Block diagram|300")).toEqual({ alt: "Block diagram", width: 300 });
    expect(parseImageAlt("|480")).toEqual({ alt: "", width: 480 });
    expect(parseImageAlt("a | b |  120 ")).toEqual({ alt: "a | b", width: 120 });
  });

  it("leaves other alt texts alone", () => {
    expect(parseImageAlt("plain")).toEqual({ alt: "plain", width: null });
    expect(parseImageAlt("a|wide")).toEqual({ alt: "a|wide", width: null });
    expect(parseImageAlt("a|5")).toEqual({ alt: "a|5", width: null });
    expect(parseImageAlt("a|99999")).toEqual({ alt: "a|99999", width: null });
  });
});

describe("asset names", () => {
  it("names by the first 12 hex digits of the SHA-256 plus the extension", async () => {
    const bytes = new Uint8Array([104, 101, 108, 108, 111]); // "hello"
    expect(await contentName(bytes.buffer, "image/png")).toBe("2cf24dba5fb0.png");
    expect(await contentName(bytes.buffer, "image/jpeg")).toBe("2cf24dba5fb0.jpg");
    expect(await contentName(bytes.buffer, "image/svg+xml")).toBe("2cf24dba5fb0.svg");
    await expect(contentName(bytes.buffer, "application/pdf")).rejects.toThrow("unsupported");
  });

  it("finds references in Markdown, once each", () => {
    const text =
      "![](assets/0123456789ab.png) ![x|200](assets/ffffffffffff.svg) ![](assets/0123456789ab.png) ![](assets/short.png)";
    expect(assetRefs(text)).toEqual(["0123456789ab.png", "ffffffffffff.svg"]);
    expect(imageMarkdown("0123456789ab.png")).toBe("![](assets/0123456789ab.png)");
    expect(assetUrl("p q", "m", "0123456789ab.png")).toBe(
      "/api/projects/p%20q/docs/m/assets/0123456789ab.png",
    );
  });
});

describe("validation", () => {
  it("explains what is wrong with a file", () => {
    expect(imageProblem({ name: "a.png", type: "image/png", size: 10 })).toBeNull();
    expect(imageProblem({ name: "a.bmp", type: "image/bmp", size: 10 })).toContain(
      "PNG, JPEG, GIF, WebP or SVG",
    );
    expect(imageProblem({ name: "a.png", type: "image/png", size: 0 })).toContain("empty");
    const big = imageProblem({ name: "huge.png", type: "image/png", size: MAX_IMAGE_BYTES + 1 });
    expect(big).toContain("the limit is 10 MB");
    expect(big).toContain("huge.png");
  });
});

describe("addImages (paste and drop)", () => {
  it("uploads once per content and inserts the Markdown at the cursor", async () => {
    const upload = vi.fn();
    const known = new Set<string>();
    const result = await addImages([file("a.png", "image/png")], {
      upload: async (f) => {
        upload();
        return { file: await contentName(await f.arrayBuffer(), f.type) };
      },
      known,
      onUploaded: (name) => known.add(name),
    });
    expect(result.problems).toEqual([]);
    expect(result.names).toHaveLength(1);
    expect(result.markdown).toBe(`![](assets/${result.names[0]})`);
    expect(upload).toHaveBeenCalledTimes(1);

    // The same image pasted again is recognised by its hash and not uploaded again.
    const again = await addImages([file("screenshot.png", "image/png")], {
      upload: async () => {
        upload();
        return { file: "never" };
      },
      known,
    });
    expect(upload).toHaveBeenCalledTimes(1);
    expect(again.markdown).toBe(result.markdown);
  });

  it("reports refused files and keeps the good ones", async () => {
    const result = await addImages(
      [file("a.bmp", "image/bmp"), file("empty.png", "image/png", new Uint8Array()), file("ok.png", "image/png")],
      { upload: async () => ({ file: "0123456789ab.png" }), known: new Set() },
    );
    expect(result.problems).toHaveLength(2);
    expect(result.markdown).toBe("![](assets/0123456789ab.png)");
  });

  it("reports a failed upload instead of hiding it", async () => {
    const result = await addImages([file("ok.png", "image/png")], {
      upload: async () => {
        throw new Error("The image is larger than 10 MiB");
      },
      known: new Set(),
    });
    expect(result.markdown).toBe("");
    expect(result.problems).toEqual(["The image is larger than 10 MiB"]);
  });
});

describe("planPaste (cross-model copy decision)", () => {
  const target = { project: "demo", model: "b" };
  const text = "See ![](assets/0123456789ab.png) and ![](assets/ffffffffffff.png)";

  it("uploads pasted image files first", () => {
    const f = file("a.png", "image/png");
    expect(planPaste({ files: [f], text: "", custom: null, remembered: null, target })).toEqual({
      kind: "images",
      files: [f],
    });
  });

  it("copies the assets when the custom clipboard type names another model", () => {
    const custom = JSON.stringify({ project: "demo", model: "a", text });
    expect(planPaste({ files: [], text, custom, remembered: null, target })).toEqual({
      kind: "copy-assets",
      from: { project: "demo", model: "a" },
      files: ["0123456789ab.png", "ffffffffffff.png"],
    });
  });

  it("falls back to the remembered copy when the text matches", () => {
    const remembered = { project: "other", model: "a", text: `${text}\r\n` };
    expect(planPaste({ files: [], text, custom: null, remembered, target })).toMatchObject({
      kind: "copy-assets",
      from: { project: "other", model: "a" },
    });
    expect(
      planPaste({
        files: [],
        text: "different text ![](assets/0123456789ab.png)",
        custom: null,
        remembered,
        target,
      }),
    ).toEqual({ kind: "default" });
  });

  it("does nothing for the same model, no images or no origin", () => {
    const same = { project: "demo", model: "b", text };
    expect(planPaste({ files: [], text, custom: null, remembered: same, target })).toEqual({ kind: "default" });
    const other = { project: "demo", model: "a", text: "plain" };
    expect(planPaste({ files: [], text: "plain", custom: null, remembered: other, target })).toEqual({
      kind: "default",
    });
    expect(planPaste({ files: [], text, custom: null, remembered: null, target })).toEqual({ kind: "default" });
    expect(planPaste({ files: [], text, custom: "not json", remembered: null, target })).toEqual({
      kind: "default",
    });
  });

  it("remembers the last copy", () => {
    forgetCopy();
    rememberCopy({ project: "p", model: "m", text: "x" });
    expect(recallCopy()).toEqual({ project: "p", model: "m", text: "x" });
    forgetCopy();
  });
});
