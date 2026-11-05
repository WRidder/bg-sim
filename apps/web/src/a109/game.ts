/**
 * Island Lift: the menus, the frame loop, and everything that turns the helicopter's numbers into a
 * picture and a sound. Behind the title screen it flies the island round by itself, landing on every
 * deck, so the menu is already the game.
 */

import * as THREE from "three";
import { Rig, VIEWS } from "../engine/camera";
import { Burst } from "../engine/effects";
import { attitude } from "../engine/frames";
import { coastOutline, type ScreenPoint } from "../engine/overlay";
import { Stage } from "../engine/stage";
import { SideBar } from "../engine/side";
import { Telemetry } from "../engine/telemetry";
import { Setup } from "../engine/tuning";
import { $, announce, BestTime, choices, clock } from "../engine/ui";
import { Island } from "../island/source";
import { buildGround } from "../island/world";
import { buildHelicopter, poseGear, poseRotor, spinRotors } from "./aircraft";
import { Cockpit, EYE } from "./cockpit";
import { Controls } from "./controls";
import { Downwash, type Wash } from "./downwash";
import { Flight, OMEGA, type Placing, ROTOR_RADIUS, type Start, TAIL_RATIO, WEIGHT } from "./flight";
import { a109Panel } from "./telemetry";
import { Hud, type HudView, warnings } from "./hud";
import { type Landing, Run } from "./mission";
import { furnish, layPads, MISSIONS, type Pad } from "./pads";
import { Assist, Autopilot } from "./pilot";
import { clearGround, Scenery, shadowTexture } from "./scenery";
import starts from "./starts.json";
import { Surface } from "./surface";
import { HeliVoice } from "./voice";

const q = new URLSearchParams(location.search);
const DEMO = q.has("demo");
const PARKED = starts[0] as Start;
const HOVER_START = starts[2] as Start;
/** The blades are drawn at a tenth of their speed: at the real one they would strobe. */
const SPIN = 0.1;
const TO_RAD = Math.PI / 180;

type Phase = "title" | "flying" | "paused" | "over";
type Aid = "assist" | "scas" | "bare";
type Mode = "round" | "town" | "free";

/** What each handling makes the keys mean, for the panel beside the menu. */
const KEY_TEXT: Record<Aid, { fore: string; side: string; lift: string; space: string }> = {
  assist: { fore: "Speed up, slow down", side: "Sidestep, or bank at speed", lift: "Climb, descend", space: "Brake to a hover" },
  scas: { fore: "Nose down, nose up", side: "Bank", lift: "Lever up, down", space: "Trim the stick here" },
  bare: { fore: "Cyclic forward, aft", side: "Cyclic left, right", lift: "Lever up, down", space: "Trim the stick here" },
};

/** The body-to-NED quaternion of the FMU's Euler angles, in degrees. */
function fromEuler(phi: number, theta: number, psi: number, into: THREE.Quaternion): THREE.Quaternion {
  const [cf, sf] = [Math.cos(phi * TO_RAD * 0.5), Math.sin(phi * TO_RAD * 0.5)];
  const [ct, st] = [Math.cos(theta * TO_RAD * 0.5), Math.sin(theta * TO_RAD * 0.5)];
  const [cp, sp] = [Math.cos(psi * TO_RAD * 0.5), Math.sin(psi * TO_RAD * 0.5)];
  return attitude(
    cf * ct * cp + sf * st * sp,
    sf * ct * cp - cf * st * sp,
    cf * st * cp + sf * ct * sp,
    cf * ct * sp - sf * st * cp,
    into,
  );
}

