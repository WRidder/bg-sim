/**
 * The buggy: a tube frame you can see through, a roll cage, long dampers and tall knobbly tyres. The
 * few panels on it are dented flat sheet, painted in sand and rust, with a light bar for show.
 */

import * as THREE from "three";
import { CARS } from "./vehicle";
import { bent, both, box, carbon, type Glow, loft, matte, merge, steel, tube, turned, type WheelParts } from "./parts";
import type { CarMesh } from "./racecar";

const { front: A, rear: B, wheelRadius: R } = CARS.buggy;
const G = -CARS.buggy.rideHeight;

function knobbly(width: number): THREE.BufferGeometry {
  const h = width / 2;
  const core = R - 0.035;
  const parts: THREE.BufferGeometry[] = [
    turned([[0.19, -h * 0.95], [core - 0.06, -h], [core, -h * 0.82], [core, h * 0.82], [core - 0.06, h], [0.19, h * 0.95]], 40),
  ];
  // Chunky blocks in two offset rows, with shoulder lugs that wrap the edge.
  const count = 22;
  for (let i = 0; i < count; i += 1) {
    const a = (i / count) * Math.PI * 2;
    for (const [z, wide, shift] of [[-h * 0.48, h * 0.62, 0], [h * 0.48, h * 0.62, 0.5]] as const) {
      const at = a + (shift * Math.PI * 2) / count;
      const lug = new THREE.BoxGeometry(0.05, 0.078, wide);
      lug.rotateZ(0.24 * Math.sign(z));
      lug.translate(core + 0.02, 0, z);
      lug.rotateZ(at);
      parts.push(lug);
      const shoulder = new THREE.BoxGeometry(0.06, 0.07, 0.05);
      shoulder.translate(core - 0.022, 0, Math.sign(z) * h * 0.98);
      shoulder.rotateZ(at + 0.14);
      parts.push(shoulder);
    }
  }
  return merge(parts);
}

function wheel(side: 1 | -1, tyre: THREE.BufferGeometry, rubber: THREE.Material, rim: THREE.Material, dark: THREE.Material): WheelParts {
  const parts = new THREE.Group();
  const h = 0.13;
  const shell = new THREE.Mesh(tyre, rubber);
  const barrel = new THREE.Mesh(turned([[0.185, h], [0.2, h * 0.92], [0.17, h * 0.6], [0.17, -h * 0.6], [0.2, -h * 0.92], [0.185, -h]], 32), rim);
  const dish: THREE.BufferGeometry[] = [turned([[0, h * 0.5], [0.06, h * 0.5], [0.075, h * 0.2]], 16)];
  for (let i = 0; i < 6; i += 1) {
    const a = (i / 6) * Math.PI * 2;
    dish.push(tube(Math.cos(a) * 0.05, Math.sin(a) * 0.05, h * 0.42, Math.cos(a) * 0.178, Math.sin(a) * 0.178, h * 0.62, 0.018, 6));
  }
  // Beadlock bolts round the rim.
  for (let i = 0; i < 16; i += 1) {
    const a = (i / 16) * Math.PI * 2;
    const bolt = new THREE.CylinderGeometry(0.007, 0.007, 0.014, 6).rotateX(Math.PI / 2);
    bolt.translate(Math.cos(a) * 0.196, Math.sin(a) * 0.196, h * 0.98);
    dish.push(bolt);
  }
  const star = merge(dish);
  const face = new THREE.Mesh(side > 0 ? star : star.clone().rotateY(Math.PI), dark);
  parts.add(shell, barrel, face);
  parts.traverse((mesh) => {
    mesh.castShadow = true;
  });
  const hub = new THREE.Group();
  const disc = new THREE.Mesh(turned([[0.05, -0.012], [0.13, -0.012], [0.13, 0.012], [0.05, 0.012]], 20), steel(0x3a3a3e, 0.5, 0.8));
  disc.position.z = -side * 0.05;
  hub.add(disc);
  return { wheel: parts, hub };
}

