/**
 * The per-example capture settings of `capture-thumbnails.mjs`: the optional `capture` object of an
 * example's gallery.json entry, overridden by the command line. Kept apart from the script so the gallery
 * test can check the committed settings without starting a browser.
 *
 *   model       the model to shoot (default: the first model with a scene)
 *   run         run the model before the 3D shot and frame the scene at `at` / `time` (default false)
 *   at          where to seek the playback, as a fraction of the run (0..1, default 0.5)
 *   time        where to seek the playback, in seconds of simulation (wins over `at`)
 *   zoom        mouse-wheel notches toward the view centre after the fit (default 0; negative zooms out)
 *   view        camera preset before the fit: iso, top, front or side
 *   orbit       [dx, dy]: after the zoom, a left drag of that many pixels from the view centre (orbits the
 *               camera around the scene point there; dy < 0 tilts a top view toward the horizon)
 *   runTimeout  seconds to wait for the run (default 900)
 */

/** The keys of a gallery.json `capture` entry. */
export const CAPTURE_KEYS = ["model", "run", "at", "time", "view", "zoom", "orbit", "runTimeout"];
export const CAPTURE_VIEWS = ["iso", "top", "front", "side"];

/** Merged and checked settings; throws on an unknown key or a bad value, so a typo does not give the old shot. */
export function captureSettings(entry, overrides = {}) {
  const settings = { ...(entry ?? {}), ...overrides };
  for (const key of Object.keys(settings)) {
    if (!CAPTURE_KEYS.includes(key)) throw new Error(`unknown capture setting ${JSON.stringify(key)}; known: ${CAPTURE_KEYS.join(", ")}`);
  }
  const { model, run, at, time, zoom, view, orbit, runTimeout } = settings;
  if (model !== undefined && (typeof model !== "string" || model.length === 0)) throw new Error('capture "model" must be a model name');
  if (run !== undefined && typeof run !== "boolean") throw new Error('capture "run" must be true or false');
  if (at !== undefined && !(typeof at === "number" && at >= 0 && at <= 1)) throw new Error(`capture "at" must be a fraction 0..1, got ${String(at)}`);
  if (time !== undefined && !(typeof time === "number" && Number.isFinite(time))) throw new Error(`capture "time" must be seconds, got ${String(time)}`);
  if (zoom !== undefined && !(Number.isInteger(zoom) && zoom >= -20 && zoom <= 40)) {
    throw new Error(`capture "zoom" must be a whole number of wheel notches (-20..40), got ${String(zoom)}`);
  }
  if (view !== undefined && !CAPTURE_VIEWS.includes(view)) throw new Error(`capture "view" must be one of ${CAPTURE_VIEWS.join(", ")}`);
  if (orbit !== undefined && !(Array.isArray(orbit) && orbit.length === 2 && orbit.every((v) => Number.isInteger(v) && Math.abs(v) <= 400))) {
    throw new Error('capture "orbit" must be [dx, dy] in whole pixels (at most 400 each)');
  }
  if (orbit !== undefined && run !== true) throw new Error('capture "orbit" needs "run": true');
  if (runTimeout !== undefined && !(typeof runTimeout === "number" && runTimeout > 0)) throw new Error('capture "runTimeout" must be positive seconds');
  if ((at !== undefined || time !== undefined) && run !== true) throw new Error('capture "at" and "time" need "run": true (there is no playback before a run)');
  return settings;
}
