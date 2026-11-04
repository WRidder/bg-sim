/**
 * The race car, built in code: a single-seater of about the size the FMU's masses say, every panel
 * from sections or wing profiles. The paint is computed per pixel from the body position, the way
 * the fighter's is, so the stripe and the number stay sharp in the closest view.
 */

import * as THREE from "three";
import { CARS } from "./vehicle";
import { both, bent, box, carbon, type Glow, hose, loft, matte, merge, type Section, steel, tube, turned, type WheelParts, wing } from "./parts";

const { front: A, rear: B, wheelRadius: R } = CARS.racecar;
/** The ground in the chassis frame, at rest. */
const G = -CARS.racecar.rideHeight;
/** The cockpit opening: centre and half lengths on the top of the tub. */
const HOLE_X = A - 1.27;
const HOLE_LONG = 0.62;
const HOLE_WIDE = 0.235;

function numberTexture(): THREE.CanvasTexture {
  const canvas = document.createElement("canvas");
  canvas.width = 256;
  canvas.height = 256;
  const c = canvas.getContext("2d") as CanvasRenderingContext2D;
  c.fillStyle = "#000";
  c.fillRect(0, 0, 256, 256);
  c.fillStyle = "#fff";
  c.font = 'italic 700 210px "Bahnschrift", "Arial Narrow", sans-serif';
  c.textAlign = "center";
  c.textBaseline = "middle";
  c.fillText("7", 118, 136);
  const texture = new THREE.CanvasTexture(canvas);
  texture.anisotropy = 8;
  return texture;
}

/** Two tones split by a slash of colour, a stripe down the spine and the number on the flanks. */
function livery(): THREE.MeshPhysicalMaterial {
  const material = new THREE.MeshPhysicalMaterial({ color: 0xffffff, roughness: 0.42, metalness: 0, clearcoat: 0.25, clearcoatRoughness: 0.22 });
  const number = { value: numberTexture() };
  material.onBeforeCompile = (shader) => {
    shader.uniforms.uNumber = number;
    shader.vertexShader = shader.vertexShader
      .replace("#include <common>", "#include <common>\nvarying vec3 vBody;")
      .replace("#include <begin_vertex>", "#include <begin_vertex>\nvBody = position;");
    shader.fragmentShader = shader.fragmentShader
      .replace("#include <common>", "#include <common>\nvarying vec3 vBody;\nuniform sampler2D uNumber;")
      .replace(
        "#include <color_fragment>",
        /* glsl */ `#include <color_fragment>
        vec3 deep = vec3(0.012, 0.055, 0.095);
        vec3 pale = vec3(0.88, 0.82, 0.70);
        vec3 hot = vec3(0.95, 0.20, 0.035);
        float slash = vBody.x + vBody.z * 1.6 - 0.42;
        vec3 paint = mix(deep, pale, smoothstep(-0.004, 0.004, slash));
        float cut = abs(slash + 0.11);
        paint = mix(paint, hot, 1.0 - smoothstep(0.088, 0.092, cut));
        float spine = abs(vBody.y);
        if (vBody.x > 0.75) paint = mix(paint, hot, 1.0 - smoothstep(0.038, 0.042, spine));
        // The number, on the engine cover's flanks.
        vec2 tag = (vec2(-vBody.x * sign(vBody.y) , vBody.z) - vec2(0.9 * sign(vBody.y), 0.17)) / 0.3 + 0.5;
        if (abs(vBody.y) > 0.05 && abs(vBody.y) < 0.45 && tag.x > 0.0 && tag.x < 1.0 && tag.y > 0.0 && tag.y < 1.0) {
          paint = mix(paint, hot, texture2D(uNumber, tag).r);
        }
        // Inside the opening: the padded rim and the dark of the tub.
        vec2 hole = vec2((vBody.x - (${HOLE_X.toFixed(3)})) / ${HOLE_LONG.toFixed(3)}, vBody.y / ${HOLE_WIDE.toFixed(3)});
        paint = mix(vec3(0.012), paint, smoothstep(0.99, 1.0, dot(hole, hole)) + step(vBody.z, ${(G + 0.2).toFixed(3)}));
        diffuseColor.rgb = paint;`,
      );
  };
  return material;
}

