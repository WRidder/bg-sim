/**
 * Island Sortie: the menus, the frame loop, and everything that turns the F-16's numbers into a
 * picture and a sound. Behind the title screen the aircraft flies the gate run by itself, so the
 * menu is already the game.
 */

import * as THREE from "three";
import { JetVoice } from "../engine/audio";
import { Rig, VIEWS } from "../engine/camera";
import { Burst, Trail } from "../engine/effects";
import { attitude } from "../engine/frames";
import { Controls, STANDARD_PAD } from "../engine/input";
import { coastOutline, type ScreenPoint } from "../engine/overlay";
import { Stage } from "../engine/stage";
import { $, announce, BestTime, choices, clock } from "../engine/ui";
import { Island } from "../island/source";
import { buildGround, GateRings, groundShadow } from "../island/world";
import { buildFighter } from "./aircraft";
import { flyTo } from "./autopilot";
import { buildCockpit } from "./cockpit";
import { Flight, gateCourse, type Start } from "./flight";
import { Hud, type HudView, warnings } from "./hud";
import starts from "./starts.json";

const q = new URLSearchParams(location.search);
const DEMO = q.has("demo");
/** Fast and fairly low, with the first gate straight ahead. */
const GATE_START = starts[2] as Start;

type Phase = "title" | "flying" | "paused" | "over";

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
  $("loading-text").textContent = "Fuelling the aircraft…";
  const { camera, field, near, pipeline, renderer, world } = stage;
  const ground = stage.ground;
  world.add(buildGround(field, stage.atmosphere.uniforms));

  const fighter = buildFighter();
  const place = new THREE.Group();
  place.add(fighter.root);
  near.add(place);
  const cockpit = buildCockpit();
  place.add(cockpit);
  const shadow = groundShadow();
  near.add(shadow);
  const rings = new GateRings();
  near.add(rings.group);
  const trails = [new Trail(), new Trail()];
  const burst = new Burst();
  near.add(trails[0].mesh, trails[1].mesh, burst.points);

  const rig = new Rig(camera, (x, z) => Math.max(ground(-z, x), 0), { eye: new THREE.Vector3(3.15, 0, 1.08), distance: 27, height: 5.5 });
  const hud = new Hud($<HTMLCanvasElement>("hud"));
  stage.onResize = (width, height) => hud.resize(width, height, Math.min(devicePixelRatio, 2));
  stage.resize();
  const outline = coastOutline(field.heights, field.size, field.extent);
  const sound = new JetVoice();
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
  );

  const flight = await Flight.create(ground, starts[0] as Start);
  const { run } = flight;
  const best = new BestTime("island-sortie-best");
  run.onGate = (gate) => {
    if (phase === "flying") {
      sound.gate(gate.hit);
      if (gate.hit) {
        rig.kick(0.5);
      }
    }
  };

  // ---- Menus ---------------------------------------------------------------------------------
  let phase: Phase = "title";
  let mode: "free" | "gates" = "free";
  const select = $<HTMLSelectElement>("start");
  for (const [i, start] of starts.entries()) {
    select.add(new Option(start.label, String(i)));
  }
  $<HTMLSelectElement>("time").value = "afternoon";
  $<HTMLSelectElement>("sky").value = "0.3";
  const showBest = (): void => {
    const record = best.get();
    $("best").textContent = record ? `Best ${clock(record)}.` : "";
  };
  showBest();
  const setMode = choices<"free" | "gates">($("mode"), (value) => {
    mode = value;
    $("start-row").hidden = value === "gates";
  }, "free");

  const show = (next: Phase): void => {
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

  const switches = (): Record<string, number> => ({
    limiter: $<HTMLInputElement>("limiter").checked ? 1 : 0,
    yaw_damper: $<HTMLInputElement>("yaw-damper").checked ? 1 : 0,
  });

  const fresh = (): void => {
    burst.clear();
    pipeline.flash = 0;
    trails.forEach((trail) => trail.clear());
    rig.snap();
    crashedAt = -1;
  };

  /** A flight from the start, with whatever the menu says. */
  const begin = (): void => {
    const start = mode === "gates" ? GATE_START : (starts[Number(select.value)] as Start);
    if (mode === "gates") {
      run.start(gateCourse(ground));
      rings.show(run.gates);
    } else {
      run.stop();
    }
    rings.group.visible = mode === "gates";
    flight.reset(start, switches());
    flight.gusts.intensity = $<HTMLInputElement>("turbulence").checked ? 2.5 : 0;
    controls.setThrottle(start.thtl0);
    fresh();
    show("flying");
  };

  /** Behind the title the aircraft flies the gate run with the gates out of sight. */
  const attract = (): void => {
    run.start(gateCourse(ground));
    rings.group.visible = false;
    flight.reset(GATE_START, {});
    flight.gusts.intensity = 0;
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

  addEventListener("keydown", (event) => {
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
      rig.view = VIEWS[(VIEWS.indexOf(rig.view) + 1) % VIEWS.length];
      rig.snap();
    } else if (event.code === "KeyM") {
      sound.muted = !sound.muted;
    }
  });
  document.addEventListener("visibilitychange", () => {
    if (document.hidden && phase === "flying") {
      show("paused");
    }
  });
  const canvas = renderer.domElement;
  canvas.addEventListener("pointerdown", (event) => {
    rig.dragging = true;
    canvas.setPointerCapture(event.pointerId);
  });
  canvas.addEventListener("pointerup", () => {
    rig.dragging = false;
  });
  canvas.addEventListener("pointermove", (event) => {
    if (rig.dragging) {
      rig.azimuth -= event.movementX * 0.006;
      rig.elevation = THREE.MathUtils.clamp(rig.elevation - event.movementY * 0.006, -1.3, 1.3);
    }
  });
  canvas.addEventListener("wheel", (event) => {
    rig.distance = THREE.MathUtils.clamp(rig.distance * Math.exp(event.deltaY * 0.0009), 14, 120);
  }, { passive: true });

  // ---- The frame -----------------------------------------------------------------------------
  const position = new THREE.Vector3();
  const quaternion = new THREE.Quaternion();
  const before = new THREE.Quaternion();
  const after = new THREE.Quaternion();
  const tip = new THREE.Vector3();
  const velocity = new THREE.Vector3();
  const projected = new THREE.Vector3();
  const stabAxis = new THREE.Vector3(0, 1, 0);
  const flapLeftAxis = new THREE.Vector3(0.153, 0.988, 0).normalize();
  const flapRightAxis = new THREE.Vector3(-0.153, 0.988, 0).normalize();
  const rudderAxis = new THREE.Vector3(-0.0797, 0, 0.9968).normalize();
  const degrees = Math.PI / 180;
  let crashedAt = -1;
  let last = performance.now();
  let time = 0;
  let wasCrashed = false;

  const screen = (point: THREE.Vector3): ScreenPoint => {
    projected.copy(point).project(camera);
    const ahead = projected.z < 1;
    return { x: 0.5 + projected.x * (ahead ? 0.5 : -0.5), y: 0.5 - projected.y * (ahead ? 0.5 : -0.5), ahead };
  };

  const finish = (title: string, text: string): void => {
    $("over-title").textContent = title;
    $("over-text").textContent = text;
    show("over");
  };

  const frame = (now: number): void => {
    const interval = now - last;
    last = now;
    const dt = Math.min(interval / 1000, 0.1);
    stage.judge(interval);
    requestAnimationFrame(frame);

    if (phase === "title" || DEMO) {
      const gate = run.next();
      if (gate) {
        flyTo(flight, gate, 190, ground);
      }
    } else if (phase === "flying") {
      controls.update(dt);
      const v = controls.value;
      flight.setControls(v.pitch, v.roll, v.yaw, v.throttle);
    }
    if (phase !== "paused") {
      time += dt;
      flight.advance(dt);
    }

    const i = flight.previous;
    const north = flight.between("north_m") + flight.north() - flight.get("north_m");
    const east = flight.between("east_m") + flight.east() - flight.get("east_m");
    position.set(east, flight.between("alt_m"), -north);
    attitude(i[3], i[4], i[5], i[6], before);
    attitude(flight.get("q_w"), flight.get("q_x"), flight.get("q_y"), flight.get("q_z"), after);
    quaternion.copy(before).slerp(after, flight.pacer.fraction);

    place.position.copy(position);
    place.quaternion.copy(quaternion);
    fighter.stabilators.quaternion.setFromAxisAngle(stabAxis, -flight.between("stab_deg") * degrees);
    fighter.flapLeft.quaternion.setFromAxisAngle(flapLeftAxis, flight.between("ail_deg") * degrees);
    fighter.flapRight.quaternion.setFromAxisAngle(flapRightAxis, -flight.between("ail_deg") * degrees);
    fighter.rudder.quaternion.setFromAxisAngle(rudderAxis, -flight.between("rdr_deg") * degrees);
    const power = flight.between("power_pct");
    const burner = Math.max(0, (power - 50) / 50);
    fighter.flame.visible = burner > 0.01 && !flight.crashed;
    fighter.flamePower.value = burner;
    fighter.flameTime.value = time;
    fighter.root.visible = rig.view !== "cockpit" && !flight.crashed;
    cockpit.visible = rig.view === "cockpit" && !flight.crashed;
    (fighter.burnerGlow.material as THREE.MeshBasicMaterial).color.setRGB(0.5 + 4 * burner + power * 0.012, 0.22 + 2 * burner, 0.08 + burner);

    const height = position.y - Math.max(ground(north, east), 0);
    const sunDir = stage.atmosphere.uniforms.uSunDir.value;
    shadow.visible = height < 900 && height > 0 && !flight.crashed;
    if (shadow.visible) {
      // Along the sun's ray to the ground, as far as a flat ground would put it.
      const slide = height / Math.max(sunDir.y, 0.2);
      const n = north + sunDir.z * slide;
      const e = east - sunDir.x * slide;
      shadow.position.set(e, Math.max(ground(n, e), 0) + 2.5, -n);
      shadow.rotation.y = -flight.get("psi_deg") * degrees;
      shadow.scale.setScalar(14);
      (shadow.material as THREE.MeshBasicMaterial).opacity = 0.55 * (1 - height / 900);
    }

    // Vapour off the wingtips when the wing works hard.
    const load = THREE.MathUtils.smoothstep(Math.abs(flight.get("nz_g")), 3.5, 7);
    trails.forEach((trail, side) => {
      tip.set(-2.3, side === 0 ? 4.7 : -4.7, 0.05).applyQuaternion(quaternion).add(position);
      trail.add(tip, flight.crashed ? 0 : load);
    });

    if (flight.crashed && !wasCrashed) {
      burst.fire(position, flight.crashReason === "Water");
      sound.crash();
      rig.kick(6);
      crashedAt = time;
    }
    wasCrashed = flight.crashed;
    const buffet = THREE.MathUtils.smoothstep(flight.get("alpha_deg"), 16, 26) * 0.5 + load * 0.2;
    velocity.set(flight.get("u_mps"), -flight.get("v_mps"), -flight.get("w_mps")).applyQuaternion(quaternion);
    if (flight.crashed) {
      rig.wreck(position, time - crashedAt, time);
    } else {
      rig.update(dt, position, quaternion, flight.get("tas_mps"), buffet, time);
    }
    stage.shiftView(phase === "title" && innerWidth > 760);
    for (const trail of trails) {
      trail.update(camera.position);
    }
    burst.update(dt, renderer.domElement.height);
    rings.update(run.gates, time);

    if (phase === "flying" || phase === "over") {
      sound.update({
        power: flight.crashed ? 0 : power / 100,
        burner: flight.crashed ? 0 : burner,
        airspeed: flight.crashed ? 0 : flight.get("tas_mps"),
        buffet: flight.crashed ? 0 : buffet,
        inside: rig.view === "cockpit" ? 1 : 0,
      });
    }

    stage.render(position, time);

    if (phase === "flying") {
      const gate = run.next();
      const view: HudView = {
        cockpit: rig.view === "cockpit",
        fov: camera.fov,
        gateOnScreen: gate ? screen(tip.set(gate.east, gate.alt, -gate.north)) : null,
        velocityOnScreen: screen(tip.copy(position).addScaledVector(velocity, 3)),
      };
      if (flight.crashed) {
        hud.clear();
      } else {
        hud.draw(flight, view, outline, time);
        if (warnings(flight).some((w) => w === "PULL UP" || w === "DEPARTED")) {
          sound.warning();
        }
      }
      if (flight.crashed && time - crashedAt > 1.8) {
        const stops = run.active ? " The run stops here." : "";
        finish("Crashed", `${flight.crashReason === "Water" ? "Into the sea." : "Into the island."}${stops}`);
      } else if (run.done !== null) {
        const score = run.score();
        const missed = run.missed();
        const record = best.offer(score);
        showBest();
        const penalty = missed ? ` with ${missed} missed (${missed * run.penalty} s added)` : ", every gate clean";
        finish(record ? "New best time" : "Run complete", `${clock(score)}${penalty}.`);
      }
    } else if (phase === "title" && (flight.crashed || run.done !== null)) {
      attract();
    }
  };

  $("loading").hidden = true;
  attract();
  show("title");
  requestAnimationFrame(frame);
  announce({
    flight,
    rig,
    begin,
    setMode,
    state: () => ({ phase, tier: stage.tier, view: rig.view, crashed: flight.crashed, time: flight.time, gates: run.gates.length }),
  });
}

void main();
