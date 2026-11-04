/**
 * A ```mermaid fence of a chat message. Mermaid is large, so it loads with the first diagram.
 * `securityLevel: "strict"` encodes the labels and turns off click handlers: the source is what
 * a model wrote. A diagram that does not parse shows its source and the parser's message.
 */

import { useEffect, useId, useState } from "react";

function isDark(): boolean {
  return document.documentElement.dataset.theme !== "light";
}

/** Rendering is global to mermaid, so one diagram at a time. */
let queue: Promise<unknown> = Promise.resolve();

async function render(id: string, text: string): Promise<string> {
  const { default: mermaid } = await import("mermaid");
  mermaid.initialize({
    startOnLoad: false,
    securityLevel: "strict",
    theme: isDark() ? "dark" : "default",
  });
  const { svg } = await mermaid.render(id, text);
  return svg;
}

export function MermaidDiagram({ text }: { text: string }) {
  const id = `mermaid-${useId().replace(/[^A-Za-z0-9]/g, "")}`;
  const [svg, setSvg] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let stale = false;
    const job = queue.then(() => render(id, text));
    queue = job.catch(() => undefined);
    job.then(
      (next) => {
        if (!stale) {
          setSvg(next);
          setError(null);
        }
      },
      (cause: unknown) => {
        if (!stale) {
          setSvg(null);
          setError(cause instanceof Error ? cause.message : String(cause));
        }
      },
    );
    return () => {
      stale = true;
    };
  }, [id, text]);

  if (error !== null) {
    return (
      <div className="assistant-mermaid assistant-mermaid--error" data-testid="mermaid-error">
        <pre>{text}</pre>
        <p role="note">This diagram could not be drawn: {error}</p>
      </div>
    );
  }
  if (svg === null) {
    return (
      <div className="assistant-mermaid" data-testid="mermaid-pending">
        <pre>{text}</pre>
      </div>
    );
  }
  // mermaid sanitised this SVG itself (securityLevel "strict").
  return <div className="assistant-mermaid" data-testid="mermaid-diagram" dangerouslySetInnerHTML={{ __html: svg }} />;
}
