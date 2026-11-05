/** What the F-16's panel shows: the engine, the envelope the flight control guards, how hard it works. */

import { AMBER, BLUE, GREEN, RED, type Panel } from "../engine/telemetry";
import type { Knob } from "../engine/tuning";
import type { Flight } from "./flight";

/** The switches of the flight control are on the title screen, and win over anything set here. */
export const F16_KNOBS: readonly Knob[] = [
  { name: "mass", label: "Mass", group: "Loading", unit: "kg", digits: 0, hint: "Fuel and stores. The start trim stays, so a change shows at once." },
  { name: "xcg", label: "Centre of gravity", group: "Loading", scale: 100, unit: "% chord", digits: 1, hint: "Further aft is livelier and less stable." },
];

export function f16Panel(f: Flight): Panel {
  return {
    sections: [
      {
        title: "Engine",
        items: [
          { kind: "gauge", label: "Power", unit: "%", get: () => f.get("power_pct"), min: 0, max: 100, zones: [[50, 100, AMBER]], digits: 0 },
          { kind: "gauge", label: "Thrust", unit: "kN", get: () => f.get("thrust_n") / 1000, min: 0, max: 130, digits: 0 },
        ],
      },
      {
        title: "Envelope",
        items: [
          {
            kind: "plot", label: "Load", unit: "g", min: -1, max: 9, digits: 1, lines: [{ at: 9, colour: RED }],
            series: [
              { label: "NZ", get: () => f.get("nz_g"), colour: GREEN },
              { label: "CMD", get: () => f.get("nz_cmd_g"), colour: "rgba(242,244,239,0.55)" },
            ],
          },
          {
            kind: "plot", label: "Angle of attack", unit: "deg", min: -5, max: 26, digits: 1, lines: [{ at: 25, colour: RED }],
            series: [{ label: "α", get: () => f.get("alpha_deg"), colour: AMBER }],
          },
          { kind: "value", label: "Mach", get: () => f.get("mach"), digits: 2 },
          { kind: "value", label: "CAS", unit: "m/s", get: () => f.get("cas_mps"), digits: 0 },
          { kind: "value", label: "Dyn. press.", unit: "kPa", get: () => f.get("qbar_pa") / 1000, digits: 1 },
          { kind: "value", label: "Sideslip", unit: "°", get: () => f.get("beta_deg"), digits: 1 },
          { kind: "value", label: "Lateral", unit: "g", get: () => f.get("ny_g"), digits: 2 },
          { kind: "value", label: "Limiter", get: () => f.get("limiter_active"), digits: 0, alert: (v) => (v > 0.5 ? RED : undefined) },
        ],
      },
      {
        title: "Rates",
        items: [
          {
            kind: "plot", label: "Body rates", unit: "deg/s", min: -60, max: 60, digits: 0,
            series: [
              { label: "P", get: () => f.get("p_dps"), colour: BLUE },
              { label: "Q", get: () => f.get("q_dps"), colour: GREEN },
              { label: "R", get: () => f.get("r_dps"), colour: AMBER },
            ],
          },
        ],
      },
      {
        title: "Surfaces",
        items: [
          { kind: "bar", label: "Stabilator", unit: "°", get: () => f.get("stab_deg"), min: -25, max: 25, digits: 1 },
          { kind: "bar", label: "Aileron", unit: "°", get: () => f.get("ail_deg"), min: -21.5, max: 21.5, digits: 1 },
          { kind: "bar", label: "Rudder", unit: "°", get: () => f.get("rdr_deg"), min: -30, max: 30, digits: 1 },
        ],
      },
    ],
  };
}
