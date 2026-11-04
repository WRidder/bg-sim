/**
 * The game: the menus, the frame loop, and everything that turns the flight's numbers into a picture
 * and a sound. Behind the title screen the aircraft flies itself round the island, so the menu is
 * already the game.
 */

import * as THREE from "three";
import { Atmosphere, type Sun, sunDirection } from "../engine/atmosphere";
import { Sound } from "../engine/audio";
import { Clouds } from "../engine/clouds";
import { Burst, Trail } from "../engine/effects";
import { attitude } from "../engine/frames";
import { Heightfield } from "../engine/heightfield";
import { Controls, STANDARD_PAD } from "../engine/input";
import { Ocean } from "../engine/ocean";
import { Pipeline } from "../engine/pipeline";
import { Terrain } from "../engine/terrain";
import { buildFighter } from "./aircraft";
import { flyTo } from "./autopilot";
import { Rig, VIEWS } from "./camera";
import { buildCockpit } from "./cockpit";
import { Flight, MISS_PENALTY, type Start } from "./flight";
import "./game.css";
import { coastOutline, Hud, type HudView, warnings } from "./hud";
import type { IslandReply, IslandRequest } from "./island.worker";
import IslandWorker from "./island.worker?worker&inline";
import starts from "./starts.json";
import { buildGround, GateRings, groundShadow } from "./world";

const q = new URLSearchParams(location.search);
const DEMO = q.has("demo");
const GRID = Number(q.get("grid") ?? 2048);
const SUNS: Record<string, Sun> = {
  morning: { elevation: 14, azimuth: 105 },
  afternoon: { elevation: 34, azimuth: 235 },
  evening: { elevation: 9, azimuth: 262 },
};
/** Fast and fairly low, with the first gate straight ahead. */
const GATE_START = starts[2] as Start;
const BEST_KEY = "island-sortie-best";

const $ = <T extends HTMLElement>(id: string): T => document.getElementById(id) as T;

function stored(): number | null {
  try {
    const value = Number(localStorage.getItem(BEST_KEY));
    return value > 0 ? value : null;
  } catch {
    return null;
  }
}

function remember(value: number): void {
  try {
    localStorage.setItem(BEST_KEY, String(value));
  } catch {
    // A private window keeps no record; the run still counts.
  }
}

function clock(seconds: number): string {
  return `${Math.floor(seconds / 60)}:${(seconds % 60).toFixed(1).padStart(4, "0")}`;
}

class Island {
  private readonly worker = new IslandWorker();
  private waiting: ((reply: IslandReply) => void) | null = null;

  constructor() {
    this.worker.onmessage = (event: MessageEvent<IslandReply>) => this.waiting?.(event.data);
  }

  request(sun: Sun): Promise<IslandReply> {
    return new Promise((resolve) => {
      this.waiting = resolve;
      const { x, y, z } = sunDirection(sun);
      this.worker.postMessage({ size: GRID, sun: { x, y, z } } satisfies IslandRequest);
    });
  }
}

type Phase = "title" | "flying" | "paused" | "over";

