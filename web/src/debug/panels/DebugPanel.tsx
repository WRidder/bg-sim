/**
 * The Debug dock tab (plan 7.9): Variables, Watch expressions, Breakpoints and
 * Edits side by side (they wrap on a narrow dock).
 */

import type { ReactNode } from "react";

import { BreakpointsSection } from "./BreakpointsSection";
import { EditsSection } from "./EditsSection";
import { VariablesSection } from "./VariablesSection";
import { WatchSection } from "./WatchSection";
import "./panels.css";

function Section({ id, title, children }: { id: string; title: string; children: ReactNode }) {
  return (
    <section className="debug-panel__section" aria-labelledby={`debug-section-${id}`} data-testid={`debug-section-${id}`}>
      <h3 className="debug-panel__title" id={`debug-section-${id}`}>
        {title}
      </h3>
      {children}
    </section>
  );
}

export function DebugPanel() {
  return (
    <div className="debug-panel" data-testid="debug-panel">
      <Section id="variables" title="Variables">
        <VariablesSection />
      </Section>
      <Section id="watch" title="Watch expressions">
        <WatchSection />
      </Section>
      <Section id="breakpoints" title="Breakpoints">
        <BreakpointsSection />
      </Section>
      <Section id="edits" title="Edits">
        <EditsSection />
      </Section>
    </div>
  );
}
