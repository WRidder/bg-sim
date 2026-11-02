/**
 * The library browser of plan 7.2: groups from the catalog, a search over the
 * name/ref/group/description, the parameter and port summary, and HTML5
 * drag-to-add with the typed payload of src/library/dnd.ts.
 *
 * Every category is a disclosure section, collapsed by default; the expanded
 * and hidden categories persist (src/library/libraryPrefs.ts, edited from the
 * quick settings of LibrarySettings.tsx). While a search is active the
 * categories with a match show expanded, and hidden categories are not searched.
 *
 * The list view shows each block with a summary line and expandable details;
 * the grid view (LibraryViewToggle.tsx) shows tiles of three per row with only
 * the icon and the name, the description in the tooltip, and opens the block
 * help on click. Both views keep the same entry testids, refs and drag payload.
 *
 * A block just added to the project library (src/library/libraryReveal.ts) is shown: its
 * category expands (and un-hides), a search that hides it clears, and the entry scrolls into
 * view with a short highlight.
 *
 * The last category, Shapes (src/library/libraryShapes.ts), lists the canvas background shapes.
 * They are not catalog blocks: a shape drags with its own MIME type, and a click (or Enter) on one
 * adds it in the middle of the visible canvas (src/editor/shapeRequests.ts) in both views.
 */

import { useEffect, useId, useMemo, useState, type DragEvent, type ReactNode } from "react";

import type { CatalogBlock, DomainName } from "../contracts/catalog";
import type { JunctionType } from "../contracts/model";
import { retrySession } from "../state/session";
import { useWorkerStore, workerNotReady } from "../api/workerStore";
import { WaitingForWorker } from "../app/WaitingForWorker";
import { useCatalogStore } from "./catalogStore";
import {
  blockSummary,
  JUNCTION_GROUP,
  libraryCategories,
  libraryGroupFor,
  searchGroups,
  SHAPES_GROUP,
} from "./catalogIndex";
import { payloadForBlock, payloadForShape, writeDragPayload } from "./dnd";
import { searchShapes, SHAPE_DESCRIPTION, type ShapeEntry } from "./libraryShapes";
import { requestShapeAtCentre } from "../editor/shapeRequests";
import { PortGlyph, type PortGlyphProps } from "./PortGlyph";
import { BlockHelpButton } from "../app/BlockHelp";
import { BlockIcon, JunctionGlyph } from "../editor/icons";
import { ChevronIcon, ShapeGlyph } from "./icons";
import { useLibraryPrefs } from "./libraryPrefs";
import { REVEAL_HIGHLIGHT_MS, useLibraryReveal } from "./libraryReveal";
import { LibraryItemMenu, type LibraryMenuState } from "./LibraryItemMenu";
import "./library.css";

interface BlockEntry {
  key: string;
  name: string;
  summary: string;
  description: string;
  icon: string;
  block: CatalogBlock;
}

interface JunctionEntry {
  key: string;
  name: string;
  junction: JunctionType;
}

const DOMAIN_LETTER: Record<DomainName, string> = {
  Electrical: "E",
  Translation: "T",
  Rotation: "R",
  Hydraulic: "H",
  Thermal: "Th",
  Generic: "G",
  Planar: "P",
  Spatial: "S",
};

function portLines(
  block: CatalogBlock,
): { key: string; text: string; domain: string; glyph: PortGlyphProps | null }[] {
  const lines: { key: string; text: string; domain: string; glyph: PortGlyphProps | null }[] = [];
  for (const port of block.ports) {
    lines.push({
      key: `p-${port.name}`,
      text: `${port.name} · power${port.size.length > 0 ? ` · ${port.size.join("x")}` : ""}`,
      domain: DOMAIN_LETTER[port.domain],
      glyph: { domain: port.domain, name: port.name, frame: port.frame },
    });
  }
  for (const input of block.inputs) {
    lines.push({
      key: `i-${input.name}`,
      text: `${input.name} · ${input.type} input${input.unit ? ` · ${input.unit}` : ""}`,
      domain: "↦",
      glyph: null,
    });
  }
  for (const output of block.outputs) {
    lines.push({
      key: `o-${output.name}`,
      text: `${output.name} · ${output.type} output${output.unit ? ` · ${output.unit}` : ""}`,
      domain: "↦",
      glyph: null,
    });
  }
  return lines;
}

