import { useEffect, useState, type RefObject } from "react";

export interface Fullscreen {
  /** The browser offers full screen (never in a plain iframe, never in jsdom). */
  readonly canFullscreen: boolean;
  /** `ref`'s element is the full-screen element now (follows Esc and the browser's own exit). */
  readonly fullscreen: boolean;
  readonly toggle: () => void;
}

/**
 * Full screen for the element in `ref`, after the ctrlX cell view's hook. It
 * follows `fullscreenchange`, so the browser's own exit (Esc) keeps the state
 * true, and it uses the element's own document so a view detached into a
 * popup window goes full screen there.
 */
export function useFullscreen(ref: RefObject<HTMLElement | null>): Fullscreen {
  const [fullscreen, setFullscreen] = useState(false);
  const [canFullscreen, setCanFullscreen] = useState(false);
  useEffect(() => {
    const doc = ref.current?.ownerDocument ?? document;
    setCanFullscreen(doc.fullscreenEnabled === true);
    const onChange = (): void => {
      setFullscreen(doc.fullscreenElement !== null && doc.fullscreenElement === ref.current);
    };
    doc.addEventListener("fullscreenchange", onChange);
    return () => doc.removeEventListener("fullscreenchange", onChange);
  }, [ref]);
  const toggle = (): void => {
    const element = ref.current;
    if (element === null) {
      return;
    }
    if (fullscreen) {
      void element.ownerDocument.exitFullscreen();
    } else {
      void element.requestFullscreen();
    }
  };
  return { canFullscreen, fullscreen, toggle };
}
