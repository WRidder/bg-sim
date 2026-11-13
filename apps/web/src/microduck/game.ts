/**
 * Microduck: drive pollen-robotics' microduck with a gamepad, its own walking policy running in the
 * browser. The page: a workbench floor, a follow camera, the duck drawn from its kinematic tree, the
 * pad read 60 times a second, the control loop run at 50 Hz (loop.ts), and a HUD that says what the
 * robot was asked and what its trunk did. What the duck stands on is a plant: the bg-sim model as an
 * FMU when there is one, otherwise a stand-in that is plainly not a simulation (plant.ts).
 */

import * as THREE from "three";
import { SideBar } from "../engine/side";
import { Telemetry } from "../engine/telemetry";
import { $, announce } from "../engine/ui";
import { Controller } from "./controller";
import { DuckModel } from "./duck";
import { findModel, FmuPlant } from "./fmuPlant";
import { DuckLoop } from "./loop";
import { type Action, BUTTON, DuckInput, type InputState, MODE_NAMES, stickCommand } from "./pad";
import { describeStop, type Plant, StandInPlant } from "./plant";
import { OnnxBrain, loadOrt } from "./policy";
import { CONTROL_DT, WALK_FILE } from "./robot";
import { duckPanel } from "./telemetry";
import walkUrl from "./policies/velstand.onnx?url";
import sitstandUrl from "./policies/alpha_sitstand.onnx?url";
import groundPickUrl from "./policies/alpha_ground_pick.onnx?url";
import rouladeUrl from "./policies/roulade.onnx?url";
import kickLeftUrl from "./policies/ball_kick_left.onnx?url";
import kickRightUrl from "./policies/ball_kick_right.onnx?url";

const q = new URLSearchParams(location.search);

/** The policy files by the slot the controller knows them as (robot.ts, controller.ts). */
const POLICIES: [string, string][] = [
  ["sitstand", sitstandUrl],
  ["ground_pick", groundPickUrl],
  ["roulade", rouladeUrl],
  ["kick_left", kickLeftUrl],
  ["kick_right", kickRightUrl],
];

type View = "follow" | "side" | "free";
const VIEWS: View[] = ["follow", "side", "free"];

async function fetchBytes(url: string): Promise<Uint8Array> {
  const response = await fetch(url);
  if (!response.ok) {
    throw new Error(`${url}: HTTP ${response.status}`);
  }
  return new Uint8Array(await response.arrayBuffer());
}

/** A floor of 10 cm tiles with a line every metre, drawn once into a canvas. */
function floorTexture(renderer: THREE.WebGLRenderer): THREE.CanvasTexture {
  const size = 1024;
  const canvas = document.createElement("canvas");
  canvas.width = canvas.height = size;
  const c = canvas.getContext("2d") as CanvasRenderingContext2D;
  const cell = size / 10;
  for (let i = 0; i < 10; i += 1) {
    for (let j = 0; j < 10; j += 1) {
      c.fillStyle = (i + j) % 2 === 0 ? "#b9b2a4" : "#aea796";
      c.fillRect(i * cell, j * cell, cell, cell);
    }
  }
  c.strokeStyle = "rgba(60, 54, 44, 0.55)";
  c.lineWidth = 6;
  c.strokeRect(0, 0, size, size);
  const texture = new THREE.CanvasTexture(canvas);
  texture.wrapS = texture.wrapT = THREE.RepeatWrapping;
  texture.colorSpace = THREE.SRGBColorSpace;
  texture.anisotropy = renderer.capabilities.getMaxAnisotropy();
  return texture;
}

