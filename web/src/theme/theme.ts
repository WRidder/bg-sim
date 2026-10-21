/**
 * Theme handling (plan 7.2, 7.8): the theme is a `data-theme` attribute on
 * <html>, dark by default, persisted in localStorage.
 *
 * Every storage access is wrapped in try/catch: localStorage throws in some
 * private-mode browsers, and a failed read must not stop the app.
 */

export type Theme = "dark" | "light";

export const THEME_STORAGE_KEY = "bgsim.theme";
export const DEFAULT_THEME: Theme = "dark";

export function isTheme(value: unknown): value is Theme {
  return value === "dark" || value === "light";
}

/** The stored theme, or null when there is none or storage is unavailable. */
export function readStoredTheme(): Theme | null {
  try {
    const stored = localStorage.getItem(THEME_STORAGE_KEY);
    return isTheme(stored) ? stored : null;
  } catch {
    return null;
  }
}

/** Stores the theme; storage failures are ignored (the theme is cosmetic). */
export function storeTheme(theme: Theme): void {
  try {
    localStorage.setItem(THEME_STORAGE_KEY, theme);
  } catch {
    /* the theme simply will not be remembered */
  }
}

export function applyTheme(theme: Theme, root: HTMLElement = document.documentElement): void {
  root.dataset.theme = theme;
}

export function initialTheme(): Theme {
  return readStoredTheme() ?? DEFAULT_THEME;
}

/** Applies the stored theme to <html>; called from main.tsx before rendering. */
export function initTheme(): Theme {
  const theme = initialTheme();
  applyTheme(theme);
  return theme;
}
