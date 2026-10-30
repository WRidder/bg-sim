/**
 * The page tree of the Docs tab (W5.6): a WAI-ARIA tree with roving focus, inline rename
 * (double-click or F2), drag and drop re-ordering and re-parenting, and the keyboard
 * alternatives Alt+Up/Down (reorder) and Alt+Left/Right (outdent/indent).
 */

import { useEffect, useMemo, useRef, useState, type DragEvent, type KeyboardEvent } from "react";

import { visibleRows, type Docs, type DocsPage, type DropPosition, type TreeRow } from "./pageTree";

export interface DocsTreeProps {
  docs: Docs;
  selected: string | null;
  dirty: ReadonlySet<string>;
  onSelect: (id: string) => void;
  onNewSibling: (afterId: string | null) => void;
  onNewChild: (parentId: string) => void;
  onRename: (id: string, title: string) => void;
  onRemove: (id: string) => void;
  onMove: (id: string, targetId: string, position: DropPosition) => void;
  /** Alt+Arrow; resolves to whether the tree changed. */
  onMoveKey: (id: string, key: string) => Promise<boolean>;
}

const DRAG_MIME = "application/x-bgsim-docs-page";

function dropPositionOf(event: DragEvent<HTMLElement>): DropPosition {
  const rect = event.currentTarget.getBoundingClientRect();
  const offset = (event.clientY - rect.top) / Math.max(rect.height, 1);
  return offset < 0.25 ? "before" : offset > 0.75 ? "after" : "inside";
}

type IconName = "page" | "child" | "rename" | "delete";

const ICON_PATHS: Record<IconName, string> = {
  // A sheet with a plus.
  page: "M4 1.5h5l3 3v10H4z M9 1.5v3h3 M8 7v4 M6 9h4",
  // A sheet with an arrow into it (a page inside a page).
  child: "M3 1.5h5l3 3v5 M8 1.5v3h3 M3 1.5v8 M3 12.5h4 M5.5 10.5l2 2-2 2 M11 11v4 M9 13h4",
  rename: "M2.5 13.5l.7-3L11 2.7l2.3 2.3L5.5 12.8z M9.8 3.9l2.3 2.3",
  delete: "M3 4.5h10 M6 4.5V2.5h4v2 M4.5 4.5l.6 9h5.8l.6-9 M7 7v4.5 M9 7v4.5",
};

function ToolbarIcon({ name }: { name: IconName }) {
  return (
    <svg
      width="16"
      height="16"
      viewBox="0 0 16 16"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.3"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
      focusable="false"
    >
      <path d={ICON_PATHS[name]} />
    </svg>
  );
}

function descendantIds(page: DocsPage): string[] {
  return page.children.flatMap((child) => [child.id, ...descendantIds(child)]);
}

