/**
 * Short Final: the menus, the frame loop, and everything that turns the aeroplane's numbers into a
 * picture and a sound. Behind the title screen the aeroplane flies an approach by itself, and lands.
 */

import * as THREE from "three";
import { Rig, VIEWS } from "../engine/camera";
import { Burst, Trail } from "../engine/effects";
import { Controls, STANDARD_PAD } from "../engine/input";
import type { ScreenPoint } from "../engine/overlay";
import { Stage } from "../engine/stage";
import { SideBar } from "../engine/side";
import { Telemetry } from "../engine/telemetry";
import { Setup } from "../engine/tuning";
import { $, announce, BestTime, choices, clock } from "../engine/ui";
import { Island } from "../island/source";
import { buildGround, GateRings } from "../island/world";
import { aeroplaneShadow, buildAeroplane } from "./aircraft";
import { Cockpit, EYE, SEAT_TILT } from "./cockpit";
import { circuitGates, coastGates, coastStart, DOWNWIND_START, LINE_UP, RUNWAY_START, SHORT_FINAL_START } from "./course";
import { FieldLights, runwayNumbers } from "./field";
import { CALM, DATUM, Flight, FRAME, LANDING_HEADING, runwayCoordinates, type Start, surfaceAt, type Touchdown, type Wind } from "./flight";
import { cessnaPanel } from "./telemetry";
import { bakeChart, Hud, readings, warnings, type HudView } from "./hud";
import { type Line, markLanding } from "./landing";
import { Pilot } from "./pilot";
import { PistonVoice } from "./voice";
import starts from "./starts.json";

const q = new URLSearchParams(location.search);
const DEMO = q.has("demo");
const FINAL_START = starts[2] as Start;
const DEG = Math.PI / 180;
const wrap = (angle: number): number => ((angle + 540) % 360) - 180;
const clamp = THREE.MathUtils.clamp;

type Phase = "title" | "flying" | "paused" | "over";
type Mode = "circuit" | "spot" | "engine" | "coast";

const WINDS: Record<string, Wind> = {
  calm: CALM,
  breeze: { head: 3, cross: 2.5, gusts: 0.4 },
  cross: { head: 2.5, cross: 7, gusts: 1 },
  rough: { head: 5, cross: 9, gusts: 2 },
};

/** The stick feels soft round the middle and firm at the end: a key press is a nudge, not a jab. */
const soften = (v: number): number => v * (0.38 + 0.62 * v * v);

/** Best is the highest score, not the lowest time, so it is kept upside down in a BestTime. */
class BestScore {
  private readonly store: BestTime;
  constructor(key: string) {
    this.store = new BestTime(key);
  }
  get(): number | null {
    const value = this.store.get();
    return value === null ? null : 1000 - value;
  }
  offer(score: number): boolean {
    return this.store.offer(1000 - score);
  }
}

