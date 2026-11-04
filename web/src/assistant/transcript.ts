/**
 * The chat as a pure fold over the session's events. There is no other record of it, so a
 * reloaded page replays the events from the start and shows the same transcript.
 */

import type {
  AssistantCodeEvent,
  AssistantEnvelope,
  AssistantFigure,
  AssistantProposal,
  AssistantQuestionSet,
  AssistantSelectionItem,
  AssistantToolCallEvent,
  AssistantUsage,
} from "../contracts/assistant";

export type TranscriptItem =
  | { kind: "user"; key: string; text: string; selection: AssistantSelectionItem[] }
  | { kind: "assistant"; key: string; text: string }
  | { kind: "tools"; key: string; calls: AssistantToolCallEvent[] }
  | { kind: "code"; key: string; cell: AssistantCodeEvent }
  | { kind: "figure"; key: string; figure: AssistantFigure }
  | { kind: "question"; key: string; question: AssistantQuestionSet; answered: boolean }
  | { kind: "simulation"; key: string; runId: string; model: string; draft: boolean; debug: boolean }
  | { kind: "project"; key: string; project: string }
  | { kind: "notice"; key: string; tone: "error" | "info"; text: string };

export interface Transcript {
  items: TranscriptItem[];
  /** The next `after` of the event stream; a replayed event below it changes nothing. */
  nextSeq: number;
  running: boolean;
  /** The last run's outcome, for the line under the transcript. */
  usage: AssistantUsage | null;
  proposal: AssistantProposal | null;
  /** The project a home-screen chat created. */
  createdProject: string | null;
}

export const EMPTY_TRANSCRIPT: Transcript = {
  items: [],
  nextSeq: 0,
  running: false,
  usage: null,
  proposal: null,
  createdProject: null,
};

/** The stream's event names: an EventSource listens to each one by name. */
export const EVENT_TYPES: readonly AssistantEnvelope["type"][] = [
  "run_start",
  "user",
  "code",
  "project_created",
  "status",
  "text",
  "tool_call",
  "proposal",
  "question",
  "figure",
  "simulation",
  "error",
  "run_end",
  "closed",
];

const END_NOTICES: Record<string, string> = {
  error: "The run failed",
  cancelled: "Stopped",
  timeout: "The run hit its time limit",
  max_turns: "The run hit its turn limit",
  budget: "The run hit its budget",
};

function appendTool(items: TranscriptItem[], call: AssistantToolCallEvent): TranscriptItem[] {
  const last = items[items.length - 1];
  if (last?.kind === "tools") {
    return [...items.slice(0, -1), { ...last, calls: [...last.calls, call] }];
  }
  return [...items, { kind: "tools", key: `tools-${call.seq}`, calls: [call] }];
}

function closeQuestions(items: TranscriptItem[]): TranscriptItem[] {
  return items.some((item) => item.kind === "question" && !item.answered)
    ? items.map((item) => (item.kind === "question" ? { ...item, answered: true } : item))
    : items;
}

/** The transcript after one event; an event already seen returns it unchanged. */
export function applyEvent(state: Transcript, event: AssistantEnvelope): Transcript {
  if (event.seq < state.nextSeq) {
    return state;
  }
  const next: Transcript = { ...state, nextSeq: event.seq + 1 };
  const key = `${event.type}-${event.seq}`;
  switch (event.type) {
    case "run_start":
      return { ...next, running: true };
    case "user":
      return {
        ...next,
        items: [
          ...closeQuestions(state.items),
          { kind: "user", key, text: event.text, selection: event.selection ?? [] },
        ],
      };
    case "text":
      return { ...next, items: [...state.items, { kind: "assistant", key, text: event.text }] };
    case "tool_call":
      return { ...next, items: appendTool(state.items, event) };
    case "code":
      return { ...next, items: [...state.items, { kind: "code", key, cell: event }] };
    case "figure":
      return { ...next, items: [...state.items, { kind: "figure", key, figure: event.figure }] };
    case "question":
      return {
        ...next,
        items: [...state.items, { kind: "question", key, question: event.question, answered: false }],
      };
    case "simulation":
      return {
        ...next,
        items: [
          ...state.items,
          {
            kind: "simulation",
            key,
            runId: event.runId,
            model: event.model,
            draft: event.draft,
            debug: event.debug === true,
          },
        ],
      };
    case "project_created":
      return {
        ...next,
        createdProject: event.project,
        items: [...state.items, { kind: "project", key, project: event.project }],
      };
    case "error":
      return {
        ...next,
        items: [...state.items, { kind: "notice", key, tone: "error", text: event.message }],
      };
    case "proposal":
      return { ...next, proposal: event.proposal };
    case "run_end": {
      const lead = END_NOTICES[event.status];
      const text = lead === undefined ? null : event.message ? `${lead}: ${event.message}` : `${lead}.`;
      return {
        ...next,
        running: false,
        usage: event.usage ?? null,
        proposal: event.proposal,
        items:
          text === null
            ? state.items
            : [
                ...state.items,
                { kind: "notice", key, tone: event.status === "cancelled" ? "info" : "error", text },
              ],
      };
    }
    case "closed":
      return { ...next, running: false };
    default:
      return next; // status lines are for the audit log
  }
}
