/**
 * The library browser of plan 7.2: groups from the catalog, a search over the
 * name/ref/group/description, the parameter and port summary, and HTML5
 * drag-to-add with the typed payload of src/library/dnd.ts.
 */

import { useMemo, useState, type DragEvent } from "react";

import type { CatalogBlock, DomainName } from "../contracts/catalog";
import type { JunctionType } from "../contracts/model";
import { retrySession } from "../state/session";
import { useCatalogStore } from "./catalogStore";
import { blockSummary, JUNCTION_GROUP, searchGroups } from "./catalogIndex";
import { payloadForBlock, writeDragPayload } from "./dnd";
import { BlockIcon, JunctionGlyph } from "../editor/icons";
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
  Generic: "G",
  Planar: "P",
  Spatial: "S",
};

function portLines(block: CatalogBlock): { key: string; text: string; domain: string }[] {
  const lines: { key: string; text: string; domain: string }[] = [];
  for (const port of block.ports) {
    lines.push({
      key: `p-${port.name}`,
      text: `${port.name} · power${port.size.length > 0 ? ` · ${port.size.join("x")}` : ""}`,
      domain: DOMAIN_LETTER[port.domain],
    });
  }
  for (const input of block.inputs) {
    lines.push({
      key: `i-${input.name}`,
      text: `${input.name} · ${input.type} input${input.unit ? ` · ${input.unit}` : ""}`,
      domain: "↦",
    });
  }
  for (const output of block.outputs) {
    lines.push({
      key: `o-${output.name}`,
      text: `${output.name} · ${output.type} output${output.unit ? ` · ${output.unit}` : ""}`,
      domain: "↦",
    });
  }
  return lines;
}

export function LibraryBrowser() {
  const index = useCatalogStore((state) => state.index);
  const status = useCatalogStore((state) => state.status);
  const error = useCatalogStore((state) => state.error);
  const [query, setQuery] = useState("");
  const [expanded, setExpanded] = useState<ReadonlySet<string>>(new Set());

  const groups = useMemo(
    () =>
      index === null
        ? []
        : searchGroups(
            index.groups.filter((group) => group.name !== JUNCTION_GROUP),
            query,
          ),
    [index, query],
  );

  const junctions = useMemo<JunctionEntry[]>(() => {
    if (index === null) {
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
  }, [index, query]);

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

  const onDragStart = (event: DragEvent<HTMLLIElement>, entry: BlockEntry | JunctionEntry) => {
    if ("block" in entry) {
      writeDragPayload(event.dataTransfer, payloadForBlock(entry.block));
    } else {
      writeDragPayload(event.dataTransfer, { kind: "junction", junction: entry.junction });
    }
  };

  if (index === null) {
    return (
      <div className="library library--status" data-testid="library-browser">
        {status === "error" ? (
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
    blockEntries.reduce((count, group) => count + group.entries.length, 0) + junctions.length;

  return (
    <div className="library" data-testid="library-browser">
      <div className="library__search">
        <input
          type="search"
          className="library__search-input"
          placeholder="Search blocks, ports, groups…"
          aria-label="Search the library"
          data-testid="library-search"
          value={query}
          onChange={(event) => setQuery(event.target.value)}
        />
        <span className="library__count" data-testid="library-count">
          {visibleCount}
        </span>
      </div>

      <div className="library__groups">
        {blockEntries.map((group) => (
          <section
            className="library-group"
            key={group.group}
            data-testid={`library-group-${group.group}`}
          >
            <h3 className="library-group__title">
              {group.group}
              <span className="library-group__count">{group.entries.length}</span>
            </h3>
            <ul className="library-group__list">
              {group.entries.map((entry) => {
                const isOpen = expanded.has(entry.key);
                return (
                  <li
                    key={entry.key}
                    className={`library-item${isOpen ? " is-open" : ""}`}
                    draggable
                    data-testid={`library-item-${entry.name}`}
                    data-ref={entry.block.ref}
                    data-icon={entry.icon}
                    onDragStart={(event) => onDragStart(event, entry)}
                    title={`${entry.block.ref} — ${entry.description}`}
                  >
                    <button
                      type="button"
                      className="library-item__main"
                      onClick={() => toggle(entry.key)}
                      aria-expanded={isOpen}
                      aria-label={`${entry.name}: ${entry.description}`}
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
                        <p className="library-item__ref">{entry.block.ref}</p>
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
                              <li key={line.key}>
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
            </ul>
          </section>
        ))}

        {junctions.length > 0 ? (
          <section className="library-group" data-testid="library-group-Junctions">
            <h3 className="library-group__title">
              {JUNCTION_GROUP}
              <span className="library-group__count">{junctions.length}</span>
            </h3>
            <ul className="library-group__list">
              {junctions.map((entry) => {
                const isOpen = expanded.has(entry.key);
                return (
                  <li
                    key={entry.key}
                    className={`library-item${isOpen ? " is-open" : ""}`}
                    draggable
                    data-testid={`library-item-junction-${entry.junction}`}
                    data-ref={entry.key}
                    onDragStart={(event) => onDragStart(event, entry)}
                    title={`${entry.name} — bonds attach to the circle edge`}
                  >
                    <button
                      type="button"
                      className="library-item__main"
                      onClick={() => toggle(entry.key)}
                      aria-expanded={isOpen}
                      aria-label={`${entry.name}: power junction`}
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
                          {entry.junction === "0"
                            ? "0 junction: equal efforts, flows sum to zero."
                            : "1 junction: equal flows, efforts sum to zero."}
                        </p>
                        <p className="library-item__ref">{entry.key}</p>
                      </div>
                    ) : null}
                  </li>
                );
              })}
            </ul>
          </section>
        ) : null}

        {visibleCount === 0 ? (
          <p className="library__no-match" data-testid="library-empty">
            No block matches “{query}”.
          </p>
        ) : null}
      </div>
    </div>
  );
}
