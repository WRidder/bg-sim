/**
 * Everything a game's picture needs before the game has said anything: the renderer, the sky, the
 * clouds, the land and the sea, the final image, and a quality that drops by itself on a slow
 * machine. A game adds its own things to `world` (the ground, under the clouds) and `near` (what
 * stays sharp in front of them).
 */

import * as THREE from "three";
import { Atmosphere, type Sun } from "./atmosphere";
import { Clouds } from "./clouds";
import type { Grid } from "./heightfield";
import { Heightfield } from "./heightfield";
import { Ocean } from "./ocean";
import { Pipeline } from "./pipeline";
import { Terrain, type TerrainOptions } from "./terrain";

/** Height grid, and the terrain's shadow for a sun: made in a worker, so it can take a while. */
export interface LandSource {
  request(sun: Sun): Promise<{ grid?: Grid; shadow: Float32Array }>;
}

export const SUNS: Record<string, Sun> = {
  morning: { elevation: 14, azimuth: 105 },
  afternoon: { elevation: 34, azimuth: 235 },
  evening: { elevation: 9, azimuth: 262 },
};

const TIERS = [
  { scale: 1, steps: 72 },
  { scale: 0.85, steps: 56 },
  { scale: 0.7, steps: 44 },
  { scale: 0.55, steps: 34 },
];

export interface StageOptions {
  canvas: HTMLCanvasElement;
  land: LandSource;
  sun?: string;
  cover?: number;
  /** A fixed quality tier; without it the stage finds its own. */
  tier?: number;
  terrain?: TerrainOptions;
  /** How wide the sun's shadow box around the focus is, in metres. */
  shadowReach?: number;
  camera?: THREE.PerspectiveCamera;
}

export class Stage {
  readonly world = new THREE.Scene();
  readonly near = new THREE.Scene();
  readonly camera: THREE.PerspectiveCamera;
  tier: number;
  onResize: (width: number, height: number) => void = () => {};
  private slow = 0;
  private sunName: string;
  private readonly sunLight = new THREE.DirectionalLight(0xffffff, 1);
  private readonly groundLight = new THREE.DirectionalLight(0xffffff, 1);

  private constructor(
    readonly renderer: THREE.WebGLRenderer,
    readonly field: Heightfield,
    readonly atmosphere: Atmosphere,
    readonly clouds: Clouds,
    readonly terrain: Terrain,
    readonly ocean: Ocean,
    readonly pipeline: Pipeline,
    private readonly land: LandSource,
    private readonly fixedTier: boolean,
    options: StageOptions,
  ) {
    this.camera = options.camera ?? new THREE.PerspectiveCamera(66, 16 / 9, 1, 400_000);
    this.tier = options.tier ?? 0;
    this.sunName = options.sun ?? "afternoon";
    this.world.add(atmosphere.dome, terrain.mesh, ocean.mesh, this.groundLight);
    const light = this.sunLight;
    const reach = options.shadowReach ?? 12;
    light.castShadow = true;
    light.shadow.mapSize.set(2048, 2048);
    Object.assign(light.shadow.camera, { left: -reach, right: reach, top: reach, bottom: -reach, near: 50, far: 150 });
    light.shadow.bias = -0.0006;
    light.shadow.normalBias = 0.02;
    renderer.shadowMap.enabled = true;
    renderer.shadowMap.type = THREE.PCFShadowMap;
    this.near.add(light, light.target);
    this.relight();
    addEventListener("resize", () => this.resize());
  }

  /** Null when this browser has no WebGL 2. */
  static async create(options: StageOptions): Promise<Stage | null> {
    let renderer: THREE.WebGLRenderer;
    try {
      renderer = new THREE.WebGLRenderer({ canvas: options.canvas, antialias: false, powerPreference: "high-performance" });
    } catch {
      return null;
    }
    const sun = SUNS[options.sun ?? "afternoon"];
    const { grid, shadow } = await options.land.request(sun);
    if (!grid) {
      throw new Error("The land came back without its grid");
    }
    const field = new Heightfield(grid, shadow);
    const atmosphere = new Atmosphere(renderer);
    atmosphere.setSun(sun);
    const clouds = new Clouds(atmosphere.uniforms, { cover: options.cover ?? 0.3 });
    const terrain = new Terrain(field, atmosphere.uniforms, clouds.shared, options.terrain);
    const ocean = new Ocean(field, atmosphere.uniforms);
    const pipeline = new Pipeline(renderer, clouds);
    const stage = new Stage(renderer, field, atmosphere, clouds, terrain, ocean, pipeline, options.land, options.tier !== undefined, options);
    stage.resize();
    return stage;
  }