function wheel(side: 1 | -1, front: boolean, glow: Glow, rubber: THREE.Material, rim: THREE.Material, rimDark: THREE.Material, wall: THREE.Material): WheelParts {
  const width = front ? 0.27 : 0.34;
  const h = width / 2;
  const outer = R;
  const bead = 0.205;
  // Axle along z; `side` is which way the outside of the wheel faces.
  const tread = turned([[bead, -h * 0.9], [outer - 0.05, -h * 0.98], [outer - 0.012, -h * 0.86], [outer, -h * 0.5], [outer, h * 0.5], [outer - 0.012, h * 0.86], [outer - 0.05, h * 0.98], [bead, h * 0.9]], 56);
  const sidewall = turned([[bead, h * 0.92], [outer - 0.05, h * 0.99]], 56);
  const parts = new THREE.Group();
  const shell = new THREE.Mesh(tread, rubber);
  const face = new THREE.Mesh(side > 0 ? sidewall : sidewall.clone().rotateY(Math.PI), wall);
  const barrel = new THREE.Mesh(turned([[bead - 0.012, h * 0.95], [bead - 0.03, h * 0.8], [bead - 0.04, -h * 0.8], [bead - 0.012, -h * 0.95]], 40), rimDark);
  barrel.material = rimDark;
  const rimLip = new THREE.Mesh(turned([[bead - 0.022, h * 0.95], [bead + 0.006, h * 0.96], [bead + 0.006, h * 0.9]], 40), rim);
  if (side < 0) {
    rimLip.rotateY(Math.PI);
  }
  // Seven curved spokes from a centre lock.
  const spokes: THREE.BufferGeometry[] = [];
  for (let i = 0; i < 7; i += 1) {
    const a = (i / 7) * Math.PI * 2;
    const b = a + 0.32;
    spokes.push(tube(Math.cos(a) * 0.045, Math.sin(a) * 0.045, h * 0.42, Math.cos(b) * (bead - 0.02), Math.sin(b) * (bead - 0.02), h * 0.82, 0.017, 6));
  }
  spokes.push(turned([[0.0, h * 0.58], [0.032, h * 0.58], [0.048, h * 0.5], [0.06, h * 0.25]], 18));
  const hubCap = merge(spokes);
  const star = new THREE.Mesh(side > 0 ? hubCap : hubCap.clone().rotateY(Math.PI), rim);
  parts.add(shell, face, barrel, rimLip, star);
  for (const mesh of parts.children) {
    mesh.castShadow = true;
    (mesh as THREE.Mesh).receiveShadow = false;
  }
  // The disc glows after hard braking; the caliper grips it without turning.
  const hub = new THREE.Group();
  const discMaterial = new THREE.MeshStandardMaterial({ color: 0x2b2b2e, roughness: 0.5, metalness: 0.8, emissive: 0xff3a08, emissiveIntensity: 0 });
  discMaterial.onBeforeCompile = (shader) => {
    shader.uniforms.uHeat = glow;
    shader.fragmentShader = shader.fragmentShader
      .replace("#include <common>", "#include <common>\nuniform float uHeat;")
      .replace("#include <emissivemap_fragment>", "#include <emissivemap_fragment>\ntotalEmissiveRadiance = vec3(3.2, 0.7, 0.08) * uHeat;");
  };
  const disc = new THREE.Mesh(turned([[0.06, -0.016], [0.165, -0.016], [0.165, 0.016], [0.06, 0.016]], 28), discMaterial);
  disc.position.z = -side * 0.02;
  const caliper = new THREE.Mesh(box(-0.04, -0.2, -0.045, 0.04, -0.13, 0.045), new THREE.MeshStandardMaterial({ color: 0xc9a227, roughness: 0.4, metalness: 0.5 }));
  caliper.position.z = -side * 0.02;
  hub.add(disc, caliper);
  return { wheel: parts, hub };
}

