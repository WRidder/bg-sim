/**
 * Pure helpers of the ModalBody3D inspector: which block reads a reduced-model file, which of its
 * declared constants the compiler fills from that file (so the generic constants editor hides
 * them), and the summary the section shows, parsed from the file text (format
 * `bgsim.modal-body`, version 1; docs/modal-body-format.md).
 */

export const MODAL_BODY_REF = "stdlib:spatial/ModalBody3D";

/** The format and version of a reduced-model file this editor reads. */
export const MODAL_FORMAT = "bgsim.modal-body";
export const MODAL_VERSION = 1;
/** The simulator's limits (ModalBody3D): modal coordinates and interfaces per body. */
export const MODAL_MAX_MODES = 48;
export const MODAL_MAX_INTERFACES = 4;
/** The block's ports, one per interface in file order. */
export const MODAL_PORTS = ["A", "B", "C", "D"] as const;

/** How the reduced-model file is written (julia/BGSimFEM). */
export const MODAL_CLI = "julia --project=julia/BGSimFEM julia/BGSimFEM/bin/bgsim-fem.jl <part>.fem.json";

/**
 * Declared constants of ModalBody3D that the compiler sets from the file (and `stiffening`, which
 * the section edits as a checkbox): an edit in the generic constants editor would be overwritten.
 */
export const MODAL_FILE_CONSTANTS: ReadonlySet<string> = new Set([
  "nm",
  "stiffening",
  "mass",
  "S0",
  "J0",
  "mk",
  "kk",
  "St",
  "Sr",
  "J1",
  "Exx",
  "Eyy",
  "Ezz",
  "Exy",
  "Exz",
  "Eyz",
  "XP",
  "QP",
  "RP",
  "PT",
  "PR",
  "Gt1",
  "Gt2",
  "Gt3",
  "Gj1",
  "Gj2",
  "Gj3",
  "Gj4",
  "Gj5",
  "Gj6",
  "Gr1",
  "Gr2",
  "Gr3",
  "Gb1",
  "Gb2",
  "Gb3",
  "Gc1",
  "Gc2",
  "Gc3",
  "Gd1",
  "Gd2",
  "Gd3",
]);

export function isModalBodyRef(ref: string | null): boolean {
  return ref === MODAL_BODY_REF;
}

/** The constants the generic editor shows for a block: all but the file-derived ones of a ModalBody3D. */
export function editableConstants<T extends { name: string }>(ref: string | null, decls: readonly T[]): T[] {
  return isModalBodyRef(ref) ? decls.filter((decl) => !MODAL_FILE_CONSTANTS.has(decl.name)) : [...decls];
}

/** A ModalBody3D's `file` constant names a project data file as `data/<name>.modal.json`. */
export const MODAL_DATA_FILE = /^data\/([A-Za-z0-9_.-]+\.modal\.json)$/i;

/** The node settings: the file path and the stiffening switch (default on). */
export function modalSettings(constants: Readonly<Record<string, unknown>> | undefined): {
  file: string;
  stiffening: boolean;
} {
  const file = typeof constants?.file === "string" ? constants.file : "";
  const raw = constants?.stiffening;
  const stiffening = !(raw === 0 || raw === false || raw === "0");
  return { file, stiffening };
}

export interface ModalInterface {
  /** The port of the block: A, B, C, D in file order. */
  port: string;
  name: string;
  /** Surface nodes the RBE2 tie holds, when given. */
  nodes: number | null;
  /** Origin in the reference frame R (m), when given. */
  position: number[] | null;
}

export interface ModalValidation {
  bandHz: number | null;
  clampedMaxRelError: number | null;
  freeMaxRelError: number | null;
}

export interface ModalSummary {
  name: string | null;
  mass: number | null;
  nm: number;
  /** How many of the nm coordinates came from fixed-interface modes (the rest: constraint modes). */
  fixedInterfaceModes: number | null;
  interfaces: ModalInterface[];
  /** Eigenfrequencies of the reduced body clamped at interface A (Hz). */
  frequencies: number[];
  validation: ModalValidation | null;
  /** The file holds the geometric-stiffening matrices. */
  hasStiffening: boolean;
  /** File name of the part's GLB with one morph target per mode (looked up in `meshes/`). */
  glb: string | null;
  /** Things that will stop the compile, e.g. more modes than the simulator takes. */
  warnings: string[];
}

export type ModalParse = { ok: true; summary: ModalSummary } | { ok: false; error: string };

