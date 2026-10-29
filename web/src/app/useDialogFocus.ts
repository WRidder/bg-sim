import { useEffect, type RefObject } from "react";

const FOCUSABLE =
  'a[href], button:not([disabled]), input:not([disabled]), select:not([disabled]), textarea:not([disabled]), [tabindex]:not([tabindex="-1"])';

function focusableIn(root: HTMLElement): HTMLElement[] {
  return [...root.querySelectorAll<HTMLElement>(FOCUSABLE)].filter(
    (element) => element.getClientRects().length > 0,
  );
}

/**
 * Modal dialog behaviour (WAI-ARIA dialog pattern): focus moves into the dialog
 * when it opens, Tab and Shift+Tab wrap inside it, Escape closes it, and focus
 * returns to the element that opened it.
 */
export function useDialogFocus(
  open: boolean,
  dialog: RefObject<HTMLElement | null>,
  onClose: () => void,
): void {
  useEffect(() => {
    if (!open) {
      return;
    }
    const opener = document.activeElement instanceof HTMLElement ? document.activeElement : null;
    dialog.current?.focus();

    const onKeyDown = (event: KeyboardEvent): void => {
      const root = dialog.current;
      if (root === null) {
        return;
      }
      if (event.key === "Escape") {
        event.preventDefault();
        event.stopPropagation();
        onClose();
        return;
      }
      if (event.key !== "Tab") {
        return;
      }
      const items = focusableIn(root);
      const first = items[0];
      const last = items[items.length - 1];
      if (first === undefined || last === undefined) {
        event.preventDefault();
        root.focus();
        return;
      }
      const active = document.activeElement;
      if (!root.contains(active) || active === root) {
        event.preventDefault();
        (event.shiftKey ? last : first).focus();
      } else if (event.shiftKey && active === first) {
        event.preventDefault();
        last.focus();
      } else if (!event.shiftKey && active === last) {
        event.preventDefault();
        first.focus();
      }
    };
    window.addEventListener("keydown", onKeyDown, true);
    return () => {
      window.removeEventListener("keydown", onKeyDown, true);
      if (opener !== null && document.contains(opener)) {
        opener.focus();
      }
    };
  }, [dialog, onClose, open]);
}
