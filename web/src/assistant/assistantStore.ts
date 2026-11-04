/**
 * The chat of the open project, or of the home screen. The backend owns the session and the
 * draft; this store folds the session's events into a transcript and does what the editor must
 * do itself: flush its autosave before a message, follow a run of the open model, and take the
 * open model back on Apply, so that an applied proposal is one undo step.
 */

import { create } from "zustand";

import type {
  AssistantAnswer,
  AssistantEnvelope,
  AssistantMessageRequest,
  AssistantProfileList,
  AssistantProposal,
  AssistantQuestionSet,
  AssistantSelectionItem,
  AssistantSessionInfo,
} from "../contracts/assistant";
import { keepRunBreakpoints } from "../debug/debugStore";
import { useDocsIndexStore, useDocsStore, useProjectDocsStore } from "../docs/docsStore";
import { fetchCatalog } from "../library/catalogClient";
import { useCatalogStore } from "../library/catalogStore";
import { useRunStore } from "../plot/runStore";
import { useSceneRevision } from "../scene/sceneRevision";
import { useDocumentStore } from "../state/documentStore";
import { saveCurrentModel } from "../state/persistence";
import {
  applyDraft,
  cancelRun,
  closeSession,
  discardDraft,
  eventsUrl,
  fetchProfiles,
  fetchSession,
  findSession,
  sendAnswers,
  sendMessage,
  startSession,
} from "./assistantApi";
import { applyEvent, EMPTY_TRANSCRIPT, EVENT_TYPES, type Transcript } from "./transcript";

const AUTO_APPLY_KEY = "bgsim.assistant.autoApply";
const RECONNECT_MS = 1000;

function readAutoApply(): boolean {
  try {
    return localStorage.getItem(AUTO_APPLY_KEY) === "1";
  } catch {
    return false;
  }
}

function writeAutoApply(on: boolean): void {
  try {
    localStorage.setItem(AUTO_APPLY_KEY, on ? "1" : "0");
  } catch {
    // the toggle then lasts until the page is reloaded
  }
}

export interface AssistantState {
  /** The chat this store holds: a project, or `null` for the home screen. */
  project: string | null;
  session: string | null;
  transcript: Transcript;
  profiles: AssistantProfileList | null;
  profile: string | null;
  autoApply: boolean;
  /** A request is on its way (the composer waits). */
  busy: boolean;
  applying: boolean;
  /** Why the last action failed. */
  error: string | null;
  /** The last Apply's outcome. */
  notice: string | null;

  attach: (project: string | null) => Promise<void>;
  loadProfiles: (refresh?: boolean) => Promise<void>;
  setProfile: (profile: string) => void;
  setAutoApply: (on: boolean) => void;
  send: (text: string, selection: readonly AssistantSelectionItem[]) => Promise<boolean>;
  answer: (question: AssistantQuestionSet, answers: AssistantAnswer[]) => Promise<void>;
  cancel: () => Promise<void>;
  apply: () => Promise<void>;
  discard: () => Promise<void>;
  newChat: () => Promise<void>;
}

/** Whether the proposal can be written at all. */
export function canApply(proposal: AssistantProposal | null): boolean {
  return proposal !== null && proposal.changed && proposal.valid;
}

function message(error: unknown): string {
  return error instanceof Error ? error.message : String(error);
}