/** The tub, the nose and the cover, one skin with the cockpit opening let into it. */
function tub(): THREE.BufferGeometry {
  const sections: Section[] = [
    { x: A + 0.98, w: 0.05, top: 0.02, bottom: 0.03, z: G + 0.16, n: 2 },
    { x: A + 0.62, w: 0.115, top: 0.055, bottom: 0.05, z: G + 0.205 },
    { x: A + 0.18, w: 0.16, top: 0.085, bottom: 0.075, z: G + 0.29 },
    { x: A - 0.32, w: 0.215, top: 0.135, bottom: 0.125, z: G + 0.355, n: 2.8 },
    { x: A - 0.8, w: 0.28, top: 0.2, bottom: 0.2, z: G + 0.355, n: 3 },
    { x: A - 1.3, w: 0.33, top: 0.255, bottom: 0.22, z: G + 0.34, n: 3.2 },
    { x: A - 1.72, w: 0.32, top: 0.34, bottom: 0.21, z: G + 0.35, n: 3.2 },
    { x: A - 2.1, w: 0.22, top: 0.47, bottom: 0.19, z: G + 0.34, n: 2.6 },
    { x: B + 0.22, w: 0.15, top: 0.31, bottom: 0.15, z: G + 0.3, n: 2.4 },
    { x: B - 0.38, w: 0.075, top: 0.08, bottom: 0.08, z: G + 0.33, n: 2.2 },
    { x: B - 0.62, w: 0.03, top: 0.015, bottom: 0.03, z: G + 0.35, n: 2 },
  ];
  return loft(sections, 96, 56);
}

/** The padded rim of the opening, laid on the skin: a ring that follows whatever the tub does there. */
function cockpitRim(skin: THREE.BufferGeometry): THREE.BufferGeometry {
  const at = skin.attributes.position as THREE.BufferAttribute;
  const ring: [number, number, number][] = [];
  for (let i = 0; i < 36; i += 1) {
    const a = (i / 36) * Math.PI * 2;
    const x = HOLE_X + HOLE_LONG * Math.cos(a);
    const y = HOLE_WIDE * Math.sin(a);
    let top = -9;
    for (let k = 0; k < at.count; k += 1) {
      if (Math.abs(at.getX(k) - x) < 0.05 && Math.abs(at.getY(k) - y) < 0.03) {
        top = Math.max(top, at.getZ(k));
      }
    }
    ring.push([x, y, top + 0.004]);
  }
  return hose(ring, 0.017, true, 90);
}

function sidepod(): THREE.BufferGeometry {
  const y = 0.5;
  const pod: Section[] = [
    { x: A - 0.84, w: 0.15, top: 0.13, bottom: 0.11, z: G + 0.24, y, n: 4.5 },
    { x: A - 1.05, w: 0.19, top: 0.16, bottom: 0.13, z: G + 0.24, y, n: 4 },
    { x: A - 1.6, w: 0.21, top: 0.15, bottom: 0.13, z: G + 0.235, y: y - 0.01, n: 3 },
    { x: A - 2.15, w: 0.17, top: 0.09, bottom: 0.12, z: G + 0.2, y: y - 0.1, n: 2.6 },
    { x: B + 0.3, w: 0.09, top: 0.03, bottom: 0.08, z: G + 0.17, y: y - 0.22, n: 2.4 },
  ];
  return loft(pod, 40, 28);
}

export interface CarMesh {
  body: THREE.Group;
  wheels: WheelParts[];
  /** The driver's eye, chassis frame. */
  eye: THREE.Vector3;
  brake: Glow;
  heat: Glow;
  /** Drawn only from inside. */
  inside: THREE.Group;
  /** Drawn only from outside: what would stand between the driver's eye and the road. */
  outside: THREE.Group;
}