async function main(): Promise<void> {
  const stage = await Stage.create({
    canvas: $<HTMLCanvasElement>("world"),
    land: new Island(Number(q.get("grid") ?? 2048)),
    tier: q.has("tier") ? Number(q.get("tier")) : undefined,
    shadowReach: 20,
  });
  if (!stage) {
    $("loading").hidden = true;
    $("failed").hidden = false;
    return;
  }
  $("loading-text").textContent = "Spinning up the rotor…";
  const { camera, field, near, pipeline, renderer, world } = stage;
  const ground = stage.ground;
  const pads = layPads(ground);
  const surface = new Surface(ground);
  furnish(surface, pads);
  const scenery = new Scenery(pads, ground, stage.atmosphere.uniforms);
  const land = buildGround(field, stage.atmosphere.uniforms);
  scenery.plant(clearGround(land, surface, pads));
  world.add(land, scenery.world);
  near.add(scenery.near);

  const heli = buildHelicopter();
  const place = new THREE.Group();
  place.add(heli.root);
  near.add(place);
  const cockpit = new Cockpit();
  place.add(cockpit.group);
  const shadow = new THREE.Mesh(
    new THREE.PlaneGeometry(1, 1),
    new THREE.MeshBasicMaterial({ map: shadowTexture(), transparent: true, opacity: 0.55, depthWrite: false }),
  );
  shadow.geometry.rotateX(-Math.PI / 2);
  shadow.visible = false;
  near.add(shadow);
  const wash = new Downwash();
  const burst = new Burst();
  near.add(wash.group, burst.points);

  const rig = new Rig(camera, (x, z) => surface.at(-z, x), {
    eye: EYE,
    distance: 17,
    height: 3.8,
    keepLevel: 0,
    fov: [58, 64],
    fastSpeed: 90,
    cockpitFov: 74,
    flybyOffset: 26,
  });
  const hud = new Hud($<HTMLCanvasElement>("hud"));
  stage.onResize = (width, height) => hud.resize(width, height, Math.min(devicePixelRatio, 2));
  stage.resize();
  const outline = coastOutline(field.heights, field.size, field.extent);
  const sound = new HeliVoice();
  const controls = new Controls();

  const padOf = (id: string): Pad => pads.find((pad) => pad.id === id) as Pad;
  const onPad = (pad: Pad): Placing => ({ north: pad.north, east: pad.east, floor: pad.top, heading: pad.heading });
  const flight = await Flight.create(surface, PARKED, onPad(pads[0]));
  const side = new SideBar("a109", (left, right) => hud.room(left, right));
  const telemetry = new Telemetry(side, a109Panel(flight));
  new Setup(side).use(flight.tuning, "Setup");
  const assist = new Assist();
  const run = new Run();
  let pilot: Autopilot | null = null;

  const bests: Record<string, BestTime> = {};
  const bestOf = (mode: string, aid: Aid): BestTime => (bests[`${mode}-${aid}`] ??= new BestTime(`island-lift-best-${mode}-${aid}`));

  // ---- Menus ---------------------------------------------------------------------------------
  let phase: Phase = "title";
  let mode: Mode = "round";
  let aid: Aid = "assist";
  const select = $<HTMLSelectElement>("start");
  for (const [i, pad] of pads.entries()) {
    select.add(new Option(pad.name, String(i)));
  }
  select.add(new Option("In a hover over the airfield", "hover"));
  $<HTMLSelectElement>("time").value = "afternoon";
  $<HTMLSelectElement>("sky").value = "0.3";
  const showBest = (): void => {
    for (const { id } of MISSIONS) {
      const record = bestOf(id, aid).get();
      $(`best-${id}`).textContent = record ? `Best ${clock(record)}.` : "";
    }
  };
  const setMode = choices<Mode>($("mode"), (value) => {
    mode = value;
    $("start-row").hidden = value !== "free";
  }, "round");
  const applyAid = (): void => {
    aid = $<HTMLSelectElement>("aid").value as Aid;
    const text = KEY_TEXT[aid];
    $("key-fore").textContent = text.fore;
    $("key-side").textContent = text.side;
    $("key-lift").textContent = text.lift;
    $("key-space").textContent = text.space;
    showBest();
  };
  applyAid();
  $("aid").addEventListener("change", applyAid);

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
    wash.clear();
    pipeline.flash = 0;
    rig.snap();
    crashedAt = -1;
    heli.root.visible = true;
  };

  const setWind = (): void => {
    // The wind comes in from the south-west, across the runway and off the sea.
    const speed = Number($<HTMLSelectElement>("wind").value);
    flight.wind = { north: speed * 0.62, east: speed * 0.78 };
    flight.gusts.intensity = $<HTMLInputElement>("turbulence").checked ? 1.6 : 0;
  };

  const routeOf = (id: string): Pad[] => (MISSIONS.find((m) => m.id === id)?.pads ?? []).map(padOf);

  /** A flight from the start, with whatever the menu says. */
  const begin = (): void => {
    pilot = null;
    flight.pilot = aid === "assist" ? assist.fly : null;
    let route: Pad[] = [];
    if (mode !== "free") {
      route = routeOf(mode);
      flight.reset(PARKED, onPad(route[0]));
      run.start(route);
      scenery.setTarget(route[1]);
      hud.say(route[1].name, route[1].job, time, "#ffc34d");
    } else {
      run.stop();
      scenery.setTarget(null);
      if (select.value === "hover") {
        flight.reset(HOVER_START, { north: pads[0].north + 120, east: pads[0].east + 300, floor: pads[0].base + 1.15, heading: 72 });
      } else {
        flight.reset(PARKED, onPad(pads[Number(select.value)]));
      }
    }
    flight.scas = aid !== "bare";
    assist.reset(flight);
    controls.reset(flight.u[0]);
    setWind();
    fresh();
    show("flying");
  };

  /** Behind the title the helicopter flies the round with the markers out of sight. */
  const attract = (): void => {
    const route = routeOf("round");
    flight.pilot = null;
    flight.reset(PARKED, onPad(route[0]));
    flight.wind = { north: 0, east: 0 };
    flight.gusts.intensity = 0;
    flight.scas = true;
    pilot = new Autopilot(route, surface);
    pilot.begin(flight);
    flight.pilot = pilot.fly;
    run.start(route);
    scenery.setTarget(null);
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

  const nextView = (): void => {
    rig.view = VIEWS[(VIEWS.indexOf(rig.view) + 1) % VIEWS.length];
    rig.azimuth = 0;
    rig.elevation = 0;
    rig.snap();
  };
  const togglePause = (): void => {
    if (phase === "flying") {
      show("paused");
    } else if (phase === "paused") {
      show("flying");
    }
  };
  addEventListener("keydown", (event) => {
    if (event.repeat) {
      return;
    }
    if (event.code === "KeyP" || event.code === "Escape") {
      togglePause();
    } else if ((phase === "flying" || phase === "over") && event.code === "KeyR") {
      begin();
    } else if (event.code === "KeyC") {
      nextView();
    } else if (event.code === "KeyM") {
      sound.muted = !sound.muted;
    } else if (event.code === "KeyH" && phase === "flying" && aid !== "assist") {
      flight.scas = !flight.scas;
    } else if (event.code === "Space" && phase === "flying" && aid !== "assist") {
      controls.forceTrim();
    } else if (event.code === "Backspace" && phase === "flying") {
      controls.trimFore = 0;
      controls.trimSide = 0;
    }
  });
  controls.onButton = (button) => {
    if (button === 9) {
      togglePause();
    } else if (button === 5) {
      nextView();
    } else if (button === 3 && phase === "flying" && aid !== "assist") {
      controls.forceTrim();
    }
  };
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
    rig.distance = THREE.MathUtils.clamp(rig.distance * Math.exp(event.deltaY * 0.0009), 10, 90);
  }, { passive: true });

  // ---- Landings ------------------------------------------------------------------------------
  const finishRun = (): void => {
    const score = run.score();
    const record = bestOf(mode, aid).offer(score);
    showBest();
    const costs = run.landings.reduce((sum, landing) => sum + landing.penalty, 0);
    const line = costs ? `${clock(run.time)} flown, ${costs} s for the landings.` : `${clock(run.time)} flown, and not a landing to fault.`;
    finish(record ? "New best time" : "Round complete", `${clock(score)}. ${line}`, run.landings);
  };

  run.onLanding = (landing: Landing) => {
    if (pilot) {
      pilot.next(flight);
      if (pilot.done) {
        attract();
      }
      return;
    }
    sound.landed(landing.score);
    hud.say(`${landing.grade}  ${landing.score}`, `${landing.pad.name}: ${landing.sink.toFixed(1)} m/s down, ${landing.offset.toFixed(1)} m off the H`, time);
    if (run.done) {
      scenery.setTarget(null);
      finishRun();
    } else {
      const next = run.next as Pad;
      scenery.setTarget(next);
      setTimeout(() => {
        if (run.next === next && phase === "flying") {
          hud.say(next.name, next.job, time, "#ffc34d");
        }
      }, 2600);
    }
  };
  run.onTouch = (sink) => {
    if (!pilot && phase === "flying") {
      sound.touch(sink);
      if (sink > 1.6) {
        rig.kick(0.5);
      }
    }
  };

  // ---- The frame -----------------------------------------------------------------------------
  const position = new THREE.Vector3();
  const quaternion = new THREE.Quaternion();
  const before = new THREE.Quaternion();
  const after = new THREE.Quaternion();
  const level = new THREE.Quaternion();
  const look = new THREE.Quaternion();
  const lookEuler = new THREE.Euler();
  const tip = new THREE.Vector3();
  const velocity = new THREE.Vector3();
  const projected = new THREE.Vector3();
  const under = new THREE.Vector3();
  let crashedAt = -1;
  let last = performance.now();
  let time = 0;
  let wasCrashed = false;
  let azimuth = 0;
  let gear = 0;
  let orbit = 2.5;
  let wasOrbiting = false;

  const screen = (point: THREE.Vector3): ScreenPoint => {
    projected.copy(point).project(camera);
    const ahead = projected.z < 1;
    return { x: 0.5 + projected.x * (ahead ? 0.5 : -0.5), y: 0.5 - projected.y * (ahead ? 0.5 : -0.5), ahead };
  };

  const finish = (title: string, text: string, landings: readonly Landing[] = []): void => {
    $("over-title").textContent = title;
    $("over-text").textContent = text;
    const table = $<HTMLTableElement>("over-table");
    table.hidden = landings.length === 0;
    table.replaceChildren(...landings.map((landing) => {
      const row = table.insertRow();
      row.insertCell().textContent = landing.pad.name;
      row.insertCell().textContent = landing.grade;
      row.insertCell().textContent = String(landing.score);
      row.insertCell().textContent = landing.penalty ? `+${landing.penalty} s` : "";
      return row;
    }));
    show("over");
  };

  const washOf = (north: number, east: number): Wash => {
    if (surface.water(north, east)) {
      return "water";
    }
    const height = surface.at(north, east);
    if (height - Math.max(ground(north, east), 0) > 0.5) {
      return "deck";
    }
    return height > 500 ? "rock" : "dust";
  };

  const fly = (dt: number): void => {
    controls.update(dt);
    const s = controls.sticks;
    if (aid === "assist") {
      assist.sticks.fore = s.fore;
      assist.sticks.side = s.side;
      assist.sticks.pedals = s.pedals;
      assist.sticks.lift = s.lift;
      assist.brake = controls.braking;
    } else {
      flight.setControls(controls.lever, s.fore, s.side, s.pedals);
    }
  };

  const frame = (now: number): void => {
    const interval = now - last;
    last = now;
    const dt = Math.min(interval / 1000, 0.1);
    stage.judge(interval);
    requestAnimationFrame(frame);

    if (phase === "flying" && !DEMO) {
      fly(dt);
    }
    if (phase !== "paused") {
      time += dt;
      flight.advance(dt);
      run.update(flight, dt);
    }

    const i = flight.previous;
    const north = flight.between("north_m") + flight.origin.north;
    const east = flight.between("east_m") + flight.origin.east;
    position.set(east, flight.between("alt_m") + flight.datum, -north);
    fromEuler(i[3], i[4], i[5], before);
    fromEuler(flight.get("phi_deg"), flight.get("theta_deg"), flight.get("psi_deg"), after);
    quaternion.copy(before).slerp(after, flight.pacer.fraction);

    place.position.copy(position);
    place.quaternion.copy(quaternion);
    const nr = flight.get("rotor_pct") / 100;
    if (phase !== "paused") {
      azimuth += SPIN * OMEGA * nr * dt;
    }
    poseRotor(heli, flight.between("a1_deg") * TO_RAD, flight.between("b1_deg") * TO_RAD);
    spinRotors(heli, azimuth, azimuth * TAIL_RATIO);
    const inside = rig.view === "cockpit" && !flight.crashed;
    heli.root.visible = !flight.crashed;
    heli.airframe.visible = !inside;
    cockpit.group.visible = inside;
    cockpit.update(dt, flight, run.next);
    // The gear goes away at speed, well clear of the ground. It is only ever a picture.
    const radar = flight.radar();
    const stow = radar > 22 && flight.get("kts") > 45;
    if (radar < 14 || flight.get("kts") < 30 || stow) {
      gear += THREE.MathUtils.clamp((stow ? 1 : 0) - gear, -dt / 2.6, dt / 2.6);
    }
    poseGear(heli, gear);
    heli.beacon.color.setRGB(Math.sin(time * 9) > 0.8 ? 26 : 0.4, Math.sin(time * 9) > 0.8 ? 3 : 0.05, Math.sin(time * 9) > 0.8 ? 1.5 : 0.03);

    const floor = surface.at(north, east);
    const height = position.y - 1.32 - floor;
    const sunDir = stage.atmosphere.uniforms.uSunDir.value;
    const over = surface.at(north + sunDir.z * height / Math.max(sunDir.y, 0.2), east - sunDir.x * height / Math.max(sunDir.y, 0.2));
    // On a deck, the real shadow takes over from the painted one.
    const onDeck = floor - Math.max(ground(north, east), 0) > 0.5;
    shadow.visible = height < 500 && !flight.crashed && !(onDeck && height < 6);
    if (shadow.visible) {
      const slide = Math.max(height, 0) / Math.max(sunDir.y, 0.2);
      const n = north + sunDir.z * slide;
      const e = east - sunDir.x * slide;
      shadow.position.set(e, over + 0.5, -n);
      shadow.rotation.y = -flight.get("psi_deg") * TO_RAD + Math.PI;
      shadow.scale.setScalar(15);
      (shadow.material as THREE.MeshBasicMaterial).opacity = 0.5 * (1 - height / 500);
    }

    // The air the rotor throws down reaches the surface when it is a few rotor spans away.
    const lift = flight.get("thrust_n") / WEIGHT;
    const blowing = (1 - THREE.MathUtils.smoothstep(height, ROTOR_RADIUS * 0.9, ROTOR_RADIUS * 5)) * THREE.MathUtils.smoothstep(lift, 0.35, 1);
    under.set(position.x, Math.max(surface.at(north, east), 0), position.z);
    wash.blow(dt, under, flight.crashed ? 0 : blowing, washOf(north, east), flight.ve * 0.5, -flight.vn * 0.5);
    wash.update(dt, renderer.domElement.height);

    if (flight.crashed && !wasCrashed) {
      burst.fire(position, flight.crashReason === "Water");
      sound.crash();
      rig.kick(5);
      crashedAt = time;
    }
    wasCrashed = flight.crashed;
    velocity.set(flight.ve, flight.get("vs_mps"), -flight.vn);

    // The chase view swings with the heading alone, tipped down a little: a helicopter's pitch and
    // bank are how it moves, and a horizon that stays put is how its pilot reads them.
    const titleView = phase === "title";
    fromEuler(0, rig.dragging || titleView ? 0 : -7, flight.get("psi_deg"), level);
    if (titleView) {
      orbit += dt * 0.07;
      rig.dragging = true;
      rig.azimuth = orbit;
      rig.elevation = -0.1;
      wasOrbiting = true;
    } else if (wasOrbiting) {
      rig.dragging = false;
      rig.azimuth = 0;
      rig.elevation = 0;
      wasOrbiting = false;
    }
    if (flight.crashed) {
      rig.wreck(position, time - crashedAt, time);
    } else if (rig.view === "cockpit") {
      rig.update(dt, position, quaternion, flight.get("tas_mps"), 0, time);
      // The rig's cockpit looks along the nose: a pilot looks at the ground ahead.
      lookEuler.set(rig.elevation - 0.17, rig.azimuth, 0, "YXZ");
      look.setFromEuler(lookEuler);
      camera.quaternion.multiply(look);
      camera.updateMatrixWorld();
    } else {
      const shake = THREE.MathUtils.smoothstep(lift, 1.05, 1.5) * 0.12;
      rig.update(dt, position, level, flight.get("tas_mps"), shake, time);
    }
    stage.shiftView(titleView && innerWidth > 760);
    burst.update(dt, renderer.domElement.height);
    scenery.update(time, camera.position, flight.wind.north, flight.wind.east);

    if (phase === "flying" || phase === "over") {
      const alive = !flight.crashed;
      const power = alive ? flight.get("power_hp") / 740 : 0;
      const descent = THREE.MathUtils.smoothstep(-flight.get("vs_mps"), 1.5, 5);
      sound.update({
        rotor: alive ? nr : 0.2,
        power,
        airspeed: alive ? flight.get("tas_mps") : 0,
        load: alive ? THREE.MathUtils.clamp(0.35 * lift + 0.5 * descent + 0.4 * THREE.MathUtils.smoothstep(flight.get("kts"), 110, 165), 0, 1) : 0,
        inside: inside ? 1 : 0,
      });
    }

    telemetry.update(dt, phase === "flying" && !flight.crashed ? "running" : phase === "title" ? "hidden" : "frozen");
    stage.render(position, time);

    if (phase === "flying") {
      const pad = run.next;
      const view: HudView = {
        cockpit: inside,
        aid,
        padOnScreen: pad ? screen(tip.set(pad.east, pad.top + 2, -pad.north)) : null,
        velocityOnScreen: screen(tip.copy(position).addScaledVector(velocity, 4)),
      };
      if (flight.crashed) {
        hud.clear();
      } else {
        hud.draw(flight, view, run, pads, outline, time);
        if (warnings(flight).some((w) => w === "LOW ROTOR" || w === "SINK RATE")) {
          sound.warning();
        }
      }
      if (flight.crashed && time - crashedAt > 1.8) {
        finish("Crashed", crashStory(flight.crashReason));
      }
    } else if (phase === "title" && flight.crashed) {
      attract();
    }
  };

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
    run,
    assist,
    controls,
    pads,
    surface,
    begin,
    hoverStart: HOVER_START,
    setMode,
    setAid: (value: Aid) => {
      $<HTMLSelectElement>("aid").value = value;
      applyAid();
    },
    state: () => ({
      phase,
      tier: stage.tier,
      view: rig.view,
      crashed: flight.crashed,
      reason: flight.crashReason,
      time: flight.time,
      pads: pads.length,
      radar: flight.radar(),
      leg: run.leg,
    }),
  });
}

function crashStory(reason: string): string {
  switch (reason) {
    case "Water":
      return "Into the sea.";
    case "Terrain":
      return "Into the island.";
    case "The gear folded":
      return "That was a landing the gear could not take.";
    case "It rolled over":
      return "It rolled over on its wheels: keep the rotor level when you touch.";
    case "The rotor stalled":
      return "The rotor lost its speed: more lever than the engines could turn.";
    case "Too steep to stand on":
      return "The ground there was too steep to stand on.";
    default:
      return `${reason}.`;
  }
}

void main();
