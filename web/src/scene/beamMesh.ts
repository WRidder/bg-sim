/**
 * Beam meshes for deformation bindings, free of Babylon: where the beam frame sits in a box or
 * cylinder visual, a mesh of the shape with enough rings along the beam to bend smoothly (and dark
 * longitudinal stripes so a twist shows), and the per-frame vertex positions, normals and strain
 * colours from the modal coordinates (`../viewer/beamModes.ts`).
 *
 * Coordinates: the visual's own frame ("shape", SDF: a box centred on its origin, a cylinder along
 * its local z) and the beam frame (x from end A to end B, s = x). p_beam = B p_shape + (E/2, 0, 0)
 * with B's rows the beam axes in shape coordinates and E the shape's extent along the beam.
 */

import type { BeamMapping, ShapeAxis } from "../contracts/model";
import {
  deformPoint, outerStrain, rotateVector, sectionRotation, sectionState, type ModalSet,
} from "../viewer/beamModes";
import type { SdfGeometry } from "./sdf";

type Vec3 = readonly [number, number, number];

const AXES: Readonly<Record<ShapeAxis, Vec3>> = {
  "+x": [1, 0, 0],
  "-x": [-1, 0, 0],
  "+y": [0, 1, 0],
  "-y": [0, -1, 0],
  "+z": [0, 0, 1],
  "-z": [0, 0, -1],
};

/** Rings along the beam: 48 segments bend smoothly up to the third mode. */
export const BEAM_SEGMENTS = 48;
/** Sectors around a round section (the plain cylinder has 32 too). */
export const ROUND_SECTORS = 32;
/** Brightness of a stripe relative to the shape colour. */
export const STRIPE_SHADE = 0.45;

/** The default beam y axis for a beam axis: +y, or +z when the axis is along y. */
export function defaultBeamY(axis: ShapeAxis): ShapeAxis {
  return axis.endsWith("y") ? "+z" : "+y";
}

/** The beam axis to suggest for a shape: a cylinder's own axis, a box's longest side. */
export function defaultBeamAxis(geometry: SdfGeometry): ShapeAxis {
  if (geometry.kind !== "box") return "+z";
  const [x, y, z] = geometry.size;
  return x >= y && x >= z ? "+x" : y >= z ? "+y" : "+z";
}

export interface BeamFrame {
  /** Rows: beam x, y, z in shape coordinates. */
  readonly basis: readonly [Vec3, Vec3, Vec3];
  /** Extent of the shape along the beam (m). */
  readonly extent: number;
  /** The beam length L of the mode shapes (m). */
  readonly length: number;
  /** The section: a rectangle of half sizes cy, cz along beam y and z, or a circle of radius cy (= cz). */
  readonly section: { readonly round: boolean; readonly cy: number; readonly cz: number };
  /** The neutral axis (beam y, z) from the shape's centre line: the sections turn about it (mapping `neutral`, default 0, 0). */
  readonly neutral: readonly [number, number];
  /** The outer fibre of the strain colouring: the section's half sizes plus the neutral-axis offset (a circle: its radius plus the offset's length). */
  readonly fibre: { readonly round: boolean; readonly cy: number; readonly cz: number };
}

function cross(a: Vec3, b: Vec3): Vec3 {
  // + 0 turns -0 into 0
  return [a[1] * b[2] - a[2] * b[1] + 0, a[2] * b[0] - a[0] * b[2] + 0, a[0] * b[1] - a[1] * b[0] + 0];
}

function axisIndex(v: Vec3): 0 | 1 | 2 {
  return v[0] !== 0 ? 0 : v[1] !== 0 ? 1 : 2;
}

/** Whether a geometry can carry a deformation binding. */
export function isBeamCapable(geometry: SdfGeometry): boolean {
  return geometry.kind === "box" || geometry.kind === "cylinder";
}

/**
 * The beam frame of a visual for a mapping, or a sentence saying why the mapping does not fit the
 * shape (a sphere or mesh, a cylinder bent across its own axis, a y along the axis).
 */
export function beamFrame(geometry: SdfGeometry, mapping: BeamMapping): BeamFrame | string {
  if (geometry.kind !== "box" && geometry.kind !== "cylinder") {
    return `a ${geometry.kind} is not a beam; a deformation binding needs a box or a cylinder`;
  }
  const ax = AXES[mapping.axis];
  const yAxis = mapping.y ?? defaultBeamY(mapping.axis);
  const ay = AXES[yAxis];
  if (axisIndex(ax) === axisIndex(ay)) return `the beam y axis ${yAxis} must be perpendicular to the beam axis ${mapping.axis}`;
  const az = cross(ax, ay);
  let extent: number;
  let section: BeamFrame["section"];
  if (geometry.kind === "cylinder") {
    if (axisIndex(ax) !== 2) return `a cylinder's axis is its local z; set the beam axis to +z or -z, not ${mapping.axis}`;
    extent = geometry.length;
    section = { round: true, cy: geometry.radius, cz: geometry.radius };
  } else {
    extent = geometry.size[axisIndex(ax)];
    section = { round: false, cy: geometry.size[axisIndex(ay)] / 2, cz: geometry.size[axisIndex(az)] / 2 };
  }
  if (!(extent > 0)) return "the shape has no length along the beam axis";
  const length = mapping.length !== undefined && mapping.length > 0 ? mapping.length : extent;
  const ny = mapping.neutral?.[0] ?? 0;
  const nz = mapping.neutral?.[1] ?? 0;
  if (!Number.isFinite(ny) || !Number.isFinite(nz)) return "the neutral axis offset must be two finite numbers (beam y, z in m)";
  const fibre = section.round
    ? { round: true, cy: section.cy + Math.hypot(ny, nz), cz: section.cz + Math.hypot(ny, nz) }
    : { round: false, cy: section.cy + Math.abs(ny), cz: section.cz + Math.abs(nz) };
  return { basis: [ax, ay, az], extent, length, section, neutral: [ny, nz], fibre };
}