export const useAssistantStore = create<AssistantState>()((set, get) => {
  let source: EventSource | null = null;
  let retry: ReturnType<typeof setTimeout> | null = null;
  /** Bumped by every attach and new chat: a late answer of the previous one is dropped. */
  let generation = 0;
  /** Below this seq an event is history, replayed for the transcript: nothing to act on. */
  let liveFrom = 0;
  /** Stop listening at this seq when no run is going. */
  let target = 0;

  const disconnect = (): void => {
    source?.close();
    source = null;
    if (retry !== null) {
      clearTimeout(retry);
      retry = null;
    }
  };

  const followRun = (runId: string, model: string, debug: boolean): void => {
    const run = useRunStore.getState();
    const open = useDocumentStore.getState();
    if (model !== open.modelName || run.status === "starting" || run.status === "running") {
      return;
    }
    if (debug) {
      keepRunBreakpoints(runId);
    }
    void run.startRun({
      followRunId: runId,
      ...(debug ? { debug: { breakpoints: [], pauseOnEntry: false } } : {}),
    });
  };

  const onEvent = (event: AssistantEnvelope): void => {
    const before = get().transcript;
    const after = applyEvent(before, event);
    if (after === before) {
      return;
    }
    set({ transcript: after });
    if (event.seq < liveFrom) {
      return;
    }
    if (event.type === "simulation") {
      followRun(event.runId, event.model, event.debug === true);
    } else if (event.type === "run_end" && get().autoApply) {
      if (canApply(event.proposal) && event.proposal.checked) {
        void get().apply();
      }
    }
  };

  const connect = (session: string, after: number): void => {
    disconnect();
    const stream = new EventSource(eventsUrl(session, after));
    source = stream;
    const receive = (raw: Event): void => {
      onEvent(JSON.parse((raw as MessageEvent<string>).data) as AssistantEnvelope);
      const { running, nextSeq } = get().transcript;
      if (!running && nextSeq >= target && source === stream) {
        disconnect();
      }
    };
    for (const type of EVENT_TYPES) {
      stream.addEventListener(type, receive);
    }
    stream.onerror = () => {
      if (source !== stream) {
        return;
      }
      disconnect();
      if (get().transcript.running) {
        retry = setTimeout(() => connect(session, get().transcript.nextSeq), RECONNECT_MS);
      }
    };
  };

  /** Catch up with a session after a call: the proposal is now, the events follow. */
  const follow = (info: AssistantSessionInfo): void => {
    target = info.events;
    set((state) => ({
      transcript: { ...state.transcript, running: info.state === "running" || state.transcript.running },
    }));
    connect(info.session, get().transcript.nextSeq);
  };

  const flushEditor = async (): Promise<void> => {
    const { saveState } = useDocumentStore.getState();
    if (saveState === "dirty" || saveState === "error") {
      await saveCurrentModel();
    }
  };

  return {
    project: null,
    session: null,
    transcript: EMPTY_TRANSCRIPT,
    profiles: null,
    profile: null,
    autoApply: readAutoApply(),
    busy: false,
    applying: false,
    error: null,
    notice: null,

    attach: async (project) => {
      generation += 1;
      const mine = generation;
      disconnect();
      set({ project, session: null, transcript: EMPTY_TRANSCRIPT, error: null, notice: null });
      try {
        const info = await findSession(project);
        if (mine !== generation || info === null) {
          return;
        }
        liveFrom = info.events;
        target = info.events;
        set({ session: info.session });
        connect(info.session, 0);
      } catch (error) {
        if (mine === generation) {
          set({ error: message(error) });
        }
      }
    },

    loadProfiles: async (refresh = false) => {
      try {
        const profiles = await fetchProfiles(refresh);
        set((state) => ({
          profiles,
          profile:
            state.profile !== null && profiles.profiles.some((entry) => entry.name === state.profile)
              ? state.profile
              : profiles.default,
        }));
      } catch (error) {
        set({ error: message(error) });
      }
    },

    setProfile: (profile) => set({ profile }),

    setAutoApply: (autoApply) => {
      writeAutoApply(autoApply);
      set({ autoApply });
    },

    send: async (text, selection) => {
      const { session, project, profile } = get();
      set({ busy: true, error: null, notice: null });
      try {
        await flushEditor();
        const body = {
          text,
          model: useDocumentStore.getState().modelName,
          run: useRunStore.getState().runId,
          ...(selection.length > 0 ? { selection: selection as AssistantMessageRequest["selection"] } : {}),
        };
        const info =
          session === null
            ? await startSession(project, { ...body, ...(profile === null ? {} : { profile }) })
            : await sendMessage(session, body);
        if (session === null) {
          liveFrom = 0;
        }
        set({ session: info.session });
        follow(info);
        return true;
      } catch (error) {
        set({ error: message(error) });
        return false;
      } finally {
        set({ busy: false });
      }
    },

    answer: async (question, answers) => {
      const { session } = get();
      if (session === null) {
        return;
      }
      set({ busy: true, error: null });
      try {
        follow(await sendAnswers(session, { questionSet: question.id, answers }));
      } catch (error) {
        set({ error: message(error) });
      } finally {
        set({ busy: false });
      }
    },

    cancel: async () => {
      const { session } = get();
      if (session !== null) {
        await cancelRun(session).catch((error: unknown) => set({ error: message(error) }));
      }
    },

    apply: async () => {
      const { session, project } = get();
      if (session === null || get().applying) {
        return;
      }
      set({ applying: true, error: null, notice: null });
      try {
        await flushEditor();
        await useDocsStore.getState().saveAll();
        await useProjectDocsStore.getState().saveAll();
        const editor = useDocumentStore.getState();
        const result = await applyDraft(session, editor.modelName);
        if (result.openModel !== undefined) {
          editor.replaceDocument(result.openModel);
          await saveCurrentModel();
        }
        const open = get().transcript.createdProject ?? project;
        if (open !== null && result.applied.some((file) => file.startsWith("library:"))) {
          useCatalogStore.getState().setCatalog(await fetchCatalog(open));
        }
        if (editor.project !== null && result.applied.some((file) => file.startsWith("doc:"))) {
          await Promise.all([
            useDocsStore.getState().reload(),
            useProjectDocsStore.getState().reload(),
            useDocsIndexStore.getState().load(editor.project, true),
          ]);
        }
        if (result.applied.some((file) => file.startsWith("scene:"))) {
          useSceneRevision.getState().bump();
        }
        set({
          notice:
            `Applied ${result.applied.length} file${result.applied.length === 1 ? "" : "s"}.` +
            (result.backup === null ? "" : " The previous versions are in the project's backup folder."),
        });
        follow(await fetchSession(session));
      } catch (error) {
        set({ error: message(error) });
      } finally {
        set({ applying: false });
      }
    },

    discard: async () => {
      const { session } = get();
      if (session === null) {
        return;
      }
      set({ error: null, notice: null });
      try {
        const info = await discardDraft(session);
        set((state) => ({ transcript: { ...state.transcript, proposal: info.proposal } }));
        follow(info);
      } catch (error) {
        set({ error: message(error) });
      }
    },

    newChat: async () => {
      const { session, project } = get();
      generation += 1;
      disconnect();
      set({ session: null, transcript: EMPTY_TRANSCRIPT, error: null, notice: null });
      if (session !== null) {
        await closeSession(session).catch((error: unknown) => set({ error: message(error) }));
      }
      set({ project });
    },
  };
});
