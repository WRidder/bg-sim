/**
 * The small seeker view: a second camera at the nose of the newest live AIM-9X, drawn under
 * the `#seeker` picture-in-picture frame. It looks along the missile's body x, so the target and
 * the world ahead appear exactly where the FMU's seeker is pointed.
 */

import * as THREE from "three";
import type { Pipeline } from "../engine/pipeline";
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
  private readonly camera = new THREE.PerspectiveCamera(46, 1.625, 2, 400_000);
  private readonly q = new THREE.Quaternion();
  private readonly nose = new THREE.Vector3();
  private readonly point = new THREE.Vector3();
  /**
   * The picture is drawn here and then put on the screen by the pipeline's last pass. Drawing the
   * scenes straight to the screen would need every material's shader a second time (three.js
   * builds one per output colour space), all compiled in the frame of the first launch.
   */
  private readonly target = new THREE.WebGLRenderTarget(4, 4, {
    type: THREE.HalfFloatType,
    format: THREE.RGBAFormat,
    samples: 4,
    depthBuffer: true,
    resolveDepthBuffer: false,
  });

  constructor(
    private readonly renderer: THREE.WebGLRenderer,
    private readonly pipeline: Pipeline,
    private readonly panel: HTMLElement,
    private readonly world: THREE.Scene,
    private readonly near: THREE.Scene,
  ) {
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
    this.camera.position.copy(missile.worldPosition(this.point)).add(this.nose);
    this.camera.quaternion.copy(this.q).multiply(MESH_TO_CAMERA);
    this.camera.updateMatrixWorld();
    this.draw(true);
  }

  /**
   * One draw nobody sees, from where `from` is: the picture's buffers exist and have been drawn
   * into before the first launch, which would otherwise pay for both in its own frame.
   */
  prepare(from: THREE.Camera): void {
    this.camera.position.copy(from.position);
    this.camera.quaternion.copy(from.quaternion);
    this.camera.updateMatrixWorld();
    this.draw(false);
  }

  private draw(show: boolean): void {
    const { renderer, target } = this;
    const canvas = renderer.domElement;
    const scaleX = canvas.width / Math.max(1, canvas.clientWidth);
    const scaleY = canvas.height / Math.max(1, canvas.clientHeight);
    // The panel has no size while it is hidden; these are its CSS width and height.
    const width = Math.max(2, Math.round((this.panel.clientWidth || 260) * scaleX));
    const height = Math.max(2, Math.round((this.panel.clientHeight || 160) * scaleY));
    if (target.width !== width || target.height !== height) {
      target.setSize(width, height);
    }
    // The sun's shadow map is already drawn for this frame.
    const shadows = renderer.shadowMap.autoUpdate;
    renderer.shadowMap.autoUpdate = false;
    renderer.setRenderTarget(target);
    renderer.clear();
    renderer.autoClear = false;
    renderer.render(this.world, this.camera);
    renderer.render(this.near, this.camera);
    renderer.autoClear = true;
    renderer.shadowMap.autoUpdate = shadows;
    renderer.setRenderTarget(null);
    if (!show) {
      return;
    }
    this.pipeline.inset(target, Math.round((canvas.width - width) / 2), Math.round(18 * scaleY), width, height);
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