async function main(): Promise<void> {
  const canvas = $<HTMLCanvasElement>("world");
  let renderer: THREE.WebGLRenderer;
  try {
    renderer = new THREE.WebGLRenderer({ canvas, antialias: false, powerPreference: "high-performance" });
  } catch {
    $("loading").hidden = true;
    $("failed").hidden = false;
    return;
  }
  const island = new Island();
  let sunName = "afternoon";
  const reply = await island.request(SUNS[sunName]);
  const grid = reply.grid;
  if (!grid) {
    throw new Error("The island came back without its grid");
  }
  $("loading-text").textContent = "Fuelling the aircraft…";
  await new Promise((resolve) => setTimeout(resolve));

  const field = new Heightfield(grid, reply.shadow);
  const ground = (north: number, east: number): number => field.at(north, east);
  const atmosphere = new Atmosphere(renderer);
  atmosphere.setSun(SUNS[sunName]);

  const world = new THREE.Scene();
  const near = new THREE.Scene();
  world.add(atmosphere.dome);
  const clouds = new Clouds(atmosphere.uniforms, { cover: 0.3 });
  const terrain = new Terrain(field, atmosphere.uniforms, clouds.shared);
  const ocean = new Ocean(field, atmosphere.uniforms);
  world.add(terrain.mesh, ocean.mesh, buildGround(field, atmosphere.uniforms));
  const pipeline = new Pipeline(renderer, clouds);

  const sunLight = new THREE.DirectionalLight(0xffffff, 1);
  const light = (): void => {
    sunLight.color.copy(atmosphere.uniforms.uSunColor.value).multiplyScalar(0.8);
    near.environment = atmosphere.environment;
    near.environmentIntensity = 0.55;
    world.environment = atmosphere.environment;
    world.environmentIntensity = 0.45;
    worldSun.color.copy(atmosphere.uniforms.uSunColor.value).multiplyScalar(0.5);
    worldSun.position.copy(atmosphere.uniforms.uSunDir.value);
  };
  const worldSun = new THREE.DirectionalLight(0xffffff, 1);
  world.add(worldSun);
  sunLight.castShadow = true;
  sunLight.shadow.mapSize.set(2048, 2048);
  Object.assign(sunLight.shadow.camera, { left: -12, right: 12, top: 12, bottom: -12, near: 50, far: 150 });
  sunLight.shadow.bias = -0.0006;
  sunLight.shadow.normalBias = 0.02;
  renderer.shadowMap.enabled = true;
  renderer.shadowMap.type = THREE.PCFShadowMap;
  near.add(sunLight, sunLight.target);
  light();

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

  const camera = new THREE.PerspectiveCamera(66, 16 / 9, 1, 400_000);
  const rig = new Rig(camera, (x, z) => Math.max(ground(-z, x), 0));
  const hud = new Hud($<HTMLCanvasElement>("hud"));
  const outline = coastOutline(field.heights, field.size, field.extent);
  const sound = new Sound();
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
  flight.onGate = (gate) => {
    sound.gate(gate.hit);
    if (gate.hit) {
      rig.kick(0.5);
    }
  };

  // ---- Size and quality ----------------------------------------------------------------------
  const tiers = [
    { scale: 1, steps: 72 },
    { scale: 0.85, steps: 56 },
    { scale: 0.7, steps: 44 },
    { scale: 0.55, steps: 34 },
  ];
  let tier = Number(q.get("tier") ?? 0);
  const resize = (): void => {
    const width = innerWidth;
    const height = innerHeight;
    const ratio = Math.min(devicePixelRatio, 1.5) * tiers[tier].scale;
    renderer.setPixelRatio(1);
    renderer.setSize(Math.round(width * ratio), Math.round(height * ratio), false);
    pipeline.resize(Math.round(width * ratio), Math.round(height * ratio));
    clouds.steps = tiers[tier].steps;
    camera.aspect = width / height;
    hud.resize(width, height, Math.min(devicePixelRatio, 2));
  };
  addEventListener("resize", resize);
  resize();
  let slow = 0;
  const judge = (interval: number): void => {
    slow = interval > 24 ? slow + interval : Math.max(0, slow - interval * 0.5);
    if (slow > 1800 && tier < tiers.length - 1 && !q.has("tier")) {
      tier += 1;
      slow = 0;
      resize();
    }
  };

  // ---- Menus ---------------------------------------------------------------------------------
  let phase: Phase = "title";
  let mode: "free" | "gates" = "free";
  const select = $<HTMLSelectElement>("start");
  for (const [i, start] of starts.entries()) {
    select.add(new Option(start.label, String(i)));
  }
  $<HTMLSelectElement>("time").value = sunName;
  $<HTMLSelectElement>("sky").value = "0.3";
  const showBest = (): void => {
    const best = stored();
    $("best").textContent = best ? `Best ${clock(best)}.` : "";
  };
  showBest();
  const setMode = (value: "free" | "gates"): void => {
    mode = value;
    for (const button of $("mode").querySelectorAll("button")) {
      button.setAttribute("aria-checked", String(button.dataset.value === value));
    }
    $("start-row").hidden = value === "gates";
  };
  setMode("free");
  for (const button of $("mode").querySelectorAll("button")) {
    button.addEventListener("click", () => setMode(button.dataset.value as "free" | "gates"));
  }

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

  /** A flight from the start, with whatever the menu says. */
  const begin = (): void => {
    const start = mode === "gates" ? GATE_START : (starts[Number(select.value)] as Start);
    if (mode === "gates") {
      flight.startGates();
      rings.show(flight.gates);
    } else {
      flight.stopGates();
    }
    rings.group.visible = mode === "gates";
    flight.reset(start, switches());
    flight.gusts.intensity = $<HTMLInputElement>("turbulence").checked ? 2.5 : 0;
    controls.setThrottle(start.thtl0);
    burst.clear();
    pipeline.flash = 0;
    trails.forEach((trail) => trail.clear());
    rig.snap();
    crashedAt = -1;
    show("flying");
  };

  const applyLook = async (): Promise<void> => {
    clouds.shared.uCover.value = Number($<HTMLSelectElement>("sky").value);
    const name = $<HTMLSelectElement>("time").value;
    if (name !== sunName) {
      sunName = name;
      atmosphere.setSun(SUNS[name]);
      light();
      field.setShadow((await island.request(SUNS[name])).shadow);
    }
  };
  $("time").addEventListener("change", () => void applyLook());
  $("sky").addEventListener("change", () => void applyLook());

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

  // ---- The aircraft on its own ---------------------------------------------------------------
  /** Behind the title the aircraft flies the gate run with the gates out of sight. */
  const autopilot = (): void => {
    const gate = flight.nextGate();
    if (gate) {
      flyTo(flight, gate, 190, ground);
    }
  };
  const attract = (): void => {
    flight.startGates();
    rings.group.visible = false;
    flight.reset(GATE_START, {});
    flight.gusts.intensity = 0;
    burst.clear();
    pipeline.flash = 0;
    rig.view = "chase";
    rig.snap();
    crashedAt = -1;
  };

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
  let offset = false;

  const screen = (point: THREE.Vector3): { x: number; y: number; ahead: boolean } => {
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
    judge(interval);
    requestAnimationFrame(frame);

    if (phase === "title" || DEMO) {
      autopilot();
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
    const p = flight.pacer.fraction;
    const north = flight.between("north_m") + flight.north() - flight.get("north_m");
    const east = flight.between("east_m") + flight.east() - flight.get("east_m");
    position.set(east, flight.between("alt_m"), -north);
    attitude(i[3], i[4], i[5], i[6], before);
    attitude(flight.get("q_w"), flight.get("q_x"), flight.get("q_y"), flight.get("q_z"), after);
    quaternion.copy(before).slerp(after, p);

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

    sunLight.position.copy(position).addScaledVector(atmosphere.uniforms.uSunDir.value, 100);
    sunLight.target.position.copy(position);

    const land = Math.max(ground(north, east), 0);
    const height = position.y - land;
    const sunDir = atmosphere.uniforms.uSunDir.value;
    shadow.visible = height < 900 && height > 0 && !flight.crashed;
    if (shadow.visible) {
      // Along the sun's ray to the ground, as far as a flat ground would put it.
      const slide = height / Math.max(sunDir.y, 0.2);
      const n = north - sunDir.z * -slide;
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
      burst.fire(position);
      sound.crash();
      rig.kick(6);
      crashedAt = time;
    }
    wasCrashed = flight.crashed;
    const buffet = THREE.MathUtils.smoothstep(flight.get("alpha_deg"), 16, 26) * 0.5 + load * 0.2;
    velocity.set(flight.get("u_mps"), -flight.get("v_mps"), -flight.get("w_mps")).applyQuaternion(quaternion);
    if (!flight.crashed) {
      rig.update(dt, position, quaternion, flight.get("tas_mps"), buffet, time);
    } else {
      rig.update(dt, position, rumbleQuaternion(quaternion, time - crashedAt), 0, 0, time);
    }
    const wide = phase === "title" && innerWidth > 760;
    if (wide !== offset) {
      offset = wide;
      if (wide) {
        camera.setViewOffset(innerWidth, innerHeight, -innerWidth * 0.2, innerHeight * 0.06, innerWidth, innerHeight);
      } else {
        camera.clearViewOffset();
      }
      camera.updateProjectionMatrix();
    }
    terrain.follow(camera.position);
    ocean.update(camera.position, time);
    for (const trail of trails) {
      trail.update(camera.position);
    }
    burst.update(dt, renderer.domElement.height);
    rings.update(flight.gates, time);

    if (phase === "flying" || phase === "over") {
      sound.update({
        power: flight.crashed ? 0 : power / 100,
        burner: flight.crashed ? 0 : burner,
        airspeed: flight.crashed ? 0 : flight.get("tas_mps"),
        buffet: flight.crashed ? 0 : buffet,
        inside: rig.view === "cockpit" ? 1 : 0,
      });
    }

    pipeline.render(world, near, camera, time);

    if (phase === "flying") {
      const gate = flight.nextGate();
      const view: HudView = {
        cockpit: rig.view === "cockpit",
        fov: camera.fov,
        gateOnScreen: gate ? screen(tip.set(gate.east, gate.alt, -gate.north)) : null,
        velocityOnScreen: screen(tip.copy(position).addScaledVector(velocity, 3)),
      };
      if (!flight.crashed) {
        hud.draw(flight, view, outline, time);
        if (warnings(flight).some((w) => w === "PULL UP" || w === "DEPARTED")) {
          sound.warning();
        }
      } else {
        hud.clear();
      }
      if (flight.crashed && time - crashedAt > 1.8) {
        const score = flight.gates.length > 0 ? " The run stops here." : "";
        finish("Crashed", `${flight.crashReason === "Water" ? "Into the sea." : "Into the island."}${score}`);
      } else if (flight.gateDone !== null) {
        const score = flight.gateScore();
        const best = stored();
        const missed = flight.gates.filter((g) => !g.hit).length;
        if (best === null || score < best) {
          remember(score);
        }
        showBest();
        const penalty = missed ? ` with ${missed} missed (${missed * MISS_PENALTY} s added)` : ", every gate clean";
        finish(best === null || score < best ? "New best time" : "Run complete", `${clock(score)}${penalty}.`);
      }
    } else if (phase === "title" && (flight.crashed || flight.gateDone !== null)) {
      attract();
    }
  };

  /** After a crash the camera drifts round the fire. */
  const rumbleQuaternion = (from: THREE.Quaternion, seconds: number): THREE.Quaternion =>
    new THREE.Quaternion().setFromAxisAngle(new THREE.Vector3(0, 1, 0), seconds * 0.12).multiply(from);

  $("loading").hidden = true;
  attract();
  show("title");
  // First paint of the world behind the title, then the page is ready for the smoke tests.
  requestAnimationFrame(frame);
  const debug = {
    flight,
    rig,
    begin,
    setMode,
    state: () => ({ phase, tier, view: rig.view, crashed: flight.crashed, time: flight.time, gates: flight.gates.length }),
  };
  (window as unknown as { game: typeof debug }).game = debug;
  requestAnimationFrame(() => requestAnimationFrame(() => {
    (window as unknown as { ready: unknown }).ready = debug.state();
  }));
}

void main();
