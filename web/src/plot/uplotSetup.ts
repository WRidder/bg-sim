/**
 * uPlot reads `window.matchMedia` while its module is evaluated (its cached
 * device-pixel-ratio listener). jsdom, which the component tests use, does not
 * implement `matchMedia`, so importing the chart module would break every test
 * that renders the shell. Browsers all provide it; this fallback only fills the
 * test gap and never changes behaviour where it exists.
 *
 * It must be imported *before* `uplot` in UPlotChart.tsx.
 */

interface MatchMediaWindow {
  matchMedia?: (query: string) => MediaQueryList;
}

if (typeof window !== "undefined") {
  const target = window as unknown as MatchMediaWindow;
  if (typeof target.matchMedia !== "function") {
    target.matchMedia = (query: string): MediaQueryList =>
      ({
        matches: false,
        media: query,
        onchange: null,
        addListener: () => {
          /* jsdom never emits media-query changes */
        },
        removeListener: () => {
          /* see addListener */
        },
        addEventListener: () => {
          /* see addListener */
        },
        removeEventListener: () => {
          /* see addListener */
        },
        dispatchEvent: () => false,
      }) as MediaQueryList;
  }
}
