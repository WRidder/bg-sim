/**
 * The theme switch (plan 7.2, 7.8): `data-theme` on <html>, dark by default,
 * persisted in localStorage, and never fatal when storage is unavailable.
 */

import { fireEvent, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { App } from "../src/app/App";
import { THEME_STORAGE_KEY, initialTheme, readStoredTheme, storeTheme } from "../src/theme/theme";

beforeEach(() => {
  localStorage.clear();
  document.documentElement.dataset.theme = "dark";
});

afterEach(() => {
  localStorage.clear();
  document.documentElement.dataset.theme = "dark";
});

describe("theme", () => {
  it("starts dark and flips data-theme and localStorage when toggled", () => {
    render(<App />);
    expect(document.documentElement.dataset.theme).toBe("dark");

    const toggle = screen.getByTestId("theme-toggle");
    expect(toggle.getAttribute("aria-label")).toBe("Switch to light theme");

    fireEvent.click(toggle);

    expect(document.documentElement.dataset.theme).toBe("light");
    expect(localStorage.getItem(THEME_STORAGE_KEY)).toBe("light");
    expect(toggle.getAttribute("aria-label")).toBe("Switch to dark theme");

    fireEvent.click(toggle);
    expect(document.documentElement.dataset.theme).toBe("dark");
    expect(localStorage.getItem(THEME_STORAGE_KEY)).toBe("dark");
  });

  it("restores a stored theme on start", () => {
    localStorage.setItem(THEME_STORAGE_KEY, "light");

    expect(initialTheme()).toBe("light");
    render(<App />);
    expect(document.documentElement.dataset.theme).toBe("light");
  });

  it("ignores a stored value that is not a theme", () => {
    localStorage.setItem(THEME_STORAGE_KEY, "solarized");

    expect(readStoredTheme()).toBeNull();
    expect(initialTheme()).toBe("dark");
  });

  it("survives a storage that throws", () => {
    vi.spyOn(Storage.prototype, "getItem").mockImplementation(() => {
      throw new Error("storage denied");
    });
    vi.spyOn(Storage.prototype, "setItem").mockImplementation(() => {
      throw new Error("storage denied");
    });

    expect(readStoredTheme()).toBeNull();
    expect(initialTheme()).toBe("dark");
    expect(() => storeTheme("light")).not.toThrow();
  });
});