function junctionDescription(junction: JunctionType): string {
  return junction === "0"
    ? "0 junction: equal efforts, flows sum to zero."
    : "1 junction: equal flows, efforts sum to zero.";
}

function LibraryGroupSection({
  name,
  count,
  open,
  onToggle,
  grid,
  children,
}: {
  name: string;
  count: number;
  open: boolean;
  onToggle: () => void;
  grid: boolean;
  children: ReactNode;
}) {
  const listId = `${useId()}-list`;
  return (
    <section
      className={`library-group${open ? " is-open" : ""}`}
      data-testid={`library-group-${name}`}
      data-expanded={open ? "true" : "false"}
    >
      <h3 className="library-group__title">
        <button
          type="button"
          className="library-group__toggle"
          aria-expanded={open}
          aria-controls={open ? listId : undefined}
          data-testid={`library-group-toggle-${name}`}
          onClick={onToggle}
        >
          <ChevronIcon className="library-group__chevron" size={12} />
          <span className="library-group__name">{name}</span>
          <span className="library-group__count">{count}</span>
        </button>
      </h3>
      {open ? (
        <ul className={`library-group__list${grid ? " library-group__list--grid" : ""}`} id={listId}>
          {children}
        </ul>
      ) : null}
    </section>
  );
}

export function LibraryBrowser() {
  const index = useCatalogStore((state) => state.index);
  const status = useCatalogStore((state) => state.status);
  const error = useCatalogStore((state) => state.error);
  const waitForWorker = useWorkerStore(workerNotReady);
  const savedExpanded = useLibraryPrefs((state) => state.expanded);
  const hidden = useLibraryPrefs((state) => state.hidden);
  const searchCollapsed = useLibraryPrefs((state) => state.searchCollapsed);
  const grid = useLibraryPrefs((state) => state.view) === "grid";
  const [menu, setMenu] = useState<LibraryMenuState | null>(null);
  const openMenu = (event: { preventDefault: () => void; clientX: number; clientY: number }, ref: string, label: string, hasSource: boolean) => {
    event.preventDefault();
    setMenu({ x: event.clientX, y: event.clientY, ref, label, hasSource });
  };
  const [query, setQuery] = useState("");
  const [expanded, setExpanded] = useState<ReadonlySet<string>>(new Set());
  const searching = query.trim().length > 0;
  const pendingReveal = useLibraryReveal((state) => state.pending);
  const [highlight, setHighlight] = useState<string | null>(null);

  // Show a block that was just added to the project library, once the
  // refreshed catalog lists it.
  useEffect(() => {
    if (pendingReveal === null || index === null) {
      return;
    }
    const block = index.blocksByRef.get(pendingReveal);
    if (block === undefined) {
      return;
    }
    useLibraryReveal.getState().consume();
    const group = libraryGroupFor(block);
    const prefs = useLibraryPrefs.getState();
    if (prefs.hidden.has(group)) {
      prefs.setHidden(group, false);
    }
    if (!prefs.expanded.has(group)) {
      prefs.expandAll([group]);
    }
    prefs.clearSearchOverrides();
    setQuery("");
    setHighlight(block.ref);
  }, [pendingReveal, index]);

  useEffect(() => {
    if (highlight === null) {
      return;
    }
    const entry = document.querySelector<HTMLElement>(
      `[data-testid="library-browser"] [data-ref="${highlight.replace(/["\\]/g, "\\$&")}"]`,
    );
    entry?.scrollIntoView?.({ block: "nearest" });
    const timer = setTimeout(() => setHighlight(null), REVEAL_HIGHLIGHT_MS);
    return () => clearTimeout(timer);
  }, [highlight]);

  const groups = useMemo(
    () =>
      index === null
        ? []
        : searchGroups(
            index.groups.filter((group) => group.name !== JUNCTION_GROUP && !hidden.has(group.name)),
            query,
          ),
    [index, query, hidden],
  );

  const junctions = useMemo<JunctionEntry[]>(() => {
    if (index === null || hidden.has(JUNCTION_GROUP)) {
      return [];
    }
    const needle = query.trim().toLowerCase();
    return index.junctions
      .map((junction) => {
        const kind = junction.ref.split(":").pop() ?? "0";
        return {
          key: junction.ref,
          name: `Junction ${kind}`,
          junction: (kind === "1" ? "1" : "0") as JunctionType,
        };
      })
      .filter(
        (entry) =>
          needle.length === 0 ||
          entry.name.toLowerCase().includes(needle) ||
          `junction ${entry.junction}`.includes(needle),
      );
  }, [index, query, hidden]);

  const shapes = useMemo<ShapeEntry[]>(
    () => (hidden.has(SHAPES_GROUP) ? [] : searchShapes(query)),
    [query, hidden],
  );

  const blockEntries: { group: string; entries: BlockEntry[] }[] = useMemo(
    () =>
      groups
        .filter((group) => group.blocks.length > 0)
        .map((group) => ({
          group: group.name,
          entries: group.blocks.map((block) => ({
            key: block.ref,
            name: block.name,
            summary: blockSummary(block),
            description: block.description,
            icon: block.icon,
            block,
          })),
        })),
    [groups],
  );

  const toggle = (key: string): void => {
    setExpanded((current) => {
      const next = new Set(current);
      if (next.has(key)) {
        next.delete(key);
      } else {
        next.add(key);
      }
      return next;
    });
  };

  // A search shows every category with a match expanded, unless the user
  // collapsed it during this search; without a search the saved state applies.
  const isGroupOpen = (name: string): boolean =>
    searching ? !searchCollapsed.has(name) : savedExpanded.has(name);
  const toggleGroup = (name: string): void => {
    const prefs = useLibraryPrefs.getState();
    if (searching) {
      prefs.toggleSearchCollapsed(name);
    } else {
      prefs.toggleExpanded(name);
    }
  };

  const onDragStart = (
    event: DragEvent<HTMLLIElement>,
    entry: BlockEntry | JunctionEntry | ShapeEntry,
  ) => {
    if ("block" in entry) {
      writeDragPayload(event.dataTransfer, payloadForBlock(entry.block));
    } else if ("kind" in entry) {
      writeDragPayload(event.dataTransfer, payloadForShape(entry.kind));
    } else {
      writeDragPayload(event.dataTransfer, { kind: "junction", junction: entry.junction });
    }
  };

  // A grid tile: the icon and the name only. A block or junction tile is dragged onto the canvas;
  // right-click (or the context-menu key) offers Show source and Info. A shape tile adds the shape.
  const renderTile = (
    entry: BlockEntry | JunctionEntry | ShapeEntry,
    tile: {
      testId: string;
      ref?: string;
      shape?: string;
      icon?: string;
      title: string;
      glyph: ReactNode;
      onActivate?: () => void;
    },
  ): ReactNode => (
    <li
      key={entry.key}
      className={`library-item library-item--tile${tile.ref !== undefined && tile.ref === highlight ? " is-new" : ""}`}
      draggable
      data-testid={tile.testId}
      data-new={tile.ref !== undefined && tile.ref === highlight ? "true" : undefined}
      data-ref={tile.ref}
      data-shape={tile.shape}
      data-icon={tile.icon}
      onDragStart={(event) => onDragStart(event, entry)}
      onContextMenu={
        tile.onActivate === undefined && tile.ref !== undefined
          ? (event) => openMenu(event, tile.ref ?? "", entry.name, "block" in entry)
          : undefined
      }
      title={tile.title}
    >
      <button
        type="button"
        className="library-item__tile"
        aria-haspopup={tile.onActivate === undefined ? "menu" : undefined}
        onClick={tile.onActivate}
      >
        <span className="library-item__icon library-item__icon--tile" aria-hidden="true">
          {tile.glyph}
        </span>
        <span className="library-item__label">{entry.name}</span>
      </button>
    </li>
  );

  if (index === null) {
    return (
      <div className="library library--status" data-testid="library-browser">
        {status === "error" && waitForWorker ? (
          <WaitingForWorker what="the library" detail={error} onRetry={retrySession} compact testId="library-waiting" />
        ) : status === "error" ? (
          <div className="library__error" role="alert">
            <p className="library__error-title">The library is unavailable</p>
            <p className="library__error-detail">{error ?? "The backend could not load the catalog."}</p>
            <button type="button" className="button" onClick={retrySession} data-testid="library-retry">
              Retry
            </button>
          </div>
        ) : (
          <p className="library__loading" data-testid="library-loading">
            Loading the library…
          </p>
        )}
      </div>
    );
  }

  const visibleCount =
    blockEntries.reduce((count, group) => count + group.entries.length, 0) +
    junctions.length +
    shapes.length;
  const allHidden =
    libraryCategories(index).every((name) => hidden.has(name)) &&
    hidden.size > 0;

  return (
    <div className="library" data-testid="library-browser" data-view={grid ? "grid" : "list"}>
      <div className="library__search">
        <input
          type="search"
          className="library__search-input"
          placeholder="Search blocks, ports, groups…"
          aria-label="Search the library"
          data-testid="library-search"
          value={query}
          onChange={(event) => {
            useLibraryPrefs.getState().clearSearchOverrides();
            setQuery(event.target.value);
          }}
        />
        <span className="library__count" data-testid="library-count">
          {visibleCount}
        </span>
      </div>

      <div className="library__groups">
        {blockEntries.map((group) => (
          <LibraryGroupSection
            key={group.group}
            name={group.group}
            count={group.entries.length}
            open={isGroupOpen(group.group)}
            onToggle={() => toggleGroup(group.group)}
            grid={grid}
          >
            {group.entries.map((entry) => {
              if (grid) {
                return renderTile(entry, {
                  testId: `library-item-${entry.name}`,
                  ref: entry.block.ref,
                  icon: entry.icon,
                  title: `${entry.name} — ${entry.description}`,
                  glyph: <BlockIcon icon={entry.icon} name={entry.name} size={40} />,
                });
              }
              const isOpen = expanded.has(entry.key);
              return (
                <li
                  key={entry.key}
                  className={`library-item${isOpen ? " is-open" : ""}${entry.block.ref === highlight ? " is-new" : ""}`}
                  draggable
                  data-testid={`library-item-${entry.name}`}
                  data-new={entry.block.ref === highlight ? "true" : undefined}
                  data-ref={entry.block.ref}
                  data-icon={entry.icon}
                  onDragStart={(event) => onDragStart(event, entry)}
                  onContextMenu={(event) => openMenu(event, entry.block.ref, entry.name, true)}
                  title={`${entry.block.ref} — ${entry.description}`}
                >
                  <button
                    type="button"
                    className="library-item__main"
                    onClick={() => toggle(entry.key)}
                    aria-expanded={isOpen}
                  >
                    <span className="library-item__icon" aria-hidden="true">
                      <BlockIcon icon={entry.icon} name={entry.name} size={30} />
                    </span>
                    <span className="library-item__text">
                      <span className="library-item__name">{entry.name}</span>
                      <span className="library-item__summary">{entry.summary}</span>
                    </span>
                    <span className="library-item__chevron" aria-hidden="true">
                      {isOpen ? "▾" : "▸"}
                    </span>
                  </button>
                  {isOpen ? (
                    <div className="library-item__details">
                      <p className="library-item__description">{entry.description}</p>
                      <p className="library-item__ref">
                        {entry.block.ref}
                        <BlockHelpButton blockRef={entry.block.ref} label={entry.name} />
                      </p>
                      {entry.block.parameters.length > 0 ? (
                        <dl className="library-item__params">
                          {entry.block.parameters.map((parameter) => (
                            <div className="library-item__param" key={parameter.name}>
                              <dt>{parameter.name}</dt>
                              <dd>
                                {parameter.default}
                                {parameter.unit ? <span> {parameter.unit}</span> : null}
                              </dd>
                            </div>
                          ))}
                        </dl>
                      ) : (
                        <p className="library-item__none">No parameters.</p>
                      )}
                      {portLines(entry.block).length > 0 ? (
                        <ul className="library-item__ports">
                          {portLines(entry.block).map((line) => (
                            <li
                              key={line.key}
                              data-testid={`library-port-${entry.name}-${line.key}`}
                            >
                              {line.glyph !== null ? <PortGlyph {...line.glyph} /> : null}
                              <span className="library-item__domain" aria-hidden="true">
                                {line.domain}
                              </span>
                              {line.text}
                            </li>
                          ))}
                        </ul>
                      ) : (
                        <p className="library-item__none">No ports.</p>
                      )}
                    </div>
                  ) : null}
                </li>
              );
            })}
          </LibraryGroupSection>
        ))}

        {junctions.length > 0 ? (
          <LibraryGroupSection
            name={JUNCTION_GROUP}
            count={junctions.length}
            open={isGroupOpen(JUNCTION_GROUP)}
            onToggle={() => toggleGroup(JUNCTION_GROUP)}
            grid={grid}
          >
            {junctions.map((entry) => {
              if (grid) {
                return renderTile(entry, {
                  testId: `library-item-junction-${entry.junction}`,
                  ref: entry.key,
                  title: `${entry.name} — ${junctionDescription(entry.junction)}`,
                  glyph: <JunctionGlyph kind={entry.junction} size={40} />,
                });
              }
              const isOpen = expanded.has(entry.key);
              return (
                <li
                  key={entry.key}
                  className={`library-item${isOpen ? " is-open" : ""}`}
                  draggable
                  data-testid={`library-item-junction-${entry.junction}`}
                  data-ref={entry.key}
                  onDragStart={(event) => onDragStart(event, entry)}
                  onContextMenu={(event) => openMenu(event, entry.key, entry.name, false)}
                  title={`${entry.name} — bonds attach to the circle edge`}
                >
                  <button
                    type="button"
                    className="library-item__main"
                    onClick={() => toggle(entry.key)}
                    aria-expanded={isOpen}
                  >
                    <span className="library-item__icon" aria-hidden="true">
                      <JunctionGlyph kind={entry.junction} size={30} />
                    </span>
                    <span className="library-item__text">
                      <span className="library-item__name">{entry.name}</span>
                      <span className="library-item__summary">power junction · 1+ bonds</span>
                    </span>
                    <span className="library-item__chevron" aria-hidden="true">
                      {isOpen ? "▾" : "▸"}
                    </span>
                  </button>
                  {isOpen ? (
                    <div className="library-item__details">
                      <p className="library-item__description">
                        {junctionDescription(entry.junction)}
                      </p>
                      <p className="library-item__ref">{entry.key}</p>
                    </div>
                  ) : null}
                </li>
              );
            })}
          </LibraryGroupSection>
        ) : null}

        {shapes.length > 0 ? (
          <LibraryGroupSection
            name={SHAPES_GROUP}
            count={shapes.length}
            open={isGroupOpen(SHAPES_GROUP)}
            onToggle={() => toggleGroup(SHAPES_GROUP)}
            grid={grid}
          >
            {shapes.map((entry) => {
              const testId = `library-item-shape-${entry.kind}`;
              const title = `${entry.name} — ${SHAPE_DESCRIPTION}. Drag it onto the canvas, or click to add it in the middle.`;
              const add = (): void => requestShapeAtCentre(entry.kind);
              if (grid) {
                return renderTile(entry, {
                  testId,
                  shape: entry.kind,
                  title,
                  glyph: <ShapeGlyph kind={entry.kind} size={40} />,
                  onActivate: add,
                });
              }
              return (
                <li
                  key={entry.key}
                  className="library-item"
                  draggable
                  data-testid={testId}
                  data-shape={entry.kind}
                  onDragStart={(event) => onDragStart(event, entry)}
                  title={title}
                >
                  <button type="button" className="library-item__main" onClick={add}>
                    <span className="library-item__icon" aria-hidden="true">
                      <ShapeGlyph kind={entry.kind} size={30} />
                    </span>
                    <span className="library-item__text">
                      <span className="library-item__name">{entry.name}</span>
                      <span className="library-item__summary">{SHAPE_DESCRIPTION}</span>
                    </span>
                  </button>
                </li>
              );
            })}
          </LibraryGroupSection>
        ) : null}

        {allHidden ? (
          <p className="library__no-match" data-testid="library-all-hidden">
            Every category is hidden. Use the library settings (the cog) to show them again.
          </p>
        ) : visibleCount === 0 ? (
          <p className="library__no-match" data-testid="library-empty">
            {hidden.size > 0
              ? `No block in the shown categories matches “${query}”. Clear the search, or show more categories in the library settings.`
              : `No block matches “${query}”. Clear the search, or try a group name such as “Bond graph”.`}
          </p>
        ) : null}
      </div>
      {menu !== null ? <LibraryItemMenu menu={menu} onClose={() => setMenu(null)} /> : null}
    </div>
  );
}
