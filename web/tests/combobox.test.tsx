import { fireEvent, render, screen } from "@testing-library/react";
import { useState } from "react";
import { describe, expect, it, vi } from "vitest";

import { Combobox, comboChoices, filterChoices, type ComboChoices } from "../src/viewer/Combobox";

const IDS = Array.from({ length: 3000 }, (_, k) => `Plant/Body${String(Math.floor(k / 10))}/q[${String((k % 10) + 1)}]`);
const BIG = comboChoices(IDS, IDS.map((id) => `${id} [m]`));
const SMALL = comboChoices(["A/x", "A/y", "B/phi"], ["A/x [m]", "A/y [m]", "B/phi [rad]"]);

/** A combobox that keeps its value, reporting every change. */
function Field({ initial, choices, noneLabel, onChange }: { initial: string; choices: ComboChoices; noneLabel?: string; onChange?: (v: string) => void }) {
  const [value, setValue] = useState(initial);
  return (
    <Combobox
      value={value}
      choices={choices}
      label="Signal"
      testId="field"
      noneLabel={noneLabel}
      placeholder={noneLabel === undefined ? "Choose a signal" : undefined}
      unknownNote="unknown"
      onChange={(v) => {
        setValue(v);
        onChange?.(v);
      }}
    />
  );
}

function input(): HTMLInputElement {
  return screen.getByTestId("field") as HTMLInputElement;
}

function optionTexts(): string[] {
  return screen.queryAllByRole("option").map((o) => o.textContent ?? "");
}

