/** A camera and a world, no game: for judging the look from screenshots. */

import * as THREE from "three";
import { Atmosphere, type Sun } from "../engine/atmosphere";
import { Clouds } from "../engine/clouds";
import { computeGrid, computeShadow, Heightfield } from "../engine/heightfield";
import { Ocean } from "../engine/ocean";
import { Pipeline } from "../engine/pipeline";
import { Terrain } from "../engine/terrain";
import { buildFighter } from "./aircraft";
import { EXTENT, islandHeight, islandMask } from "../island/island";

const q = new URLSearchParams(location.search);
const num = (key: string, fallback: number): number => Number(q.get(key) ?? fallback);
const canvas = document.querySelector("canvas") as HTMLCanvasElement;
const renderer = new THREE.WebGLRenderer({ canvas, antialias: false, powerPreference: "high-performance" });
const width = 1280;
const height = 720;
renderer.setSize(width, height, false);

const t0 = performance.now();
const grid = computeGrid(num("grid", 2048), EXTENT, islandHeight, islandMask);
const sun: Sun = { elevation: num("sunel", 24), azimuth: num("sunaz", 235) };
const atmosphere = new Atmosphere(renderer);
atmosphere.setSun(sun);
const field = new Heightfield(grid, computeShadow(grid, atmosphere.uniforms.uSunDir.value));
const t1 = performance.now();

const scene = new THREE.Scene();
const near = new THREE.Scene();
scene.add(atmosphere.dome);
const clouds = new Clouds(atmosphere.uniforms, { cover: num("cover", 0.3) });
const terrain = new Terrain(field, atmosphere.uniforms, clouds.shared);
scene.add(terrain.mesh);
const ocean = new Ocean(field, atmosphere.uniforms);
scene.add(ocean.mesh);
const pipeline = new Pipeline(renderer, clouds);
pipeline.resize(width, height);

if (q.has("plane")) {
  near.environment = atmosphere.environment;
  const sunLight = new THREE.DirectionalLight(0xffffff, 1);
  sunLight.color.copy(atmosphere.uniforms.uSunColor.value).multiplyScalar(0.62);
  near.add(sunLight, sunLight.target);
  const fighter = buildFighter();
  // Mesh frame (x forward, y left, z up) to world (x east, y up, z south), flying north.
  fighter.root.rotation.set(-Math.PI / 2, 0, Math.PI / 2, "XYZ");
  const place = new THREE.Group();
  place.add(fighter.root);
  place.position.set(num("e", 0), num("h", 3048), -num("n", 0));
  place.rotation.set((num("pp", 0) * Math.PI) / 180, (num("py", 0) * Math.PI) / 180, (num("pr", 0) * Math.PI) / 180, "YXZ");
  near.add(place);
  sunLight.position.copy(place.position).addScaledVector(atmosphere.uniforms.uSunDir.value, 100);
  sunLight.target.position.copy(place.position);
  sunLight.castShadow = true;
  sunLight.shadow.mapSize.set(2048, 2048);
  sunLight.shadow.camera.left = -12;
  sunLight.shadow.camera.right = 12;
  sunLight.shadow.camera.top = 12;
  sunLight.shadow.camera.bottom = -12;
  sunLight.shadow.camera.near = 50;
  sunLight.shadow.camera.far = 150;
  sunLight.shadow.bias = -0.0006;
  sunLight.shadow.normalBias = 0.02;
  renderer.shadowMap.enabled = true;
  renderer.shadowMap.type = THREE.PCFShadowMap;
  fighter.flamePower.value = num("ab", 0);
  fighter.flame.visible = q.has("ab");
}

const camera = new THREE.PerspectiveCamera(num("fov", 60), width / height, 2, 400_000);
camera.position.set(num("e", 0) + num("ce", 0), num("h", 3048) + num("cu", 0), -num("n", 0) - num("cn", 0));
const yaw = (num("yaw", 0) * Math.PI) / 180;
const pitch = (num("pitch", -8) * Math.PI) / 180;
camera.lookAt(
  camera.position.x + Math.sin(yaw) * Math.cos(pitch),
  camera.position.y + Math.sin(pitch),
  camera.position.z - Math.cos(yaw) * Math.cos(pitch),
);
camera.updateMatrixWorld();
camera.updateProjectionMatrix();
terrain.follow(camera.position);
ocean.update(camera.position, 10, renderer);
const t2 = performance.now();
pipeline.render(scene, near, camera, 10);
const gl = renderer.getContext();
const pixel = new Uint8Array(4);
const sync = () => gl.readPixels(0, 0, 1, 1, gl.RGBA, gl.UNSIGNED_BYTE, pixel);
sync();
const t3 = performance.now();
for (let i = 0; i < 30; i += 1) {
  pipeline.render(scene, near, camera, 10 + i / 60);
  sync();
}
const frameMs = (performance.now() - t3) / 30;
const info = gl.getExtension("WEBGL_debug_renderer_info");
(window as unknown as { ready: unknown }).ready = {
  fieldMs: Math.round(t1 - t0),
  setupMs: Math.round(t2 - t1),
  firstMs: Math.round(t3 - t2),
  frameMs: Math.round(frameMs * 10) / 10,
  gpu: info ? gl.getParameter(info.UNMASKED_RENDERER_WEBGL) : "?",
  max: field.heights.reduce((a, b) => Math.max(a, b), 0),
  landShare: field.heights.filter((h) => h > 0).length / field.heights.length,
};
