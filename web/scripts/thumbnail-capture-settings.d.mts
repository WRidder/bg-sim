/** Types of thumbnail-capture-settings.mjs (for the gallery test). */

export interface CaptureSettings {
  model?: string;
  run?: boolean;
  at?: number;
  time?: number;
  zoom?: number;
  view?: "iso" | "top" | "front" | "side";
  orbit?: [number, number];
  runTimeout?: number;
}

export const CAPTURE_KEYS: readonly string[];
export const CAPTURE_VIEWS: readonly string[];
export function captureSettings(entry: unknown, overrides?: Partial<CaptureSettings>): CaptureSettings;
