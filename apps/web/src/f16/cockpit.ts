/**
 * The view from the seat: the glare shield and its displays, the side rails, the bow of the canopy
 * and the head-up display's glass. Built in the aircraft's mesh frame, so it flies along.
 */

import * as THREE from "three";

/** The pilot's eye, in the aircraft's frame. */
const EYE = new THREE.Vector3(3.15, 0, 1.08);
/** Extrusion space to the mesh frame: the shape's x goes left, its y up, the depth forward. */
const FORWARD_EXTRUSION = new THREE.Matrix4().makeBasis(
  new THREE.Vector3(0, 1, 0),
  new THREE.Vector3(0, 0, 1),
  new THREE.Vector3(1, 0, 0),
);

/** A rounded top over a flat bottom, swept forward from the pilot. */
function shroud(wide: number, tall: number, length: number, material: THREE.Material): THREE.Mesh {
  const shape = new THREE.Shape();
  shape.absellipse(0, 0, wide, tall, 0, Math.PI, false, 0);
  shape.lineTo(-wide, -0.9);
  shape.lineTo(wide, -0.9);
  const geometry = new THREE.ExtrudeGeometry(shape, { depth: length, bevelEnabled: false, curveSegments: 28 });
  geometry.applyMatrix4(FORWARD_EXTRUSION);
  return new THREE.Mesh(geometry, material);
}

function display(wide: number, tall: number, tone: string): THREE.Mesh {
  const canvas = document.createElement("canvas");
  canvas.width = 128;
  canvas.height = 128;
  const c = canvas.getContext("2d") as CanvasRenderingContext2D;
  c.fillStyle = "#04100c";
  c.fillRect(0, 0, 128, 128);
  c.strokeStyle = tone;
  c.lineWidth = 2;
  c.strokeRect(10, 10, 108, 108);
  for (let i = 0; i < 5; i += 1) {
    c.beginPath();
    c.arc(64, 116, 22 + i * 22, Math.PI, 0);
    c.globalAlpha = 0.55;
    c.stroke();
  }
  const texture = new THREE.CanvasTexture(canvas);
  texture.colorSpace = THREE.SRGBColorSpace;
  const mesh = new THREE.Mesh(
    new THREE.PlaneGeometry(wide, tall),
    new THREE.MeshBasicMaterial({ map: texture, color: new THREE.Color(0.7, 0.7, 0.7) }),
  );
  mesh.rotation.set(0, -Math.PI / 2, -Math.PI / 2, "ZYX");
  return mesh;
}

export function buildCockpit(): THREE.Group {
  const group = new THREE.Group();
  const dark = new THREE.MeshStandardMaterial({ color: 0x101214, roughness: 0.8 });
  const panel = new THREE.MeshStandardMaterial({ color: 0x24282b, roughness: 0.7 });
  const grey = new THREE.MeshStandardMaterial({ color: 0x4a4f53, roughness: 0.6, metalness: 0.2 });
  const glass = new THREE.MeshStandardMaterial({ color: 0x0a2a24, roughness: 0.1, metalness: 0.5, transparent: true, opacity: 0.14, depthWrite: false });

  // The shield's top edge sits about 16 degrees below the line of sight.
  const shield = shroud(0.34, 0.1, 0.7, dark);
  shield.position.set(0.56, 0, -0.26);
  group.add(shield);
  const face = shroud(0.42, 0.03, 0.05, panel);
  face.position.set(0.5, 0, -0.34);
  group.add(face);
  for (const side of [1, -1]) {
    const screen = display(0.16, 0.16, side > 0 ? "#6fe0a0" : "#ffc34d");
    screen.position.set(0.495, side * 0.2, -0.46);
    group.add(screen);
    const rail = new THREE.Mesh(new THREE.BoxGeometry(2.6, 0.13, 0.5), grey);
    rail.position.set(-0.3, side * 0.56, -0.56);
    group.add(rail);
    const post = new THREE.Mesh(new THREE.CylinderGeometry(0.0035, 0.0035, 0.16, 6), grey);
    post.rotation.x = Math.PI / 2;
    post.position.set(0.58, side * 0.075, -0.1);
    group.add(post);
  }

  // The canopy's bow: an arch over the seat, behind the eye's forward view.
  const bow = new THREE.Mesh(new THREE.TorusGeometry(0.58, 0.02, 8, 48, Math.PI), grey);
  bow.geometry.applyMatrix4(FORWARD_EXTRUSION);
  bow.position.set(-0.1, 0, -0.32);
  group.add(bow);

  const combiner = new THREE.Mesh(new THREE.PlaneGeometry(0.17, 0.15), glass);
  combiner.rotation.set(0, -Math.PI / 2 + 0.22, -Math.PI / 2, "ZYX");
  combiner.position.set(0.56, 0, -0.03);
  group.add(combiner);

  group.position.copy(EYE);
  group.visible = false;
  return group;
}