/** A mesh of the beam shape, with what the deformation needs per vertex. */
export interface BeamMesh {
  /** Rest positions and normals in shape coordinates (xyz per vertex). */
  readonly positions: Float32Array;
  readonly normals: Float32Array;
  readonly indices: Uint32Array;
  /** Rest vertex colours (rgba): white, stripes darker. */
  readonly colors: Float32Array;
  /** s of every ring. */
  readonly ringS: Float64Array;
  /** Per vertex: its ring, its section coordinates (beam y, z) and its rest normal in beam coordinates. */
  readonly ring: Uint16Array;
  readonly sy: Float32Array;
  readonly sz: Float32Array;
  readonly nBeam: Float32Array;
  /** Per vertex: the stripe shade (1: none). */
  readonly shade: Float32Array;
  readonly vertexCount: number;
}

interface Edge {
  readonly p0: readonly [number, number];
  readonly p1: readonly [number, number];
  readonly n0: readonly [number, number];
  readonly n1: readonly [number, number];
  readonly stripe: boolean;
}

/** The outline of the section, counter-clockwise in (y, z), as edges with outward normals. */
function sectionEdges(frame: BeamFrame, stripes: boolean): Edge[] {
  const { round, cy, cz } = frame.section;
  const edges: Edge[] = [];
  if (round) {
    const stripeEvery = ROUND_SECTORS / 4;
    for (let k = 0; k < ROUND_SECTORS; k++) {
      const a0 = (2 * Math.PI * k) / ROUND_SECTORS;
      const a1 = (2 * Math.PI * (k + 1)) / ROUND_SECTORS;
      const n0: [number, number] = [Math.cos(a0), Math.sin(a0)];
      const n1: [number, number] = [Math.cos(a1), Math.sin(a1)];
      edges.push({ p0: [cy * n0[0], cy * n0[1]], p1: [cy * n1[0], cy * n1[1]], n0, n1, stripe: stripes && k % stripeEvery === 0 });
    }
    return edges;
  }
  // a rectangle: four sides, each split in three so the middle third can be a stripe
  const corners: [number, number][] = [[cy, -cz], [cy, cz], [-cy, cz], [-cy, -cz]];
  const STRIPE_FROM = 5 / 12;
  const STRIPE_TO = 7 / 12;
  for (let k = 0; k < 4; k++) {
    const a = corners[k] ?? [0, 0];
    const b = corners[(k + 1) % 4] ?? [0, 0];
    const d: [number, number] = [b[0] - a[0], b[1] - a[1]];
    const len = Math.hypot(d[0], d[1]) || 1;
    const n: [number, number] = [d[1] / len, -d[0] / len];
    const at = (t: number): [number, number] => [a[0] + d[0] * t, a[1] + d[1] * t];
    const cuts = [0, STRIPE_FROM, STRIPE_TO, 1];
    for (let j = 0; j < 3; j++) {
      edges.push({ p0: at(cuts[j] ?? 0), p1: at(cuts[j + 1] ?? 1), n0: n, n1: n, stripe: stripes && j === 1 });
    }
  }
  return edges;
}

/**
 * A mesh of the shape that `frame` describes: the lateral surface as one quad strip per section edge
 * with `segments` rings along the beam, and the two end caps. Its rest shape is the plain box or
 * cylinder. Triangles wind like Babylon's own builders.
 */
