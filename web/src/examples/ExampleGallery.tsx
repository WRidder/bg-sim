import { exampleInfo } from "./gallery";
import "./gallery.css";

export interface ExampleGalleryProps {
  examples: readonly string[];
  /** The example being imported, or null. All cards disable while one imports. */
  busy: string | null;
  onOpen: (example: string) => void;
}

/** A card per example: thumbnail, title, one-line description and "Open sample". */
export function ExampleGallery({ examples, busy, onOpen }: ExampleGalleryProps) {
  return (
    <ul className="example-gallery" data-testid="example-gallery">
      {examples.map((name) => {
        const info = exampleInfo(name);
        return (
          <li className="example-card" key={name} data-testid={`example-card-${name}`}>
            <div className="example-card__thumb">
              {info.thumbnail !== null ? (
                <img
                  src={info.thumbnail}
                  alt=""
                  width={480}
                  height={300}
                  loading="lazy"
                  decoding="async"
                  data-testid={`example-thumbnail-${name}`}
                />
              ) : (
                <div
                  className="example-card__placeholder"
                  data-testid={`example-placeholder-${name}`}
                  aria-hidden="true"
                >
                  <span className="example-card__placeholder-glyph">◇</span>
                </div>
              )}
              {info.hasScene ? (
                <span className="example-card__badge" title="This example has a 3D scene">
                  <span aria-hidden="true">▣ </span>3D
                </span>
              ) : null}
            </div>
            <div className="example-card__body">
              <h3 className="example-card__title">{info.title}</h3>
              <p className="example-card__description">{info.description}</p>
              <button
                type="button"
                className="button example-card__open"
                data-testid={`example-open-${name}`}
                aria-label={`Open sample ${info.title}`}
                disabled={busy !== null}
                onClick={() => onOpen(name)}
              >
                {busy === name ? "Importing…" : "Open sample"}
              </button>
            </div>
          </li>
        );
      })}
    </ul>
  );
}
