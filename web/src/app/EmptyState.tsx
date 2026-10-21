import type { ReactNode } from "react";

export interface EmptyStateProps {
  /** What is missing, e.g. "No models open". */
  title: string;
  /** What to do about it (plan 7.8: empty states have guidance). */
  hint: ReactNode;
}

/** The shared empty state of every panel in the shell. */
export function EmptyState({ title, hint }: EmptyStateProps) {
  return (
    <div className="empty-state">
      <p className="empty-state__title">{title}</p>
      <p className="empty-state__hint">{hint}</p>
    </div>
  );
}