export function DocsTree(props: DocsTreeProps) {
  const { docs, selected, dirty, onSelect, onNewSibling, onNewChild, onRename, onRemove, onMove, onMoveKey } = props;
  const [collapsed, setCollapsed] = useState<ReadonlySet<string>>(new Set());
  const [editing, setEditing] = useState<string | null>(null);
  const [focusId, setFocusId] = useState<string | null>(null);
  const [dragId, setDragId] = useState<string | null>(null);
  const [drop, setDrop] = useState<{ id: string; position: DropPosition } | null>(null);
  const pendingFocus = useRef<string | null>(null);
  const rowRefs = useRef(new Map<string, HTMLDivElement>());

  const rows = useMemo(() => visibleRows(docs, collapsed), [docs, collapsed]);
  const active = focusId !== null && rows.some((row) => row.page.id === focusId) ? focusId : (selected ?? rows[0]?.page.id ?? null);

  useEffect(() => {
    const id = pendingFocus.current;
    if (id !== null) {
      rowRefs.current.get(id)?.focus();
      pendingFocus.current = null;
    }
  });

  const focusRow = (id: string | undefined): void => {
    if (id === undefined) {
      return;
    }
    setFocusId(id);
    rowRefs.current.get(id)?.focus();
  };

  const setOpen = (id: string, open: boolean): void => {
    setCollapsed((previous) => {
      const next = new Set(previous);
      if (open) {
        next.delete(id);
      } else {
        next.add(id);
      }
      return next;
    });
  };

  const onKeyDown = (event: KeyboardEvent<HTMLDivElement>, row: TreeRow, index: number): void => {
    if (event.target !== event.currentTarget) {
      return;
    }
    const { page } = row;
    if (event.altKey && event.key.startsWith("Arrow")) {
      event.preventDefault();
      pendingFocus.current = page.id;
      void onMoveKey(page.id, event.key).then((changed) => {
        if (changed && event.key === "ArrowRight") {
          // Indenting nests the page under its previous sibling; make sure it is visible.
          const above = rows[index - 1];
          if (above !== undefined) {
            setOpen(above.page.id, true);
          }
        }
        rowRefs.current.get(page.id)?.focus();
      });
      return;
    }
    switch (event.key) {
      case "ArrowDown":
        event.preventDefault();
        focusRow(rows[index + 1]?.page.id);
        break;
      case "ArrowUp":
        event.preventDefault();
        focusRow(rows[index - 1]?.page.id);
        break;
      case "Home":
        event.preventDefault();
        focusRow(rows[0]?.page.id);
        break;
      case "End":
        event.preventDefault();
        focusRow(rows[rows.length - 1]?.page.id);
        break;
      case "ArrowRight":
        event.preventDefault();
        if (page.children.length > 0) {
          if (collapsed.has(page.id)) {
            setOpen(page.id, true);
          } else {
            focusRow(page.children[0]?.id);
          }
        }
        break;
      case "ArrowLeft":
        event.preventDefault();
        if (page.children.length > 0 && !collapsed.has(page.id)) {
          setOpen(page.id, false);
        } else if (row.parentId !== null) {
          focusRow(row.parentId);
        }
        break;
      case "Enter":
      case " ":
        event.preventDefault();
        onSelect(page.id);
        break;
      case "F2":
        event.preventDefault();
        setEditing(page.id);
        break;
      case "Delete":
        event.preventDefault();
        onRemove(page.id);
        break;
      default:
        break;
    }
  };

  const commitRename = (id: string, title: string): void => {
    setEditing(null);
    onRename(id, title);
    pendingFocus.current = id;
  };

  const forbidden = useMemo(() => {
    if (dragId === null) {
      return new Set<string>();
    }
    const dragged = rows.find((row) => row.page.id === dragId);
    return new Set(dragged === undefined ? [dragId] : [dragId, ...descendantIds(dragged.page)]);
  }, [dragId, rows]);

  const renderList = (pages: readonly DocsPage[], depth: number): React.ReactNode =>
    pages.map((page, position) => {
      const index = rows.findIndex((row) => row.page.id === page.id);
      const row = rows[index];
      if (row === undefined) {
        return null;
      }
      const hasChildren = page.children.length > 0;
      const open = !collapsed.has(page.id);
      const isSelected = selected === page.id;
      const dropHere = drop?.id === page.id ? drop.position : undefined;
      return (
        <li key={page.id} role="none">
          <div
            ref={(element) => {
              if (element === null) {
                rowRefs.current.delete(page.id);
              } else {
                rowRefs.current.set(page.id, element);
              }
            }}
            role="treeitem"
            aria-level={depth + 1}
            aria-setsize={pages.length}
            aria-posinset={position + 1}
            aria-selected={isSelected}
            aria-expanded={hasChildren ? open : undefined}
            tabIndex={active === page.id ? 0 : -1}
            className="docs-tree__row"
            style={{ paddingLeft: `calc(var(--space-2) * ${depth} + var(--space-1))` }}
            data-testid={`docs-tree-item-${page.id}`}
            data-page-id={page.id}
            data-dirty={dirty.has(page.id) ? "true" : undefined}
            data-drop={dropHere}
            draggable={editing !== page.id}
            onFocus={(event) => {
              if (event.target === event.currentTarget) {
                setFocusId(page.id);
              }
            }}
            onClick={() => {
              setFocusId(page.id);
              onSelect(page.id);
            }}
            onDoubleClick={() => setEditing(page.id)}
            onKeyDown={(event) => onKeyDown(event, row, index)}
            onDragStart={(event) => {
              event.dataTransfer.setData(DRAG_MIME, page.id);
              event.dataTransfer.setData("text/plain", page.title);
              event.dataTransfer.effectAllowed = "move";
              setDragId(page.id);
            }}
            onDragOver={(event) => {
              if (dragId === null || forbidden.has(page.id)) {
                return;
              }
              event.preventDefault();
              event.dataTransfer.dropEffect = "move";
              const position = dropPositionOf(event);
              if (drop?.id !== page.id || drop.position !== position) {
                setDrop({ id: page.id, position });
              }
            }}
            onDragLeave={() => setDrop((current) => (current?.id === page.id ? null : current))}
            onDrop={(event) => {
              const id = event.dataTransfer.getData(DRAG_MIME);
              if (id === "" || forbidden.has(page.id)) {
                return;
              }
              event.preventDefault();
              const position = dropPositionOf(event);
              setDrop(null);
              setDragId(null);
              pendingFocus.current = id;
              onMove(id, page.id, position);
              if (position === "inside") {
                setOpen(page.id, true);
              }
            }}
            onDragEnd={() => {
              setDragId(null);
              setDrop(null);
            }}
          >
            <span
              className="docs-tree__toggle"
              aria-hidden="true"
              onClick={(event) => {
                if (hasChildren) {
                  event.stopPropagation();
                  setOpen(page.id, !open);
                }
              }}
            >
              {hasChildren ? (open ? "▾" : "▸") : ""}
            </span>
            {editing === page.id ? (
              <input
                className="docs-tree__input"
                aria-label="Page title"
                defaultValue={page.title}
                maxLength={200}
                autoFocus
                onFocus={(event) => event.currentTarget.select()}
                onClick={(event) => event.stopPropagation()}
                onDoubleClick={(event) => event.stopPropagation()}
                onKeyDown={(event) => {
                  event.stopPropagation();
                  if (event.key === "Enter") {
                    commitRename(page.id, event.currentTarget.value);
                  } else if (event.key === "Escape") {
                    setEditing(null);
                    pendingFocus.current = page.id;
                  }
                }}
                onBlur={(event) => {
                  if (editing === page.id) {
                    commitRename(page.id, event.currentTarget.value);
                  }
                }}
              />
            ) : (
              <span className="docs-tree__title">{page.title}</span>
            )}
            {dirty.has(page.id) ? (
              <span className="docs-tree__dirty" title="Unsaved changes">
                <span aria-hidden="true">●</span>
                <span className="visually-hidden">Unsaved changes</span>
              </span>
            ) : null}
          </div>
          {hasChildren && open ? (
            <ul role="group" className="docs-tree__group">
              {renderList(page.children, depth + 1)}
            </ul>
          ) : null}
        </li>
      );
    });

  const selectedRow = rows.find((row) => row.page.id === selected);

  return (
    <div className="docs-tree" data-testid="docs-tree">
      <div className="docs-tree__toolbar" role="toolbar" aria-label="Page actions">
        <button
          type="button"
          className="icon-button"
          data-testid="docs-new-page"
          aria-label="New page"
          onClick={() => onNewSibling(selected)}
          title="New page next to the selected page"
        >
          <ToolbarIcon name="page" />
        </button>
        <button
          type="button"
          className="icon-button"
          data-testid="docs-new-child"
          aria-label="New child page"
          disabled={selected === null}
          onClick={() => selected !== null && onNewChild(selected)}
          title="New page inside the selected page"
        >
          <ToolbarIcon name="child" />
        </button>
        <button
          type="button"
          className="icon-button"
          data-testid="docs-rename"
          aria-label="Rename page"
          disabled={selected === null}
          onClick={() => setEditing(selected)}
          title="Rename the selected page (F2)"
        >
          <ToolbarIcon name="rename" />
        </button>
        <button
          type="button"
          className="icon-button"
          data-testid="docs-delete"
          aria-label="Delete page"
          disabled={selectedRow === undefined}
          onClick={() => selected !== null && onRemove(selected)}
          title="Delete the selected page (Delete)"
        >
          <ToolbarIcon name="delete" />
        </button>
      </div>
      <ul role="tree" aria-label="Pages" className="docs-tree__list">
        {renderList(docs.pages, 0)}
      </ul>
      <p className="docs-tree__hint">
        Alt+Up/Down reorders, Alt+Left/Right changes the level, F2 renames. Drag a page to move it.
      </p>
    </div>
  );
}
