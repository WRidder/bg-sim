/**
 * Edits (plan 7.9): the parameter and state changes made while paused, as the
 * run manifest records them (`debug.edits`). "Replay" runs the model again with
 * those edits applied and follows the new run like a normal run; "Save
 * parameters to model" writes the edited parameter values into the model
 * document as one undoable change (state edits are never saved).
 */

import { useState } from "react";

import type { Edit } from "../../contracts/debug";
import { useRunStore } from "../../plot/runStore";
import { useDocumentStore } from "../../state/documentStore";
import { editText, parameterChangesOf } from "./editsModel";
import { postReplay } from "./panelsApi";

const NO_EDITS: readonly Edit[] = [];

export function EditsSection() {
  const runId = useRunStore((state) => state.runId);
  const runStatus = useRunStore((state) => state.status);
  const edits = useRunStore((state) => state.manifest?.debug?.edits) ?? NO_EDITS;
  const [message, setMessage] = useState<{ tone: "ok" | "error"; text: string } | null>(null);
  const [busy, setBusy] = useState(false);

  const settled = runStatus === "done" || runStatus === "failed" || runStatus === "cancelled";
  const { changes } = parameterChangesOf(edits);

  const replay = async (): Promise<void> => {
    if (runId === null) {
      return;
    }
    setBusy(true);
    setMessage(null);
    try {
      const next = await postReplay(runId);
      await useRunStore.getState().startRun({ followRunId: next });
    } catch (error) {
      setMessage({ tone: "error", text: error instanceof Error ? error.message : String(error) });
    } finally {
      setBusy(false);
    }
  };

  const save = (): void => {
    const { changes: toSave, skipped } = parameterChangesOf(edits);
    const missing = useDocumentStore.getState().applyParameterChanges(toSave);
    const problems = [...skipped, ...missing];
    const saved = toSave.length - missing.length;
    if (problems.length > 0) {
      setMessage({
        tone: "error",
        text: `Saved ${saved} of ${toSave.length + skipped.length} parameters. No block matches ${problems.join(", ")}; edit those in the inspector.`,
      });
    } else {
      setMessage({
        tone: "ok",
        text: `Saved ${saved} parameter${saved === 1 ? "" : "s"} to the model. Undo (Ctrl+Z) reverts them.`,
      });
    }
  };

  return (
    <div data-testid="edits-section">
      <div className="debug-edits__actions">
        <button
          type="button"
          className="button"
          data-testid="edits-replay"
          disabled={edits.length === 0 || !settled || busy}
          title={
            edits.length === 0
              ? "Nothing to replay: no edits were made"
              : settled
                ? "Run the model again with these edits applied"
                : "Stop or finish the debug run first, then replay"
          }
          onClick={() => void replay()}
        >
          Replay
        </button>
        <button
          type="button"
          className="button"
          data-testid="edits-save"
          disabled={changes.length === 0}
          title={
            changes.length === 0
              ? "No parameter edits to save (state edits are never saved)"
              : "Write the edited parameter values into the model (one undo step)"
          }
          onClick={save}
        >
          Save parameters to model
        </button>
      </div>
      {message !== null ? (
        <p
          className={message.tone === "error" ? "debug-panel__error" : "debug-panel__pause"}
          role={message.tone === "error" ? "alert" : "status"}
          data-testid="edits-message"
        >
          {message.text}
        </p>
      ) : null}
      {edits.length === 0 ? (
        <p className="debug-panel__hint" data-testid="edits-empty">
          No edits in this session. While paused, change a parameter in the inspector (live mode) and it is
          listed here.
        </p>
      ) : (
        <ul className="debug-edits" aria-label="Edits of this session">
          {edits.map((edit, index) => (
            <li key={`${edit.target}-${edit.t}-${index}`} data-testid="edit-row" data-kind={edit.kind}>
              <span className="debug-edits__kind">{edit.kind}</span>
              <code>{editText(edit)}</code>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
