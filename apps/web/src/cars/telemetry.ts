/**
 * What the cars' panel shows. The tyre figures say why the car does what it does: how far up its
 * force curve each corner is, and the body slip that a drift is. Downforce is not an FMU output, so
 * it is the formula of the model's Aero block with the model's numbers.
 */

import { AMBER, GREEN, RED, type Panel, type Read, type Zone } from "../engine/telemetry";
import type { Knob } from "../engine/tuning";
import type { Kind } from "./track";
import type { Corner, Vehicle } from "./vehicle";

const RHO = 1.225;

/** The numbers of the two tyres in examples/cars/design/vehicles.py that set where the peak is. */
export interface TyreData {
  Fz0: number;
  mux: number;
  muy: number;
  dmu: number;
  Kx: number;
  Cx: number;
  Ky: number;
  Ky2: number;
  Cy: number;
}

const SLICK: TyreData = { Fz0: 2200, mux: 1.65, muy: 1.6, dmu: -0.12, Kx: 25, Cx: 1.6, Ky: 22, Ky2: 2.5, Cy: 1.45 };
const OFFROAD: TyreData = { Fz0: 2500, mux: 1, muy: 0.95, dmu: -0.08, Kx: 16, Cx: 1.5, Ky: 12, Ky2: 2.2, Cy: 1.35 };

const SETUP = {
  racecar: { tyre: SLICK, load: 6, bump: 45, droop: 60, motor: 20000, torque: 300, kw: 260, clA: 2.6, g: 3, beta: 12 },
  buggy: { tyre: OFFROAD, load: 8, bump: 200, droop: 170, motor: 12000, torque: 150, kw: 120, clA: 0, g: 1.5, beta: 25 },
} as const;

/**
 * The tyre's normalised slip, as the model's Tyre block has it (design/tyre.py): 1 is the top of
 * the force curve, and past it the tyre slides. `mu` is the surface's friction scale.
 */
export function normalisedSlip(ty: TyreData, fz: number, kappa: number, tanAlpha: number, mu: number): number {
  const load = Math.max(fz, 1);
  const scale = Math.max(1 + (ty.dmu * (load - ty.Fz0)) / ty.Fz0, 0.1);
  const mx = mu * ty.mux * scale;
  const my = mu * ty.muy * scale;
  const peakKappa = Math.tan(Math.PI / (2 * ty.Cx)) / (ty.Kx / (ty.Cx * mx));
  const stiffness = ty.Ky * ty.Fz0 * Math.sin(2 * Math.atan(load / (ty.Ky2 * ty.Fz0)));
  const peakAlpha = Math.tan(Math.PI / (2 * ty.Cy)) / (stiffness / (ty.Cy * my * load));
  return Math.hypot(kappa / peakKappa, tanAlpha / peakAlpha);
}

const TC = "How far the driven wheels may overrun the car. Lower keeps the tail in line on the throttle.";
const BRAKE = "Torque per wheel at full pedal. There is no ABS: too much locks the wheels.";

const SETUPS: Record<Kind, readonly Knob[]> = {
  racecar: [
    { name: "MotorR/kappa_tc", label: "Traction control slip", group: "Traction", scale: 100, unit: "%", digits: 1, hint: TC },
    { name: "MotorR/T_max", label: "Motor torque", group: "Traction", unit: "N m", digits: 0, hint: "Below about 200 N m full throttle cannot break the rear tyres away, and the launch is slower." },
    { name: "MotorR/P_max", label: "Motor power", group: "Traction", scale: 0.001, unit: "kW", digits: 0 },
    { name: "LsdR/d", label: "Limited slip", group: "Traction", unit: "N m s", digits: 0, hint: "Locks the rear wheels together. More resists turning in and steps out sooner on the throttle." },
    { name: "Aero/ClA", label: "Downforce", group: "Aero", unit: "m²", digits: 2, hint: "Grip at speed. Nothing at a hairpin." },
    { name: "Aero/front", label: "Aero balance", group: "Aero", scale: 100, unit: "% front", digits: 0, hint: "Less at the front plants the rear at speed." },
    { name: "Aero/CdA", label: "Drag", group: "Aero", unit: "m²", digits: 2 },
    { name: "Brakes/Tf", label: "Front brakes", group: "Brakes", unit: "N m", digits: 0, hint: BRAKE },
    { name: "Brakes/Tr", label: "Rear brakes", group: "Brakes", unit: "N m", digits: 0 },
    { name: "MotorR/P_regen", label: "Regeneration", group: "Brakes", scale: 0.001, unit: "kW", digits: 0 },
    { name: "ArbF/k", label: "Front anti-roll bar", group: "Balance", unit: "N/m", digits: 0, hint: "Stiffer takes grip from this end in steady corners." },
    { name: "ArbR/k", label: "Rear anti-roll bar", group: "Balance", unit: "N/m", digits: 0 },
  ],
  buggy: [
    { name: "MotorF/kappa_tc", label: "Front traction slip", group: "Traction", scale: 100, unit: "%", digits: 1, hint: TC },
    { name: "MotorR/kappa_tc", label: "Rear traction slip", group: "Traction", scale: 100, unit: "%", digits: 1 },
    { name: "MotorF/T_max", label: "Front motor torque", group: "Traction", unit: "N m", digits: 0 },
    { name: "MotorR/T_max", label: "Rear motor torque", group: "Traction", unit: "N m", digits: 0 },
    { name: "MotorF/P_max", label: "Front motor power", group: "Traction", scale: 0.001, unit: "kW", digits: 0 },
    { name: "MotorR/P_max", label: "Rear motor power", group: "Traction", scale: 0.001, unit: "kW", digits: 0 },
    { name: "LsdF/d", label: "Front coupling", group: "Traction", unit: "N m s", digits: 0 },
    { name: "LsdR/d", label: "Rear coupling", group: "Traction", unit: "N m s", digits: 0 },
    { name: "Brakes/Tf", label: "Front brakes", group: "Brakes", unit: "N m", digits: 0, hint: BRAKE },
    { name: "Brakes/Tr", label: "Rear brakes", group: "Brakes", unit: "N m", digits: 0 },
    { name: "Brakes/Th", label: "Handbrake", group: "Brakes", unit: "N m", digits: 0 },
    { name: "ArbF/k", label: "Front anti-roll bar", group: "Balance", unit: "N/m", digits: 0 },
  ],
};

