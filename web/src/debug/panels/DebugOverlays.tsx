/** The debug overlays that live outside the Debug tab: the Break-when dialog and the Explain popover. */

import { ExplainPopover } from "../explain/ExplainPopover";
import { BreakWhenDialog } from "./BreakWhenDialog";
import "./panels.css";

export function DebugOverlays() {
  return (
    <>
      <BreakWhenDialog />
      <ExplainPopover />
    </>
  );
}
