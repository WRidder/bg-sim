/** What the A109's panel shows: the rotor first, it is what a pilot must keep alive, then the controls. */

import { AMBER, BLUE, GREEN, RED, type Panel } from "../engine/telemetry";
import type { Flight } from "./flight";

export function a109Panel(f: Flight): Panel {
  return {
    sections: [
      {
        title: "Rotor and engines",
        items: [
          { kind: "gauge", label: "Rotor", unit: "%", get: () => f.get("rotor_pct"), min: 60, max: 120, zones: [[60, 90, RED], [95, 105, GREEN], [110, 120, RED]], digits: 0 },
          { kind: "gauge", label: "Power", unit: "hp", get: () => f.get("power_hp"), min: 0, max: 1200, zones: [[900, 1200, AMBER]], digits: 0 },
          { kind: "plot", label: "Rotor thrust", unit: "kN", min: 0, max: 45, digits: 1, series: [{ label: "T", get: () => f.get("thrust_n") / 1000, colour: GREEN }] },
        ],
      },
      {
        title: "Motion",
        items: [
          {
            kind: "plot", label: "Body rates", unit: "deg/s", min: -40, max: 40, digits: 0,
            series: [
              { label: "P", get: () => f.get("p_dps"), colour: BLUE },
              { label: "Q", get: () => f.get("q_dps"), colour: GREEN },
              { label: "R", get: () => f.get("r_dps"), colour: AMBER },
            ],
          },
          { kind: "value", label: "Air speed", unit: "kt", get: () => f.get("kts"), digits: 0 },
          { kind: "value", label: "Vert. speed", unit: "m/s", get: () => f.get("vs_mps"), digits: 1 },
          { kind: "value", label: "Sideslip", unit: "°", get: () => f.get("beta_deg"), digits: 0 },
        ],
      },
      {
        title: "Controls",
        items: [
          { kind: "bar", label: "Collective", unit: "°", get: () => f.get("theta0_deg"), min: 0, max: 20, digits: 1 },
          { kind: "bar", label: "Long. cyclic", unit: "°", get: () => f.get("B1_deg"), min: -12, max: 12, digits: 1 },
          { kind: "bar", label: "Lat. cyclic", unit: "°", get: () => f.get("A1_deg"), min: -8, max: 8, digits: 1 },
          { kind: "bar", label: "Tail pitch", unit: "°", get: () => f.get("theta_tr_deg"), min: -10, max: 25, digits: 1 },
          { kind: "scatter", label: "Rotor flapping", x: () => f.get("b1_deg"), y: () => f.get("a1_deg"), range: 8, rings: [4, 8] },
          {
            kind: "corners", label: "Wheel loads", unit: "kN", min: 0, max: 20, digits: 1,
            get: [() => f.get("fn_nose") / 1000, () => f.get("fn_left") / 1000, () => f.get("fn_right") / 1000],
          },
        ],
      },
    ],
  };
}
