/** Shared helpers for unit tests that render the library browser. */

import { fireEvent, screen } from "@testing-library/react";

/** Open every collapsed library category (categories start collapsed). */
export function expandLibraryGroups(): void {
  for (const toggle of screen.queryAllByTestId(/^library-group-toggle-/)) {
    if (toggle.getAttribute("aria-expanded") === "false") {
      fireEvent.click(toggle);
    }
  }
}
