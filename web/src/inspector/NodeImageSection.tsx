/**
 * The Image section of a subsystem's inspector (plan 3.3 `ui.image`): choose a PNG or SVG
 * file, paste one (the Paste button reads the async Clipboard API; Ctrl+V works while the
 * drop area has focus, and on the canvas while the subsystem is the only selection), pick
 * the fit, or remove it. An image over 512 KB is shrunk automatically and the status line
 * says what happened. Every change is a document-store command, so Ctrl+Z / Ctrl+Y and
 * the autosave apply.
 */

import { useMemo, useRef } from "react";

import type { ModelNode } from "../contracts/model";
import {
  decodedLength,
  formatBytes,
  imageFromDataTransfer,
  mimeLabel,
  NODE_IMAGE_ACCEPT,
  NODE_IMAGE_MAX_BYTES,
  NodeImageError,
  nodeImageFitStyle,
  nodeImageSrc,
  readClipboardImage,
  type AsyncClipboardLike,
} from "../editor/nodeImage";
import {
  applyNodeImage,
  reportNodeImageError,
  useNodeImageStatus,
} from "../editor/nodeImageApply";
import { useDocumentStore } from "../state/documentStore";
import { SelectField } from "./fields";

/** Marks the paste target so the canvas leaves Ctrl+V inside it to the section. */
export const NODE_IMAGE_PASTE_ATTRIBUTE = "data-node-image-paste";

const FIT_OPTIONS = [
  { value: "contain", label: "Keep aspect ratio" },
  { value: "stretch", label: "Stretch to fill" },
] as const;

export interface NodeImageSectionProps {
  node: ModelNode;
  /** The clipboard the Paste button reads; tests pass a fake. */
  clipboard?: AsyncClipboardLike;
}

export function NodeImageSection({ node, clipboard }: NodeImageSectionProps) {
  const input = useRef<HTMLInputElement | null>(null);
  const image = node.ui?.image ?? null;
  const status = useNodeImageStatus((state) =>
    state.status !== null && state.status.nodeId === node.id ? state.status : null,
  );
  const busy = status?.kind === "busy";
  const src = useMemo(() => (image === null ? null : nodeImageSrc(image)), [image]);

  const onFile = (file: File | undefined): void => {
    if (file === undefined) {
      return;
    }
    void applyNodeImage(node.id, async () => ({
      bytes: new Uint8Array(await file.arrayBuffer()),
      mime: file.type,
    })).finally(() => {
      if (input.current !== null) input.current.value = "";
    });
  };

  const onPasteButton = (): void => {
    void applyNodeImage(node.id, () => readClipboardImage(clipboard));
  };

  const onPaste = (event: React.ClipboardEvent<HTMLDivElement>): void => {
    event.preventDefault();
    event.stopPropagation();
    const load = imageFromDataTransfer(event.clipboardData);
    if (load === null) {
      reportNodeImageError(
        node.id,
        new NodeImageError("The clipboard holds no PNG or SVG image."),
      );
      return;
    }
    void applyNodeImage(node.id, load);
  };

  return (
    <section
      className="inspector-section"
      aria-labelledby="inspector-image-title"
      data-testid="inspector-image"
    >
      <h4 className="inspector-section__title" id="inspector-image-title">
        Image
      </h4>
      <div
        className={`inspector-image${image === null ? " is-empty" : ""}`}
        tabIndex={0}
        role="group"
        aria-label="Subsystem image: press Ctrl+V to paste an image here"
        data-testid="inspector-image-drop"
        {...{ [NODE_IMAGE_PASTE_ATTRIBUTE]: "" }}
        onPaste={onPaste}
      >
        {image !== null && src !== null ? (
          <img
            className="inspector-image__preview"
            src={src}
            alt={`${node.name} image`}
            style={nodeImageFitStyle(image.fit)}
            data-testid="inspector-image-preview"
            data-fit={image.fit}
          />
        ) : (
          <span className="inspector-image__hint">Click here and press Ctrl+V to paste</span>
        )}
      </div>
      {image !== null ? (
        <p className="inspector-note" data-testid="inspector-image-meta">
          {mimeLabel(image.mime)} · {formatBytes(decodedLength(image.data))} of{" "}
          {formatBytes(NODE_IMAGE_MAX_BYTES)}
        </p>
      ) : null}
      <div className="inspector-actions">
        <input
          ref={input}
          type="file"
          accept={NODE_IMAGE_ACCEPT}
          hidden
          data-testid="inspector-image-input"
          onChange={(event) => onFile(event.target.files?.[0])}
        />
        <button
          type="button"
          className="button inspector-button"
          data-testid="inspector-image-choose"
          disabled={busy}
          onClick={() => input.current?.click()}
        >
          Choose file…
        </button>
        <button
          type="button"
          className="button inspector-button"
          data-testid="inspector-image-paste"
          disabled={busy}
          title="Paste a PNG or SVG image from the clipboard"
          onClick={onPasteButton}
        >
          Paste
        </button>
        <button
          type="button"
          className="button inspector-button"
          data-testid="inspector-image-remove"
          disabled={image === null || busy}
          onClick={() => {
            useDocumentStore.getState().setNodeImage(node.id, null);
            if (status !== null) {
              useNodeImageStatus.getState().setStatus(null);
            }
          }}
        >
          Remove
        </button>
      </div>
      {status !== null ? (
        <p
          className={`inspector-copy inspector-copy--${status.kind}`}
          role={status.kind === "error" ? "alert" : "status"}
          data-testid="inspector-image-status"
        >
          {status.message}
        </p>
      ) : null}
      {image !== null ? (
        <SelectField
          id="inspector-image-fit"
          testId="inspector-image-fit"
          label="fit"
          value={image.fit}
          options={FIT_OPTIONS}
          onChange={(next) => {
            const result = useDocumentStore
              .getState()
              .setNodeImageFit(node.id, next === "stretch" ? "stretch" : "contain");
            return result.ok ? null : (result.error ?? "The fit was refused.");
          }}
          description="Keep aspect ratio letterboxes the image in the block; stretch fills the block."
          invalidMessage="Choose keep aspect ratio or stretch."
        />
      ) : (
        <p className="inspector-note">
          PNG or SVG (JPEG and WebP work too). An image over{" "}
          {formatBytes(NODE_IMAGE_MAX_BYTES)} is shrunk to fit.
        </p>
      )}
    </section>
  );
}