export function buildBuggy(): CarMesh {
  const body = new THREE.Group();
  const frame = steel(0x25282a, 0.55, 0.6);
  const cage = new THREE.MeshStandardMaterial({ color: 0xc9401a, roughness: 0.42, metalness: 0.35 });
  const fibre = carbon();
  const sheet = new THREE.MeshStandardMaterial({ color: 0xffffff, roughness: 0.55, metalness: 0 });
  sheet.onBeforeCompile = (shader) => {
    shader.vertexShader = shader.vertexShader.replace("#include <common>", "#include <common>\nvarying vec3 vBody;").replace("#include <begin_vertex>", "#include <begin_vertex>\nvBody = position;");
    shader.fragmentShader = shader.fragmentShader.replace("#include <common>", "#include <common>\nvarying vec3 vBody;").replace(
      "#include <color_fragment>",
      /* glsl */ `#include <color_fragment>
      vec3 sand = vec3(0.70, 0.60, 0.43);
      vec3 rust = vec3(0.58, 0.15, 0.04);
      float stripe = smoothstep(0.17, 0.175, abs(vBody.y - 0.0)) ;
      vec3 paint = mix(rust, sand, stripe);
      float dust = smoothstep(-0.55, -0.15, -vBody.z - 0.2);
      diffuseColor.rgb = mix(paint, vec3(0.5, 0.38, 0.26), dust * 0.55);`,
    );
  };
  const add = (geometry: THREE.BufferGeometry, material: THREE.Material): THREE.Mesh => {
    const mesh = new THREE.Mesh(geometry, material);
    mesh.castShadow = true;
    mesh.receiveShadow = true;
    body.add(mesh);
    return mesh;
  };

  const r = 0.026;
  const low = G + 0.3;
  const belt = G + 0.68;
  const roof = G + 1.5;
  const noseX = A + 0.74;
  const tailX = B - 0.78;
  // The main rails, the same both sides.
  add(both(merge([
    bent([[noseX, 0.3, low + 0.24], [A + 0.4, 0.46, low], [A - 0.3, 0.5, low], [B + 0.3, 0.5, low], [tailX, 0.34, low + 0.22]], r),
    bent([[noseX, 0.3, low + 0.24], [A + 0.42, 0.5, belt - 0.06], [A - 0.5, 0.56, belt], [B + 0.3, 0.56, belt], [tailX, 0.34, low + 0.22]], r),
    bent([[A + 0.42, 0.5, belt - 0.06], [A + 0.4, 0.46, low]], r),
    bent([[A - 0.5, 0.56, belt], [A - 0.5, 0.5, low]], r),
    bent([[B + 0.3, 0.56, belt], [B + 0.3, 0.5, low]], r),
    bent([[A + 0.42, 0.5, belt - 0.06], [A - 0.5, 0.5, low]], r * 0.8),
    bent([[B + 0.3, 0.56, belt], [A - 0.5, 0.5, low]], r * 0.8),
    bent([[B + 0.3, 0.5, low], [tailX + 0.1, 0.36, G + 1.02]], r * 0.8),
    bent([[B + 0.3, 0.56, belt], [tailX + 0.1, 0.36, G + 1.02]], r * 0.8),
  ])), frame);
  for (const x of [noseX, A + 0.4, A - 0.3, A - 1.6, B + 0.3, tailX]) {
    const y = x === noseX || x === tailX ? 0.32 : 0.5;
    const z = x === noseX || x === tailX ? low + 0.24 : low;
    add(tube(x, -y, z, x, y, z, r * 0.9), frame);
  }
  // The cage, in its own colour: A pillars, roof hoop, main hoop, rear stays and a door bar.
  const mainX = A - 2.0;
  add(both(merge([
    bent([[A - 0.5, 0.56, belt], [A - 1.0, 0.58, G + 1.42], [A - 1.3, 0.5, roof], [mainX, 0.48, roof], [mainX - 0.14, 0.56, G + 1.3], [mainX, 0.56, belt]], 0.03),
    bent([[mainX - 0.1, 0.52, G + 1.4], [tailX + 0.1, 0.36, G + 1.02]], 0.026),
    bent([[A - 0.65, 0.57, G + 0.98], [mainX - 0.04, 0.57, G + 0.98]], 0.024),
  ])), cage);
  add(tube(A - 1.3, -0.5, roof, A - 1.3, 0.5, roof, 0.03), cage);
  add(tube(mainX, -0.48, roof, mainX, 0.48, roof, 0.03), cage);
  add(tube(mainX, -0.48, roof, A - 1.3, 0.5, roof, 0.024), cage);
  add(tube(A - 0.5, -0.56, belt, A - 0.5, 0.56, belt, 0.028), cage);
  add(tube(mainX - 0.14, -0.56, G + 1.3, mainX - 0.14, 0.56, G + 1.3, 0.026), cage);

  // Panels: bonnet, roof skin, floor and the skid plate under the nose.
  add(loft([
    { x: noseX - 0.02, w: 0.3, top: 0.025, bottom: 0.03, z: low + 0.36, n: 6 },
    { x: A + 0.3, w: 0.46, top: 0.05, bottom: 0.03, z: belt - 0.1, n: 6 },
    { x: A - 0.42, w: 0.5, top: 0.075, bottom: 0.03, z: belt + 0.06, n: 8 },
    { x: A - 0.46, w: 0.5, top: 0.02, bottom: 0.03, z: belt + 0.09, n: 8 },
  ], 24, 24), sheet);
  add(box(mainX - 0.02, -0.46, roof + 0.03, A - 1.32, 0.46, roof + 0.038), sheet);
  add(box(B + 0.3, -0.49, low + 0.02, A + 0.4, 0.49, low + 0.03), fibre);
  add(box(A + 0.38, -0.36, low - 0.09, noseX, 0.36, low + 0.03).rotateY(0.0), steel(0x5e6266, 0.5, 0.8));
  // Side panels between the belt and the floor.
  add(both(box(B + 0.32, 0.525, low + 0.05, A - 0.52, 0.53, belt - 0.05)), sheet);
  // Mudguards over the rear wheels, and front ones cut high for the long travel.
  const guard = (x: number): THREE.BufferGeometry => {
    const shape: THREE.BufferGeometry[] = [];
    const rows = 10;
    for (let i = 0; i < rows; i += 1) {
      const a0 = Math.PI * 0.12 + (i / rows) * Math.PI * 0.6;
      const a1 = Math.PI * 0.12 + ((i + 1) / rows) * Math.PI * 0.6;
      const rise = R + 0.22;
      shape.push(tube(x + Math.cos(a0) * rise, 0.87, G + R + Math.sin(a0) * rise, x + Math.cos(a1) * rise, 0.87, G + R + Math.sin(a1) * rise, 0.012, 5));
      const sheetPart = new THREE.BoxGeometry((rise * Math.PI * 0.6) / rows + 0.01, 0.3, 0.006);
      sheetPart.rotateY(-(a0 + a1) / 2 + Math.PI / 2);
      sheetPart.translate(x + (Math.cos(a0) + Math.cos(a1)) * rise * 0.5, 0.87, G + R + (Math.sin(a0) + Math.sin(a1)) * rise * 0.5);
      shape.push(sheetPart);
    }
    return merge(shape);
  };
  add(both(guard(B)), sheet);
  add(both(guard(A)), sheet);

  // The drive units front and rear, and the battery box behind the seats.
  add(box(A - 0.25, -0.2, low + 0.06, A + 0.22, 0.2, low + 0.3), steel(0x34373a, 0.5, 0.7));
  add(box(B - 0.25, -0.22, low + 0.04, B + 0.25, 0.22, low + 0.32), steel(0x34373a, 0.5, 0.7));
  add(box(B + 0.3, -0.42, belt + 0.02, A - 1.92, 0.42, belt + 0.26), matte(0x1a1c1e, 0.6));
  add(box(tailX + 0.06, -0.3, G + 0.82, B - 0.2, 0.3, G + 0.86), frame);
  // The spare, flat on the rear deck.
  const spareTyre = new THREE.Mesh(knobbly(0.26), matte(0x111112, 0.92));
  spareTyre.position.set(B - 0.3, 0, G + 0.97);
  spareTyre.castShadow = true;
  body.add(spareTyre);

  // Lights: a bar on the roof, two round lamps on the nose, and the brake lamps at the back.
  const lens = new THREE.MeshStandardMaterial({ color: 0xffffff, roughness: 0.1, emissive: 0xffeecc, emissiveIntensity: 1.6 });
  add(box(A - 1.27, -0.42, roof + 0.05, A - 1.24, 0.42, roof + 0.13), matte(0x0c0d0e, 0.5));
  for (let i = 0; i < 6; i += 1) {
    const y = -0.34 + i * 0.136;
    add(new THREE.CylinderGeometry(0.03, 0.03, 0.01, 16).rotateZ(Math.PI / 2).translate(A - 1.235, y, roof + 0.09), lens);
  }
  add(both(new THREE.CylinderGeometry(0.075, 0.09, 0.09, 20).rotateZ(Math.PI / 2).translate(noseX + 0.03, 0.22, low + 0.42)), matte(0x0c0d0e, 0.4));
  add(both(new THREE.CylinderGeometry(0.066, 0.066, 0.01, 20).rotateZ(Math.PI / 2).translate(noseX + 0.08, 0.22, low + 0.42)), lens);
  const brake: Glow = { value: 0 };
  const lamp = new THREE.ShaderMaterial({
    uniforms: { uOn: brake },
    vertexShader: "void main() { gl_Position = projectionMatrix * modelViewMatrix * vec4(position, 1.0); }",
    fragmentShader: "uniform float uOn; void main() { gl_FragColor = vec4(vec3(0.5 + uOn * 8.0, 0.02 + uOn * 0.5, 0.01 + uOn * 0.3), 1.0); }",
  });
  add(both(box(tailX + 0.04, 0.22, G + 0.82, tailX + 0.06, 0.32, G + 0.9)), lamp);

  // The crew, belted in behind a low screen of mesh: helmets and shoulders.
  const person = (y: number, tone: number): void => {
    const helmet = new THREE.Mesh(new THREE.SphereGeometry(0.125, 24, 18), new THREE.MeshPhysicalMaterial({ color: tone, roughness: 0.3, clearcoat: 1 }));
    helmet.position.set(-0.24, y, G + 1.3);
    helmet.scale.set(1.08, 0.98, 1);
    helmet.castShadow = true;
    const visor = new THREE.Mesh(new THREE.SphereGeometry(0.128, 18, 10, -0.9, 1.8, 1.25, 0.55), new THREE.MeshStandardMaterial({ color: 0x050608, roughness: 0.1, metalness: 0.7 }));
    visor.position.copy(helmet.position);
    visor.rotation.x = Math.PI / 2;
    const torso = new THREE.Mesh(loft([
      { x: -0.18, w: 0.17, top: 0.1, bottom: 0.3, z: G + 1.02, y, n: 3 },
      { x: -0.36, w: 0.17, top: 0.12, bottom: 0.3, z: G + 1.02, y, n: 3 },
    ], 4, 14), matte(0x2c3136, 0.85));
    torso.castShadow = true;
    const seat = new THREE.Mesh(box(-0.5, y - 0.2, G + 0.56, -0.38, y + 0.2, G + 1.34), matte(0x101214, 0.8));
    body.add(helmet, visor, torso, seat);
  };
  person(0.3, 0xd8d2c0);
  person(-0.3, 0x2a4a5a);

  const inside = new THREE.Group();
  const wheelRim = new THREE.Mesh(new THREE.TorusGeometry(0.17, 0.016, 10, 30).rotateY(Math.PI / 2).translate(0.26, 0.3, G + 1.04), matte(0x121416, 0.9));
  const column = new THREE.Mesh(tube(0.26, 0.3, G + 1.04, 0.7, 0.3, G + 0.84, 0.018), frame);
  inside.add(wheelRim, column);
  inside.visible = false;
  body.add(inside);

  const tyre = knobbly(0.34);
  const rubber = matte(0x0d0d0e, 0.94);
  const rim = steel(0x8d8778, 0.62, 0.3);
  const dark = steel(0x1c1e20, 0.5, 0.7);
  const wheels: WheelParts[] = [wheel(1, tyre, rubber, rim, dark), wheel(-1, tyre, rubber, rim, dark), wheel(1, tyre, rubber, rim, dark), wheel(-1, tyre, rubber, rim, dark)];
  return { body, wheels, eye: new THREE.Vector3(-0.2, 0.3, G + 1.36), brake, heat: { value: 0 }, inside, outside: new THREE.Group() };
}
