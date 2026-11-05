/**
 * Apex & Dust: the menus, the frame loop, and everything that turns a car's numbers into a picture
 * and a sound. Behind the title screen the car lies down laps by itself on the route you have chosen,
 * so the menu is already the game.
 */

import * as THREE from "three";
import { SUNS, Stage } from "../engine/stage";
import { $, announce, BestTime, choices } from "../engine/ui";
import { Puffs, SkidMarks } from "./fx";
import { type GhostLap, loadGhost, type Pose, Recording, saveGhost } from "./ghost";
import { detailTexture, groundMaterial, type GroundUniforms, roadRibbon } from "./ground";
import { COLOURS, deltaText, Hud, type HudState, lapText } from "./hud";
import { roadHeight } from "./land";
import { Line } from "./line";
import { CarModel } from "./model";
import { Pedals } from "./pedals";
import { Pilot } from "./pilot";
import { buildScenery, type Scenery } from "./scenery";
import { Land, writeField } from "./source";
import type { Kind, Track } from "./track";
import { trackFor, TRACKS } from "./tracks";
import { type View, VIEWS, Views } from "./views";
import { CarVoice } from "./voice";
import { CARS, CORNERS, type Lap, Vehicle } from "./vehicle";

const q = new URLSearchParams(location.search);
const DEMO = q.has("demo");
const KEY = "apex-dust";

type Phase = "title" | "grid" | "driving" | "paused" | "over";


