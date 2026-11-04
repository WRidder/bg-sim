/**
 * The assistant's side panel (plan/ASSISTANT_PLAN.md), next to the screens of the app. On the
 * home screen it is a chat without a project: it answers questions and can create one. In a
 * project it proposes changes to a draft, runs simulations and shows what it found; the selection
 * chips above the message box are what it will see of the editor.
 */

import { useEffect, useMemo, useRef, useState, type KeyboardEvent, type PointerEvent } from "react";

import "./assistant.css";

import { projectUrl, type AppRoute } from "../app/route";
import { useDocumentStore } from "../state/documentStore";
import { CodeCard } from "./CodeCard";
import { ChatMarkdown } from "./ChatMarkdown";
import { FigureCard } from "./FigureCard";
import { useAssistantPanelStore } from "./panelStore";
import { ProposalReview } from "./ProposalReview";
import { QuestionCard } from "./QuestionCard";
import { useAssistantStore } from "./assistantStore";
import {
  diagramSelection,
  selectionKey,
  selectionLabel,
  trackDocSelection,
  useAssistantSelectionStore,
} from "./selectionStore";
import type { TranscriptItem } from "./transcript";
import type { AssistantSelectionItem } from "../contracts/assistant";

const HOME_SUGGESTIONS = [
  "What is a bond graph?",
  "Which example shows a DC motor?",
  "Create a project with a mass-spring-damper model",
];
const PROJECT_SUGGESTIONS = [
  "Explain this model",
  "Run it and tell me how it settles",
  "Plot the spectrum of a signal",
];

function ToolCalls({ item }: { item: Extract<TranscriptItem, { kind: "tools" }> }) {
  const failed = item.calls.filter((call) => call.isError).length;
  const last = item.calls[item.calls.length - 1];
  return (
    <details className="assistant-tools" data-testid="assistant-tools">
      <summary>
        {item.calls.length} tool call{item.calls.length === 1 ? "" : "s"}
        {failed > 0 ? `, ${failed} refused` : ""}
        {last === undefined ? "" : ` · ${last.name}`}
      </summary>
      <ul>
        {item.calls.map((call) => (
          <li key={call.seq} data-error={call.isError}>
            <code>{call.name}</code> {call.summary}
          </li>
        ))}
      </ul>
    </details>
  );
}

function Chips({ items, onRemove }: { items: readonly AssistantSelectionItem[]; onRemove?: (key: string) => void }) {
  return (
    <ul className="assistant-chips" aria-label="Selection">
      {items.map((item) => {
        const key = selectionKey(item);
        return (
          <li key={key} className="assistant-chip" data-kind={item.kind} data-testid={`selection-chip-${item.kind}`}>
            <span className="assistant-chip__kind">{item.kind}</span>
            <span className="assistant-chip__label">{selectionLabel(item)}</span>
            {onRemove === undefined ? null : (
              <button type="button" aria-label={`Do not send ${selectionLabel(item)}`} onClick={() => onRemove(key)}>
                ×
              </button>
            )}
          </li>
        );
      })}
    </ul>
  );
}

function Item({ item }: { item: TranscriptItem }) {
  const busy = useAssistantStore((state) => state.busy);
  const answer = useAssistantStore((state) => state.answer);
  switch (item.kind) {
    case "user":
      return (
        <div className="assistant-message assistant-message--user" data-testid="assistant-user">
          {item.selection.length > 0 ? <Chips items={item.selection} /> : null}
          <p>{item.text}</p>
        </div>
      );
    case "assistant":
      return (
        <div className="assistant-message" data-testid="assistant-text">
          <ChatMarkdown text={item.text} />
        </div>
      );
    case "tools":
      return <ToolCalls item={item} />;
    case "code":
      return <CodeCard cell={item.cell} />;
    case "figure":
      return <FigureCard figure={item.figure} />;
    case "question":
      return (
        <QuestionCard
          question={item.question}
          answered={item.answered}
          busy={busy}
          onAnswer={(answers) => void answer(item.question, answers)}
        />
      );
    case "simulation":
      return (
        <p className="assistant-event">
          {item.debug ? "Debugging" : "Simulated"} {item.model}
          {item.draft ? " (draft)" : ""} · run {item.runId}
        </p>
      );
    case "project":
      return (
        <div className="assistant-event" data-testid="assistant-project-created">
          Created project {item.project}.{" "}
          <button
            type="button"
            className="assistant-link"
            onClick={() => window.location.assign(projectUrl(item.project))}
          >
            Open project
          </button>
        </div>
      );
    case "notice":
      return (
        <p className={`assistant-event assistant-event--${item.tone}`} role={item.tone === "error" ? "alert" : undefined}>
          {item.text}
        </p>
      );
  }
}