function record(value: unknown): Record<string, unknown> | null {
  return typeof value === "object" && value !== null && !Array.isArray(value)
    ? (value as Record<string, unknown>)
    : null;
}

function finite(value: unknown): number | null {
  return typeof value === "number" && Number.isFinite(value) ? value : null;
}

function count(value: unknown): number | null {
  const n = finite(value);
  return n !== null && Number.isInteger(n) && n >= 0 ? n : null;
}

function numbers(value: unknown): number[] | null {
  if (!Array.isArray(value)) return null;
  const out = value.map(finite);
  return out.every((entry): entry is number => entry !== null) ? out : null;
}

const HINT = `write it with julia/BGSimFEM (${MODAL_CLI})`;

/** The summary of a reduced-model file, or why it cannot be read. */
export function parseModalSummary(text: string): ModalParse {
  let document: unknown;
  try {
    document = JSON.parse(text);
  } catch (error) {
    const reason = error instanceof Error ? error.message : String(error);
    return { ok: false, error: `The file is not valid JSON (${reason}); ${HINT}.` };
  }
  const root = record(document);
  if (root === null || root.format !== MODAL_FORMAT) {
    return {
      ok: false,
      error: `The file is not a reduced-model file (it needs "format": "${MODAL_FORMAT}"); ${HINT}.`,
    };
  }
  if (root.version !== MODAL_VERSION) {
    return {
      ok: false,
      error: `The file has version ${JSON.stringify(root.version)} of the reduced-model format; this editor reads version ${MODAL_VERSION}. Write it again with the BGSimFEM of this installation.`,
    };
  }
  const nm = count(root.nm);
  if (nm === null || nm < 1) {
    return { ok: false, error: `The file has no valid number of modes "nm"; ${HINT}.` };
  }
  if (!Array.isArray(root.interfaces) || root.interfaces.length === 0) {
    return { ok: false, error: `The file lists no interfaces; ${HINT}.` };
  }
  const interfaces: ModalInterface[] = root.interfaces.map((entry, position) => {
    const item = record(entry);
    const name = typeof item?.name === "string" ? item.name : `#${String(position + 1)}`;
    return {
      port: MODAL_PORTS[position] ?? `#${String(position + 1)}`,
      name,
      nodes: count(item?.nodes),
      position: numbers(item?.position),
    };
  });

  const validationRoot = record(record(root.validation)?.frequencies);
  const validation: ModalValidation | null =
    validationRoot === null
      ? null
      : {
          bandHz: finite(validationRoot.band_hz),
          clampedMaxRelError: finite(record(validationRoot.clamped)?.max_rel_error_in_band),
          freeMaxRelError: finite(record(validationRoot.free)?.max_rel_error_in_band),
        };
  const visual = record(root.visual);
  const warnings: string[] = [];
  if (nm > MODAL_MAX_MODES) {
    warnings.push(
      `The file has ${String(nm)} modal coordinates; the simulator takes at most ${String(MODAL_MAX_MODES)}. Drop modes in the part spec (modes.drop_above_hz) and write the file again.`,
    );
  }
  if (interfaces.length > MODAL_MAX_INTERFACES) {
    warnings.push(
      `The file has ${String(interfaces.length)} interfaces; the block has ports for ${String(MODAL_MAX_INTERFACES)}.`,
    );
  }
  return {
    ok: true,
    summary: {
      name: typeof root.name === "string" ? root.name : null,
      mass: finite(root.mass),
      nm,
      fixedInterfaceModes: count(root.fixed_interface_modes),
      interfaces,
      frequencies: numbers(root.frequency_hz) ?? [],
      validation,
      hasStiffening: record(root.stiffening) !== null,
      glb: typeof visual?.glb === "string" && visual.glb.length > 0 ? visual.glb : null,
      warnings,
    },
  };
}

/** A frequency for the summary: whole hertz from 1 kHz up, four significant digits below. */
export function formatHz(value: number): string {
  return Math.abs(value) >= 1000 ? String(Math.round(value)) : String(Number(value.toPrecision(4)));
}

/** A number with four significant digits (mass, positions). */
export function formatNumber(value: number): string {
  return String(Number(value.toPrecision(4)));
}

/** A relative error as a percentage with two significant digits: `3.1 %`. */
export function formatPercent(value: number): string {
  return `${String(Number((value * 100).toPrecision(2)))} %`;
}
