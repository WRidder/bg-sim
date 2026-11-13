/**
 * Island Sortie: the menus, the frame loop, and everything that turns the F-16's numbers into a
 * picture and a sound. Behind the title screen the aircraft cruises round the island by itself.
 */

import * as THREE from "three";
import { JetVoice } from "../engine/audio";
import { Rig, VIEWS } from "../engine/camera";
import { Burst, Trail } from "../engine/effects";
import { attitude } from "../engine/frames";
import { ACE_BUTTONS, ACE_PAD, Controls, PAD, PadState } from "../engine/input";
import { coastOutline, type ScreenPoint } from "../engine/overlay";
import { Stage } from "../engine/stage";
import { SideBar } from "../engine/side";
import { Telemetry } from "../engine/telemetry";
import { Setup } from "../engine/tuning";
import { $, announce, BestScore, BestTime, choices, clock } from "../engine/ui";
import { CALM, lift, surfaceAt } from "../island/airfield";
import { FieldLights, runwayNumbers } from "../island/field";
import { type Line, type Marks, markLanding, writeLines } from "../island/landing";
import { Island } from "../island/source";
import { buildGround, GateRings, groundShadow } from "../island/world";
import { buildFighter } from "./aircraft";
import { flyOrbit, flyTo, type Orbit } from "./autopilot";
import { buildCockpit } from "./cockpit";
import { FINAL_START, Flight, gateCourse, ORIGIN, RUNWAY_START, type Start } from "./flight";
import { DroneManager, LockOn } from "./targets";
import { MissileSystem } from "./missiles";
import { DroneView, MissileView } from "./weapons";
import { SeekerView } from "./seeker";
import { F16_KNOBS, f16Panel } from "./telemetry";
import { Hud, type HudView, type Shot, warnings } from "./hud";
import starts from "./starts.json";

const q = new URLSearchParams(location.search);
const DEMO = q.has("demo");
/** Fast and fairly low, with the first gate straight ahead. */
const GATE_START = starts[2] as Start;
const STARTS: readonly Start[] = [...(starts as Start[]), RUNWAY_START, FINAL_START];
/** What a good landing is in a fast jet: firm, on the mains, with the nose well up. */
const JET: Marks = { sink: [100, 600], pitch: 9 };
const BOUND = { Water: "Into the sea.", Terrain: "Into the island." } as Record<string, string | undefined>;
/** Behind the title: round the island, clockwise, so the land stays on the free side of the menu. */
const TITLE_ORBIT: Orbit = { north: 6000, east: 1500, radius: 30000, alt: 1500 };

