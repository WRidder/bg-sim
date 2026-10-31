import { fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { MetaValue } from "../src/inspector/fields";

/** jsdom has no layout: pretend the text needs `scroll` px in a `client` px box. */
function layout(scroll: number, client: number): void {
  vi.spyOn(HTMLElement.prototype, "scrollHeight", "get").mockReturnValue(scroll);
  vi.spyOn(HTMLElement.prototype, "clientHeight", "get").mockReturnValue(client);
}

afterEach(() => {
  vi.restoreAllMocks();
});

describe("MetaValue", () => {
  it("shows a value that fits in three lines as plain text", () => {
    layout(14, 14);
    render(<MetaValue text="0.5" testId="value" />);
    const value = screen.getByTestId("value");
    expect(value.getAttribute("role")).toBeNull();
    expect(value.className).not.toContain("is-toggle");
  });

  it("clamps a longer value to three lines and expands it on click or Enter", () => {
    layout(560, 42);
    const table = `[${Array.from({ length: 40 }, (_, k) => `${k} ${k * 0.25} ${k * 0.5}`).join("; ")}]`;
    render(<MetaValue text={table} testId="value" />);
    const value = screen.getByRole("button");
    expect(value.textContent).toBe(table);
    expect(value.getAttribute("aria-expanded")).toBe("false");
    fireEvent.click(value);
    expect(value.getAttribute("aria-expanded")).toBe("true");
    expect(value.className).toContain("is-open");
    fireEvent.keyDown(value, { key: "Enter" });
    expect(value.getAttribute("aria-expanded")).toBe("false");
    expect(value.className).not.toContain("is-open");
  });
});
