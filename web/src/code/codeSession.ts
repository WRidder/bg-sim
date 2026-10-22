/**
 * The Code tab's open-source session (plan 7.7) and the bridge from the DOM
 * `bgsim:open-source` event that W1.2/W1.3 emit.
 *
 * The event has to reach the Code tab even while the Diagram tab is active,
 * so each mounted centre tab registers `useOpenSourceEvents`. A request also
 * asks the shell to select the Code tab by clicking its own tab button: the
 * app shell belongs to W1.1 and is deliberately not edited here.
 */

import { useEffect } from "react";
import { create } from "zustand";

import type { Model } from "../contracts/model";
import { OPEN_SOURCE_EVENT } from "../diagnostics/navigation";
import type { CatalogIndex } from "../library/catalogIndex";
import { resolveOpenDetail, type CodeTarget, type OpenSourceDetail } from "./sources";

export const CODE_TAB_ID = "center-tab-code";

export interface SourceRequest {
  detail: OpenSourceDetail;
  /** Increments for repeated requests of the same source so the caret moves again. */
  nonce: number;
}

interface CodeSessionState {
  target: CodeTarget | null;
  request: SourceRequest | null;
  error: string | null;
  nonce: number;
  open: (target: CodeTarget) => void;
  requestSource: (detail: OpenSourceDetail) => void;
  consumeRequest: (target: CodeTarget) => void;
  fail: (message: string) => void;
  close: () => void;
}

export const useCodeSessionStore = create<CodeSessionState>()((set) => ({
  target: null,
  request: null,
  error: null,
  nonce: 0,

  open: (target) =>
    set((state) => ({ target, error: null, request: null, nonce: state.nonce + 1 })),

  requestSource: (detail) =>
    set((state) => ({
      request: { detail, nonce: state.nonce + 1 },
      nonce: state.nonce + 1,
    })),

  consumeRequest: (target) =>
    set((state) => ({
      target,
      request: null,
      error: null,
      nonce: state.nonce + 1,
    })),

  fail: (message) => set({ error: message, request: null }),

  close: () => set({ target: null, request: null, error: null }),
}));

/** Select the Code tab in the centre area, when it is not already selected. */
export function revealCodeTab(): void {
  if (typeof document === "undefined") {
    return;
  }
  const tab = document.getElementById(CODE_TAB_ID);
  if (tab instanceof HTMLElement && tab.getAttribute("aria-selected") !== "true") {
    tab.click();
  }
}

/** Hand a source request to the Code tab, optionally bringing it to the front. */
export function requestSource(
  detail: OpenSourceDetail,
  options: { reveal?: boolean } = {},
): void {
  useCodeSessionStore.getState().requestSource(detail);
  if (options.reveal === true) {
    revealCodeTab();
  }
}

/** Open an already-resolved target (the source picker and "new inline block"). */
export function openTarget(target: CodeTarget): void {
  useCodeSessionStore.getState().open(target);
  revealCodeTab();
}

function isOpenSourceDetail(value: unknown): value is OpenSourceDetail {
  if (typeof value !== "object" || value === null) {
    return false;
  }
  const detail = value as Partial<OpenSourceDetail>;
  return (
    (detail.kind === "stdlib" || detail.kind === "project" || detail.kind === "inline") &&
    typeof detail.ref === "string" &&
    typeof detail.line === "number" &&
    typeof detail.col === "number"
  );
}

/**
 * Resolve pending requests against the current document and catalog. Call it
 * from the Code tab; it runs whenever the request, the document or the
 * catalog changes, so a request that arrives before the model is open still
 * lands.
 */
export function useResolveSourceRequests(
  doc: Model | null,
  index: CatalogIndex | null,
): void {
  const request = useCodeSessionStore((state) => state.request);
  useEffect(() => {
    if (request === null) {
      return;
    }
    const { detail } = request;
    if (detail.kind === "inline" && doc === null) {
      return;
    }
    if (detail.kind !== "inline" && index === null) {
      return;
    }
    const target = resolveOpenDetail(detail, doc, index);
    const store = useCodeSessionStore.getState();
    if (target === null) {
      store.fail(`The source "${detail.ref}" is not in the open project or its library.`);
      return;
    }
    store.consumeRequest(target);
  }, [request, doc, index]);
}

/** Listen for the W1.2/W1.3 event while a centre tab is mounted. */
export function useOpenSourceEvents(): void {
  useEffect(() => {
    const listener = (event: Event): void => {
      const detail = (event as CustomEvent<unknown>).detail;
      if (isOpenSourceDetail(detail)) {
        requestSource(detail);
      }
    };
    window.addEventListener(OPEN_SOURCE_EVENT, listener);
    return () => window.removeEventListener(OPEN_SOURCE_EVENT, listener);
  }, []);
}

/** Test hook: forget everything that is open. */
export function resetCodeSession(): void {
  useCodeSessionStore.setState({
    target: null,
    request: null,
    error: null,
    nonce: 0,
  });
}