type Phase = "title" | "flying" | "paused" | "over";
type Mode = "free" | "gates" | "intercept";

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
  world.add(buildGround(field, stage.atmosphere.uniforms), runwayNumbers(stage.atmosphere.uniforms));
  const lights = new FieldLights(ground);
  near.add(lights.group);

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
  // Rubber smoke off each main wheel at the moment of touchdown.
  const smoke = [new Trail(40, 0.3, new THREE.Color(0.5, 0.5, 0.52)), new Trail(40, 0.3, new THREE.Color(0.5, 0.5, 0.52))];
  near.add(trails[0].mesh, trails[1].mesh, smoke[0].mesh, smoke[1].mesh, burst.points);

  const rig = new Rig(camera, (x, z) => Math.max(ground(-z, x), 0), { eye: new THREE.Vector3(3.15, 0, 1.08), distance: 27, height: 5.5 });
  const hud = new Hud($<HTMLCanvasElement>("hud"));
  stage.onResize = (width, height) => hud.resize(width, height, Math.min(devicePixelRatio, 2));
  stage.resize();
  const outline = coastOutline(field.heights, field.size, field.extent);
  const sound = new JetVoice();
  const pad = new PadState();
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
    ACE_PAD,
    undefined,
    pad,
    ACE_BUTTONS,
  );

  const flight = await Flight.create(ground, STARTS[0]);
  const targets = new DroneManager(ground);
  const lock = new LockOn();
  const weapons = await MissileSystem.create();
  const seeker = new SeekerView(renderer, pipeline, $("seeker"), stage.world, stage.near);
  // The drones and rounds are built now and used again, so a launch or a kill builds nothing.
  const droneViews = new Map<number, DroneView>();
  const missileViews = new Map<number, MissileView>();
  const spareDrones = [new DroneView(near), new DroneView(near), new DroneView(near)];
  const spareMissiles = [new MissileView(near), new MissileView(near), new MissileView(near), new MissileView(near)];
  const side = new SideBar("f16", (left, right) => hud.room(left, right));
  const telemetry = new Telemetry(side, f16Panel(flight));
  new Setup(side).use(flight.tuning, "Aircraft setup", F16_KNOBS);
  const { run } = flight;
  const best = new BestTime("island-sortie-best");
  const bestLanding = new BestScore("island-sortie-landing");
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
  let mode: Mode = "free";
  const select = $<HTMLSelectElement>("start");
  for (const [i, start] of STARTS.entries()) {
    select.add(new Option(start.label, String(i)));
  }
  $<HTMLSelectElement>("time").value = "afternoon";
  $<HTMLSelectElement>("sky").value = "0.3";
  const showBest = (): void => {
    const record = best.get();
    $("best").textContent = record ? `Best ${clock(record)}.` : "";
  };
  showBest();
  const setMode = choices<Mode>($("mode"), (value) => {
    mode = value;
    $("start-row").hidden = value === "gates";
  }, "free");

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

  const switches = (): Record<string, number> => ({
    limiter: $<HTMLInputElement>("limiter").checked ? 1 : 0,
    yaw_damper: $<HTMLInputElement>("yaw-damper").checked ? 1 : 0,
  });

  const clearWeaponViews = (): void => {
    for (const view of droneViews.values()) {
      view.hide();
      spareDrones.push(view);
    }
    for (const view of missileViews.values()) {
      view.hide();
      spareMissiles.push(view);
    }
    droneViews.clear();
    missileViews.clear();
  };

  const fresh = (): void => {
    burst.clear();
    pipeline.flash = 0;
    trails.forEach((trail) => trail.clear());
    smoke.forEach((trail) => trail.clear());
    clearWeaponViews();
    fighter.stations.forEach((station) => (station.visible = true));
    rig.snap();
    crashedAt = -1;
    wasOnGround = flight.onGround;
    smokeUntil = -1;
  };

  /** A flight from the start, with whatever the menu says. */
  const begin = (): void => {
    const start = mode === "gates" ? GATE_START : STARTS[Number(select.value)];
    if (mode === "gates") {
      run.start(gateCourse(ground));
      rings.show(run.gates);
    } else {
      run.stop();
    }
    rings.group.visible = mode === "gates";
    flight.frame = { ...ORIGIN, heading: 0 };
    flight.reset(start, switches());
    flight.gusts.intensity = $<HTMLInputElement>("turbulence").checked ? 2.5 : 0;
    controls.setThrottle(start.thtl0);
    weapons.reset();
    lock.reset();
    if (mode === "intercept") {
      targets.reset(flight.north(), flight.east(), flight.altitude(), flight.heading());
    } else {
      targets.clear();
    }
    fresh();
    show("flying");
  };

  /** The start's heading is north, so the orbit begins on its west side, already on the circle. */
  const attract = (): void => {
    run.stop();
    rings.group.visible = false;
    flight.frame = { north: TITLE_ORBIT.north, east: TITLE_ORBIT.east - TITLE_ORBIT.radius, heading: 0 };
    flight.reset(GATE_START, {});
    flight.gusts.intensity = 0;
    rig.view = "chase";
    targets.clear();
    weapons.reset();
    lock.reset();
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

  /** The launch: the selected drone, the next free wingtip and its world launch frame. */
  const fireWeapon = (): void => {
    if (mode !== "intercept" || phase !== "flying") {
      return;
    }
    const state = lock.state();
    const target = targets.byId(state.selectedId);
    if (!state.locked || !target) {
      return;
    }
    const side = weapons.freeSide();
    if (side === null) {
      return;
    }
    const station = flight.stationWorld(side);
    const frame = { north: station.north, east: station.east, alt: station.alt, heading: flight.heading() };
    if (weapons.fire(side, frame, target, flight.get("tas_mps"))) {
      fighter.stations[side].visible = false;
      lock.consume();
    }
  };

  const nextView = (): void => {
    rig.view = VIEWS[(VIEWS.indexOf(rig.view) + 1) % VIEWS.length];
    rig.snap();
  };

  /**
   * The buttons of a gamepad, laid out as in Ace Combat 7: Circle (B) fires, Triangle (Y) takes the
   * next target, R3 changes the view, Options (Start) pauses. Cross (A) also answers a menu. The
   * gear is not in that game; it is on D-pad down.
   */
  const padButtons = (): void => {
    pad.update();
    if (!pad.connected) {
      return;
    }
    const start = pad.pressed(PAD.START);
    if (phase === "title" || phase === "over") {
      if (start || pad.pressed(PAD.A)) {
        sound.start();
        begin();
      }
      return;
    }
    if (phase === "paused") {
      if (start || pad.pressed(PAD.A)) {
        show("flying");
      }
      return;
    }
    if (start) {
      show("paused");
      return;
    }
    if (pad.pressed(PAD.B)) {
      fireWeapon();
    }
    if (pad.pressed(PAD.Y) && mode === "intercept") {
      lock.cycle(targets);
    }
    if (pad.pressed(PAD.R3)) {
      nextView();
    }
    if (pad.pressed(PAD.DOWN)) {
      flight.toggleGear();
    }
  };

  /** The right stick looks round the aircraft, and lets go like the mouse does. */
  const padLook = (dt: number): void => {
    const x = pad.axis(2);
    const y = pad.axis(3);
    if (x === 0 && y === 0) {
      return;
    }
    const follow = Math.min(1, dt * 10);
    rig.azimuth += (-x * 2.8 - rig.azimuth) * follow;
    rig.elevation += (THREE.MathUtils.clamp(-y * 1.1, -1.3, 1.3) - rig.elevation) * follow;
  };

  const brakeKeys = new Set<string>();
  addEventListener("keydown", (event) => {
    if (event.code === "KeyB" || event.code === "Space") {
      brakeKeys.add(event.code);
      event.preventDefault();
    }
    if (event.repeat) {
      return;
    }
    if (phase !== "title") {
      sound.start();   // a flight begun from the gamepad is silent until a key or a click allows sound
    }
    if (phase === "flying" && (event.code === "KeyP" || event.code === "Escape")) {
      show("paused");
    } else if (phase === "paused" && (event.code === "KeyP" || event.code === "Escape")) {
      show("flying");
    } else if ((phase === "flying" || phase === "over") && event.code === "KeyR") {
      begin();
    } else if (phase === "flying" && event.code === "KeyG") {
      flight.toggleGear();
    } else if (event.code === "KeyC") {
      nextView();
    } else if (event.code === "Tab" || event.code === "KeyN") {
      if (phase === "flying" && mode === "intercept") {
        event.preventDefault();
        lock.cycle(targets);
      }
    } else if (event.code === "KeyM" && event.shiftKey) {
      sound.muted = !sound.muted;
    } else if (event.code === "KeyM") {
      fireWeapon();
    }
  });
  addEventListener("keyup", (event) => {
    brakeKeys.delete(event.code);
  });
  addEventListener("blur", () => {
    brakeKeys.clear();
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
  const frameTurn = new THREE.Quaternion();
  const up = new THREE.Vector3(0, 1, 0);
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
  let wasOnGround = false;
  let smokeUntil = -1;

  const screen = (point: THREE.Vector3): ScreenPoint => {
    projected.copy(point).project(camera);
    const ahead = projected.z < 1;
    return { x: 0.5 + projected.x * (ahead ? 0.5 : -0.5), y: 0.5 - projected.y * (ahead ? 0.5 : -0.5), ahead };
  };

  const finish = (title: string, text: string, total = "", lines: Line[] = []): void => {
    $("over-title").textContent = title;
    $("over-text").textContent = text;
    $("over-score").textContent = total;
    writeLines($("over-lines"), lines);
    show("over");
  };

  const finishLanding = (): void => {
    const sheet = markLanding(flight.touchdowns, flight.stoppedAt, 0, flight.scraped, JET);
    const record = bestLanding.offer(sheet.total);
    finish(sheet.verdict, record ? "A new best." : `Best ${bestLanding.get()}.`, String(sheet.total), sheet.lines);
  };

  const frame = (now: number): void => {
    const interval = now - last;
    last = now;
    const dt = Math.min(interval / 1000, 0.1);
    stage.judge(interval);
    requestAnimationFrame(frame);
    padButtons();

    if (phase === "title") {
      flyOrbit(flight, TITLE_ORBIT, 190, ground);
    } else if (DEMO) {
      const gate = run.next();
      if (gate) {
        flyTo(flight, gate, 190, ground);
      }
    } else if (phase === "flying") {
      controls.update(dt);
      const v = controls.value;
      flight.setControls(v.pitch, v.roll, v.yaw, v.throttle);
      // The left trigger takes the throttle off, and on the ground it is the brakes as well.
      flight.setBrakes(brakeKeys.size > 0 ? 1 : pad.value(PAD.LT));
      padLook(dt);
    }
    if (phase !== "paused") {
      time += dt;
      flight.advance(dt);
      if (mode === "intercept" && phase === "flying" && !flight.crashed) {
        targets.step(dt, flight.north(), flight.east(), flight.altitude(), flight.heading());
        lock.update(dt, [flight.north(), flight.east(), flight.altitude()], flight.noseNed(), targets);
        weapons.advance(dt);
        fighter.stations[0].visible = weapons.slotFree(0);
        fighter.stations[1].visible = weapons.slotFree(1);
        for (const missile of weapons.live) {
          if (missile.justHit) {
            missile.justHit = false;
            const target = targets.byId(missile.targetId);
            if (target) {
              targets.kill(missile.targetId);
              burst.fire(tip.set(target.east, target.alt, -target.north));
            }
          }
        }
      }
    }

    const i = flight.previous;
    const [north, east] = flight.at(flight.between("north_m"), flight.between("east_m"));
    position.set(east, flight.between("alt_m") + lift(north, east), -north);
    attitude(i[3], i[4], i[5], i[6], before);
    attitude(flight.get("q_w"), flight.get("q_x"), flight.get("q_y"), flight.get("q_z"), after);
    quaternion.copy(before).slerp(after, flight.pacer.fraction).premultiply(frameTurn.setFromAxisAngle(up, -flight.frame.heading * degrees));

    place.position.copy(position);
    place.quaternion.copy(quaternion);
    fighter.stabilators.quaternion.setFromAxisAngle(stabAxis, -flight.between("stab_deg") * degrees);
    fighter.flapLeft.quaternion.setFromAxisAngle(flapLeftAxis, flight.between("ail_deg") * degrees);
    fighter.flapRight.quaternion.setFromAxisAngle(flapRightAxis, -flight.between("ail_deg") * degrees);
    fighter.rudder.quaternion.setFromAxisAngle(rudderAxis, -flight.between("rdr_deg") * degrees);
    fighter.gear.pose(flight.between("gear_pos"), flight.between("steer_rad"), flight.between("fn_nose"), flight.between("fn_left"), flight.between("fn_right"));
    const power = flight.between("power_pct");
    const burner = Math.max(0, (power - 50) / 50);
    fighter.flame.visible = burner > 0.01 && !flight.crashed;
    fighter.flamePower.value = burner;
    fighter.flameTime.value = time;
    fighter.root.visible = rig.view !== "cockpit" && !flight.crashed;
    cockpit.visible = rig.view === "cockpit" && !flight.crashed;
    (fighter.burnerGlow.material as THREE.MeshBasicMaterial).color.setRGB(0.5 + 4 * burner + power * 0.012, 0.22 + 2 * burner, 0.08 + burner);

    const height = position.y - flight.floor(north, east);
    const sunDir = stage.atmosphere.uniforms.uSunDir.value;
    shadow.visible = height < 900 && height > 0 && !flight.crashed;
    if (shadow.visible) {
      // Along the sun's ray to the ground, as far as a flat ground would put it.
      const slide = height / Math.max(sunDir.y, 0.2);
      const n = north + sunDir.z * slide;
      const e = east - sunDir.x * slide;
      const under = surfaceAt(n, e);
      shadow.position.set(e, flight.floor(n, e) + (under === "runway" || under === "paved" ? 0.12 : 2.5), -n);
      shadow.rotation.y = -flight.heading() * degrees;
      shadow.scale.setScalar(14);
      (shadow.material as THREE.MeshBasicMaterial).opacity = 0.55 * (1 - height / 900);
    }

    // Vapour off the wingtips when the wing works hard.
    const load = THREE.MathUtils.smoothstep(Math.abs(flight.get("nz_g")), 3.5, 7);
    trails.forEach((trail, side) => {
      tip.set(-2.3, side === 0 ? 4.7 : -4.7, 0.05).applyQuaternion(quaternion).add(position);
      trail.add(tip, flight.crashed ? 0 : load);
    });

    if (flight.onGround && !wasOnGround && phase !== "paused") {
      const touchdown = flight.touchdowns[flight.touchdowns.length - 1];
      if (touchdown) {
        rig.kick(0.4 + Math.min(touchdown.sink / 300, 1.2));
        smokeUntil = time + 0.6;
      }
    }
    wasOnGround = flight.onGround;
    smoke.forEach((trail, side) => {
      tip.set(-0.785, side === 0 ? 1.219 : -1.219, -1.6).applyQuaternion(quaternion).add(position);
      trail.add(tip, time < smokeUntil ? 1.2 : 0);
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
    for (const trail of [...trails, ...smoke]) {
      trail.update(camera.position);
    }
    lights.update(camera.position, CALM, time);
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

    if (mode === "intercept" && phase !== "title") {
      for (const drone of targets.drones) {
        let view = droneViews.get(drone.id);
        if (!drone.alive) {
          if (view) {
            view.hide();
            spareDrones.push(view);
            droneViews.delete(drone.id);
          }
          continue;
        }
        if (!view) {
          view = spareDrones.pop() ?? new DroneView(near);
          droneViews.set(drone.id, view);
        }
        view.update(drone);
      }
      for (let k = weapons.live.length - 1; k >= 0; k -= 1) {
        const missile = weapons.live[k];
        let view = missileViews.get(missile.id);
        if (!view) {
          view = spareMissiles.pop() ?? new MissileView(near);
          missileViews.set(missile.id, view);
        }
        // A spent round stays until its smoke has faded, then gives its mesh back.
        if (view.update(missile, camera.position, phase === "paused" ? 0 : dt)) {
          view.hide();
          spareMissiles.push(view);
          missileViews.delete(missile.id);
          weapons.retire(missile);
        }
      }
    }

    telemetry.update(dt, phase === "flying" && !flight.crashed ? "running" : phase === "title" ? "hidden" : "frozen");
    stage.render(position, time);
    const seekerMissile = mode === "intercept" ? weapons.newest() : null;
    seeker.render(seekerMissile);
    const seekerDrone = seekerMissile ? targets.byId(seekerMissile.targetId) : null;
    const seekerMark = seekerMissile && seekerDrone ? seeker.project(seekerDrone) : null;

    if (phase === "flying") {
      const gate = run.next();
      const selected = targets.byId(lock.selectedId);
      const shots: Shot[] = [];
      if (mode === "intercept") {
        for (const missile of weapons.live) {
          if (missile.active && !missile.done) {
            const at = missile.worldPosition(tip);
            shots.push({ north: -at.z, east: at.x, onScreen: screen(at), timeToGo: missile.timeToGo, tracking: missile.tracking || missile.time < 0.6 });
          }
        }
      }
      const view: HudView = {
        cockpit: rig.view === "cockpit",
        fov: camera.fov,
        gateOnScreen: gate ? screen(tip.set(gate.east, gate.alt, -gate.north)) : null,
        velocityOnScreen: screen(tip.copy(position).addScaledVector(velocity, 3)),
        targetOnScreen: selected ? screen(tip.set(selected.east, selected.alt, -selected.north)) : null,
        targetRange: lock.rangeM,
        lock: mode === "intercept" ? lock.state() : null,
        contacts: mode === "intercept" ? targets.contacts(lock.selectedId, lock.locked) : [],
        seeker: seekerMissile !== null,
        seekerMark,
        reload: weapons.reloading ? weapons.reloadLeft : null,
        shots,
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
        finish("Crashed", `${BOUND[flight.crashReason] ?? `${flight.crashReason}.`}${stops}`);
      } else if (flight.landing === "stopped" && !run.active) {
        finishLanding();
      } else if (run.done !== null) {
        const score = run.score();
        const missed = run.missed();
        const record = best.offer(score);
        showBest();
        const penalty = missed ? ` with ${missed} missed (${missed * run.penalty} s added)` : ", every gate clean";
        finish(record ? "New best time" : "Run complete", `${clock(score)}${penalty}.`);
      }
    } else if (phase === "title" && flight.crashed) {
      attract();
    }
  };

  // Every shader the sortie can need is built behind the loading screen: the rounds, the drones
  // and the fireball are not drawn until they are used, and would stop the frame that needs them.
  await stage.warm();
  seeker.prepare(camera);
  sound.prepare();
  $("loading").hidden = true;
  attract();
  show("title");
  requestAnimationFrame(frame);
  announce({
    telemetry,
    side,
    flight,
    rig,
    stage,
    fighter,
    begin,
    setMode,
    state: () => ({ phase, tier: stage.tier, view: rig.view, crashed: flight.crashed, time: flight.time, gates: run.gates.length,
                    mode, drones: targets.alive().length, lock: lock.state(), missiles: weapons.free }),
  });
}

void main();
