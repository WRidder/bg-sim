/** What the Cessna's panel shows: the engine and propeller first, then the wing and the wheels. */

import { AMBER, BLUE, GREEN, RED, type Panel } from "../engine/telemetry";
import type { Flight } from "./flight";

export function cessnaPanel(f: Flight): Panel {
  return {
    sections: [
      {
        title: "Engine and propeller",
        items: [
          { kind: "gauge", label: "Prop speed", unit: "rpm", get: () => f.get("rpm"), min: 0, max: 3000, zones: [[2100, 2700, GREEN], [2700, 3000, RED]], digits: 0 },
          { kind: "gauge", label: "Manifold", unit: "inHg", get: () => f.get("map_inhg"), min: 10, max: 30, zones: [[15, 29, GREEN]], digits: 1 },
          { kind: "plot", label: "Power", unit: "hp", min: 0, max: 180, digits: 0, series: [{ label: "HP", get: () => f.get("hp"), colour: GREEN }] },
          { kind: "value", label: "Thrust", unit: "N", get: () => f.get("thrust_n"), digits: 0 },
          { kind: "value", label: "Fuel flow", unit: "gal/h", get: () => f.get("ff_gph"), digits: 1 },
          { kind: "value", label: "Stall", get: () => f.get("stall_flag"), digits: 0, alert: (v) => (v > 0.5 ? RED : undefined) },
        ],
      },
      {
        title: "Wing",
        items: [
          {
            kind: "plot", label: "Angle of attack", unit: "deg", min: -2, max: 18, digits: 1, lines: [{ at: 15, colour: RED }],
            series: [{ label: "α", get: () => f.get("alpha_deg"), colour: AMBER }],
          },
          { kind: "plot", label: "Speed", unit: "kt", min: 40, max: 130, digits: 0, series: [{ label: "IAS", get: () => f.get("kias"), colour: BLUE }] },
          { kind: "value", label: "Vert. speed", unit: "ft/min", get: () => f.get("vs_fpm"), digits: 0 },
          { kind: "value", label: "Height", unit: "ft", get: () => f.get("agl_ft"), digits: 0 },
          { kind: "value", label: "Slip", get: () => f.get("slip"), digits: 2 },
        ],
      },
      {
        title: "Surfaces and gear",
        items: [
          { kind: "bar", label: "Elevator", unit: "°", get: () => f.get("elevator_deg"), min: -28, max: 28, digits: 1 },
          { kind: "bar", label: "Aileron", unit: "°", get: () => f.get("aileron_deg"), min: -20, max: 20, digits: 1 },
          { kind: "bar", label: "Rudder", unit: "°", get: () => f.get("rudder_deg"), min: -24, max: 24, digits: 1 },
          { kind: "bar", label: "Flaps", unit: "°", get: () => f.get("flap_deg"), min: 0, max: 30, digits: 0 },
          {
            kind: "corners", label: "Wheel loads", unit: "kN", min: 0, max: 6, digits: 1,
            get: [() => f.get("fn_nose") / 1000, () => f.get("fn_left") / 1000, () => f.get("fn_right") / 1000],
          },
        ],
      },
    ],
  };
}