export function buildRacecar(): CarMesh {
  const body = new THREE.Group();
  const paint = livery();
  const fibre = carbon();
  const black = matte(0x08090a, 0.6);
  const add = (geometry: THREE.BufferGeometry, material: THREE.Material, shadow = true): THREE.Mesh => {
    const mesh = new THREE.Mesh(geometry, material);
    mesh.castShadow = shadow;
    mesh.receiveShadow = true;
    body.add(mesh);
    return mesh;
  };

  const skin = tub();
  add(skin, paint);
  add(cockpitRim(skin), black);
  add(both(sidepod()), paint);
  // The radiator intake: a dark mouth in the front of each pod.
  add(both(loft([
    { x: A - 0.8, w: 0.135, top: 0.11, bottom: 0.09, z: G + 0.24, y: 0.5, n: 4.5 },
    { x: A - 0.86, w: 0.14, top: 0.115, bottom: 0.095, z: G + 0.24, y: 0.5, n: 4.5 },
  ], 2, 20)), black);
  // Floor: a flat plate between the wheels, its edge turned down, the diffuser rising at the back.
  const plan = new THREE.Shape();
  plan.moveTo(A - 0.42, 0.16);
  plan.bezierCurveTo(A - 0.72, 0.3, A - 0.82, 0.68, A - 1.02, 0.7);
  plan.lineTo(B + 0.42, 0.7);
  plan.lineTo(B + 0.28, 0.52);
  plan.lineTo(B + 0.28, -0.52);
  plan.lineTo(B + 0.42, -0.7);
  plan.lineTo(A - 1.02, -0.7);
  plan.bezierCurveTo(A - 0.82, -0.68, A - 0.72, -0.3, A - 0.42, -0.16);
  plan.closePath();
  add(new THREE.ExtrudeGeometry(plan, { depth: 0.016, bevelEnabled: false }).translate(0, 0, G + 0.045), fibre);
  const diffuser = merge([
    new THREE.BoxGeometry(0.46, 1.04, 0.012).rotateY(0.34).translate(B + 0.08, 0, G + 0.1),
    ...[-0.46, -0.22, 0, 0.22, 0.46].map((y) => box(B - 0.15, y - 0.006, G + 0.05, B + 0.3, y + 0.006, G + 0.19)),
  ]);
  add(diffuser, fibre);
  // The rear light, under the wing's beam, sits in the diffuser's centre fence.
  const brake: Glow = { value: 0 };
  const lamp = new THREE.ShaderMaterial({
    uniforms: { uOn: brake },
    vertexShader: "void main() { gl_Position = projectionMatrix * modelViewMatrix * vec4(position, 1.0); }",
    fragmentShader: "uniform float uOn; void main() { gl_FragColor = vec4(vec3(0.4 + uOn * 9.0, 0.02 + uOn * 0.5, 0.01 + uOn * 0.3), 1.0); }",
  });
  add(box(B - 0.17, -0.04, G + 0.1, B - 0.15, 0.04, G + 0.19), lamp, false);

  // Front wing: three elements, curving up towards end plates that turn the air round the wheels.
  const frontWing = merge([
    wing(A + 0.74, 0.17, G + 0.13, 0.82, 0.09, -0.24, 0.032),
    wing(A + 0.62, 0.13, G + 0.19, 0.82, 0.09, -0.46, 0.05),
  ]);
  const accent = new THREE.MeshPhysicalMaterial({ color: 0xe2410f, roughness: 0.4, clearcoat: 0.4, clearcoatRoughness: 0.3 });
  add(wing(A + 1.02, 0.34, G + 0.075, 0.82, 0.1, -0.05, 0.015), fibre);
  add(frontWing, accent);
  const plate = new THREE.Shape();
  plate.moveTo(A + 1.05, G + 0.045);
  plate.lineTo(A + 0.42, G + 0.045);
  plate.lineTo(A + 0.42, G + 0.26);
  plate.quadraticCurveTo(A + 0.72, G + 0.29, A + 1.05, G + 0.13);
  plate.closePath();
  const endPlate = new THREE.ExtrudeGeometry(plate, { depth: 0.012, bevelEnabled: false }).rotateX(Math.PI / 2).translate(0, 0.84, 0);
  add(both(endPlate), fibre);
  add(both(box(A + 0.28, 0.038, G + 0.08, A + 0.74, 0.05, G + 0.2)), fibre);

  // Rear wing: main plane and flap on two end plates, carried by a swan-neck pylon.
  add(merge([
    wing(B - 0.32, 0.34, G + 0.82, 0.49, 0.12, -0.1, 0),
    wing(B - 0.61, 0.17, G + 0.89, 0.49, 0.1, -0.46, 0),
  ]), fibre);
  const rearPlate = new THREE.Shape();
  rearPlate.moveTo(B - 0.28, G + 0.5);
  rearPlate.lineTo(B - 0.86, G + 0.46);
  rearPlate.lineTo(B - 0.86, G + 0.98);
  rearPlate.lineTo(B - 0.24, G + 0.94);
  rearPlate.closePath();
  add(both(new THREE.ExtrudeGeometry(rearPlate, { depth: 0.012, bevelEnabled: false }).rotateX(Math.PI / 2).translate(0, 0.5, 0)), accent);
  add(both(hose([[B - 0.05, 0.03, G + 0.36], [B - 0.22, 0.03, G + 0.62], [B - 0.42, 0.03, G + 0.8]], 0.011, false, 16)), fibre);
  add(tube(B - 0.3, -0.04, G + 0.42, B - 0.3, 0.04, G + 0.42, 0.03), fibre);

  // Above the driver: the air intake, a thin fin behind it, and the head protection hoop.
  add(loft([
    { x: A - 2.0, w: 0.002, top: 0.02, bottom: 0.1, z: G + 0.72, n: 2 },
    { x: A - 2.05, w: 0.008, top: 0.05, bottom: 0.12, z: G + 0.72, n: 2 },
    { x: B - 0.1, w: 0.006, top: 0.12, bottom: 0.25, z: G + 0.6, n: 2 },
    { x: B - 0.42, w: 0.002, top: 0.02, bottom: 0.03, z: G + 0.46, n: 2 },
  ], 20, 8), paint);
  add(loft([
    { x: A - 1.8, w: 0.075, top: 0.075, bottom: 0.075, z: G + 0.74, n: 3 },
    { x: A - 1.83, w: 0.07, top: 0.07, bottom: 0.07, z: G + 0.74, n: 3 },
  ], 2, 16), black);
  const halo: [number, number, number][] = [
    [A - 0.8, 0.27, G + 0.5], [A - 0.94, 0.26, G + 0.68], [A - 1.3, 0.25, G + 0.73], [A - 1.65, 0.22, G + 0.72], [A - 1.84, 0, G + 0.72],
  ];
  const left = hose([[A - 0.72, 0, G + 0.68], [A - 0.82, 0.14, G + 0.7], [A - 1.05, 0.25, G + 0.72], [A - 1.4, 0.26, G + 0.72], [A - 1.72, 0.17, G + 0.69]], 0.021, false, 32);
  const outside = new THREE.Group();
  body.add(outside);
  outside.add(add(both(left), fibre), add(tube(A - 0.72, 0, G + 0.5, A - 0.72, 0, G + 0.69, 0.024, 10), fibre), add(both(bent([halo[3], [A - 1.7, 0.19, G + 0.56]], 0.018)), fibre));
  // Mirrors on stalks, ahead of the pods.
  add(both(merge([
    tube(A - 0.9, 0.3, G + 0.52, A - 0.86, 0.46, G + 0.6, 0.008),
    loft([{ x: A - 0.84, w: 0.05, top: 0.024, bottom: 0.024, z: G + 0.6, y: 0.48, n: 3 }, { x: A - 0.9, w: 0.055, top: 0.03, bottom: 0.03, z: G + 0.6, y: 0.48, n: 3 }, { x: A - 0.92, w: 0.055, top: 0.03, bottom: 0.03, z: G + 0.6, y: 0.48, n: 3 }], 4, 14),
  ])), paint);
  add(both(box(A - 0.915, 0.43, G + 0.575, A - 0.925, 0.53, G + 0.625)), steel(0x39424a, 0.08, 1));

  // The driver: a helmet with a dark visor and a stripe, and the seat's shoulders in the opening.
  const helmet = new THREE.Group();
  helmet.position.set(A - 1.42, 0, G + 0.585);
  const shell = new THREE.Mesh(new THREE.SphereGeometry(0.115, 28, 20), new THREE.MeshPhysicalMaterial({ color: 0xe9e4d8, roughness: 0.25, clearcoat: 1 }));
  shell.scale.set(1.08, 0.96, 1);
  const visor = new THREE.Mesh(new THREE.SphereGeometry(0.118, 22, 12, -0.95, 1.9, 1.2, 0.62), new THREE.MeshStandardMaterial({ color: 0x050608, roughness: 0.08, metalness: 0.7 }));
  visor.rotation.x = Math.PI / 2;
  visor.scale.set(1.08, 1, 0.96);
  const ring = new THREE.Mesh(new THREE.TorusGeometry(0.1, 0.012, 8, 28), matte(0xe0532a, 0.5));
  ring.rotation.y = Math.PI / 2;
  ring.position.x = -0.02;
  ring.scale.set(1, 1.1, 1);
  helmet.add(shell, visor, ring);
  helmet.traverse((part) => {
    part.castShadow = true;
  });
  body.add(helmet);
  add(both(loft([{ x: A - 1.4, w: 0.09, top: 0.07, bottom: 0.07, z: G + 0.46, y: 0.12, n: 2.2 }, { x: A - 1.56, w: 0.09, top: 0.08, bottom: 0.08, z: G + 0.46, y: 0.12, n: 2.2 }], 4, 12)), matte(0x20262c, 0.8));

  // Only the driver sees these: the wheel and the top of the dash.
  const inside = new THREE.Group();
  const dash = new THREE.Mesh(loft([
    { x: A - 0.92, w: 0.2, top: 0.05, bottom: 0.06, z: G + 0.5, n: 3 },
    { x: A - 1.02, w: 0.2, top: 0.06, bottom: 0.08, z: G + 0.5, n: 3 },
  ], 4, 18), fibre);
  const rimShape = new THREE.Mesh(new THREE.TorusGeometry(0.125, 0.014, 10, 30).rotateY(Math.PI / 2).rotateZ(0).translate(A - 1.08, 0, G + 0.52), matte(0x121416, 0.9));
  rimShape.scale.set(1, 1, 1);
  inside.add(dash, rimShape);
  body.add(inside);
  inside.visible = false;

  const heat: Glow = { value: 0 };
  const rubber = matte(0x0c0c0d, 0.84);
  const wall = matte(0x101012, 0.7);
  wall.onBeforeCompile = (shader) => {
    // A coloured band round the sidewall, as a tyre maker marks its compound.
    shader.vertexShader = shader.vertexShader.replace("#include <common>", "#include <common>\nvarying vec2 vAt;").replace("#include <begin_vertex>", "#include <begin_vertex>\nvAt = position.xy;");
    shader.fragmentShader = shader.fragmentShader.replace("#include <common>", "#include <common>\nvarying vec2 vAt;").replace(
      "#include <color_fragment>",
      `#include <color_fragment>
      float r = length(vAt);
      float a = atan(vAt.y, vAt.x);
      float mark = step(0.262, r) * step(r, 0.276) * step(0.16, abs(sin(a * 1.5)));
      diffuseColor.rgb = mix(diffuseColor.rgb, vec3(0.86, 0.72, 0.1), mark);`,
    );
  };
  const rim = steel(0xc4c7cc, 0.32, 0.95);
  const rimDark = steel(0x26282c, 0.5, 0.8);
  const wheels: WheelParts[] = [
    wheel(1, true, heat, rubber, rim, rimDark, wall),
    wheel(-1, true, heat, rubber, rim, rimDark, wall),
    wheel(1, false, heat, rubber, rim, rimDark, wall),
    wheel(-1, false, heat, rubber, rim, rimDark, wall),
  ];
  return { body, wheels, eye: new THREE.Vector3(A - 1.34, 0, G + 0.73), brake, heat, inside, outside };
}