export function carKnobs(kind: Kind): readonly Knob[] {
  return SETUPS[kind];
}

const SLIP: readonly Zone[] = [[0, 0.7, GREEN], [0.7, 1, AMBER], [1, 1e9, RED]];

export function carPanel(car: Vehicle): Panel {
  const setup = SETUP[car.kind];
  const corners = ["fl", "fr", "rl", "rr"] as const;
  const slip = (corner: Corner, i: number): Read => () =>
    normalisedSlip(setup.tyre, car.get(`${corner}_fz`), car.get(`${corner}_kappa`), Math.tan(car.get(`${corner}_alpha`)), car.u[5 + i]);
  const degrees = (read: Read): Read => () => (read() * 180) / Math.PI;
  return {
    sections: [
      {
        title: "Driver",
        items: [
          {
            kind: "plot", label: "Pedals", unit: "%", min: 0, max: 100, digits: 0,
            series: [
              { label: "THR", get: () => car.u[1] * 100, colour: GREEN },
              { label: "BRK", get: () => car.u[2] * 100, colour: RED },
            ],
          },
          { kind: "bar", label: "Steering", get: () => car.u[0], min: -1, max: 1, digits: 2 },
        ],
      },
      {
        title: "Balance",
        items: [
          {
            kind: "plot", label: "Body slip", unit: "deg", min: -setup.beta, max: setup.beta, digits: 1,
            lines: [{ at: 8, colour: AMBER }, { at: -8, colour: AMBER }],
            series: [{ label: "β", get: degrees(() => car.get("beta")), colour: AMBER }],
          },
          { kind: "scatter", label: "G-G", x: () => car.get("ay_g"), y: () => car.get("ax_g"), range: setup.g, rings: setup.g > 2 ? [1, 2, 3] : [0.5, 1, 1.5], sides: ["L", "R", "ACC", "BRK"] },
          { kind: "corners", label: "Slip / peak", get: corners.map(slip), min: 0, max: 1.5, zones: SLIP, digits: 2 },
        ],
      },
      {
        title: "Tyres and suspension",
        items: [
          { kind: "corners", label: "Load", unit: "kN", get: corners.map((c) => () => car.get(`${c}_fz`) / 1000), min: 0, max: setup.load, digits: 1 },
          { kind: "corners", label: "Travel", unit: "mm", get: corners.map((c) => () => car.get(`${c}_travel`) * 1000), min: -setup.droop, max: setup.bump, digits: 0 },
        ],
      },
      {
        title: "Drive",
        items: [
          { kind: "gauge", label: "Rear motor", unit: "rpm", get: () => car.get("motor_r_rpm"), min: 0, max: setup.motor, zones: [[setup.motor * 0.92, setup.motor, RED]], digits: 0 },
          { kind: "gauge", label: "Battery power", unit: "kW", get: () => car.get("battery_w") / 1000, min: -setup.kw, max: setup.kw, zones: [[-setup.kw, 0, GREEN]], digits: 0 },
          { kind: "bar", label: "Rear torque", unit: "N m", get: () => car.get("motor_r_torque"), min: -setup.torque, max: setup.torque, digits: 0, mark: () => car.get("motor_r_tlim") },
          ...(setup.clA > 0 ? [{ kind: "bar", label: "Downforce", unit: "N", get: () => 0.5 * RHO * car.tuning.inUse("Aero/ClA") * car.get("u") ** 2, min: 0, max: 6000, digits: 0 } as const] : []),
          { kind: "bar", label: "Charge", unit: "%", get: () => car.get("soc") * 100, min: 0, max: 100, digits: 0, zones: [[0, 12, RED]] },
          { kind: "value", label: "Bus", unit: "V", get: () => car.get("battery_v"), digits: 0 },
          { kind: "value", label: "Current", unit: "A", get: () => car.get("battery_a"), digits: 0 },
          { kind: "value", label: "Yaw rate", unit: "°/s", get: degrees(() => car.get("yaw_rate")), digits: 0 },
        ],
      },
    ],
  };
}
