/**
 * The "Reverse bond direction" item of the bond context menu (plan/PORT_ORIENTATION_PLAN.md O8, O14).
 *
 * Refused when a port of the bond is declared `in`/`out`, or when a `through` pair forbids it: the item
 * stays visible, is marked `aria-disabled`, and its tooltip and the line under it say why. A bond between
 * a 0-junction and a 1-junction stays enabled and says what the reversal does, never that it is harmless.
 */

import type { ReverseCheck } from "./reverseBond";

export interface ReverseBondItemProps {
  check: ReverseCheck | null;
  onReverse: () => void;
}

export function ReverseBondItem({ check, onReverse }: ReverseBondItemProps) {
  const refused = check !== null && !check.ok;
  const text = check === null ? null : check.ok ? check.note : check.reason;
  return (
    <>
      <button
        type="button"
        role="menuitem"
        data-testid="reverse-bond"
        aria-disabled={refused ? true : undefined}
        data-disabled={refused ? "true" : undefined}
        title={text ?? undefined}
        onClick={() => {
          if (!refused) {
            onReverse();
          }
        }}
      >
        Reverse bond direction
      </button>
      {text !== null ? (
        <p className="editor-menu__note" data-testid="reverse-bond-note">
          {text}
        </p>
      ) : null}
    </>
  );
}
