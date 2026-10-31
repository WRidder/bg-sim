/**
 * The hook the shell uses to ask the (lazily loaded) Docs tab whether leaving it would lose
 * edits. It is separate from the docs store so the main bundle does not pull the store in:
 * until the Docs tab has been opened nothing is registered and nothing is unsaved.
 */

interface LeaveGuard {
  hasUnsaved: () => boolean;
  saveAll: () => Promise<boolean>;
}

let guard: LeaveGuard | null = null;

export function registerLeaveGuard(next: LeaveGuard): void {
  guard = next;
}

export function hasUnsavedDocs(): boolean {
  return guard?.hasUnsaved() ?? false;
}

export function saveUnsavedDocs(): Promise<boolean> {
  return guard?.saveAll() ?? Promise.resolve(true);
}

let leaveConfirmed = false;

/** The user already chose to leave without saving (in-app prompt): skip the browser's own. */
export function confirmLeave(): void {
  leaveConfirmed = true;
}

export function isLeaveConfirmed(): boolean {
  return leaveConfirmed;
}
