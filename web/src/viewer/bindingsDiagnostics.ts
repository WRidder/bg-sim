import type { Diagnostic } from "../contracts/diagnostic";
import { useDiagnosticsStore } from "../diagnostics/store";
import { BINDING_CODES } from "./bindingsValidate";

/**
 * Publish the binding diagnostics (E301-E304) to the Diagnostics panel through the viewer diagnostics,
 * next to the scene's own (E305, E306), which stay as they are.
 */
export function publishBindingDiagnostics(diagnostics: readonly Diagnostic[]): void {
  const store = useDiagnosticsStore.getState();
  const kept = store.viewerDiagnostics.filter((d) => !BINDING_CODES.includes(d.code));
  const next = [...kept, ...diagnostics];
  if (next.length === store.viewerDiagnostics.length && next.every((d, i) => d === store.viewerDiagnostics[i])) return;
  store.setViewerDiagnostics(next);
}