export function buildBeamMesh(frame: BeamFrame, stripes: boolean, segments: number = BEAM_SEGMENTS): BeamMesh {
  const edges = sectionEdges(frame, stripes);
  const rings = segments + 1;
  const outline = edges.length;
  const lateral = outline * 2 * rings;
  const capVerts = 2 * (outline + 1);
  const n = lateral + capVerts;
  const ring = new Uint16Array(n);
  const sy = new Float32Array(n);
  const sz = new Float32Array(n);
  const nBeam = new Float32Array(3 * n);
  const shade = new Float32Array(n).fill(1);
  const indices: number[] = [];
  const ringS = new Float64Array(rings);
  for (let i = 0; i < rings; i++) ringS[i] = (frame.extent * i) / segments;

  let v = 0;
  const put = (r: number, y: number, z: number, nx: number, ny: number, nz: number, sh: number): number => {
    ring[v] = r;
    sy[v] = y;
    sz[v] = z;
    nBeam[3 * v] = nx;
    nBeam[3 * v + 1] = ny;
    nBeam[3 * v + 2] = nz;
    shade[v] = sh;
    return v++;
  };
  // lateral strips; vertex (edge e, ring i, end j) = base + 2 i + j
  for (const e of edges) {
    const base = v;
    const sh = e.stripe ? STRIPE_SHADE : 1;
    for (let i = 0; i < rings; i++) {
      put(i, e.p0[0], e.p0[1], 0, e.n0[0], e.n0[1], sh);
      put(i, e.p1[0], e.p1[1], 0, e.n1[0], e.n1[1], sh);
    }
    for (let i = 0; i < segments; i++) {
      const a0 = base + 2 * i;
      const a1 = a0 + 1;
      const b0 = a0 + 2;
      const b1 = a0 + 3;
      // outward normal = (p1 - p0) x (along +s) ... wound clockwise about the normal (Babylon front face)
      indices.push(a0, b0, a1, a1, b0, b1);
    }
  }
  // caps: a fan around the centre; end A faces -x, end B +x
  for (const [r, nx] of [[0, -1], [segments, 1]] as const) {
    const centre = put(r, 0, 0, nx, 0, 0, 1);
    const first = v;
    for (const e of edges) put(r, e.p0[0], e.p0[1], nx, 0, 0, 1);
    for (let k = 0; k < outline; k++) {
      const a = first + k;
      const b = first + ((k + 1) % outline);
      // the outline runs counter-clockwise about +x
      if (nx > 0) indices.push(centre, b, a);
      else indices.push(centre, a, b);
    }
  }
  const positions = new Float32Array(3 * n);
  const normals = new Float32Array(3 * n);
  const colors = new Float32Array(4 * n);
  const mesh: BeamMesh = { positions, normals, indices: Uint32Array.from(indices), colors, ringS, ring, sy, sz, nBeam, shade, vertexCount: n };
  deformBeamMesh(mesh, frame, [], 1, positions, normals);
  for (let k = 0; k < n; k++) {
    const sh = shade[k] ?? 1;
    colors.set([sh, sh, sh, 1], 4 * k);
  }
  return mesh;
}

/**
 * Deformed positions and normals (shape coordinates) of a beam mesh for modal coordinates `sets`,
 * every coordinate times `scale` (the exaggeration). Evaluates the mode shapes once per ring.
 */
export function deformBeamMesh(mesh: BeamMesh, frame: BeamFrame, sets: readonly ModalSet[], scale: number, positions: Float32Array, normals: Float32Array): void {
  const [bx, by, bz] = frame.basis;
  const half = frame.extent / 2;
  const [ny0, nz0] = frame.neutral;
  const rings = mesh.ringS.length;
  const rot: ReturnType<typeof sectionRotation>[] = [];
  const states: ReturnType<typeof sectionState>[] = [];
  for (let i = 0; i < rings; i++) {
    const st = sectionState(sets, mesh.ringS[i] ?? 0, frame.length, scale);
    states.push(st);
    rot.push(sectionRotation(st));
  }
  for (let k = 0; k < mesh.vertexCount; k++) {
    const r = mesh.ring[k] ?? 0;
    const st = states[r];
    const R = rot[r];
    if (st === undefined || R === undefined) continue;
    // the section turns about the neutral axis (ny0, nz0), not about the shape's centre line
    const [px, dy, dz] = deformPoint(st, R, mesh.ringS[r] ?? 0, (mesh.sy[k] ?? 0) - ny0, (mesh.sz[k] ?? 0) - nz0);
    const py = dy + ny0;
    const pz = dz + nz0;
    const [nx, ny, nz] = rotateVector(R, mesh.nBeam[3 * k] ?? 0, mesh.nBeam[3 * k + 1] ?? 0, mesh.nBeam[3 * k + 2] ?? 0);
    // shape = B^T (beam - (E/2, 0, 0))
    const qx = px - half;
    positions[3 * k] = bx[0] * qx + by[0] * py + bz[0] * pz;
    positions[3 * k + 1] = bx[1] * qx + by[1] * py + bz[1] * pz;
    positions[3 * k + 2] = bx[2] * qx + by[2] * py + bz[2] * pz;
    normals[3 * k] = bx[0] * nx + by[0] * ny + bz[0] * nz;
    normals[3 * k + 1] = bx[1] * nx + by[1] * ny + bz[1] * nz;
    normals[3 * k + 2] = bx[2] * nx + by[2] * ny + bz[2] * nz;
  }
}

/** Bending strain of the outer fibre (measured from the neutral axis) at every ring (true deformation: no exaggeration). */
export function ringStrains(mesh: BeamMesh, frame: BeamFrame, sets: readonly ModalSet[]): Float64Array {
  const out = new Float64Array(mesh.ringS.length);
  const bending = sets.filter((s) => s.family !== "torsion");
  for (let i = 0; i < out.length; i++) out[i] = outerStrain(sectionState(bending, mesh.ringS[i] ?? 0, frame.length, 1), frame.fibre);
  return out;
}