function useChips(): { items: AssistantSelectionItem[]; dismiss: (keys: readonly string[]) => void } {
  const doc = useDocumentStore((state) => state.doc);
  const modelName = useDocumentStore((state) => state.modelName);
  const activePath = useDocumentStore((state) => state.activePath);
  const selection = useDocumentStore((state) => state.selection);
  const code = useAssistantSelectionStore((state) => state.code);
  const docText = useAssistantSelectionStore((state) => state.doc);
  const dismissed = useAssistantSelectionStore((state) => state.dismissed);
  const dismiss = useAssistantSelectionStore((state) => state.dismiss);
  const forget = useAssistantSelectionStore((state) => state.forget);

  const diagram = useMemo(
    () => diagramSelection(doc, modelName, activePath, selection),
    [doc, modelName, activePath, selection],
  );
  useEffect(() => {
    if (diagram === null) {
      forget("diagram");
    }
  }, [diagram, forget]);

  const items = useMemo(
    () =>
      [diagram, code, docText].filter(
        (item): item is AssistantSelectionItem => item !== null && !dismissed.has(selectionKey(item)),
      ),
    [diagram, code, docText, dismissed],
  );
  return { items, dismiss };
}

function Composer({ project }: { project: string | null }) {
  const [text, setText] = useState("");
  const running = useAssistantStore((state) => state.transcript.running);
  const busy = useAssistantStore((state) => state.busy);
  const send = useAssistantStore((state) => state.send);
  const cancel = useAssistantStore((state) => state.cancel);
  const { items, dismiss } = useChips();

  const submit = (): void => {
    const message = text.trim();
    if (message === "" || running || busy) {
      return;
    }
    void send(message, items).then((sent) => {
      if (sent) {
        setText("");
        dismiss(items.map(selectionKey));
      }
    });
  };
  const onKeyDown = (event: KeyboardEvent<HTMLTextAreaElement>): void => {
    if (event.key === "Enter" && !event.shiftKey) {
      event.preventDefault();
      submit();
    }
  };

  return (
    <div className="assistant-composer">
      {items.length > 0 ? <Chips items={items} onRemove={(key) => dismiss([key])} /> : null}
      <textarea
        rows={3}
        data-testid="assistant-input"
        aria-label="Message to the assistant"
        placeholder={project === null ? "Ask about bg-sim, or describe a new project" : "Ask, or describe a change"}
        value={text}
        onChange={(event) => setText(event.target.value)}
        onKeyDown={onKeyDown}
      />
      <div className="assistant-composer__actions">
        <span className="assistant-composer__hint">Enter sends, Shift+Enter is a new line</span>
        {running ? (
          <button type="button" className="assistant-button" data-testid="assistant-cancel" onClick={() => void cancel()}>
            Stop
          </button>
        ) : (
          <button
            type="button"
            className="assistant-button assistant-button--primary"
            data-testid="assistant-send"
            disabled={text.trim() === "" || busy}
            onClick={submit}
          >
            Send
          </button>
        )}
      </div>
    </div>
  );
}

function Header({ onNew }: { onNew: () => void }) {
  const profiles = useAssistantStore((state) => state.profiles);
  const profile = useAssistantStore((state) => state.profile);
  const setProfile = useAssistantStore((state) => state.setProfile);
  const session = useAssistantStore((state) => state.session);
  const setOpen = useAssistantPanelStore((state) => state.setOpen);
  return (
    <header className="assistant-panel__header">
      <h2>Assistant</h2>
      {profiles !== null && profiles.profiles.length > 1 ? (
        <select
          aria-label="Assistant profile"
          data-testid="assistant-profile"
          value={profile ?? ""}
          disabled={session !== null}
          onChange={(event) => setProfile(event.target.value)}
        >
          {profiles.profiles.map((entry) => (
            <option key={entry.name} value={entry.name}>
              {entry.available ? entry.name : `${entry.name} (not available)`}
            </option>
          ))}
        </select>
      ) : null}
      <button type="button" className="assistant-button" data-testid="assistant-new-chat" onClick={onNew}>
        New chat
      </button>
      <button
        type="button"
        className="icon-button"
        aria-label="Close the assistant"
        data-testid="assistant-close"
        onClick={() => setOpen(false)}
      >
        ×
      </button>
    </header>
  );
}

function ResizeHandle() {
  const width = useAssistantPanelStore((state) => state.width);
  const setWidth = useAssistantPanelStore((state) => state.setWidth);
  const onPointerDown = (event: PointerEvent<HTMLDivElement>): void => {
    event.preventDefault();
    const target = event.currentTarget;
    target.setPointerCapture(event.pointerId);
    const startX = event.clientX;
    const startWidth = width;
    const move = (next: globalThis.PointerEvent): void => setWidth(startWidth + startX - next.clientX);
    const stop = (): void => {
      target.removeEventListener("pointermove", move);
      target.removeEventListener("pointerup", stop);
      target.removeEventListener("pointercancel", stop);
    };
    target.addEventListener("pointermove", move);
    target.addEventListener("pointerup", stop);
    target.addEventListener("pointercancel", stop);
  };
  const onKeyDown = (event: KeyboardEvent<HTMLDivElement>): void => {
    if (event.key === "ArrowLeft" || event.key === "ArrowRight") {
      event.preventDefault();
      setWidth(width + (event.key === "ArrowLeft" ? 24 : -24));
    }
  };
  return (
    <div
      className="assistant-panel__handle"
      role="separator"
      aria-orientation="vertical"
      aria-label="Resize the assistant"
      aria-valuenow={width}
      tabIndex={0}
      onPointerDown={onPointerDown}
      onKeyDown={onKeyDown}
    />
  );
}

