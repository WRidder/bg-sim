/**
 * A small GLB in the layout the FEM reduction tool writes for a flexible body (mode-shapes binding):
 * one node, one mesh, one triangle primitive with POSITION, NORMAL and uint32 indices, a material,
 * and one morph target per mode (POSITION and NORMAL deltas), `mesh.weights` all 0,
 * `mesh.extras.targetNames` and `asset.extras.bgsim`. Target k moves vertex 2 by (k + 1) * 0.01 m
 * along z per unit modal coordinate. With `stress`, the GLB also carries the reduction's stress table
 * (`asset.extras.bgsim.stress`, `modalStress` per vertex, mode and component) for that many modes.
 */

/** The table's stress (Pa per unit modal coordinate) of vertex v, mode k, component c (xx yy zz xy xz yz). */
export function modalStress(v: number, k: number, c: number): number {
  if (c === 0) return 1e6 * (v + 1) * (k + 1);
  if (c === 3 && v === 2) return 1e6 * (k + 1);
  return 0;
}

export interface ModalGlbOptions {
  /** Modes of the stress table (none when absent). */
  readonly stress?: number;
  /** Byte length the table's bufferView claims (default: the true one), to test a broken table. */
  readonly stressViewLength?: number;
}

function minMax(values: Float32Array): { min: number[]; max: number[] } {
  const min = [Infinity, Infinity, Infinity];
  const max = [-Infinity, -Infinity, -Infinity];
  for (let i = 0; i < values.length; i++) {
    const c = i % 3;
    min[c] = Math.min(min[c] ?? 0, values[i] ?? 0);
    max[c] = Math.max(max[c] ?? 0, values[i] ?? 0);
  }
  return { min, max };
}

/** The z delta of vertex 2 in target k (m per unit modal coordinate). */
export function modalDelta(k: number): number {
  return (k + 1) * 0.01;
}

export function modalGlb(modes: number, options: ModalGlbOptions = {}): Uint8Array<ArrayBuffer> {
  const positions = new Float32Array([0, 0, 0, 1, 0, 0, 0, 1, 0]);
  const normals = new Float32Array([0, 0, 1, 0, 0, 1, 0, 0, 1]);
  const indices = new Uint32Array([0, 1, 2]);
  const chunks: ArrayBufferView[] = [positions, normals, indices];
  const targets: { POSITION: number; NORMAL: number }[] = [];
  const accessors: Record<string, unknown>[] = [
    { bufferView: 0, componentType: 5126, count: 3, type: "VEC3", ...minMax(positions) },
    { bufferView: 1, componentType: 5126, count: 3, type: "VEC3" },
    { bufferView: 2, componentType: 5125, count: 3, type: "SCALAR" },
  ];
  for (let k = 0; k < modes; k++) {
    const dp = new Float32Array([0, 0, 0, 0, 0, 0, 0, 0, modalDelta(k)]);
    const dn = new Float32Array(9);
    targets.push({ POSITION: accessors.length, NORMAL: accessors.length + 1 });
    accessors.push({ bufferView: chunks.length, componentType: 5126, count: 3, type: "VEC3", ...minMax(dp) });
    accessors.push({ bufferView: chunks.length + 1, componentType: 5126, count: 3, type: "VEC3" });
    chunks.push(dp, dn);
  }
  const stressModes = options.stress ?? 0;
  const stressView = chunks.length;
  if (stressModes > 0) {
    const table = new Float32Array(3 * stressModes * 6);
    for (let v = 0; v < 3; v++) for (let k = 0; k < stressModes; k++) for (let c = 0; c < 6; c++) table[(v * stressModes + k) * 6 + c] = modalStress(v, k, c);
    chunks.push(table);
  }
  const bufferViews: Record<string, unknown>[] = [];
  let offset = 0;
  for (const c of chunks) {
    bufferViews.push({ buffer: 0, byteOffset: offset, byteLength: c.byteLength });
    offset += c.byteLength;
  }
  const view = bufferViews[stressView];
  if (stressModes > 0 && options.stressViewLength !== undefined && view !== undefined) view.byteLength = options.stressViewLength;
  const stress =
    stressModes > 0
      ? { stress: { bufferView: stressView, mesh: 0, primitive: 0, vertices: 3, modes: stressModes, components: ["xx", "yy", "zz", "xy", "xz", "yz"], layout: "vertex, mode, component", unit: "Pa per unit modal coordinate" } }
      : {};
  const bin = new Uint8Array(offset);
  offset = 0;
  for (const c of chunks) {
    bin.set(new Uint8Array(c.buffer, c.byteOffset, c.byteLength), offset);
    offset += c.byteLength;
  }
  const names = Array.from({ length: modes }, (_, k) => `mode ${String(k + 1)}`);
  const json = JSON.stringify({
    asset: { version: "2.0", extras: { bgsim: { kind: "modal-body", modes, frequency_hz: names.map((_, k) => 10 * (k + 1)), ...stress } } },
    scene: 0,
    scenes: [{ nodes: [0] }],
    nodes: [{ mesh: 0 }],
    meshes: [
      {
        primitives: [{ attributes: { POSITION: 0, NORMAL: 1 }, indices: 2, mode: 4, material: 0, ...(modes > 0 ? { targets } : {}) }],
        ...(modes > 0 ? { weights: names.map(() => 0), extras: { targetNames: names } } : {}),
      },
    ],
    materials: [{ pbrMetallicRoughness: { baseColorFactor: [0.6, 0.65, 0.7, 1] } }],
    accessors,
    bufferViews,
    buffers: [{ byteLength: bin.length }],
  });
  const pad = (n: number): number => (4 - (n % 4)) % 4;
  const jsonBytes = new TextEncoder().encode(json + " ".repeat(pad(new TextEncoder().encode(json).length)));
  const total = 12 + 8 + jsonBytes.length + 8 + bin.length;
  const out = new Uint8Array(total);
  const dv = new DataView(out.buffer);
  dv.setUint32(0, 0x46546c67, true);
  dv.setUint32(4, 2, true);
  dv.setUint32(8, total, true);
  dv.setUint32(12, jsonBytes.length, true);
  dv.setUint32(16, 0x4e4f534a, true);
  out.set(jsonBytes, 20);
  const o = 20 + jsonBytes.length;
  dv.setUint32(o, bin.length, true);
  dv.setUint32(o + 4, 0x004e4942, true);
  out.set(bin, o + 8);
  return out;
}
