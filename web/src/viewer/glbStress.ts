/**
 * The stress table of a FEM flexible body's GLB (written by `julia/BGSimFEM` next to the morph targets)
 * and the per-vertex von Mises stress of the stress colouring of a mode-shapes binding.
 *
 * `asset.extras.bgsim.stress` names a bufferView of the BIN chunk: Float32 little-endian, `vertices *
 * modes * 6` values, the six stress components (xx, yy, zz, xy, xz, yz, in Pa) of every vertex per unit
 * modal coordinate, element (v, k, c) at `(v * modes + k) * 6 + c`. `v` is the vertex in the order of the
 * primitive's POSITION accessor, `k` the mode (morph target). The stress at a vertex is the superposition
 * sigma_c(v) = sum_k eta_k S[v, k, c] (linear in the modal coordinates), and the colour shows its von Mises
 * value (nonlinear, so it is taken after the superposition).
 */

/** A GLB's stress table. */
export interface StressTable {
  readonly vertices: number;
  readonly modes: number;
  /** `vertices * modes * 6` values, Pa per unit modal coordinate. */
  readonly data: Float32Array;
}

const GLB_MAGIC = 0x46546c67;
const CHUNK_JSON = 0x4e4f534a;
const CHUNK_BIN = 0x004e4942;

function isRecord(v: unknown): v is Record<string, unknown> {
  return typeof v === "object" && v !== null && !Array.isArray(v);
}

function count(v: unknown): number | null {
  return typeof v === "number" && Number.isInteger(v) && v > 0 ? v : null;
}

/**
 * The stress table of a GLB, or null when the bytes are no GLB, the file has no `asset.extras.bgsim.stress`,
 * or the table does not fit its bufferView (a GLB without a table is ordinary: a mesh from another tool,
 * or one written before the reduction recovered stresses).
 */
export function readStressTable(bytes: ArrayBufferView): StressTable | null {
  if (bytes.byteLength < 20) return null;
  const dv = new DataView(bytes.buffer, bytes.byteOffset, bytes.byteLength);
  if (dv.getUint32(0, true) !== GLB_MAGIC) return null;
  const jsonLength = dv.getUint32(12, true);
  if (dv.getUint32(16, true) !== CHUNK_JSON || 20 + jsonLength > bytes.byteLength) return null;
  let gltf: unknown;
  try {
    gltf = JSON.parse(new TextDecoder().decode(new Uint8Array(bytes.buffer, bytes.byteOffset + 20, jsonLength)));
  } catch {
    return null;
  }
  if (!isRecord(gltf)) return null;
  const asset = gltf.asset;
  const extras = isRecord(asset) ? asset.extras : undefined;
  const bgsim = isRecord(extras) ? extras.bgsim : undefined;
  const stress = isRecord(bgsim) ? bgsim.stress : undefined;
  if (!isRecord(stress)) return null;
  const vertices = count(stress.vertices);
  const modes = count(stress.modes);
  const viewIndex = stress.bufferView;
  const views = gltf.bufferViews;
  if (vertices === null || modes === null || typeof viewIndex !== "number" || !Array.isArray(views)) return null;
  const view: unknown = views[viewIndex];
  if (!isRecord(view)) return null;
  const binAt = 20 + jsonLength;
  if (binAt + 8 > bytes.byteLength || dv.getUint32(binAt + 4, true) !== CHUNK_BIN) return null;
  const binLength = dv.getUint32(binAt, true);
  const offset = typeof view.byteOffset === "number" ? view.byteOffset : 0;
  const length = typeof view.byteLength === "number" ? view.byteLength : -1;
  const n = vertices * modes * 6;
  if (length !== 4 * n || offset < 0 || offset + length > binLength || binAt + 8 + binLength > bytes.byteLength) return null;
  const data = new Float32Array(n);
  const start = binAt + 8 + offset;
  for (let i = 0; i < n; i++) data[i] = dv.getFloat32(start + 4 * i, true);
  return { vertices, modes, data };
}

/**
 * Per-vertex von Mises stress (Pa) of the table under the modal coordinates `eta` (gain applied, never
 * exaggerated): coordinates beyond the table's modes are ignored, missing ones count as 0. Writes into
 * `out` (length `vertices`) and returns it.
 */
export function vonMises(table: StressTable, eta: readonly number[], out: Float32Array = new Float32Array(table.vertices)): Float32Array {
  const { vertices, modes, data } = table;
  const m = Math.min(modes, eta.length);
  const s = [0, 0, 0, 0, 0, 0];
  for (let v = 0; v < vertices; v++) {
    s.fill(0);
    const base = v * modes * 6;
    for (let k = 0; k < m; k++) {
      const e = eta[k] ?? 0;
      if (e === 0 || !Number.isFinite(e)) continue;
      const o = base + 6 * k;
      for (let c = 0; c < 6; c++) s[c] = (s[c] ?? 0) + e * (data[o + c] ?? 0);
    }
    const [xx = 0, yy = 0, zz = 0, xy = 0, xz = 0, yz = 0] = s;
    out[v] = Math.sqrt(0.5 * ((xx - yy) ** 2 + (yy - zz) ** 2 + (zz - xx) ** 2) + 3 * (xy * xy + xz * xz + yz * yz));
  }
  return out;
}
