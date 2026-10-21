/**
 * Vitest setup, jsdom environment.
 *
 * Two gaps in jsdom must be filled before the shell can render:
 *
 * 1. `ResizeObserver` — react-resizable-panels 4.14.8 constructs one from
 *    `element.ownerDocument.defaultView.ResizeObserver` without checking that
 *    it exists (node_modules/react-resizable-panels/dist/react-resizable-panels.js,
 *    `new n(...)`). The stub never fires; panel sizes are a browser concern.
 *    (`matchMedia` needs no stub: the library guards that call itself.)
 * 2. Cleanup — @testing-library/react only auto-cleans up when the test
 *    framework globals are enabled, and this project runs with `globals: false`.
 */

import { cleanup } from "@testing-library/react";
import { afterEach } from "vitest";

class ResizeObserverStub implements ResizeObserver {
  observe(): void {
    /* jsdom has no layout, so there is nothing to observe */
  }

  unobserve(): void {
    /* see observe */
  }

  disconnect(): void {
    /* see observe */
  }
}

if (typeof globalThis.ResizeObserver === "undefined") {
  globalThis.ResizeObserver = ResizeObserverStub;
}

afterEach(() => {
  cleanup();
});
