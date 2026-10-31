/**
 * A sticky note on the canvas (`diagram.annotations`, kind `text`): a coloured
 * card behind the blocks and wires with Markdown text.
 *
 * * The text renders with the Docs renderer, restricted (no images or tables,
 *   headings as bold text); it loads lazily, plain text shows meanwhile.
 * * Double-click (or "Edit text" in its menu) swaps in a plain textarea of the
 *   same size; a click outside or Esc goes back. One editing session is one
 *   undo step.
 * * A selected note resizes from its corners; it moves like any node.
 * * Long text scrolls inside the note: while the text overflows, the wheel
 *   scrolls the note instead of zooming the canvas (`nowheel`).
 */

import { lazy, memo, Suspense, useCallback, useEffect, useLayoutEffect, useRef, useState } from "react";
import {
  NodeResizer,
  type Node,
  type NodeProps,
  type OnResize,
} from "@xyflow/react";

import type { AnnotationColor } from "../../contracts/model";
import { useDocumentStore } from "../../state/documentStore";
import { NOTE_MIN_SIZE } from "../notes";
import { beginNoteTextGesture, endNoteTextGesture, useNoteEditStore } from "../noteEditing";
import "./note.css";

const NoteMarkdown = lazy(() => import("../../docs/NoteMarkdown"));

export interface NoteNodeData extends Record<string, unknown> {
  /** The annotation id (the canvas id is `note:<id>`). */
  noteId: string;
  text: string;
  color: AnnotationColor;
}

export type NoteNodeType = Node<NoteNodeData, "note">;

function NoteEditor({ noteId, text }: { noteId: string; text: string }) {
  const [draft, setDraft] = useState(text);
  const ref = useRef<HTMLTextAreaElement>(null);

  useEffect(() => {
    beginNoteTextGesture(noteId);
    const area = ref.current;
    if (area !== null) {
      area.focus();
      area.setSelectionRange(area.value.length, area.value.length);
    }
    // A press anywhere outside the editor ends the edit, also where the canvas
    // keeps the focus from moving (a press on the pane or on another node).
    const onPointerDown = (event: PointerEvent): void => {
      if (event.target instanceof window.Node && ref.current?.contains(event.target) === true) {
        return;
      }
      useNoteEditStore.getState().stop(noteId);
    };
    window.addEventListener("pointerdown", onPointerDown, true);
    return () => {
      window.removeEventListener("pointerdown", onPointerDown, true);
      endNoteTextGesture(noteId);
    };
  }, [noteId]);

  const finish = (): void => {
    useNoteEditStore.getState().stop(noteId);
  };

  return (
    <textarea
      ref={ref}
      className="sticky-note__editor nodrag nowheel nopan"
      data-testid="sticky-note-editor"
      aria-label="Note text (Markdown)"
      spellCheck
      value={draft}
      placeholder="Write a note in Markdown…"
      onChange={(event) => {
        const value = event.target.value;
        setDraft(value);
        useDocumentStore.getState().setNoteText(noteId, value, { coalesce: true });
      }}
      onBlur={finish}
      onKeyDown={(event) => {
        // The canvas and xyflow keep their keys (Del, R, arrows) away from the text.
        event.stopPropagation();
        if (event.key === "Escape") {
          event.preventDefault();
          finish();
        }
      }}
      // A double-click selects a word; it must not reach the note's own handler.
      onDoubleClick={(event) => event.stopPropagation()}
    />
  );
}

function NoteText({ text }: { text: string }) {
  const scrollRef = useRef<HTMLDivElement>(null);
  const innerRef = useRef<HTMLDivElement>(null);
  const [overflows, setOverflows] = useState(false);

  const measure = useCallback(() => {
    const box = scrollRef.current;
    if (box !== null) {
      setOverflows(box.scrollHeight > box.clientHeight + 1);
    }
  }, []);

  useLayoutEffect(measure, [measure, text]);
  useEffect(() => {
    if (typeof ResizeObserver === "undefined") {
      return undefined;
    }
    const observer = new ResizeObserver(measure);
    if (scrollRef.current !== null) {
      observer.observe(scrollRef.current);
    }
    if (innerRef.current !== null) {
      observer.observe(innerRef.current);
    }
    return () => observer.disconnect();
  }, [measure]);

  return (
    <div
      ref={scrollRef}
      className={`sticky-note__content${overflows ? " nowheel is-scrollable" : ""}`}
      data-testid="sticky-note-content"
      data-scrollable={overflows ? "true" : "false"}
    >
      <div ref={innerRef} className="sticky-note__markdown">
        {text.trim() === "" ? (
          <p className="sticky-note__placeholder">Double-click to write a note.</p>
        ) : (
          <Suspense fallback={<p className="sticky-note__plain">{text}</p>}>
            <NoteMarkdown text={text} />
          </Suspense>
        )}
      </div>
    </div>
  );
}

function NoteNodeView({ data, selected, width, height }: NodeProps<NoteNodeType>) {
  const editing = useNoteEditStore((state) => state.editing === data.noteId);

  const onResizeStart = useCallback(() => {
    useDocumentStore.getState().beginGesture("note-resize");
  }, []);
  const onResize: OnResize = useCallback(
    (_event, params) => {
      useDocumentStore.getState().setNoteFrame(
        data.noteId,
        { x: params.x, y: params.y, w: params.width, h: params.height },
        true,
      );
    },
    [data.noteId],
  );
  const onResizeEnd = useCallback(() => {
    useDocumentStore.getState().endGesture();
  }, []);

  return (
    <div
      className={`sticky-note sticky-note--${data.color}${selected ? " is-selected" : ""}${editing ? " is-editing" : ""}`}
      style={{ width: width ?? "100%", height: height ?? "100%" }}
      data-testid="sticky-note"
      data-note-id={data.noteId}
      data-color={data.color}
      onDoubleClick={() => useNoteEditStore.getState().start(data.noteId)}
    >
      <NodeResizer
        isVisible={selected === true && !editing}
        minWidth={NOTE_MIN_SIZE.w}
        minHeight={NOTE_MIN_SIZE.h}
        handleClassName="sticky-note__handle"
        lineClassName="sticky-note__resize-line"
        onResizeStart={onResizeStart}
        onResize={onResize}
        onResizeEnd={onResizeEnd}
      />
      <div className="sticky-note__paper">
        {editing ? <NoteEditor noteId={data.noteId} text={data.text} /> : <NoteText text={data.text} />}
      </div>
      <span className="sticky-note__fold" aria-hidden="true" />
    </div>
  );
}

export const NoteNode = memo(NoteNodeView);