async function main(): Promise<void> {
  const stage = await Stage.create({
    canvas: $<HTMLCanvasElement>("world"),
    land: new Island(Number(q.get("grid") ?? 2048)),
    tier: q.has("tier") ? Number(q.get("tier")) : undefined,
  });
  if (!stage) {
    $("loading").hidden = true;
    $("failed").hidden = false;
    return;
  }
  $("loading-text").textContent = "Checking the oil…";
  const { camera, field, near, pipeline, renderer, world } = stage;
  const ground = stage.ground;
  world.add(buildGround(field, stage.atmosphere.uniforms), runwayNumbers(stage.atmosphere.uniforms));

  const plane = buildAeroplane();
  const place = new THREE.Group();
  place.add(plane.root);
  near.add(place);
  const cockpit = new Cockpit();
  place.add(cockpit.group);
  const shadow = aeroplaneShadow();
  near.add(shadow);
  const rings = new GateRings();
  near.add(rings.group);
  const lights = new FieldLights(ground);
  near.add(lights.group);
  // Blue-grey rubber smoke off each main wheel at the moment of touchdown.
  const smoke = [new Trail(40, 0.3, new THREE.Color(0.5, 0.5, 0.52)), new Trail(40, 0.3, new THREE.Color(0.5, 0.5, 0.52))];
  const burst = new Burst();
  near.add(smoke[0].mesh, smoke[1].mesh, burst.points);

  // A low camera over the wheels: the ground rushing up is half of a landing.
  const rig = new Rig(camera, (x, z) => Math.max(ground(-z, x), 0) - 1.6, {
    eye: EYE,
    distance: 17,
    height: 2.3,
    keepLevel: 0.7,
    fov: [54, 60],
    fastSpeed: 90,
    cockpitFov: 78,
    flybyOffset: 30,
    flybyRange: 280,
  });
  const hud = new Hud($<HTMLCanvasElement>("hud"));
  stage.onResize = (width, height) => hud.resize(width, height, Math.min(devicePixelRatio, 2));
  stage.resize();
  const chart = bakeChart(field.heights, field.size);
  const sound = new PistonVoice();
  const controls = new Controls(
    {
      pull: ["ArrowDown", "KeyS"],
      push: ["ArrowUp", "KeyW"],
      left: ["ArrowLeft", "KeyA"],
      right: ["ArrowRight", "KeyD"],
      yawLeft: ["KeyQ", "KeyZ"],
      yawRight: ["KeyE", "KeyX"],
      throttleUp: ["PageUp", "Equal", "NumpadAdd"],
      throttleDown: ["PageDown", "Minus", "NumpadSubtract"],
    },
    STANDARD_PAD,
    { stick: 1.8, spring: 3.2, throttle: 0.42 },
  );

  const flight = await Flight.create(ground, RUNWAY_START);
  const side = new SideBar("cessna", (left, right) => hud.room(left, right));
  const telemetry = new Telemetry(side, cessnaPanel(flight));
  new Setup(side).use(flight.tuning, "Setup");
  const { run } = flight;
  const bests: Record<Mode, BestScore | BestTime> = {
    circuit: new BestScore("short-final-circuit"),
    spot: new BestScore("short-final-spot"),
    engine: new BestScore("short-final-engine"),
    coast: new BestTime("short-final-coast"),
  };
  run.onGate = (gate) => {
    if (phase === "flying") {
      sound.gate(gate.hit);
    }
  };

  // ---- Menus ---------------------------------------------------------------------------------
  let phase: Phase = "title";
  let mode: Mode = "circuit";
  let pilot = new Pilot("final");
  $<HTMLSelectElement>("time").value = "afternoon";
  $<HTMLSelectElement>("sky").value = "0.3";
  const showBest = (): void => {
    for (const name of ["circuit", "spot", "engine"] as const) {
      const record = bests[name].get();
      $(`best-${name}`).textContent = record === null ? "" : `Best ${record}.`;
    }
    const time = bests.coast.get();
    $("best-coast").textContent = time === null ? "" : `Best ${clock(time)}.`;
  };
  showBest();
  const setMode = choices<Mode>($("mode"), (value) => {
    mode = value;
  }, "circuit");

  const show = (next: Phase): void => {
    if (next === "flying" && phase !== "paused") {
      telemetry.reset();
    }
    phase = next;
    $("title").hidden = next !== "title";
    $("pause").hidden = next !== "paused";
    $("over").hidden = next !== "over";
    hud.clear();
    flight.paused = next === "paused";
    if (next === "title") {
      sound.stop();
    }
  };

  const fresh = (): void => {
    burst.clear();
    pipeline.flash = 0;
    smoke.forEach((trail) => trail.clear());
    rig.snap();
    crashedAt = -1;
    wasCrashed = false;
    settled = 0;
    drawnSink = 0;
    lastCard = null;
    cardUntil = 0;
    engineCut = false;
    wasOnGround = flight.get("on_ground") > 0.5;
    holdHeading = LANDING_HEADING;
    trimRate = 0;
  };

  const scripted = (): void => {
    pilot.fly(flight, flight.pacer.step);
    const gate = pilot.phase === "route" ? run.next() : undefined;
    if (gate) {
      pilot.route(flight, gate, ground);
    }
  };

  /** A flight from the start, with whatever the menu says. */
  const begin = (): void => {
    const wind = WINDS[$<HTMLSelectElement>("wind").value] ?? CALM;
    if (mode === "circuit") {
      flight.reset(RUNWAY_START, LINE_UP, circuitGates(ground));
    } else if (mode === "spot") {
      run.stop();
      flight.reset(SHORT_FINAL_START);
    } else if (mode === "engine") {
      run.stop();
      flight.reset(DOWNWIND_START);
    } else {
      const { start, values } = coastStart(ground);
      flight.reset(start, values, coastGates(ground));
    }
    flight.wind = wind;
    rings.show(run.gates);
    controls.setThrottle(flight.throttle);
    pilot = new Pilot(mode === "circuit" ? "roll" : mode === "coast" ? "route" : mode === "engine" ? "glide" : "final");
    fresh();
    show("flying");
  };

  /** Behind the title the aeroplane comes in from the bay on its own. */
  const attract = (): void => {
    run.stop();
    rings.show(run.gates);
    flight.reset(FINAL_START);
    flight.wind = CALM;
    pilot = new Pilot("final");
    rig.view = "chase";
    fresh();
  };

  const applySky = (): void => {
    void stage.setSky($<HTMLSelectElement>("time").value, Number($<HTMLSelectElement>("sky").value));
  };
  $("time").addEventListener("change", applySky);
  $("sky").addEventListener("change", applySky);

  $("fly").addEventListener("click", () => {
    sound.start();
    begin();
  });
  $("resume").addEventListener("click", () => show("flying"));
  const toMenu = (): void => {
    attract();
    show("title");
  };
  $("restart").addEventListener("click", begin);
  $("quit").addEventListener("click", toMenu);
  $("again").addEventListener("click", begin);
  $("over-quit").addEventListener("click", toMenu);

  const flapsBy = (step: number): void => {
    const next = clamp(flight.flaps + step, 0, 3);
    if (next !== flight.flaps) {
      flight.setFlaps(next);
      sound.flap();
    }
  };
  const nextView = (): void => {
    rig.view = VIEWS[(VIEWS.indexOf(rig.view) + 1) % VIEWS.length];
    lookYaw = 0;
    lookPitch = 0;
    rig.snap();
  };

  const brakeKeys = new Set<string>();
  addEventListener("keydown", (event) => {
    if (event.code === "KeyB" || event.code === "Space") {
      brakeKeys.add(event.code);
      event.preventDefault();
    }
    if (event.code === "Home" || event.code === "BracketLeft") {
      trimRate = -1;
    } else if (event.code === "End" || event.code === "BracketRight") {
      trimRate = 1;
    }
    if (event.repeat) {
      return;
    }
    if (phase === "flying" && (event.code === "KeyP" || event.code === "Escape")) {
      show("paused");
    } else if (phase === "paused" && (event.code === "KeyP" || event.code === "Escape")) {
      show("flying");
    } else if ((phase === "flying" || phase === "over") && event.code === "KeyR") {
      begin();
    } else if (event.code === "KeyC") {
      nextView();
    } else if (event.code === "KeyM") {
      sound.muted = !sound.muted;
    } else if (phase === "flying" && event.code === "KeyF") {
      flapsBy(1);
    } else if (phase === "flying" && event.code === "KeyV") {
      flapsBy(-1);
    }
  });
  addEventListener("keyup", (event) => {
    brakeKeys.delete(event.code);
    if (["Home", "End", "BracketLeft", "BracketRight"].includes(event.code)) {
      trimRate = 0;
    }
  });
  addEventListener("blur", () => {
    brakeKeys.clear();
    trimRate = 0;
  });
  document.addEventListener("visibilitychange", () => {
    if (document.hidden && phase === "flying") {
      show("paused");
    }
  });
  const canvas = renderer.domElement;
  let lookYaw = 0;
  let lookPitch = 0;
  canvas.addEventListener("pointerdown", (event) => {
    rig.dragging = true;
    canvas.setPointerCapture(event.pointerId);
  });
  canvas.addEventListener("pointerup", () => {
    rig.dragging = false;
  });
  canvas.addEventListener("pointermove", (event) => {
    if (!rig.dragging) {
      return;
    }
    if (rig.view === "cockpit") {
      lookYaw = clamp(lookYaw - event.movementX * 0.005, -2.4, 2.4);
      lookPitch = clamp(lookPitch - event.movementY * 0.005, -0.8, 1);
    } else {
      rig.azimuth -= event.movementX * 0.006;
      rig.elevation = clamp(rig.elevation - event.movementY * 0.006, -1.3, 1.3);
    }
  });
  canvas.addEventListener("wheel", (event) => {
    rig.distance = clamp(rig.distance * Math.exp(event.deltaY * 0.0009), 9, 70);
  }, { passive: true });

  // A pad has no keys for levers, so its buttons get read here: triggers for power, bumpers for flaps.
  const padWas: boolean[] = [];
  const padEdge = (pad: Gamepad, button: number): boolean => {
    const down = pad.buttons[button]?.pressed ?? false;
    const edge = down && !padWas[button];
    padWas[button] = down;
    return edge;
  };
  const gamepad = (dt: number): number => {
    const pad = navigator.getGamepads?.().find((p) => p);
    if (!pad) {
      return 0;
    }
    const up = pad.buttons[7]?.value ?? 0;
    const down = pad.buttons[6]?.value ?? 0;
    if (up > 0.05 || down > 0.05) {
      controls.setThrottle(clamp(controls.value.throttle + (up - down) * 0.5 * dt, 0, 1));
    }
    if (padEdge(pad, 5)) {
      flapsBy(1);
    }
    if (padEdge(pad, 4)) {
      flapsBy(-1);
    }
    if (padEdge(pad, 3)) {
      nextView();
    }
    if (padEdge(pad, 9)) {
      show(phase === "flying" ? "paused" : "flying");
    }
    if (pad.buttons[12]?.pressed) {
      flight.trim -= 0.25 * dt;
    }
    if (pad.buttons[13]?.pressed) {
      flight.trim += 0.25 * dt;
    }
    return pad.buttons[0]?.value ?? 0;
  };

  // ---- The frame -----------------------------------------------------------------------------
  const position = new THREE.Vector3();
  const quaternion = new THREE.Quaternion();
  const before = new THREE.Quaternion();
  const after = new THREE.Quaternion();
  const tip = new THREE.Vector3();
  const projected = new THREE.Vector3();
  const pilotEye = new THREE.Vector3();
  const look = new THREE.Quaternion();
  const lookEuler = new THREE.Euler();
  const hingeY = new THREE.Vector3(0, 1, 0);
  const rudderAxis = new THREE.Vector3(-0.074, 0, 0.997).normalize();
  const hingeZ = new THREE.Vector3(0, 0, 1);
  const h = FRAME.heading * DEG;
  const frameTurn = new THREE.Quaternion().setFromRotationMatrix(
    new THREE.Matrix4().makeBasis(
      new THREE.Vector3(Math.sin(h), 0, -Math.cos(h)),
      new THREE.Vector3(-Math.cos(h), 0, -Math.sin(h)),
      new THREE.Vector3(0, 1, 0),
    ),
  );
  let crashedAt = -1;
  let wasCrashed = false;
  let wasOnGround = true;
  let last = performance.now();
  let time = 0;
  let settled = 0;
  let drawnSink = 0;
  let lastCard: Touchdown | null = null;
  let cardUntil = 0;
  let engineCut = false;
  let holdHeading = LANDING_HEADING;
  let trimRate = 0;
  let smokeUntil = 0;

  const screen = (point: THREE.Vector3): ScreenPoint => {
    projected.copy(point).project(camera);
    const ahead = projected.z < 1;
    return { x: 0.5 + projected.x * (ahead ? 0.5 : -0.5), y: 0.5 - projected.y * (ahead ? 0.5 : -0.5), ahead };
  };

  const finish = (title: string, text: string, total: string, lines: Line[]): void => {
    $("over-title").textContent = title;
    $("over-text").textContent = text;
    $("over-score").textContent = total;
    const table = $("over-lines");
    table.textContent = "";
    for (const line of lines) {
      const row = document.createElement("div");
      row.className = "line";
      const bar = line.of > 0 ? `<i style="width:${Math.round((100 * line.points) / line.of)}%"></i>` : "";
      row.innerHTML = `<span>${line.label}</span><small>${line.detail}</small><b>${line.points > 0 && line.of === 0 ? "+" : ""}${line.points}${line.of > 0 ? ` / ${line.of}` : ""}</b><u>${bar}</u>`;
      table.append(row);
    }
    show("over");
  };

  const finishLanding = (): void => {
    const sheet = markLanding(flight.touchdowns, flight.stoppedAt, run.active ? run.gates.filter((g) => !g.hit).length : 0, flight.scraped);
    const best = bests[mode] as BestScore;
    const record = best.offer(sheet.total);
    showBest();
    if (sheet.total >= 78) {
      sound.fanfare();
    }
    finish(sheet.verdict, record ? "A new best." : `Best ${best.get()}.`, String(sheet.total), sheet.lines);
  };

  /** What the instructor would say now, if the player has left the instructor on. */
  const coach = (): string => {
    if (!$<HTMLInputElement>("instructor").checked) {
      return "";
    }
    const kias = flight.get("kias");
    const feet = flight.get("agl_ft");
    const onGround = flight.get("on_ground") > 0.5;
    if (engineCut && !onGround && flight.get("rpm") < 1200) {
      return feet > 120 ? "Engine out: hold 70 kt, keep the runway close" : "Flaps for the drop, then ease it down";
    }
    if (mode === "circuit" && flight.touchdowns.length === 0) {
      if (onGround && flight.throttle < 0.9 && kias < 30) {
        return "Full throttle: hold Page Up";
      }
      if (onGround && kias > 48) {
        return "Rotate: ease back";
      }
      if (onGround) {
        return "Keep it straight";
      }
      const next = run.next();
      const done = run.gates.indexOf(next as (typeof run.gates)[number]);
      if (feet > 300 && flight.flaps > 0 && done < 3) {
        return "Flaps up: V";
      }
      if (done === 3) {
        return "Downwind: throttle back to hold level";
      }
      if (done === 4) {
        return "Throttle back, flaps down: F";
      }
      if (done >= 5 && flight.flaps < 3 && flight.get("alt_ft") > 120) {
        return "Full flap on final: F";
      }
    }
    if (flight.touchdowns.length > 0) {
      return flight.get("gs_mps") > 2 ? "Idle, hold the brakes: B" : "";
    }
    if ((mode === "spot" || mode === "engine" || (mode === "circuit" && run.done !== null)) && !onGround) {
      if (feet < 14) {
        return "Flare: throttle idle, ease back and hold";
      }
      if (feet < 40) {
        return "Throttle idle";
      }
    }
    return "";
  };

  const frame = (now: number): void => {
    const interval = now - last;
    last = now;
    const dt = Math.min(interval / 1000, 0.1);
    stage.judge(interval);
    requestAnimationFrame(frame);

    const autopilot = phase === "title" || DEMO;
    flight.autopilot = autopilot ? scripted : null;
    if (phase === "flying" && !autopilot && !flight.crashed) {
      controls.update(dt);
      const v = controls.value;
      const padBrake = gamepad(dt);
      const pedalsIn = soften(v.yaw);
      const turn = flight.get("turn_dps");
      let pedals = pedalsIn;
      const assisted = $<HTMLInputElement>("auto-rudder").checked;
      if (assisted) {
        if (flight.get("on_ground") > 0.5) {
          // On the runway the pedals steer: with them centred, the nose stays where it was left.
          if (Math.abs(pedalsIn) > 0.03) {
            holdHeading = flight.heading();
          } else {
            pedals = clamp(0.06 * wrap(holdHeading - flight.heading()) - 0.04 * turn, -0.7, 0.7);
          }
        } else {
          // A touchdown close to the runway's heading straightens up along it.
          holdHeading = Math.abs(wrap(flight.heading() - LANDING_HEADING)) < 10 ? LANDING_HEADING : flight.heading();
          pedals = pedalsIn - 0.01 * turn;
        }
      }
      // The FMU's yoke is a direct elevator: its bite grows with the square of the speed, and at
      // full travel it would stand the aeroplane on its tail. This is what the force in a real
      // yoke does for a pilot: the same pull gives about the same pitch rate at any speed.
      const kias = Math.max(flight.get("kias"), 28);
      const pitchFeel = (28 / kias) ** 2;
      const rollFeel = Math.min((44 / kias) ** 2, 1);
      let roll = soften(v.roll) * rollFeel;
      if (assisted && flight.get("on_ground") < 0.5 && Math.abs(v.roll) < 0.02 && Math.abs(flight.get("phi_deg")) < 12) {
        // Hands off, shallow banks ease back to level: the model rolls off slowly on its own.
        roll = clamp(-0.018 * flight.get("phi_deg"), -0.1, 0.1);
      }
      flight.setControls(soften(v.pitch) * pitchFeel, roll, pedals, v.throttle);
      if (assisted && Math.abs(v.pitch) > 0.02) {
        // While the nose is being held, the trim creeps to the speed it is held at: from the desktop
        // app's trims, 0.0072 of a unit per knot either side of 76, at any flap setting.
        const want = clamp(0.0072 * (76 - flight.get("kias")), -0.3, 0.3);
        flight.trim += clamp(want - flight.trim, -0.09 * dt, 0.09 * dt);
      }
      flight.setBrakes(Math.max(brakeKeys.size > 0 ? 1 : 0, padBrake));
      flight.trim += trimRate * 0.25 * dt;
    }
    if (phase !== "paused") {
      flight.advance(dt);
    }
    if (phase !== "paused") {
      time += dt;
    }
    if (mode === "engine" && phase === "flying" && !engineCut && flight.time > 3) {
      engineCut = true;
      flight.cutEngine();
      sound.cough();
    }

    const i = flight.previous;
    flight.drawnPoint(tip);
    position.copy(tip);
    before.set(i[4], i[5], i[6], i[3]).normalize().premultiply(frameTurn);
    after.set(flight.get("q_x"), flight.get("q_y"), flight.get("q_z"), flight.get("q_w")).normalize().premultiply(frameTurn);
    quaternion.copy(before).slerp(after, flight.pacer.fraction);

    // Off the paving the land is a little below the FMU's plane: let the wheels down onto it.
    const north = -position.z;
    const east = position.x;
    const surface = surfaceAt(north, east);
    const wantSink = surface === "grass" && flight.get("alt_m") < 5 ? DATUM - Math.max(ground(north, east), 0) : 0;
    drawnSink += (wantSink - drawnSink) * Math.min(1, dt * 5);
    position.y -= drawnSink;

    place.position.copy(position);
    place.quaternion.copy(quaternion);
    plane.aileronLeft.quaternion.setFromAxisAngle(hingeY, -flight.between("aileron_deg") * DEG);
    plane.aileronRight.quaternion.setFromAxisAngle(hingeY, flight.between("aileron_deg") * DEG);
    plane.flapLeft.quaternion.setFromAxisAngle(hingeY, -flight.between("flap_deg") * DEG);
    plane.flapRight.quaternion.setFromAxisAngle(hingeY, -flight.between("flap_deg") * DEG);
    plane.elevator.quaternion.setFromAxisAngle(hingeY, -flight.between("elevator_deg") * DEG);
    plane.rudder.quaternion.setFromAxisAngle(rudderAxis, -flight.between("rudder_deg") * DEG);
    plane.noseWheel.quaternion.setFromAxisAngle(hingeZ, -flight.between("steer_rad"));
    const rpm = flight.get("rpm");
    const spinning = rpm > 420;
    plane.disc.visible = spinning && !flight.crashed;
    plane.discOpacity.value = THREE.MathUtils.smoothstep(rpm, 420, 1200);
    plane.discAngle.value += dt * 19;
    plane.propeller.children[1].visible = !spinning;
    plane.propeller.rotation.x = -flight.between("prop_angle");
    const rolling = flight.get("on_ground") > 0.5 ? flight.get("gs_mps") : 0;
    for (const wheel of plane.wheels) {
      wheel.rotation.y += (rolling * dt) / 0.22;
    }
    plane.strobe.visible = time % 1.3 < 0.06;
    plane.beacon.visible = time % 1 < 0.1;
    plane.root.visible = !flight.crashed;
    cockpit.group.visible = rig.view === "cockpit" && !flight.crashed;

    const height = position.y - Math.max(ground(north, east), 0);
    const sunDir = stage.atmosphere.uniforms.uSunDir.value;
    shadow.visible = height < 400 && !flight.crashed;
    if (shadow.visible) {
      const slide = Math.max(height, 0) / Math.max(sunDir.y, 0.2);
      const n = north + sunDir.z * slide;
      const e = east - sunDir.x * slide;
      const paved = surfaceAt(n, e);
      const floor = paved === "runway" || paved === "paved" ? DATUM : Math.max(ground(n, e), 0);
      shadow.position.set(e, floor + 0.12, -n);
      shadow.rotation.y = -flight.heading() * DEG;
      (shadow.material as THREE.MeshBasicMaterial).opacity = 0.6 * (1 - height / 400);
    }

    const onGround = flight.get("on_ground") > 0.5;
    if (onGround && !wasOnGround && phase !== "paused") {
      const touchdown = flight.touchdowns[flight.touchdowns.length - 1];
      if (touchdown) {
        lastCard = touchdown;
        cardUntil = time + 6;
        sound.chirp(touchdown.sink);
        rig.kick(0.3 + Math.min(touchdown.sink / 400, 1));
        smokeUntil = time + 0.55;
      }
    }
    wasOnGround = onGround;
    smoke.forEach((trail, side) => {
      tip.set(-0.32, side === 0 ? 1.09 : -1.09, -1.25).applyQuaternion(quaternion).add(position);
      trail.add(tip, time < smokeUntil ? 1.2 : 0);
    });

    if (flight.crashed && !wasCrashed) {
      const water = flight.crashReason === "Water";
      position.y = water ? 0.5 : position.y;
      burst.fire(position, water);
      sound.crash();
      rig.kick(6);
      crashedAt = time;
    }
    wasCrashed = flight.crashed;
    const stall = flight.get("alpha_deg") > 13 && !onGround ? THREE.MathUtils.smoothstep(flight.get("alpha_deg"), 13, 17) : 0;
    const buffet = stall * 0.28 + (onGround ? Math.min(rolling / 40, 1) * 0.05 : 0);
    if (flight.crashed) {
      rig.wreck(position, time - crashedAt, time);
    } else {
      rig.update(dt, position, quaternion, flight.get("ktas") * 0.5144, buffet, time);
      if (rig.view === "cockpit") {
        // After the rig: it holds the eye fixed, and the pilot's head is the player's.
        if (!rig.dragging) {
          const back = Math.exp(-dt / 0.6);
          lookYaw *= back;
          lookPitch *= back;
        }
        lookEuler.set(lookPitch - SEAT_TILT, lookYaw, 0, "YXZ");
        look.setFromEuler(lookEuler);
        camera.quaternion.multiply(look);
        camera.updateMatrixWorld();
      }
    }
    stage.shiftView(phase === "title" && innerWidth > 760);
    for (const trail of smoke) {
      trail.update(camera.position);
    }
    burst.update(dt, renderer.domElement.height);
    rings.update(run.gates, time);
    pilotEye.copy(EYE).applyQuaternion(quaternion).add(position);
    lights.update(pilotEye, flight.wind, time);

    if (phase === "flying" || phase === "over") {
      sound.update({
        rpm: flight.crashed ? 0 : rpm,
        power: flight.crashed ? 0 : clamp(flight.get("hp") / 160, 0, 1),
        airspeed: flight.crashed ? 0 : flight.get("ktas") * 0.5144,
        rolling: flight.crashed ? 0 : rolling,
        stall: flight.crashed ? 0 : warnings(flight).includes("STALL") ? 1 : 0,
        inside: rig.view === "cockpit" ? 1 : 0,
      });
    }
    const windText = windLine(flight.wind);
    if (rig.view === "cockpit") {
      cockpit.update(flight, readings(flight), run.next() ? bearing() : null, windText, time);
    }

    telemetry.update(dt, phase === "flying" && !flight.crashed ? "running" : phase === "title" ? "hidden" : "frozen");
    stage.render(position, time);

    if (phase === "flying") {
      const gate = run.next();
      let range = 0;
      let target: ScreenPoint | null = null;
      if (gate) {
        range = Math.hypot(gate.north - flight.north(), gate.east - flight.east(), gate.alt - flight.altitude());
        target = screen(tip.set(gate.east, gate.alt, -gate.north));
      }
      const view: HudView = {
        cockpit: rig.view === "cockpit",
        target,
        targetRange: range,
        bearing: gate ? bearing() : null,
        coach: coach(),
        clock: mode === "coast" ? clock(run.time) : "",
        touchdown: time < cardUntil ? lastCard : null,
        wind: windText,
      };
      if (flight.crashed) {
        hud.clear();
      } else {
        hud.draw(flight, view, chart, time);
        const warn = warnings(flight);
        if (warn.includes("PULL UP")) {
          sound.warning();
        }
      }
      if (flight.crashed && time - crashedAt > 2.4) {
        const words: Record<string, string> = {
          Water: "Into the sea.",
          Terrain: "Into the island.",
          "The gear folded": "That landing was harder than the gear could take.",
          "tail strike": "The tail hit the ground: too much back pressure, too early.",
          "propeller strike": "The propeller hit the ground: the nose came down first.",
          "left wing strike": "A wing tip caught the ground.",
          "right wing strike": "A wing tip caught the ground.",
        };
        finish("Crashed", words[flight.crashReason] ?? flight.crashReason, "", []);
      } else if (mode === "coast" && run.done !== null) {
        const score = run.score();
        const missed = run.missed();
        const record = (bests.coast as BestTime).offer(score);
        showBest();
        const penalty = missed ? `${missed} missed, ${missed * run.penalty} s added` : "Every ring clean";
        finish(record ? "New best time" : "Run complete", penalty, clock(score), []);
      } else if (flight.landing === "stopped") {
        settled += dt;
        if (settled > 0.7) {
          finishLanding();
        }
      }
    } else if (phase === "title" && (flight.crashed || flight.landing === "stopped")) {
      settled += dt;
      if (settled > 3) {
        attract();
      }
    }
  };

  function bearing(): number {
    const gate = run.next();
    return gate ? (Math.atan2(gate.east - flight.east(), gate.north - flight.north()) / DEG + 360) % 360 : 0;
  }

  function windLine(wind: Wind): string {
    const speed = Math.hypot(wind.head, wind.cross);
    if (speed < 0.1) {
      return "WIND CALM";
    }
    const from = (LANDING_HEADING + (Math.atan2(wind.cross, wind.head) / DEG) + 360) % 360;
    return `WIND ${String(Math.round(from / 10) * 10 % 360 || 360).padStart(3, "0")} / ${Math.round(speed * 1.944)} KT`;
  }

  $("loading").hidden = true;
  attract();
  show("title");
  requestAnimationFrame(frame);
  announce({
    telemetry,
    side,
    stage,
    flight,
    rig,
    begin,
    setMode,
    state: () => ({
      phase,
      mode,
      tier: stage.tier,
      view: rig.view,
      crashed: flight.crashed,
      crash: flight.crashReason,
      time: flight.time,
      gates: run.gates.length,
      passed: run.gates.filter((g) => g.passed).length,
      landing: flight.landing,
      touchdowns: flight.touchdowns.length,
      pilot: pilot.phase,
      ...runwayCoordinates(flight.north(), flight.east()),
    }),
  });
}

void main();
