/**
 * The small seeker view: a second WebGL camera at the nose of the newest live AIM-9X, drawn into
 * the `#seeker` picture-in-picture canvas. It looks along the missile's body x, so the target and
 * the world ahead appear exactly where the FMU's seeker is pointed.
 */

import * as THREE from "three";
import type { Missile } from "./missiles";

const FORWARD = new THREE.Vector3(1, 0, 0);
const MESH_TO_CAMERA = new THREE.Quaternion().setFromRotationMatrix(
  new THREE.Matrix4().makeBasis(new THREE.Vector3(0, -1, 0), new THREE.Vector3(0, 0, 1), new THREE.Vector3(-1, 0, 0)),
);

export interface SeekerMark {
  x: number;
  y: number;
  visible: boolean;
}

export class SeekerView {
  private readonly camera = new THREE.PerspectiveCamera(46, 1.625, 0.5, 50000);
  private readonly q = new THREE.Quaternion();
  private readonly nose = new THREE.Vector3();
  private readonly point = new THREE.Vector3();

  constructor(
    private readonly renderer: THREE.WebGLRenderer,
    private readonly panel: HTMLElement,
    private readonly world: THREE.Scene,
    private readonly near: THREE.Scene,
  ) {
    this.camera.aspect = 1.625;
    this.camera.updateProjectionMatrix();
    panel.hidden = true;
  }

  /** Draw the view from `missile`, or hide the panel when there is none. */
  render(missile: Missile | null): void {
    if (!missile || missile.done || !missile.active) {
      this.panel.hidden = true;
      return;
    }
    this.panel.hidden = false;
    missile.worldQuaternion(this.q);
    this.nose.copy(FORWARD).applyQuaternion(this.q).multiplyScalar(1.5);
    this.camera.position.copy(missile.worldPosition()).add(this.nose);
    this.camera.quaternion.copy(this.q).multiply(MESH_TO_CAMERA);
    this.camera.updateMatrixWorld();

    const canvas = this.renderer.domElement;
    const scaleX = canvas.width / Math.max(1, canvas.clientWidth);
    const scaleY = canvas.height / Math.max(1, canvas.clientHeight);
    const width = Math.round(this.panel.clientWidth * scaleX);
    const height = Math.round(this.panel.clientHeight * scaleY);
    const x = Math.round((canvas.width - width) / 2);
    const y = Math.round(18 * scaleY);
    const previous = this.renderer.getRenderTarget();
    this.renderer.setRenderTarget(null);
    this.renderer.setViewport(x, y, width, height);
    this.renderer.setScissor(x, y, width, height);
    this.renderer.setScissorTest(true);
    this.renderer.setClearColor(0x8db6d8, 1);
    this.renderer.autoClear = true;
    this.renderer.clear();
    this.renderer.autoClear = false;
    this.renderer.render(this.world, this.camera);
    this.renderer.render(this.near, this.camera);
    this.renderer.autoClear = true;
    this.renderer.setScissorTest(false);
    this.renderer.setRenderTarget(previous);
    this.renderer.setViewport(0, 0, canvas.width, canvas.height);
  }

  /** Where the target appears inside the seeker panel, in CSS pixels on the HUD canvas. */
  project(target: { north: number; east: number; alt: number }): SeekerMark {
    const rect = this.panel.getBoundingClientRect();
    this.point.set(target.east, target.alt, -target.north).project(this.camera);
    const x = rect.left + (this.point.x * 0.5 + 0.5) * rect.width;
    const y = rect.top + (-this.point.y * 0.5 + 0.5) * rect.height;
    return {
      x,
      y,
      visible: this.point.z > -1 && this.point.z < 1 && x >= rect.left && x <= rect.right && y >= rect.top && y <= rect.bottom,
    };
  }
}
