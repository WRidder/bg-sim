/**
 * The keyboard shortcuts of the app (plan 7.8), listed once for the help overlay.
 * The handlers live where the behaviour lives (Canvas, RunBar, TopBar,
 * PlaybackBar, `useAppShortcuts`); `tests/shortcuts.test.tsx` checks the ones
 * owned by the shell.
 */

export interface ShortcutEntry {
  /** Key combinations, each rendered as key caps; alternatives are separate combinations. */
  keys: readonly (readonly string[])[];
  description: string;
}

export interface ShortcutGroup {
  title: string;
  entries: readonly ShortcutEntry[];
}

export const SHORTCUT_GROUPS: readonly ShortcutGroup[] = [
  {
    title: "Anywhere",
    entries: [
      { keys: [["Ctrl", "Enter"]], description: "Run the model" },
      { keys: [["Ctrl", "O"]], description: "Open a project, model or sample" },
      { keys: [["/"]], description: "Focus the library search" },
      { keys: [["F1"]], description: "Help for the selected block (this list when none is selected)" },
      { keys: [["?"]], description: "Show or hide this list" },
      { keys: [["Esc"]], description: "Close a dialog, cancel a connection drag, leave a subsystem" },
    ],
  },
  {
    title: "Debugging",
    entries: [
      { keys: [["F5"]], description: "Start a debug run, or continue a paused one" },
      { keys: [["Shift", "F5"]], description: "Stop the debug run" },
      { keys: [["F6"]], description: "Pause the running debug run" },
      { keys: [["F10"]], description: "Step statement (starts paused at the entry when idle)" },
      { keys: [["F11"]], description: "Step tick (starts paused at the entry when idle)" },
      { keys: [["F9"]], description: "Toggle a breakpoint on the current line of the Code tab" },
    ],
  },
  {
    title: "Diagram",
    entries: [
      { keys: [["Ctrl", "Z"]], description: "Undo" },
      { keys: [["Ctrl", "Y"], ["Ctrl", "Shift", "Z"]], description: "Redo" },
      { keys: [["Ctrl", "C"], ["Ctrl", "V"]], description: "Copy and paste the selection" },
      { keys: [["Del"]], description: "Delete the selection" },
      { keys: [["R"]], description: "Rotate the selection" },
      { keys: [["F"]], description: "Flip the selection" },
      { keys: [["Ctrl", "drag"]], description: "Connect from the nearest port of a block" },
    ],
  },
  {
    title: "3D view",
    entries: [{ keys: [["Space"]], description: "Play or pause the playback (3D view focused)" }],
  },
  {
    title: "Plots",
    entries: [
      { keys: [["drag"]], description: "Zoom to a time range" },
      { keys: [["double-click"]], description: "Show the whole run" },
    ],
  },
];

/** True when typing, so single-key shortcuts must not fire. */
export function isTypingTarget(target: EventTarget | null): boolean {
  if (!(target instanceof HTMLElement)) {
    return false;
  }
  const tag = target.tagName;
  return tag === "INPUT" || tag === "TEXTAREA" || tag === "SELECT" || target.isContentEditable;
}