  /** Bilinear ground height at a point, the sea floor below zero. */
  ground = (north: number, east: number): number => this.field.at(north, east);

  private relight(): void {
    const { atmosphere, near, world } = this;
    const { uSunColor, uSunDir } = atmosphere.uniforms;
    this.sunLight.color.copy(uSunColor.value).multiplyScalar(0.8);
    this.groundLight.color.copy(uSunColor.value).multiplyScalar(0.5);
    this.groundLight.position.copy(uSunDir.value);
    near.environment = atmosphere.environment;
    near.environmentIntensity = 0.55;
    world.environment = atmosphere.environment;
    world.environmentIntensity = 0.45;
  }

  /** Changes the time of day and the cloud cover. */
  async setSky(sunName: string, cover: number): Promise<void> {
    this.clouds.shared.uCover.value = cover;
    if (sunName !== this.sunName) {
      this.sunName = sunName;
      this.atmosphere.setSun(SUNS[sunName]);
      this.relight();
      this.field.setShadow((await this.land.request(SUNS[sunName])).shadow);
    }
  }

  resize(): void {
    const width = innerWidth;
    const height = innerHeight;
    const ratio = Math.min(devicePixelRatio, 1.5) * TIERS[this.tier].scale;
    const w = Math.round(width * ratio);
    const h = Math.round(height * ratio);
    this.renderer.setPixelRatio(1);
    this.renderer.setSize(w, h, false);
    this.pipeline.resize(w, h);
    this.clouds.steps = TIERS[this.tier].steps;
    this.camera.aspect = width / height;
    this.onResize(width, height);
  }

  /**
   * Builds the shaders of everything in the two scenes, shown or not. A game calls it behind its
   * loading screen once its objects are in: what is first drawn later (an effect, a weapon) then
   * costs no frame. The compile runs beside the page; one hidden draw of every object then makes
   * the browser finish what it leaves until a shader is first used.
   */
  async warm(): Promise<void> {
    const { camera, pipeline, renderer } = this;
    // The programs depend on where they draw to; this is where the pipeline draws the scenes.
    renderer.setRenderTarget(pipeline.scene);
    await Promise.all([renderer.compileAsync(this.world, camera), renderer.compileAsync(this.near, camera)]);
    const kept: [THREE.Object3D, boolean, boolean][] = [];
    for (const scene of [this.world, this.near]) {
      scene.traverse((object) => {
        kept.push([object, object.visible, object.frustumCulled]);
        object.visible = true;
        object.frustumCulled = false;
      });
    }
    renderer.setRenderTarget(pipeline.scene);
    renderer.render(this.world, camera);
    renderer.render(this.near, camera);
    renderer.setRenderTarget(null);
    for (const [object, visible, culled] of kept) {
      object.visible = visible;
      object.frustumCulled = culled;
    }
  }

  /**
   * Feeds in the time between two frames; a run of slow ones lowers the quality. One frame counts
   * for at most 100 ms: a single long stop (a tab switch, a compile) says nothing about the speed.
   */
  judge(milliseconds: number): void {
    milliseconds = Math.min(milliseconds, 100);
    this.slow = milliseconds > 24 ? this.slow + milliseconds : Math.max(0, this.slow - milliseconds * 0.5);
    if (this.slow > 1800 && this.tier < TIERS.length - 1 && !this.fixedTier) {
      this.tier += 1;
      this.slow = 0;
      this.resize();
    }
  }

  /** Lights what is near `focus`, then draws the frame. */
  render(focus: THREE.Vector3, time: number): void {
    const { uSunDir } = this.atmosphere.uniforms;
    this.sunLight.position.copy(focus).addScaledVector(uSunDir.value, 100);
    this.sunLight.target.position.copy(focus);
    this.terrain.follow(this.camera.position);
    this.ocean.update(this.camera.position, time, this.renderer);
    this.pipeline.render(this.world, this.near, this.camera, time);
  }

  /** Slides the picture over, so a menu can have the left of the screen. */
  private shifted = false;
  shiftView(on: boolean): void {
    if (on === this.shifted) {
      return;
    }
    this.shifted = on;
    if (on) {
      this.camera.setViewOffset(innerWidth, innerHeight, -innerWidth * 0.2, innerHeight * 0.06, innerWidth, innerHeight);
    } else {
      this.camera.clearViewOffset();
    }
    this.camera.updateProjectionMatrix();
  }
}
