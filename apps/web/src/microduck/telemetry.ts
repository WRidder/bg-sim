/** What the duck's telemetry window shows: command against motion, the left leg, the policy. */

import { AMBER, BLUE, GREEN, type Panel, RED } from "../engine/telemetry";
import type { DuckLoop } from "./loop";
import type { OnnxBrain } from "./policy";

const DEG = 180 / Math.PI;

export function duckPanel(loop: DuckLoop, brain: () => OnnxBrain | null): Panel {
  const cmd = (i: number) => (): number => loop.filter.value.twist[i];
  const act = (i: number) => (): number => loop.actual[i];
  const target = (j: number) => (): number => (loop.lastTick?.targets[j] ?? 0) * DEG;
  const joint = (j: number) => (): number => loop.plant.state.q[j] * DEG;
  const action = (): number[] => Array.from(loop.lastTick?.step?.action ?? []);
  return {
    sections: [
      {
        title: "Command and motion",
        items: [
          { kind: "plot", label: "Forward", unit: "m/s", min: -0.3, max: 0.4, digits: 2, series: [{ label: "cmd", get: cmd(0), colour: AMBER }, { label: "trunk", get: act(0), colour: BLUE }] },
          { kind: "plot", label: "Left", unit: "m/s", min: -0.3, max: 0.3, digits: 2, series: [{ label: "cmd", get: cmd(1), colour: AMBER }, { label: "trunk", get: act(1), colour: BLUE }] },
          { kind: "plot", label: "Turn", unit: "rad/s", min: -1, max: 1, digits: 2, series: [{ label: "cmd", get: cmd(2), colour: AMBER }, { label: "trunk", get: act(2), colour: BLUE }] },
          { kind: "value", label: "Trunk height", unit: "mm", get: () => loop.plant.state.position[2] * 1000, digits: 0 },
          { kind: "value", label: "Left foot", get: () => loop.plant.state.contact?.[0] ?? NaN, digits: 0 },
          { kind: "value", label: "Right foot", get: () => loop.plant.state.contact?.[1] ?? NaN, digits: 0 },
        ],
      },
      {
        title: "Left leg: target and position",
        items: [
          { kind: "plot", label: "Hip pitch", unit: "°", min: -50, max: 10, digits: 0, series: [{ label: "target", get: target(2), colour: AMBER }, { label: "joint", get: joint(2), colour: GREEN }] },
          { kind: "plot", label: "Knee", unit: "°", min: -40, max: 40, digits: 0, series: [{ label: "target", get: target(3), colour: AMBER }, { label: "joint", get: joint(3), colour: GREEN }] },
          { kind: "plot", label: "Ankle", unit: "°", min: 0, max: 60, digits: 0, series: [{ label: "target", get: target(4), colour: AMBER }, { label: "joint", get: joint(4), colour: GREEN }] },
        ],
      },
      {
        title: "Policy",
        items: [
          { kind: "bar", label: "Largest action", get: () => Math.max(0, ...action().map(Math.abs)), min: 0, max: 2, digits: 2, zones: [[1.5, 2, RED]] },
          { kind: "value", label: "Inference", unit: "ms", get: () => brain()?.lastMs ?? NaN, digits: 2 },
          { kind: "value", label: "Ticks", get: () => loop.ticks, digits: 0 },
        ],
      },
    ],
  };
}