export interface AssistantPanelProps {
  route: AppRoute;
}

export function AssistantPanel({ route }: AssistantPanelProps) {
  const width = useAssistantPanelStore((state) => state.width);
  const storeProject = useDocumentStore((state) => state.project);
  const project = storeProject ?? (route.kind === "start" ? null : route.project);

  const attach = useAssistantStore((state) => state.attach);
  const loadProfiles = useAssistantStore((state) => state.loadProfiles);
  const transcript = useAssistantStore((state) => state.transcript);
  const session = useAssistantStore((state) => state.session);
  const error = useAssistantStore((state) => state.error);
  const notice = useAssistantStore((state) => state.notice);
  const applying = useAssistantStore((state) => state.applying);
  const autoApply = useAssistantStore((state) => state.autoApply);
  const setAutoApply = useAssistantStore((state) => state.setAutoApply);
  const apply = useAssistantStore((state) => state.apply);
  const discard = useAssistantStore((state) => state.discard);
  const newChat = useAssistantStore((state) => state.newChat);
  const send = useAssistantStore((state) => state.send);
  const profiles = useAssistantStore((state) => state.profiles);
  const profile = useAssistantStore((state) => state.profile);

  const [confirmingNew, setConfirmingNew] = useState(false);
  const log = useRef<HTMLDivElement | null>(null);
  const pinned = useRef(true);

  useEffect(() => {
    void attach(project);
    void loadProfiles();
  }, [attach, loadProfiles, project]);

  useEffect(() => trackDocSelection(), []);

  useEffect(() => {
    const element = log.current;
    if (element !== null && pinned.current) {
      element.scrollTop = element.scrollHeight;
    }
  }, [transcript.items, transcript.running]);

  const chosen = profiles?.profiles.find((entry) => entry.name === profile) ?? null;
  const proposal = transcript.proposal;
  const suggestions = project === null ? HOME_SUGGESTIONS : PROJECT_SUGGESTIONS;

  const onNew = (): void => {
    if (proposal?.changed === true) {
      setConfirmingNew(true);
    } else {
      void newChat();
    }
  };

  return (
    <aside className="assistant-panel" style={{ width }} aria-label="Assistant" data-testid="assistant-panel">
      <ResizeHandle />
      <Header onNew={onNew} />
      {confirmingNew ? (
        <div className="assistant-confirm" role="alert" data-testid="assistant-confirm-new">
          <p>A new chat drops the changes that were not applied.</p>
          <button
            type="button"
            className="assistant-button"
            onClick={() => {
              setConfirmingNew(false);
              void newChat();
            }}
          >
            Drop them
          </button>
          <button type="button" className="assistant-button" onClick={() => setConfirmingNew(false)}>
            Keep the chat
          </button>
        </div>
      ) : null}
      <div
        ref={log}
        className="assistant-panel__log"
        role="log"
        aria-label="Conversation"
        data-testid="assistant-log"
        onScroll={(event) => {
          const element = event.currentTarget;
          pinned.current = element.scrollHeight - element.scrollTop - element.clientHeight < 40;
        }}
      >
        {transcript.items.length === 0 && !transcript.running ? (
          <div className="assistant-panel__empty">
            <p>
              {project === null
                ? "Ask about bg-sim and the example projects, or describe a project to create."
                : `Ask about ${project}, or describe a change. Changes stay a proposal until you apply them.`}
            </p>
            <ul>
              {suggestions.map((suggestion) => (
                <li key={suggestion}>
                  <button type="button" className="assistant-link" onClick={() => void send(suggestion, [])}>
                    {suggestion}
                  </button>
                </li>
              ))}
            </ul>
          </div>
        ) : null}
        {transcript.items.map((item) => (
          <Item key={item.key} item={item} />
        ))}
        {transcript.running ? (
          <p className="assistant-event assistant-event--working" role="status" data-testid="assistant-working">
            Working…
          </p>
        ) : null}
      </div>
      {chosen !== null && !chosen.available && session === null ? (
        <p className="assistant-event assistant-event--error" role="alert" data-testid="assistant-unavailable">
          The profile {chosen.name} is not available: {chosen.reason ?? "unknown reason"}{" "}
          <button
            type="button"
            className="assistant-button"
            data-testid="assistant-check-profile"
            onClick={() => void loadProfiles(true)}
          >
            Check again
          </button>
        </p>
      ) : null}
      {error === null ? null : (
        <p className="assistant-event assistant-event--error" role="alert" data-testid="assistant-error">
          {error}
        </p>
      )}
      {notice === null ? null : (
        <p className="assistant-event" role="status" data-testid="assistant-notice">
          {notice}
        </p>
      )}
      {proposal?.changed === true ? (
        <ProposalReview
          proposal={proposal}
          running={transcript.running}
          applying={applying}
          autoApply={autoApply}
          onApply={() => void apply()}
          onDiscard={() => void discard()}
          onAutoApply={setAutoApply}
        />
      ) : null}
      <Composer project={project} />
    </aside>
  );
}
