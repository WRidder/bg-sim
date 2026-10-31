/**
 * The inspector's hint that the dashboard overrides a parameter for the next run
 * (DASHBOARD_PLAN.md): "dashboard: 12.5" for an input card, "dashboard: schedule" for a
 * schedule column. The model value itself stays what the field shows.
 */

import type { Model } from "../contracts/model";
import { formatNumber } from "../plot/format";
import { useDocumentStore } from "../state/documentStore";
import { dashboardOverrideOf } from "./model";

/** The badge text for `target`, or null when the dashboard leaves it alone. */
export function overrideBadgeText(doc: Model | null, target: string): string | null {
  const override = dashboardOverrideOf(doc?.dashboard, target);
  if (override === null) {
    return null;
  }
  if (override.kind === "schedule") {
    return "dashboard: schedule";
  }
  const value = override.value;
  return `dashboard: ${typeof value === "boolean" ? String(value) : formatNumber(value)}`;
}

export function DashboardOverrideBadge({ target }: { target: string }) {
  const text = useDocumentStore((state) => overrideBadgeText(state.doc, target));
  if (text === null) {
    return null;
  }
  return (
    <span
      className="inspector-tag inspector-tag--dashboard"
      title="The Dashboard tab overrides this parameter for the next run; the model value is unchanged."
      data-testid={`dashboard-override-${target}`}
    >
      {text}
    </span>
  );
}
