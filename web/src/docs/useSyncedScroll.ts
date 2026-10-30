import { useEffect, type RefObject } from "react";

/**
 * Keep the scroll position of the editor (`.cm-scroller`) and the preview (`.docs-preview`)
 * inside `root` proportional to each other while `active` (the Split mode).
 */
export function useSyncedScroll(
  active: boolean,
  root: RefObject<HTMLElement | null>,
  resetKey: string,
): void {
  useEffect(() => {
    const container = root.current;
    if (!active || container === null) {
      return;
    }
    const editor = container.querySelector<HTMLElement>(".cm-scroller");
    const preview = container.querySelector<HTMLElement>(".docs-preview");
    if (editor === null || preview === null) {
      return;
    }
    // The element that last received a programmatic scroll ignores the echo event.
    let echo: HTMLElement | null = null;
    const follow = (from: HTMLElement, to: HTMLElement) => () => {
      if (echo === from) {
        echo = null;
        return;
      }
      const room = from.scrollHeight - from.clientHeight;
      const fraction = room > 0 ? from.scrollTop / room : 0;
      const target = Math.round(fraction * (to.scrollHeight - to.clientHeight));
      if (Math.abs(to.scrollTop - target) > 1) {
        echo = to;
        to.scrollTop = target;
      }
    };
    const fromEditor = follow(editor, preview);
    const fromPreview = follow(preview, editor);
    editor.addEventListener("scroll", fromEditor, { passive: true });
    preview.addEventListener("scroll", fromPreview, { passive: true });
    return () => {
      editor.removeEventListener("scroll", fromEditor);
      preview.removeEventListener("scroll", fromPreview);
    };
  }, [active, root, resetKey]);
}