describe("the searchable signal field", () => {
  it("shows the value with its unit and renders no options while closed", () => {
    render(<Field initial="Plant/Body3/q[2]" choices={BIG} />);
    expect(input().value).toBe("Plant/Body3/q[2] [m]");
    expect(input().getAttribute("role")).toBe("combobox");
    expect(input().getAttribute("aria-expanded")).toBe("false");
    expect(input().dataset["value"]).toBe("Plant/Body3/q[2]");
    expect(screen.queryAllByRole("option")).toHaveLength(0);
  });

  it("opens on a click at the current value and renders only a window of 3000 signals", () => {
    render(<Field initial="Plant/Body200/q[1]" choices={BIG} />);
    fireEvent.click(input());
    expect(input().getAttribute("aria-expanded")).toBe("true");
    const options = screen.getAllByRole("option");
    expect(options.length).toBeGreaterThan(0);
    expect(options.length).toBeLessThanOrEqual(30);
    expect(options[0]?.getAttribute("aria-setsize")).toBe("3000");
    // the active option is the current value, and the input points at it
    const active = screen.getByRole("option", { selected: true });
    expect(active.dataset["value"]).toBe("Plant/Body200/q[1]");
    expect(input().getAttribute("aria-activedescendant")).toBe(active.id);
  });

  it("filters by every typed term, case-insensitively, and Enter takes the first match", () => {
    const changed = vi.fn();
    render(<Field initial="" choices={BIG} onChange={changed} />);
    expect(input().placeholder).toBe("Choose a signal");
    fireEvent.change(input(), { target: { value: "body12 Q[3" } });
    expect(optionTexts()).toEqual(["Plant/Body12/q[3] [m]", "Plant/Body120/q[3] [m]", "Plant/Body121/q[3] [m]", "Plant/Body122/q[3] [m]", "Plant/Body123/q[3] [m]", "Plant/Body124/q[3] [m]", "Plant/Body125/q[3] [m]", "Plant/Body126/q[3] [m]", "Plant/Body127/q[3] [m]", "Plant/Body128/q[3] [m]", "Plant/Body129/q[3] [m]"]);
    fireEvent.keyDown(input(), { key: "Enter" });
    expect(changed).toHaveBeenCalledWith("Plant/Body12/q[3]");
    expect(input().value).toBe("Plant/Body12/q[3] [m]");
    expect(screen.queryAllByRole("option")).toHaveLength(0);
  });

  it("says so when nothing matches, and Enter then changes nothing", () => {
    const changed = vi.fn();
    render(<Field initial="A/x" choices={SMALL} onChange={changed} />);
    fireEvent.change(input(), { target: { value: "zzz" } });
    expect(screen.getByText("No match")).toBeTruthy();
    fireEvent.keyDown(input(), { key: "Enter" });
    expect(changed).not.toHaveBeenCalled();
  });

  it("moves with the arrow keys, chooses with Enter and restores the value on Escape", () => {
    const changed = vi.fn();
    render(<Field initial="A/x" choices={SMALL} onChange={changed} />);
    fireEvent.keyDown(input(), { key: "ArrowDown" });
    expect(screen.getByRole("option", { selected: true }).dataset["value"]).toBe("A/x");
    fireEvent.keyDown(input(), { key: "ArrowDown" });
    fireEvent.keyDown(input(), { key: "ArrowDown" });
    fireEvent.keyDown(input(), { key: "ArrowDown" });
    // stops at the last option
    expect(screen.getByRole("option", { selected: true }).dataset["value"]).toBe("B/phi");
    fireEvent.keyDown(input(), { key: "ArrowUp" });
    fireEvent.keyDown(input(), { key: "Enter" });
    expect(changed).toHaveBeenLastCalledWith("A/y");

    fireEvent.change(input(), { target: { value: "phi" } });
    fireEvent.keyDown(input(), { key: "Escape" });
    expect(input().value).toBe("A/y [m]");
    expect(input().getAttribute("aria-expanded")).toBe("false");
    expect(changed).toHaveBeenCalledTimes(1);
  });

  it("windows the list as the active option moves through thousands of signals", () => {
    render(<Field initial="" choices={BIG} />);
    fireEvent.keyDown(input(), { key: "ArrowDown" });
    for (let k = 0; k < 5; k++) fireEvent.keyDown(input(), { key: "PageDown" });
    const active = screen.getByRole("option", { selected: true });
    expect(active.getAttribute("aria-posinset")).toBe("61");
    expect(screen.getAllByRole("option").length).toBeLessThanOrEqual(30);
  });

  it("chooses an option with the mouse", () => {
    const changed = vi.fn();
    render(<Field initial="A/x" choices={SMALL} onChange={changed} />);
    fireEvent.click(input());
    fireEvent.click(screen.getByRole("option", { name: "B/phi [rad]" }));
    expect(changed).toHaveBeenCalledWith("B/phi");
    expect(input().value).toBe("B/phi [rad]");
  });

  it("stays closed after a choice inside a label (which passes clicks on to the input)", () => {
    const changed = vi.fn();
    render(
      <label>
        <span>Signal</span>
        <Field initial="A/x" choices={SMALL} onChange={changed} />
      </label>,
    );
    fireEvent.click(input());
    fireEvent.click(screen.getByRole("option", { name: "A/y [m]" }));
    expect(changed).toHaveBeenCalledWith("A/y");
    expect(input().getAttribute("aria-expanded")).toBe("false");
    expect(screen.queryAllByRole("option")).toHaveLength(0);
  });

  it("keeps an unknown value, marked, and offers it first", () => {
    render(<Field initial="Old/name" choices={SMALL} />);
    expect(input().value).toBe("Old/name (unknown)");
    expect(input().getAttribute("aria-invalid")).toBe("true");
    fireEvent.click(input());
    expect(optionTexts()).toEqual(["Old/name (unknown)", "A/x [m]", "A/y [m]", "B/phi [rad]"]);
    expect(screen.getByRole("option", { selected: true }).dataset["value"]).toBe("Old/name");
  });

  it("offers none first in an optional field, and an emptied field means none", () => {
    const changed = vi.fn();
    render(<Field initial="A/x" choices={SMALL} noneLabel="none" onChange={changed} />);
    fireEvent.click(input());
    expect(optionTexts()[0]).toBe("none");
    fireEvent.click(screen.getByRole("option", { name: "none" }));
    expect(changed).toHaveBeenLastCalledWith("");
    expect(input().value).toBe("none");
    fireEvent.change(input(), { target: { value: "B/phi" } });
    fireEvent.blur(input());
    expect(changed).toHaveBeenLastCalledWith("B/phi");
    fireEvent.change(input(), { target: { value: "" } });
    fireEvent.blur(input());
    expect(changed).toHaveBeenLastCalledWith("");
  });

  it("takes typed text on leaving only when it names a choice exactly", () => {
    const changed = vi.fn();
    render(<Field initial="A/x" choices={SMALL} onChange={changed} />);
    fireEvent.change(input(), { target: { value: "A/" } });
    fireEvent.blur(input());
    expect(changed).not.toHaveBeenCalled();
    expect(input().value).toBe("A/x [m]");
    fireEvent.change(input(), { target: { value: "B/phi" } });
    fireEvent.blur(input());
    expect(changed).toHaveBeenCalledWith("B/phi");
  });

  it("does not submit a form on Enter", () => {
    const submit = vi.fn((e: { preventDefault: () => void }) => {
      e.preventDefault();
    });
    render(
      <form onSubmit={submit}>
        <Field initial="A/x" choices={SMALL} />
      </form>,
    );
    // Enter is handled (default prevented): it opens the list, then chooses
    expect(fireEvent.keyDown(input(), { key: "Enter" })).toBe(false);
    expect(input().getAttribute("aria-expanded")).toBe("true");
    expect(fireEvent.keyDown(input(), { key: "Enter" })).toBe(false);
    expect(submit).not.toHaveBeenCalled();
  });
});

describe("filterChoices", () => {
  it("matches every term anywhere in the label, keeping list order", () => {
    expect(filterChoices(SMALL, "a")).toEqual([0, 1, 2]);
    expect(filterChoices(SMALL, " [m] a/ ")).toEqual([0, 1]);
    expect(filterChoices(SMALL, "RAD")).toEqual([2]);
    expect(filterChoices(SMALL, "")).toEqual([0, 1, 2]);
  });
});
