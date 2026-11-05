/** A landing, marked out of a hundred: what a check pilot would look at, in the order he would. */

import { AIRFIELD } from "../island/island";
import { AIM_POINT, type Surface, type Touchdown } from "./flight";

export interface Line {
  label: string;
  /** What was measured. */
  detail: string;
  points: number;
  of: number;
}

export interface Sheet {
  total: number;
  verdict: string;
  lines: Line[];
}

const scale = (value: number, full: number, none: number): number => Math.max(0, Math.min(1, (none - value) / (none - full)));

export function verdict(total: number): string {
  if (total >= 92) {
    return "Greased it";
  }
  if (total >= 78) {
    return "Lovely landing";
  }
  if (total >= 58) {
    return "Solid arrival";
  }
  if (total >= 35) {
    return "Everyone got out";
  }
  return "Call the mechanic";
}

export function markLanding(touchdowns: Touchdown[], stopped: { surface: Surface } | null, missedRings = 0, scraped = false): Sheet {
  const first = touchdowns[0];
  const sinkPoints = Math.round(40 * scale(first.sink, 120, 700));
  const aimError = Math.abs(first.along - AIM_POINT);
  const aimPoints = first.along < 0 ? 0 : Math.round(25 * scale(aimError, 30, 400));
  const offset = Math.abs(first.across);
  const linePoints = Math.round(20 * scale(offset, 2, AIRFIELD.width / 2));
  const tidy = scale(Math.abs(first.bank), 1.5, 8) * (first.noseFirst ? 0 : 1) * scale(Math.max(4 - first.pitch, 0), 1, 7);
  const tidyPoints = Math.round(15 * tidy);
  const lines: Line[] = [
    { label: "Sink rate", detail: `${Math.round(first.sink)} ft/min`, points: sinkPoints, of: 40 },
    { label: "Aiming point", detail: first.along < 0 ? `${Math.round(-first.along)} m short` : `${Math.abs(Math.round(first.along - AIM_POINT))} m ${first.along >= AIM_POINT ? "long" : "short"}`, points: aimPoints, of: 25 },
    { label: "Centre line", detail: `${offset.toFixed(1)} m ${first.across >= 0 ? "right" : "left"}`, points: linePoints, of: 20 },
    { label: "Attitude", detail: first.noseFirst ? "nose wheel first" : `${first.pitch.toFixed(0)}° nose up, ${Math.abs(first.bank).toFixed(0)}° bank`, points: tidyPoints, of: 15 },
  ];
  const bounces = touchdowns.filter((t) => t.bounce).length;
  let total = sinkPoints + aimPoints + linePoints + tidyPoints;
  if (bounces > 0) {
    lines.push({ label: "Bounces", detail: bounces === 1 ? "one" : String(bounces), points: -8 * bounces, of: 0 });
    total -= 8 * bounces;
  }
  if (missedRings > 0) {
    lines.push({ label: "Rings missed", detail: String(missedRings), points: -2 * missedRings, of: 0 });
    total -= 2 * missedRings;
  }
  if (scraped) {
    lines.push({ label: "Tail scrape", detail: "the skid touched", points: -10, of: 0 });
    total -= 10;
  }
  const onRunway = first.surface === "runway" && (stopped === null || stopped.surface !== "grass");
  if (!onRunway) {
    lines.push({ label: "Off the runway", detail: "on the grass", points: -30, of: 0 });
    total -= 30;
  }
  total = Math.max(0, total);
  return { total, verdict: verdict(total), lines };
}
