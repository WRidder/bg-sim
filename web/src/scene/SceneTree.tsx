import { useState } from "react";

import type { TreeEntry } from "./resolve";

export interface SceneTreeProps {
  readonly tree: readonly TreeEntry[];
  /** The selected entity ref, or null. */
  readonly selected: string | null;
  readonly onSelect: (ref: string | null) => void;
}

/** Glyph plus word for each entity kind, so the kind is never carried by colour alone. */
const KIND_GLYPH: Record<TreeEntry["kind"], string> = {
  model: "▣",
  link: "■",
  joint: "◎",
  frame: "┼",
  visual: "◇",
};

function Row({ entry, depth, selected, collapsed, toggle, onSelect }: {
  entry: TreeEntry;
  depth: number;
  selected: string | null;
  collapsed: ReadonlySet<string>;
  toggle: (ref: string) => void;
  onSelect: (ref: string | null) => void;
}) {
  const open = !collapsed.has(entry.ref);
  const isSelected = selected === entry.ref;
  return (
    <li className="scene-tree__item">
      <div
        className="scene-tree__row"
        style={{ paddingLeft: `calc(var(--space-2) * ${depth} + var(--space-1))` }}
        data-selected={isSelected ? "true" : undefined}
      >
        {entry.children.length > 0 ? (
          <button
            type="button"
            className="scene-tree__toggle"
            aria-label={`${open ? "Collapse" : "Expand"} ${entry.label}`}
            aria-expanded={open}
            onClick={() => {
              toggle(entry.ref);
            }}
          >
            {open ? "▾" : "▸"}
          </button>
        ) : (
          <span className="scene-tree__toggle" aria-hidden="true" />
        )}
        <button
          type="button"
          className="scene-tree__label"
          data-testid={`scene-tree-row-${entry.ref}`}
          data-kind={entry.kind}
          aria-pressed={isSelected}
          onClick={() => {
            onSelect(isSelected ? null : entry.ref);
          }}
        >
          <span className="scene-tree__glyph" aria-hidden="true">
            {KIND_GLYPH[entry.kind]}
          </span>
          <span className="scene-tree__name">{entry.label}</span>
          <span className="scene-tree__kind">{entry.detail === "" ? entry.kind : `${entry.kind} · ${entry.detail}`}</span>
        </button>
      </div>
      {entry.children.length > 0 && open ? (
        <ul className="scene-tree__list">
          {entry.children.map((child) => (
            <Row key={child.ref} entry={child} depth={depth + 1} selected={selected} collapsed={collapsed} toggle={toggle} onSelect={onSelect} />
          ))}
        </ul>
      ) : null}
    </li>
  );
}

/**
 * The scene as a tree beside the 3D view: models, links with their visuals, joints and frames.
 * It lives in the 3D View tab, not in the left panel, because it exists only while a scene is
 * loaded in the viewer and selecting in either place drives the other (the viewer's selection).
 * A row is a toggle: click to select and outline, click again to clear.
 */
export function SceneTree({ tree, selected, onSelect }: SceneTreeProps) {
  const [open, setOpen] = useState(true);
  const [collapsed, setCollapsed] = useState<ReadonlySet<string>>(new Set());
  const toggle = (ref: string) => {
    setCollapsed((previous) => {
      const next = new Set(previous);
      if (!next.delete(ref)) next.add(ref);
      return next;
    });
  };
  return (
    <aside className="scene-tree" data-testid="scene-tree" data-open={open} aria-label="Scene tree">
      <button
        type="button"
        className="scene-tree__header"
        aria-expanded={open}
        data-testid="scene-tree-toggle"
        onClick={() => {
          setOpen(!open);
        }}
      >
        <span aria-hidden="true">{open ? "▾" : "▸"}</span> Scene
      </button>
      {open ? (
        <ul className="scene-tree__list scene-tree__list--root" aria-label="Scene entities">
          {tree.map((entry) => (
            <Row key={entry.ref} entry={entry} depth={0} selected={selected} collapsed={collapsed} toggle={toggle} onSelect={onSelect} />
          ))}
        </ul>
      ) : null}
    </aside>
  );
}
