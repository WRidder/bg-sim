import { useCallback, useEffect, useState } from "react";

import { applyTheme, initialTheme, storeTheme, type Theme } from "./theme";

export interface ThemeController {
  theme: Theme;
  setTheme: (theme: Theme) => void;
  toggleTheme: () => void;
}

/**
 * The app's theme state: reads the stored theme once, keeps <html data-theme>
 * in step, and writes every change back to localStorage.
 */
export function useTheme(): ThemeController {
  const [theme, setThemeState] = useState<Theme>(initialTheme);

  useEffect(() => {
    applyTheme(theme);
  }, [theme]);

  const setTheme = useCallback((next: Theme) => {
    storeTheme(next);
    setThemeState(next);
  }, []);

  const toggleTheme = useCallback(() => {
    setTheme(theme === "dark" ? "light" : "dark");
  }, [setTheme, theme]);

  return { theme, setTheme, toggleTheme };
}
