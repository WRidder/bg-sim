import { useState, type MouseEvent } from "react";

import { API_BASE } from "../api/client";
import { assetUrl } from "../docs/docsImages";
import "../examples/gallery.css";
import type { ModelCardInfo, ModelPreview } from "../state/modelApi";
import { modelUrl } from "./route";
import { modifiedDate, previewLayout, shortDescription } from "./modelCards";

/** A miniature of the top-level diagram: blocks, junctions and the connections between them. */
export function DiagramPreview({ preview }: { preview: ModelPreview }) {
  const layout = previewLayout(preview);
  if (layout === null) {
    return null;
  }
  const { size } = layout;
  const half = size / 2;
  return (
    <svg
      className="model-card__preview"
      viewBox={layout.viewBox}
      preserveAspectRatio="xMidYMid meet"
      aria-hidden="true"
      focusable="false"
    >
      {preview.links.map(([from, to, kind], index) => {
        const a = preview.nodes[from];
        const b = preview.nodes[to];
        if (a === undefined || b === undefined) {
          return null;
        }
        return (
          <line
            key={index}
            className={`model-card__link model-card__link--${kind}`}
            x1={a[0]}
            y1={a[1]}
            x2={b[0]}
            y2={b[1]}
            vectorEffect="non-scaling-stroke"
          />
        );
      })}
      {preview.nodes.map(([x, y, kind], index) =>
        kind === "j" ? (
          <circle
            key={index}
            className="model-card__node model-card__node--j"
            cx={x}
            cy={y}
            r={half * 0.55}
            vectorEffect="non-scaling-stroke"
          />
        ) : (
          <rect
            key={index}
            className={`model-card__node model-card__node--${kind}`}
            x={x - half}
            y={y - half * 0.75}
            width={size}
            height={size * 0.75}
            rx={size * 0.12}
            vectorEffect="non-scaling-stroke"
          />
        ),
      )}
    </svg>
  );
}

function CardThumb({ project, card }: { project: string; card: ModelCardInfo }) {
  const [broken, setBroken] = useState(false);
  if (card.thumbnail !== null && !broken) {
    return (
      <img
        src={assetUrl(project, card.name, card.thumbnail, API_BASE)}
        alt=""
        loading="lazy"
        decoding="async"
        data-testid={`model-thumbnail-${card.name}`}
        onError={() => setBroken(true)}
      />
    );
  }
  if (card.preview.nodes.length > 0) {
    return (
      <div className="model-card__miniature" data-testid={`model-miniature-${card.name}`}>
        <DiagramPreview preview={card.preview} />
      </div>
    );
  }
  return (
    <div
      className="example-card__placeholder"
      data-testid={`model-placeholder-${card.name}`}
      aria-hidden="true"
    >
      <span className="example-card__placeholder-glyph">◇</span>
    </div>
  );
}

export interface ModelCardGridProps {
  project: string;
  cards: readonly ModelCardInfo[];
  /** The model open in the editor, marked on its card; null on the picker page. */
  current?: string | null;
  /** Smaller cards for the top-bar model menu. */
  compact?: boolean;
  /** `data-testid` prefix of the card links: `model-card` (picker page) or `model-option` (menu). */
  testIdPrefix?: string;
  /** The model being opened; every card disables while one opens. */
  busy?: string | null;
  onOpen: (model: string) => void;
}

/**
 * A card per model, in the visual of the example gallery: thumbnail (the first
 * image of the model's docs, else a miniature of its diagram), name, a short
 * description and the block count. Every card is a link to the model's editor
 * URL, so Ctrl/middle-click opens it in a new tab; a plain click or Enter goes
 * through `onOpen`, which saves first.
 */
export function ModelCardGrid({
  project,
  cards,
  current = null,
  compact = false,
  testIdPrefix = "model-card",
  busy = null,
  onOpen,
}: ModelCardGridProps) {
  const open = (event: MouseEvent<HTMLAnchorElement>, model: string): void => {
    if (event.button !== 0 || event.ctrlKey || event.metaKey || event.shiftKey || event.altKey) {
      return;
    }
    event.preventDefault();
    if (busy === null) {
      onOpen(model);
    }
  };
  return (
    <ul
      className={`example-gallery model-grid${compact ? " model-grid--compact" : ""}`}
      data-testid={compact ? "model-menu-grid" : "model-grid"}
    >
      {cards.map((card) => {
        const isCurrent = card.name === current;
        const description = shortDescription(card.description);
        const date = modifiedDate(card.modified);
        const meta = [
          `${card.nodes} block${card.nodes === 1 ? "" : "s"}`,
          ...(date !== "" ? [date] : []),
          ...(card.inProject ? [] : ["not in the project list"]),
        ].join(" · ");
        return (
          <li key={card.name} className="model-grid__item">
            <a
              className={`example-card model-card${isCurrent ? " is-current" : ""}`}
              href={modelUrl(project, card.name)}
              data-testid={`${testIdPrefix}-${card.name}`}
              aria-current={isCurrent ? "page" : undefined}
              aria-disabled={busy !== null ? true : undefined}
              onClick={(event) => open(event, card.name)}
            >
              <div className="example-card__thumb">
                <CardThumb project={project} card={card} />
                {isCurrent ? (
                  <span className="example-card__badge model-card__current">Open</span>
                ) : null}
              </div>
              <div className="example-card__body">
                <h3 className="example-card__title model-card__title">
                  {busy === card.name ? `Opening ${card.name}…` : card.name}
                </h3>
                <p
                  className={`example-card__description${description === null ? " model-card__description--none" : ""}`}
                >
                  {card.error !== null
                    ? "This model file cannot be read; open it to see the error."
                    : (description ?? "No description yet.")}
                </p>
                <span className="model-card__meta">{meta}</span>
              </div>
            </a>
          </li>
        );
      })}
    </ul>
  );
}
