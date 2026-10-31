import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { MetaValue } from "../src/inspector/fields";

describe("MetaValue", () => {
  it("shows a short value as plain code", () => {
    render(<MetaValue text="0.5" testId="value" />);
    expect(screen.queryByRole("button")).toBeNull();
    expect(screen.getByText("0.5").tagName).toBe("CODE");
  });

  it("folds a long value to one line and expands it on click", () => {
    const table = `[${Array.from({ length: 40 }, (_, k) => `${k} ${k * 0.25} ${k * 0.5}`).join("; ")}]`;
    render(<MetaValue text={table} testId="value" />);
    const button = screen.getByTestId("value");
    expect(button.getAttribute("aria-expanded")).toBe("false");
    expect(button.className).not.toContain("is-open");
    expect(button.textContent).toBe(table);
    fireEvent.click(button);
    expect(button.getAttribute("aria-expanded")).toBe("true");
    expect(button.className).toContain("is-open");
    fireEvent.click(button);
    expect(button.getAttribute("aria-expanded")).toBe("false");
  });
});
