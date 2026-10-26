/**
 * Ctrl-drag quick connect: while Ctrl (or Cmd) is held, pressing anywhere on an
 * element starts a connection from its nearest source port instead of moving
 * the element (the canvas implements the gesture and supplies this context).
 */

import { createContext, useContext } from "react";
import type { PointerEvent as ReactPointerEvent } from "react";

export interface QuickConnect {
  enabled: boolean;
  start: (event: ReactPointerEvent, nodeId: string) => void;
}

export const QuickConnectContext = createContext<QuickConnect>({
  enabled: false,
  start: () => undefined,
});

export function useQuickConnect(): QuickConnect {
  return useContext(QuickConnectContext);
}