async function main(): Promise<void> {
  // ---- Messages ------------------------------------------------------------------------------
  let toastUntil = 0;
  const toast = (text: string, seconds = 2.5): void => {
    $("toast").textContent = text;
    $("toast").classList.add("on");
    toastUntil = performance.now() + seconds * 1000;
  };

  // ---- The picture ---------------------------------------------------------------------------
  const canvas = $<HTMLCanvasElement>("world");
  let renderer: THREE.WebGLRenderer;
  try {
    renderer = new THREE.WebGLRenderer({ canvas, antialias: true });
  } catch {
    $("loading").hidden = true;
    $("failed").hidden = false;
    return;
  }
  renderer.setPixelRatio(Math.min(devicePixelRatio, 2));
  renderer.shadowMap.enabled = true;
  renderer.shadowMap.type = THREE.PCFShadowMap;
  renderer.toneMapping = THREE.ACESFilmicToneMapping;
  const scene = new THREE.Scene();
  scene.background = new THREE.Color(0x2a3238);
  scene.fog = new THREE.Fog(0x2a3238, 4, 14);
  const camera = new THREE.PerspectiveCamera(42, 1, 0.01, 60);
  scene.add(new THREE.HemisphereLight(0xdfe8ff, 0x4a4036, 1.3));
  const sun = new THREE.DirectionalLight(0xfff1dc, 2.4);
  sun.castShadow = true;
  sun.shadow.mapSize.set(2048, 2048);
  sun.shadow.camera.left = sun.shadow.camera.bottom = -0.6;
  sun.shadow.camera.right = sun.shadow.camera.top = 0.6;
  sun.shadow.camera.near = 0.1;
  sun.shadow.camera.far = 6;
  sun.shadow.bias = -0.0004;
  scene.add(sun, sun.target);
  const texture = floorTexture(renderer);
  texture.repeat.set(40, 40);
  const floor = new THREE.Mesh(new THREE.PlaneGeometry(40, 40), new THREE.MeshStandardMaterial({ map: texture, roughness: 0.9 }));
  floor.rotation.x = -Math.PI / 2;
  floor.receiveShadow = true;
  scene.add(floor);
  const duck = new DuckModel();
  scene.add(duck.root);

  // Footprints where a sole touched down: a trail that shows the steps.
  const printGeometry = new THREE.CircleGeometry(0.018, 16).rotateX(-Math.PI / 2);
  const printMaterial = new THREE.MeshBasicMaterial({ color: 0x8a5a1c, transparent: true, opacity: 0.35, depthWrite: false });
  const prints = Array.from({ length: 80 }, () => {
    const m = new THREE.Mesh(printGeometry, printMaterial);
    m.visible = false;
    scene.add(m);
    return m;
  });
  let nextPrint = 0;
  const wasDown = [true, true];

  const resize = (): void => {
    renderer.setSize(innerWidth, innerHeight, false);
    camera.aspect = innerWidth / innerHeight;
    camera.updateProjectionMatrix();
  };
  addEventListener("resize", resize);
  resize();

  // ---- The plant -----------------------------------------------------------------------------
  $("loading-text").textContent = "Looking for the bg-sim model…";
  let plant: Plant;
  let plantNote = "";
  const model = q.has("standin") ? null : await findModel();
  if (model) {
    try {
      plant = await FmuPlant.create(model);
    } catch (error) {
      plantNote = `The FMU did not fit (${(error as Error).message}). `;
      plant = new StandInPlant();
    }
  } else {
    plantNote = "No bg-sim FMU built for this page yet. ";
    plant = new StandInPlant();
  }
  const banner = $("banner");
  const describePlant = (): void => {
    if (plant instanceof StandInPlant) {
      banner.textContent = `${plantNote}Stand-in plant, not the bg-sim model: the joints follow the policy's targets with a lag, and the trunk is ${
        plant.carry === "foot" ? "carried round the stance foot (K: at the asked speed)" : "moved at the asked speed, not by the legs (K: round the stance foot)"
      }, kept level. No physics: the duck cannot fall.`;
    } else {
      banner.textContent = plant.label;
      banner.classList.add("fmu");
    }
    banner.classList.remove("stopped");
  };
  // Stays up until R or Create: when, and what the FMU reported.
  const showStopped = (): void => {
    const stop = loop.plant.stop;
    banner.textContent = `${loop.plant.label}: ${stop ? describeStop(stop) : "stopped"}. The policy is no longer run; the duck is drawn in its last good state. R or Create starts again.`;
    banner.classList.add("stopped");
  };
  if (plant instanceof StandInPlant && q.get("carry") === "foot") {
    plant.setCarry("foot");
  }
  describePlant();

  // ---- The policy ----------------------------------------------------------------------------
  let brain: OnnxBrain | null = null;
  const fallback: OnnxBrain = { has: () => false } as unknown as OnnxBrain;
  const controller = new Controller({
    has: (net) => (brain ?? fallback).has(net),
    infer: (net, obs, fresh) => {
      if (!brain) throw new Error("no policy loaded");
      return brain.infer(net, obs, fresh);
    },
  });
  const loop = new DuckLoop(plant, controller);
  loop.enabled = false;
  let policyText = "loading…";
  $("loading-text").textContent = "Starting ONNX Runtime and loading the walking policy…";
  try {
    const ort = await loadOrt();
    const b = new OnnxBrain(ort);
    await b.load("walk", await fetchBytes(walkUrl));
    brain = b;
    loop.enabled = true;
    policyText = WALK_FILE;
    // The one-shots are not needed to walk: they arrive while the duck already stands.
    void (async () => {
      for (const [slot, url] of POLICIES) {
        try {
          await b.load(slot, await fetchBytes(url));
        } catch (error) {
          console.warn(`policy ${slot}:`, error);
        }
      }
    })();
  } catch (error) {
    policyText = "not loaded";
    toast(`The policy did not load: ${(error as Error).message}. The joints hold the home pose.`, 8);
    console.error(error);
  }

  // ---- Input, side window --------------------------------------------------------------------
  const input = new DuckInput();
  input.onConnect = (name, connected) => toast(connected ? `Gamepad connected: ${name}` : "Gamepad disconnected", 3);
  // A side window takes the controls card's place; H still shows and hides the card itself.
  let helpWanted = true;
  let sideRoom = 0;
  const placeHelp = (): void => {
    $("help").hidden = !helpWanted || sideRoom > 0;
  };
  const side = new SideBar("microduck", (left, right) => {
    sideRoom = left + right;
    $("status").style.left = `${left + 10}px`;
    $("pad").style.left = `${left + 10}px`;
    placeHelp();
  });
  const telemetry = new Telemetry(side, duckPanel(loop, () => brain));

  // ---- Camera --------------------------------------------------------------------------------
  let view: View = "follow";
  let offset = 0.95; // round from straight behind, rad: enough to see the beak
  let elevation = 0.38;
  let distance = 0.85;
  let freeAngle = 0;
  let dragging = false;
  const target = new THREE.Vector3();
  let heading = 0;
  canvas.addEventListener("pointerdown", (e) => {
    dragging = true;
    canvas.setPointerCapture(e.pointerId);
  });
  canvas.addEventListener("pointerup", () => (dragging = false));
  canvas.addEventListener("pointermove", (e) => {
    if (!dragging) return;
    offset -= e.movementX * 0.006;
    freeAngle -= e.movementX * 0.006;
    elevation = THREE.MathUtils.clamp(elevation + e.movementY * 0.005, 0.05, 1.4);
  });
  canvas.addEventListener("wheel", (e) => (distance = THREE.MathUtils.clamp(distance * Math.exp(e.deltaY * 0.001), 0.3, 4)), { passive: true });

  // ---- What the buttons do -------------------------------------------------------------------
  let paused = false;
  const setPaused = (on: boolean): void => {
    paused = on;
    $("paused").hidden = !on;
  };
  const refuse = (why: string | null): void => {
    if (why) toast(why);
  };
  const reset = (): void => {
    loop.reset();
    failure = "";
    describePlant();
    prints.forEach((p) => (p.visible = false));
    telemetry.reset();
    snap = true;
  };
  const act = (action: Action): void => {
    switch (action) {
      case "sit":
        return refuse(loop.enabled ? controller.sitToggle() : "the policy is off");
      case "groundPick":
        return refuse(loop.enabled ? controller.startGroundPick() : "the policy is off");
      case "roulade":
        return refuse(loop.enabled ? controller.startSkill("roulade") : "the policy is off");
      case "kickLeft":
        return refuse(loop.enabled ? controller.startSkill("kick_left") : "the policy is off");
      case "kickRight":
        return refuse(loop.enabled ? controller.startSkill("kick_right") : "the policy is off");
      case "policy":
        if (!brain) return toast("No policy loaded");
        loop.setEnabled(!loop.enabled);
        return toast(loop.enabled ? "Policy on" : "Policy off: the joints go home and hold");
      case "reset":
        return reset();
      case "camera":
        view = VIEWS[(VIEWS.indexOf(view) + 1) % VIEWS.length];
        freeAngle = heading + Math.PI + offset;
        return toast(`Camera: ${view}`, 1.2);
    }
  };
  addEventListener("keydown", (e) => {
    if (e.repeat) return;
    if (e.code === "KeyH") {
      helpWanted = !helpWanted;
      if (helpWanted && sideRoom > 0) toast("The controls come back when the side window closes (T)");
      placeHelp();
    }
    if (e.code === "KeyK" && loop.plant instanceof StandInPlant) {
      loop.plant.setCarry(loop.plant.carry === "foot" ? "command" : "foot");
      describePlant();
    }
    if (e.code === "KeyP" || e.code === "Escape") setPaused(!paused);
  });
  document.addEventListener("visibilitychange", () => {
    if (document.hidden) setPaused(true);
  });

  // ---- The control loop, at 50 Hz on plant time ----------------------------------------------
  let latest: InputState = input.update(0);
  let owed = 0;
  let pumping = false;
  let failure = "";
  const pump = async (): Promise<void> => {
    pumping = true;
    try {
      while (owed >= CONTROL_DT && !paused) {
        if (!loop.plant.healthy) {
          owed = 0; // a stopped plant is not stepped and its frozen state not fed to the policy
          break;
        }
        owed -= CONTROL_DT;
        if (latest.rouladeHeld && loop.enabled) controller.startSkill("roulade"); // the held button chains
        await loop.tick(stickCommand(latest.mode, latest.sticks), latest.mouth);
        if (!loop.plant.healthy) {
          const stop = loop.plant.stop;
          failure = `The plant ${stop ? describeStop(stop) : "stopped"}. The policy is no longer run. Create or R starts again.`;
          showStopped();
          toast(failure, 10);
          break;
        }
      }
    } catch (error) {
      failure = (error as Error).message;
      loop.setEnabled(false);
      toast(`Policy stopped: ${failure}`, 8);
      console.error(error);
    } finally {
      pumping = false;
    }
  };

  // ---- HUD -----------------------------------------------------------------------------------
  const sticks = $<HTMLCanvasElement>("sticks").getContext("2d") as CanvasRenderingContext2D;
  const buttonNames: [number, string][] = [
    [BUTTON.cross, "✕"],
    [BUTTON.circle, "○"],
    [BUTTON.square, "□"],
    [BUTTON.triangle, "△"],
    [BUTTON.l1, "L1"],
    [BUTTON.r1, "R1"],
    [BUTTON.create, "Create"],
    [BUTTON.options, "Options"],
    [BUTTON.up, "↑"],
    [BUTTON.down, "↓"],
    [BUTTON.left, "←"],
    [BUTTON.right, "→"],
    [BUTTON.ps, "PS"],
  ];
  const chips = buttonNames.map(([, name]) => {
    const span = document.createElement("span");
    span.textContent = name;
    $("buttons").append(span);
    return span;
  });
  const fmt = (v: number): string => (Math.abs(v) < 0.005 ? "0.00" : v.toFixed(2));
  const drawSticks = (s: InputState): void => {
    const c = sticks;
    c.clearRect(0, 0, 240, 112);
    const stick = (cx: number, x: number, y: number, label: string): void => {
      c.strokeStyle = "rgba(242,244,239,0.3)";
      c.lineWidth = 2;
      c.beginPath();
      c.arc(cx, 54, 44, 0, Math.PI * 2);
      c.stroke();
      c.strokeStyle = "rgba(242,244,239,0.12)";
      c.beginPath();
      c.arc(cx, 54, 44 * 0.1, 0, Math.PI * 2); // the dead zone
      c.stroke();
      c.fillStyle = "#ffb347";
      c.beginPath();
      c.arc(cx + x * 44, 54 - y * 44, 7, 0, Math.PI * 2);
      c.fill();
      c.fillStyle = "rgba(242,244,239,0.55)";
      c.font = "11px Segoe UI, sans-serif";
      c.fillText(label, cx - 4, 108);
    };
    stick(54, s.sticks.lx, s.sticks.ly, "L");
    stick(170, s.sticks.rx, s.sticks.ry, "R");
    const lt = s.frame?.lt ?? 0;
    const rt = s.frame?.rt ?? 0;
    for (const [x, v] of [[108, lt], [222, rt]] as const) {
      c.fillStyle = "rgba(242,244,239,0.12)";
      c.fillRect(x, 10, 8, 88);
      c.fillStyle = "#6cc4ff";
      c.fillRect(x, 98 - 88 * v, 8, 88 * v);
    }
  };
  let hudOwed = 0;
  const drawHud = (s: InputState): void => {
    $("policy").textContent = policyText;
    $("net").textContent = !loop.plant.healthy || failure ? "stopped" : loop.enabled ? (loop.lastTick?.label ?? "–") : "off";
    $("mode").textContent = MODE_NAMES[s.mode];
    const cmd = loop.filter.value.twist;
    const fed = loop.enabled && loop.plant.healthy; // what the policy is being given now
    const span = [0.4, 0.3, 1];
    for (let i = 0; i < 3; i += 1) {
      $(`cmd-${i}`).textContent = fmt(fed ? cmd[i] : 0);
      $(`act-${i}`).textContent = fmt(loop.actual[i]);
      const share = THREE.MathUtils.clamp((fed ? cmd[i] : 0) / span[i], -1, 1);
      const bar = $(`bar-${i}`);
      bar.style.left = `${50 + Math.min(0, share) * 50}%`;
      bar.style.width = `${Math.abs(share) * 50}%`;
      $(`mark-${i}`).style.left = `${50 + THREE.MathUtils.clamp(loop.actual[i] / span[i], -1, 1) * 50}%`;
    }
    const name = $("pad-name");
    name.textContent = s.pad ? `Gamepad: ${s.pad}` : "No gamepad: keyboard. Connect a DualSense (USB or Bluetooth) and press any button.";
    name.classList.toggle("on", !!s.pad);
    chips.forEach((chip, i) => chip.classList.toggle("on", !!s.frame?.held[buttonNames[i][0]]));
    drawSticks(s);
    if (performance.now() > toastUntil) $("toast").classList.remove("on");
  };

  // ---- The frame -----------------------------------------------------------------------------
  const joints = new Float64Array(15);
  const position = new Float64Array(3);
  const quaternion = new THREE.Quaternion();
  const before = new THREE.Quaternion();
  const sole = new THREE.Vector3();
  const eye = new THREE.Vector3();
  let snap = true;
  let last = performance.now();

  const frame = (now: number): void => {
    requestAnimationFrame(frame);
    const dt = Math.min((now - last) / 1000, 0.1);
    last = now;
    latest = input.update(dt);
    for (const action of latest.actions) act(action);
    if (!paused) {
      owed = Math.min(owed + dt, 0.1); // a slow machine slows the duck down rather than spiralling
      if (!pumping) void pump();
    }

    // Draw between the last two control ticks.
    const fraction = THREE.MathUtils.clamp(owed / CONTROL_DT, 0, 1);
    const s = loop.plant.state;
    loop.drawnJoints(fraction, joints);
    for (let i = 0; i < 3; i += 1) position[i] = loop.before.position[i] + (s.position[i] - loop.before.position[i]) * fraction;
    const b = loop.before.quaternion;
    before.set(b[1], b[2], b[3], b[0]);
    quaternion.set(s.quaternion[1], s.quaternion[2], s.quaternion[3], s.quaternion[0]);
    before.slerp(quaternion, fraction);
    duck.update(joints, position, [before.w, before.x, before.y, before.z]);
    const [w, x, y, z] = s.quaternion;
    heading = Math.atan2(2 * (w * z + x * y), 1 - 2 * (y * y + z * z));

    // A footprint where a sole comes down.
    if (s.contact) {
      for (const foot of [0, 1] as const) {
        const down = s.contact[foot] > 0.5;
        if (down && !wasDown[foot]) {
          duck.sole(foot, sole);
          const p = prints[nextPrint];
          nextPrint = (nextPrint + 1) % prints.length;
          p.position.set(sole.x, 0.0006, sole.z);
          p.visible = true;
        }
        wasDown[foot] = down;
      }
    }

    // The camera: behind and to one side, following the heading, or held where it was put.
    const goal = eye.set(position[0], position[2] * 0.75, -position[1]);
    if (snap) target.copy(goal);
    target.lerp(goal, 1 - Math.exp(-dt * 6));
    const angle = view === "follow" ? heading + Math.PI + offset : view === "side" ? heading + Math.PI / 2 : freeAngle;
    const cam = new THREE.Vector3(Math.cos(angle) * Math.cos(elevation), Math.sin(elevation), -Math.sin(angle) * Math.cos(elevation)).multiplyScalar(distance).add(target);
    if (snap) camera.position.copy(cam);
    camera.position.lerp(cam, 1 - Math.exp(-dt * 4));
    camera.lookAt(target);
    snap = false;
    sun.position.set(target.x + 1.2, target.y + 2.4, target.z + 0.8);
    sun.target.position.copy(target);

    hudOwed += dt;
    if (hudOwed > 1 / 20) {
      hudOwed = 0;
      drawHud(latest);
    }
    telemetry.update(dt, paused ? "frozen" : "running");
    renderer.render(scene, camera);
  };

  $("loading").hidden = true;
  requestAnimationFrame(frame);
  announce({
    loop,
    controller,
    input,
    side,
    telemetry,
    act,
    state: () => ({
      plant: loop.plant.kind,
      label: loop.plant.label,
      carry: loop.plant instanceof StandInPlant ? loop.plant.carry : null,
      policy: policyText,
      loaded: brain?.loaded ?? [],
      enabled: loop.enabled,
      net: loop.lastTick?.label ?? null,
      ticks: loop.ticks,
      mode: latest.mode,
      pad: latest.pad,
      command: Array.from(loop.filter.value.twist),
      actual: Array.from(loop.actual),
      position: Array.from(loop.plant.state.position),
      gravity: Array.from(loop.plant.state.gravity),
      contact: loop.plant.state.contact ? Array.from(loop.plant.state.contact) : null,
      plantTime: loop.plant.state.time,
      // The FMU's wall time per 20 ms control tick (the model's real-time factor is meanMs / 20).
      timing: loop.plant instanceof FmuPlant ? { ...loop.plant.timing } : null,
      heading,
      action: Array.from(loop.lastTick?.step?.action ?? []),
      failure,
      stop: loop.plant.stop ?? null,
      paused,
    }),
  });
}

void main();