async function main(): Promise<void> {
  let kind: Kind = q.get("car") === "buggy" ? "buggy" : "racecar";
  const firstTrack = TRACKS.find((t) => t.id === q.get("track")) ?? TRACKS.find((t) => t.car === kind);
  let trackId = (firstTrack ?? TRACKS[0]).id;
  kind = trackFor(trackId).definition.car;

  const land = new Land(trackId, Number(q.get("grid") ?? 2048));
  const stage = await Stage.create({
    canvas: $<HTMLCanvasElement>("world"),
    land,
    tier: q.has("tier") ? Number(q.get("tier")) : undefined,
    terrain: { baseCell: 2, half: 64, levels: 7 },
    shadowReach: 11,
    camera: new THREE.PerspectiveCamera(62, 16 / 9, 0.3, 400_000),
  });
  if (!stage) {
    $("loading").hidden = true;
    $("failed").hidden = false;
    return;
  }
  $("loading-text").textContent = "Warming the tyres…";
  const { camera, field, near, pipeline, renderer, world, atmosphere, clouds } = stage;
  const shared: GroundUniforms = { uDetail: { value: detailTexture(renderer) }, uStyle: { value: kind === "racecar" ? 0 : 1 }, uLine: { value: 0 } };
  const baseGround = stage.terrain.mesh.material as THREE.ShaderMaterial;
  stage.terrain.mesh.material = groundMaterial(field, atmosphere.uniforms, clouds.shared, shared, baseGround);
  writeField(field, land.grid(), land.sink());

  let track: Track = trackFor(trackId);
  let line = new Line(track);
  let pilot = new Pilot(track, line);
  const lines = new Map<string, Line>([[trackId, line]]);
  let ribbon: THREE.Mesh = roadRibbon(track, line, field, atmosphere.uniforms, clouds.shared, shared);
  world.add(ribbon);
  let scenery: Scenery = buildScenery(track, line, atmosphere.uniforms);
  world.add(scenery.group);

  const vehicles: Partial<Record<Kind, Vehicle>> = {};
  const models: Partial<Record<Kind, { car: CarModel; ghost: CarModel }>> = {};
  const shadowPatch = buildShadowPatch();
  near.add(shadowPatch.mesh);
  // The road and the sand throw warm light up at a car; the sky alone would leave its flanks blue.
  near.add(new THREE.HemisphereLight(0x000000, 0xb09a78, 1.3));
  const sky = atmosphere.uniforms;
  const skid = new SkidMarks();
  const puffs = new Puffs(2600, sky.uSunDir, sky.uSunColor as { value: THREE.Color });
  near.add(skid.mesh, puffs.points);

  const garage = async (which: Kind): Promise<{ car: Vehicle; model: CarModel; ghost: CarModel }> => {
    let car = vehicles[which];
    if (!car) {
      car = await Vehicle.create(which, track);
      vehicles[which] = car;
      car.onLap = onLap;
      car.onSector = onSector;
      car.onInvalid = onInvalid;
      car.onStep = onStep;
      const parts = { car: new CarModel(which), ghost: new CarModel(which, true) };
      models[which] = parts;
      near.add(parts.car.root, parts.ghost.root);
    }
    const parts = models[which] as { car: CarModel; ghost: CarModel };
    car.track = track;
    for (const [name, set] of Object.entries(models)) {
      set.car.root.visible = name === which;
      if (name !== which) {
        set.ghost.root.visible = false;
      }
    }
    return { car, model: parts.car, ghost: parts.ghost };
  };

  const views = new Views(camera, (x, z) => (Math.abs(x) < 2040 && Math.abs(z) < 2040 ? Math.max(field.at(-z, x), 0) : 0));
  views.spots = scenery.spots;
  const hud = new Hud($<HTMLCanvasElement>("hud"));
  hud.setTrack(track);
  stage.onResize = (width, height) => hud.resize(width, height, Math.min(devicePixelRatio, 2));
  stage.resize();
  const sound = new CarVoice();
  const pedals = new Pedals();

  let phase: Phase = "title";
  let time = 0;
  let sessionLaps = 3;
  let grid = 0;
  let lit = -2;
  let lightsOutAt = 0;
  let wentAt = -9;
  let crashTimer = -1;
  let fading = 0;
  let ghostLap: GhostLap | null = null;
  let useGhost = true;
  const recording = new Recording();
  const pose: Pose = { x: 0, y: 0, z: 0, w: 1, qx: 0, qy: 0, qz: 0, steer: 0 };
  const hudState: HudState = { laps: 3, record: null, delta: null, flash: null, message: null, lights: -2, time: 0 };
  let carNow = vehicles[kind] as Vehicle;
  let modelNow: CarModel;
  let ghostModel: CarModel;

  const bestFor = (id: string): BestTime => new BestTime(`${KEY}-best-${id}`);
  const ghostKey = (id: string): string => `${KEY}-ghost-${id}`;

  function say(text: string, color: string, seconds = 2.2): void {
    hudState.message = { text, color, until: time + seconds };
  }

  function onSector(sector: number, seconds: number): void {
    if (phase !== "driving") {
      return;
    }
    hudState.flash = { text: `S${sector + 1}  ${seconds.toFixed(2)}`, color: COLOURS.WHITE, until: time + 2.4 };
  }

  function onInvalid(): void {
    if (phase === "driving") {
      sound.fault();
      say("TRACK LIMITS: LAP NOT COUNTED", COLOURS.HOT);
    }
  }

  function onStep(lapTime: number): void {
    recording.sample(carNow, lapTime);
  }

  function onLap(lap: Lap): void {
    if (phase !== "driving" && !DEMO) {
      return;
    }
    const best = bestFor(trackId);
    const before = best.get();
    const record = !DEMO && lap.valid && best.offer(lap.time);
    if (record && phase === "driving") {
      ghostLap = recording.take(lap.time);
      saveGhost(ghostKey(trackId), ghostLap);
    }
    recording.clear();
    hudState.record = best.get();
    sound.lap(record);
    if (!lap.valid) {
      hudState.flash = { text: `${lapText(lap.time)}  NOT COUNTED`, color: COLOURS.MUTED, until: time + 4 };
    } else if (record) {
      hudState.flash = { text: `${lapText(lap.time)}  BEST LAP`, color: COLOURS.BEST, until: time + 4 };
    } else {
      hudState.flash = { text: `${lapText(lap.time)}  ${before === null ? "" : deltaText(lap.time - before)}`, color: COLOURS.WHITE, until: time + 4 };
    }
    if (sessionLaps > 0 && carNow.laps.length >= sessionLaps && phase === "driving") {
      finishSession();
    }
  }

  // ---- Menus ---------------------------------------------------------------------------------
  const trackList = $("track");
  const describeBest = (id: string): string => {
    const record = bestFor(id).get();
    const medals = trackFor(id).definition.medals;
    if (!record) {
      return `Gold ${lapText(medals[0]).slice(0, -2)}`;
    }
    const medal = record <= medals[0] ? " gold" : record <= medals[1] ? " silver" : record <= medals[2] ? " bronze" : "";
    return `Best ${lapText(record)}${medal}`;
  };
  const fillTracks = (): void => {
    trackList.textContent = "";
    for (const definition of TRACKS.filter((t) => t.car === kind)) {
      const button = document.createElement("button");
      button.setAttribute("role", "radio");
      button.dataset.value = definition.id;
      const name = document.createElement("strong");
      name.textContent = definition.name;
      const text = document.createElement("span");
      text.textContent = `${(trackFor(definition.id).length / 1000).toFixed(1)} km. ${definition.blurb} `;
      const best = document.createElement("em");
      best.textContent = describeBest(definition.id);
      text.append(best);
      button.append(name, text);
      button.setAttribute("aria-checked", String(definition.id === trackId));
      button.addEventListener("click", () => void chooseTrack(definition.id));
      trackList.append(button);
    }
  };

  let changing = false;
  async function chooseTrack(id: string): Promise<void> {
    if (changing || (id === trackId && carNow)) {
      return;
    }
    changing = true;
    $("switching").hidden = false;
    trackId = id;
    track = trackFor(id);
    kind = track.definition.car;
    await land.change(id, SUNS[$<HTMLSelectElement>("time").value], field);
    let planned = lines.get(id);
    if (!planned) {
      planned = new Line(track);
      lines.set(id, planned);
    }
    line = planned;
    pilot = new Pilot(track, line);
    world.remove(ribbon);
    ribbon.geometry.dispose();
    (ribbon.material as THREE.Material).dispose();
    ribbon = roadRibbon(track, line, field, atmosphere.uniforms, clouds.shared, shared);
    world.add(ribbon);
    world.remove(scenery.group);
    scenery.dispose();
    scenery = buildScenery(track, line, atmosphere.uniforms);
    world.add(scenery.group);
    views.spots = scenery.spots;
    shared.uStyle.value = kind === "racecar" ? 0 : 1;
    hud.setTrack(track);
    const { car, model, ghost } = await garage(kind);
    carNow = car;
    modelNow = model;
    ghostModel = ghost;
    fillTracks();
    changing = false;
    attract();
    $("switching").hidden = true;
  }

  const setCar = choices<Kind>($("car"), (value) => {
    if (value !== kind) {
      void chooseTrack((TRACKS.find((t) => t.car === value) as { id: string }).id);
      kind = value;
    }
    fillTracks();
  }, kind);

  $<HTMLSelectElement>("time").value = "afternoon";
  $<HTMLSelectElement>("sky").value = "0.22";
  const applySky = (): void => {
    void stage.setSky($<HTMLSelectElement>("time").value, Number($<HTMLSelectElement>("sky").value));
  };
  $("time").addEventListener("change", applySky);
  $("sky").addEventListener("change", applySky);

  const show = (next: Phase): void => {
    phase = next;
    $("title").hidden = next !== "title";
    $("pause").hidden = next !== "paused";
    $("over").hidden = next !== "over";
    hud.clear();
    carNow.paused = next === "paused";
    if (next === "title") {
      sound.stop();
    }
  };

  const fresh = (): void => {
    skid.clear();
    puffs.clear();
    views.snap();
    pedals.reset();
    pipeline.flash = 0;
    crashTimer = -1;
    fading = 0;
    recording.clear();
    pilot.reset();
    hudState.flash = null;
    hudState.message = null;
    hudState.delta = null;
  };

  /** To the grid, with whatever the menu says. */
  const begin = (): void => {
    sessionLaps = Number($<HTMLSelectElement>("laps").value);
    useGhost = $<HTMLInputElement>("ghost").checked;
    shared.uLine.value = $<HTMLInputElement>("line").checked ? 1 : 0;
    carNow.autopilot = null;
    carNow.startRun();
    ghostLap = loadGhost(ghostKey(trackId));
    hudState.laps = sessionLaps;
    hudState.record = bestFor(trackId).get();
    fresh();
    grid = 0;
    lit = 0;
    scenery.setLights(0);
    lightsOutAt = 4.2 + 1.1 * Math.random();
    show("grid");
  };

  /** Behind the title the car runs the route by itself. */
  const attract = (): void => {
    carNow.startRun();
    carNow.go();
    carNow.autopilot = (car) => pilot.drive(car);
    carNow.paused = false;
    hudState.record = null;
    shared.uLine.value = 0;
    ghostModel.root.visible = false;
    views.view = "chase";
    lit = -2;
    scenery.setLights(-1);
    fresh();
  };

  const finishSession = (): void => {
    const { laps } = carNow;
    const list = $("over-laps");
    list.textContent = "";
    let quickest = Infinity;
    for (const lap of laps) {
      if (lap.valid) {
        quickest = Math.min(quickest, lap.time);
      }
    }
    laps.forEach((lap, i) => {
      const row = document.createElement("li");
      const name = document.createElement("span");
      name.textContent = `Lap ${i + 1}`;
      const value = document.createElement("b");
      value.textContent = lap.valid ? lapText(lap.time) : `${lapText(lap.time)} not counted`;
      if (lap.time === quickest) {
        row.className = "fastest";
      }
      row.append(name, value);
      list.append(row);
    });
    const medals = track.definition.medals;
    const best = bestFor(trackId).get();
    const medal = quickest === Infinity ? "" : quickest <= medals[0] ? "Gold" : quickest <= medals[1] ? "Silver" : quickest <= medals[2] ? "Bronze" : "";
    $("over-title").textContent = quickest === Infinity ? "No lap counted" : best !== null && quickest <= best + 1e-9 ? "New best lap" : "Session over";
    $("over-text").textContent = quickest === Infinity ? "Stay inside the white lines next time." : `Your quickest here: ${lapText(quickest)}. ${medal ? `That is ${medal === "Gold" ? "gold" : `a ${medal.toLowerCase()} medal`}.` : `Bronze starts at ${lapText(medals[2])}.`}`;
    // The car cools down on its own behind the panel.
    carNow.autopilot = (car) => {
      pilot.pace = 0.5;
      pilot.drive(car);
      pilot.pace = 0.97;
    };
    show("over");
  };

  $("go").addEventListener("click", () => {
    sound.start();
    begin();
  });
  $("resume").addEventListener("click", () => show("driving"));
  const toMenu = (): void => {
    attract();
    fillTracks();
    show("title");
  };
  $("restart").addEventListener("click", begin);
  $("quit").addEventListener("click", toMenu);
  $("again").addEventListener("click", begin);
  $("over-quit").addEventListener("click", toMenu);

  const cycleView = (): void => {
    views.view = VIEWS[(VIEWS.indexOf(views.view) + 1) % VIEWS.length] as View;
    views.snap();
  };
  const pause = (): void => {
    if (phase === "driving" || phase === "grid") {
      pausedFrom = phase;
      show("paused");
    } else if (phase === "paused") {
      show(pausedFrom);
    }
  };
  let pausedFrom: Phase = "driving";
  pedals.onButton = (name) => {
    if (name === "view") {
      cycleView();
    } else if (name === "pause") {
      pause();
    } else if (name === "reverse") {
      carNow.toggleReverse();
    } else if (phase === "driving" || phase === "over") {
      begin();
    }
  };
  addEventListener("keydown", (event) => {
    if (event.repeat) {
      return;
    }
    if (event.code === "KeyP" || event.code === "Escape") {
      pause();
    } else if ((phase === "driving" || phase === "over" || phase === "grid") && event.code === "KeyR") {
      begin();
    } else if (event.code === "KeyC") {
      cycleView();
    } else if (event.code === "KeyV") {
      carNow.toggleReverse();
    } else if (event.code === "KeyM") {
      sound.muted = !sound.muted;
    }
  });
  document.addEventListener("visibilitychange", () => {
    if (document.hidden && (phase === "driving" || phase === "grid")) {
      pause();
    }
  });
  const canvas = renderer.domElement;
  canvas.addEventListener("pointerdown", (event) => {
    views.dragging = true;
    canvas.setPointerCapture(event.pointerId);
  });
  canvas.addEventListener("pointerup", () => {
    views.dragging = false;
  });
  canvas.addEventListener("pointermove", (event) => {
    if (views.dragging) {
      views.azimuth -= event.movementX * 0.006;
      views.elevation = THREE.MathUtils.clamp(views.elevation - event.movementY * 0.006, -0.5, 1.2);
    }
  });
  canvas.addEventListener("wheel", (event) => {
    views.distance = THREE.MathUtils.clamp(views.distance * Math.exp(event.deltaY * 0.0009), 0.7, 2.4);
  }, { passive: true });

  // ---- The frame -----------------------------------------------------------------------------
  const contact = new THREE.Vector3();
  const across = new THREE.Vector3();
  const velocity = new THREE.Vector3();
  const grey = new THREE.Color(0.86, 0.86, 0.88);
  const stoneDust = new THREE.Color(0.62, 0.57, 0.48);
  const earth = new THREE.Color(0.62, 0.44, 0.28);
  const grassBits = new THREE.Color(0.32, 0.36, 0.16);
  let last = performance.now();
  let landing = 0;

  const drive = (dt: number): void => {
    const car = carNow;
    const speed = Math.max(car.get("speed"), 1);
    const data = CARS[car.kind];
    // The lock that stays useful: about what the tyres can turn into cornering at this speed.
    const reach = Math.min(1, (data.wheelbase * (car.kind === "racecar" ? 24 : 11)) / (speed * speed) / data.lock + 0.04);
    pedals.update(dt, reach);
    const v = pedals.value;
    const held = phase === "grid";
    car.setControls(v.steer, held ? 0 : v.throttle, held ? 1 : v.brake, v.handbrake);
  };

  /** What the wheels throw up, and the sound and shake of the surface. */
  const wheelsAtWork = (dt: number): { slip: number; loose: number; kerb: number; rumble: number } => {
    const car = carNow;
    const yaw = car.get("yaw");
    across.set(-Math.sin(yaw), 0, -Math.cos(yaw));
    const width = car.kind === "racecar" ? 0.14 : 0.16;
    const speed = car.get("speed");
    velocity.set(Math.cos(yaw) * speed, 0, -Math.sin(yaw) * speed);
    let slip = 0;
    let loose = 0;
    let kerb = 0;
    CORNERS.forEach((corner, i) => {
      const fz = car.get(`${corner}_fz`);
      const down = fz > 150;
      const kappa = Math.abs(car.get(`${corner}_kappa`));
      const alpha = Math.abs(car.get(`${corner}_alpha`));
      const surface = car.surfaces[i];
      const over = Math.max((kappa - 0.13) / 0.25, (alpha - 0.13) / 0.2);
      // Slip ratios mean nothing near a standstill.
      const scrub = down ? THREE.MathUtils.clamp(over, 0, 1) * Math.min(1, speed / 5) : 0;
      contact.set(car.get(`${corner}_xc`), car.get(`${corner}_yc`), car.get(`${corner}_zc`) + 0.015).applyMatrix4(modelNow.toScene);
      const hard = surface === "asphalt" || surface === "runoff" || surface === "kerb";
      const moving = Math.min(1, speed / 12);
      if (hard) {
        slip = Math.max(slip, scrub * Math.min(1, speed / 6));
        skid.add(i, contact, across, width, scrub * 0.62);
        if (surface === "kerb" && down) {
          kerb += 0.25;
        }
        if (scrub > 0.2 && Math.random() < dt * 60 * scrub) {
          contact.y += 0.12;
          puffs.emit(contact, velocity.x * 0.22 + (Math.random() - 0.5) * 2, 0.6 + Math.random(), velocity.z * 0.22 + (Math.random() - 0.5) * 2, 1.1 + Math.random(), 0.4, 2.8 + Math.random() * 1.5, grey, 0.34 * scrub + 0.05);
        }
      } else if (down) {
        loose += 0.25;
        const dirt = surface === "dirt" || surface === "loose" || surface === "scrub";
        skid.add(i, contact, across, width * 1.25, dirt ? 0.16 + 0.3 * scrub : 0.4);
        const rate = (dirt ? 15 : 10) * moving * (0.25 + 0.75 * Math.max(scrub, Math.min(1, speed / 30)));
        if (Math.random() < dt * rate) {
          contact.y += 0.1;
          const tone = surface === "grass" ? grassBits : surface === "gravel" ? stoneDust : earth;
          const lift = 0.8 + Math.random() * (1.2 + speed * 0.05);
          puffs.emit(contact, velocity.x * 0.34 + (Math.random() - 0.5) * 3, lift, velocity.z * 0.34 + (Math.random() - 0.5) * 3, 1.5 + Math.random() * 2.4, 0.6, 3.4 + Math.random() * 3 + speed * 0.05, tone, 0.34);
        }
      } else {
        skid.add(i, contact, across, width, 0);
      }
    });
    const total = CORNERS.reduce((sum, corner) => sum + car.get(`${corner}_fz`), 0);
    const weight = car.kind === "racecar" ? 7100 : 8900;
    // Coming down from a jump: the wheels take several times the weight at once.
    landing = Math.max(0, landing - dt);
    if (total > weight * 2.6 && landing === 0 && phase === "driving") {
      landing = 0.4;
      sound.thump();
      views.kick(1.4);
      const n = 26;
      for (let i = 0; i < n; i += 1) {
        const a = (i / n) * Math.PI * 2;
        contact.set(car.get("chassis_px") + Math.cos(a), car.get("chassis_py") + Math.sin(a), car.get("chassis_pz") - 0.6).applyMatrix4(modelNow.toScene);
        puffs.emit(contact, Math.cos(a) * 6, 0.8, -Math.sin(a) * 6, 1.4 + Math.random(), 0.8, 4 + Math.random() * 2, earth, 0.3);
      }
    }
    const rumble = kerb * Math.min(1, speed / 20) * 0.55 + loose * Math.min(1, speed / 25) * (car.kind === "racecar" ? 0.5 : 0.13);
    return { slip, loose, kerb, rumble };
  };

  /** Barriers are the game's, not the FMU's: a stop, dust, and a tow back to the road. */
  const crashes = (dt: number): void => {
    const car = carNow;
    if (car.crashed && crashTimer < 0) {
      crashTimer = 0;
      if (phase === "driving" || phase === "grid") {
        sound.crash();
        views.kick(4);
        say(car.crashReason === "rolled" ? "ROLLED: BACK ON THE ROAD" : "INTO THE BARRIER: BACK ON THE ROAD", COLOURS.HOT);
      }
      contact.set(car.get("chassis_px"), car.get("chassis_py"), car.get("chassis_pz")).applyMatrix4(modelNow.toScene);
      const tone = car.kind === "racecar" ? stoneDust : earth;
      for (let i = 0; i < 90; i += 1) {
        const a = Math.random() * Math.PI * 2;
        const r = 2 + Math.random() * 14;
        puffs.emit(contact, Math.cos(a) * r, Math.random() * 6, Math.sin(a) * r, 1.4 + Math.random() * 2, 0.6, 4 + Math.random() * 3, tone, 0.4);
      }
    }
    if (crashTimer >= 0) {
      crashTimer += dt;
      if (crashTimer > 1.3) {
        pipeline.flash = Math.min(1, (crashTimer - 1.3) / 0.3);
      }
      if (crashTimer > 1.65) {
        car.recover(car.s);
        pilot.reset();
        views.snap();
        crashTimer = -1;
        fading = 0.5;
      }
    } else if (fading > 0) {
      fading = Math.max(0, fading - dt);
      pipeline.flash = fading * 2;
    }
  };

  const updateGhost = (): void => {
    const car = carNow;
    const show = useGhost && phase === "driving" && ghostLap !== null && ghostLap.at(car.lapTime, pose) !== null;
    ghostModel.root.visible = show;
    if (show) {
      ghostModel.updateGhost(pose);
    }
    if (phase === "driving" && ghostLap) {
      const then = ghostLap.timeAt(car.s);
      hudState.delta = then === null || car.laps.length === 0 ? null : car.lapTime - then;
    }
  };

  const frame = (now: number): void => {
    const interval = now - last;
    last = now;
    const dt = Math.min(interval / 1000, 0.1);
    stage.judge(interval);
    requestAnimationFrame(frame);
    const car = carNow;
    if (changing) {
      // The old car on the new land is nobody's business.
      pipeline.flash = 1;
    }
    if (phase === "grid") {
      grid += dt;
      const count = Math.min(5, Math.floor(grid / 0.75));
      if (count !== lit && lit >= 0) {
        lit = count;
        if (count > 0) {
          sound.lightBeep(false);
        }
        scenery.setLights(count);
      }
      if (grid > lightsOutAt) {
        lit = -1;
        wentAt = time;
        scenery.setLights(-1);
        sound.lightBeep(true);
        car.go();
        phase = "driving";
        if (DEMO) {
          car.autopilot = (driven) => pilot.drive(driven);
        }
        hudState.flash = { text: "GO", color: COLOURS.GOOD, until: time + 1 };
      }
    }
    if ((phase === "grid" || phase === "driving") && !DEMO) {
      drive(dt);
    }
    if (phase !== "paused") {
      time += dt;
      car.advance(dt);
    }
    crashes(dt);
    modelNow.update(car, dt);
    const work = phase === "paused" ? { slip: 0, loose: 0, kerb: 0, rumble: 0 } : wheelsAtWork(dt);
    updateGhost();
    views.update(dt, car, modelNow, work.rumble, time);
    modelNow.mesh.inside.visible = views.view === "cockpit";
    modelNow.mesh.outside.visible = views.view !== "cockpit";
    shadowPatch.follow(car.kind, car.between("chassis_px"), car.between("chassis_py"));
    stage.shiftView(phase === "title" && innerWidth > 760);
    puffs.update(dt, renderer.domElement.height, camera.fov);

    if (phase === "grid" || phase === "driving" || phase === "over") {
      sound.update({
        rpm: car.get("motor_r_rpm"),
        load: car.get("motor_r_power") / (car.kind === "racecar" ? 260000 : 60000),
        slip: work.slip,
        loose: work.loose,
        kerb: work.kerb,
        speed: car.get("speed"),
        inside: views.view === "cockpit" ? 1 : 0,
      });
    }
    // Paint is not a mirror: less sky in it than the stage gives an aeroplane's skin.
    near.environmentIntensity = 0.32;
    stage.render(sunFocus(modelNow), time);

    if (phase === "grid" || phase === "driving") {
      hudState.lights = phase === "grid" ? lit : time < wentAt + 1.1 ? -1 : -2;
      hudState.time = time;
      hud.draw(car, hudState);
    }
    if (phase === "title" && car.laps.length >= 200) {
      attract();
    }
  };

  const focus = new THREE.Vector3();
  const sunFocus = (model: CarModel): THREE.Vector3 => focus.set(0, 0, 0).applyMatrix4(model.body.matrix).applyMatrix4(model.toScene);

  function buildShadowPatch(): { mesh: THREE.Mesh; follow(kind: Kind, x: number, y: number): void } {
    const cells = 30;
    const span = 15;
    const geometry = new THREE.PlaneGeometry(span, span, cells, cells);
    geometry.rotateX(-Math.PI / 2);
    const material = new THREE.ShadowMaterial({ opacity: 0.55, depthWrite: false, polygonOffset: true, polygonOffsetFactor: -2, polygonOffsetUnits: -6 });
    const mesh = new THREE.Mesh(geometry, material);
    mesh.receiveShadow = true;
    mesh.frustumCulled = false;
    const position = geometry.attributes.position as THREE.BufferAttribute;
    const from = (position.array as Float32Array).slice();
    return {
      mesh,
      follow(which, x, y): void {
        const cell = span / cells;
        const sx = Math.round(x / cell) * cell;
        const sy = Math.round(y / cell) * cell;
        for (let i = 0; i < position.count; i += 1) {
          const px = from[i * 3] + sx;
          const pz = from[i * 3 + 2] - sy;
          position.setXYZ(i, px, roadHeight(which, px, -pz) + 0.012, pz);
        }
        position.needsUpdate = true;
      },
    };
  }

  const first = await garage(kind);
  carNow = first.car;
  modelNow = first.model;
  ghostModel = first.ghost;
  fillTracks();
  $("loading").hidden = true;
  attract();
  show("title");
  if (DEMO) {
    $<HTMLSelectElement>("laps").value = "0";
    begin();
  }
  requestAnimationFrame(frame);
  announce({
    get car() {
      return carNow;
    },
    get model() {
      return modelNow;
    },
    get track() {
      return track;
    },
    views,
    stage,
    begin,
    setCar,
    chooseTrack,
    state: () => ({ phase, lights: lit, tier: stage.tier, view: views.view, track: trackId, kind, crashed: carNow.crashed, time: carNow.clock, laps: carNow.laps.length, kmh: Math.round(carNow.get("kmh")), s: Math.round(carNow.s), d: carNow.d, ghost: ghostModel.root.visible }),
  });
}

void main();
