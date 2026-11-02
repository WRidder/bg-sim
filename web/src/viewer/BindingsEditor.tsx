import { memo, useCallback, useLayoutEffect, useMemo, useRef, useState, type ReactElement } from "react";

import type { Diagnostic } from "../contracts/diagnostic";
import type {
  BeamMapping, Binding, Colormap, DeformationBasis, DeformationBinding, DeformationFamily, ModeShapeBinding, SegmentBinding,
  SegmentBrokenStyle, SegmentPlane, ShapeAxis,
} from "../contracts/model";
import { defaultBeamAxis, defaultBeamY, isBeamCapable } from "../scene/beamMesh";
import type { BuiltScene } from "../scene/build";
import type { TreeEntry } from "../scene/resolve";
import { segmentAxis } from "../scene/segment";
import { useDocumentStore } from "../state/documentStore";
import { maxModes } from "./beamModes";
import { COLORMAPS, colormapGradient } from "./bindingsColormaps";
import { allowedKinds, MAX_MESH_MODES, signalsOf, validateBindingRows, type SignalUnits } from "./bindingsValidate";
import { Combobox, comboChoices, NO_CHOICES, type ComboChoices } from "./Combobox";
import { modalBlocks, modalSignals, type ModalBlock } from "./modalBlocks";

export interface BindingsEditorProps {
  readonly built: BuiltScene | null;
  readonly bindings: readonly Binding[];
  /** The signals to pick from; null while no check or run has listed them. */
  readonly signals: SignalUnits | null;
  /** The entity to outline in 3D while a row is hovered or focused. */
  readonly onHover: (target: string | null) => void;
}

const PROPERTIES = ["position", "pose", "scale.x", "scale.y", "scale.z", "color", "visible", "deformation", "mode-shapes", "segment"] as const;
type Property = (typeof PROPERTIES)[number];
const POSE_PARTS = ["q_w", "q_x", "q_y", "q_z", "x", "y", "z"] as const;
const DEFAULT_RANGE: [number, number] = [0, 1];
const DEFAULT_STRAIN_RANGE: [number, number] = [0, 0.001];
/** von Mises range of a new stress colouring, Pa (0 to 50 MPa). */
const DEFAULT_STRESS_RANGE: [number, number] = [0, 5e7];
const FAMILIES: readonly DeformationFamily[] = ["bending-y", "bending-z", "torsion"];
const MODAL_BASES: readonly DeformationBasis[] = ["clamped-free", "free-free"];
/** Torsion also takes the lumped twist of a torsion spring (`linear`, one coordinate). */
const TORSION_BASES: readonly DeformationBasis[] = [...MODAL_BASES, "linear"];

/** The bases a family offers. */
function basesFor(family: DeformationFamily): readonly DeformationBasis[] {
  return family === "torsion" ? TORSION_BASES : MODAL_BASES;
}

/** A deformation binding (or draft) after a family or basis change: `linear` is torsion only, with one coordinate. */
function withFamilyBasis<T extends { family: DeformationFamily; basis: DeformationBasis }>(draft: T, family: DeformationFamily, basis: DeformationBasis): T {
  const fitted = family !== "torsion" && basis === "linear" ? "clamped-free" : basis;
  return { ...draft, family, basis: fitted };
}
const SHAPE_AXES: readonly ShapeAxis[] = ["+x", "-x", "+y", "-y", "+z", "-z"];
/** End-point coordinates of a segment: planar (u, v) pairs or spatial (x, y, z) triples, A then B. */
const SEGMENT_PLANAR = ["u_A", "v_A", "u_B", "v_B"] as const;
const SEGMENT_SPATIAL = ["x_A", "y_A", "z_A", "x_B", "y_B", "z_B"] as const;
const PLANES: readonly SegmentPlane[] = ["xz", "xy", "yz"];
const BROKEN_STYLES: readonly SegmentBrokenStyle[] = ["snapped", "hidden"];
const POINT_KINDS = ["planar", "spatial"] as const;

/** The coordinate labels of a segment with `n` signals. */
function segmentParts(n: number): readonly string[] {
  return n === 6 ? SEGMENT_SPATIAL : SEGMENT_PLANAR;
}

interface Choice {
  readonly ref: string;
  readonly label: string;
}

/** Entities of the scene tree a property can take as target (deformation: box and cylinder visuals only; mode-shapes: mesh visuals). */
function targetsFor(tree: readonly TreeEntry[], property: Property, built: BuiltScene | null): Choice[] {
  const kinds = allowedKinds(property);
  const out: Choice[] = [];
  const walk = (entries: readonly TreeEntry[]): void => {
    for (const e of entries) {
      if (kinds.includes(e.kind) && !(e.kind === "joint" && e.detail === "fixed") && fitsProperty(e.ref, property, built)) {
        out.push({ ref: e.ref, label: e.detail !== "" ? `${e.ref} (${e.detail})` : e.ref });
      }
      walk(e.children);
    }
  };
  walk(tree);
  return out;
}

function fitsProperty(ref: string, property: Property, built: BuiltScene | null): boolean {
  if (built === null) return true;
  if (property === "deformation") {
    const g = built.visualGeometry(ref);
    return g !== null && isBeamCapable(g);
  }
  if (property === "segment") {
    const g = built.visualGeometry(ref);
    return g !== null && typeof segmentAxis(g) !== "string";
  }
  if (property === "mode-shapes") return built.visualGeometry(ref)?.kind === "mesh";
  return true;
}

/** A number that is committed on blur or Enter, so typing is one undo step. */
function NumberField({ value, label, testId, onCommit }: { value: number; label: string; testId: string; onCommit: (v: number) => void }): ReactElement {
  const [draft, setDraft] = useState<string | null>(null);
  const commit = (): void => {
    if (draft === null) return;
    const v = Number(draft);
    setDraft(null);
    if (draft.trim() !== "" && Number.isFinite(v) && v !== value) onCommit(v);
  };
  return (
    <input
      type="text"
      inputMode="decimal"
      className="bindings__number"
      aria-label={label}
      data-testid={testId}
      value={draft ?? String(value)}
      onChange={(e) => {
        setDraft(e.target.value);
      }}
      onBlur={commit}
      onKeyDown={(e) => {
        if (e.key === "Enter") commit();
        if (e.key === "Escape") setDraft(null);
      }}
    />
  );
}

/** An optional number, positive unless `signed`: empty means the default (shown as the placeholder). */
function OptionalNumberField({ value, placeholder, label, testId, signed = false, onCommit }: { value: number | undefined; placeholder: string; label: string; testId: string; signed?: boolean; onCommit: (v: number | undefined) => void }): ReactElement {
  const [draft, setDraft] = useState<string | null>(null);
  const commit = (): void => {
    if (draft === null) return;
    setDraft(null);
    const text = draft.trim();
    if (text === "") {
      if (value !== undefined) onCommit(undefined);
      return;
    }
    const v = Number(text);
    if (Number.isFinite(v) && (signed || v > 0) && v !== value) onCommit(v);
  };
  return (
    <input
      type="text"
      inputMode="decimal"
      className="bindings__number"
      aria-label={label}
      data-testid={testId}
      placeholder={placeholder}
      value={draft ?? (value === undefined ? "" : String(value))}
      onChange={(e) => {
        setDraft(e.target.value);
      }}
      onBlur={commit}
      onKeyDown={(e) => {
        if (e.key === "Enter") commit();
        if (e.key === "Escape") setDraft(null);
      }}
    />
  );
}

/** The signals to pick from as combobox choices (`id [unit]`), built once per signal list; null: none listed yet. */
function signalChoices(signals: SignalUnits | null): ComboChoices | null {
  if (signals === null) return null;
  const ids = [...signals.keys()];
  return comboChoices(
    ids,
    ids.map((id) => {
      const unit = signals.get(id);
      return unit !== undefined && unit !== null && unit !== "" ? `${id} [${unit}]` : id;
    }),
  );
}

/**
 * A signal of a binding: a searchable field over the model's signals (the list is built only while it
 * is open), or a plain text field while no check or run has listed them. `optional`: empty means none
 * (a segment's failure flag); otherwise an empty field asks to choose a signal.
 */
function SignalField({ value, choices, label, testId, optional = false, onChange }: { value: string; choices: ComboChoices | null; label: string; testId: string; optional?: boolean; onChange: (v: string) => void }): ReactElement {
  if (choices === null) {
    return (
      <input type="text" className="bindings__signal" aria-label={label} data-testid={testId} value={value} placeholder={optional ? "none" : "Plant/Arm/phi1"} onChange={(e) => { onChange(e.target.value); }} />
    );
  }
  return (
    <Combobox
      className="bindings__signal"
      value={value}
      choices={choices}
      label={label}
      testId={testId}
      noneLabel={optional ? "none" : undefined}
      placeholder={optional ? undefined : "Choose a signal"}
      unknownNote="unknown"
      onChange={onChange}
    />
  );
}

function Choose<T extends string>({ value, options, label, testId, onChange }: { value: T; options: readonly T[]; label: string; testId?: string; onChange: (v: T) => void }): ReactElement {
  return (
    <select aria-label={label} data-testid={testId} value={value} onChange={(e) => { onChange(e.target.value as T); }}>
      {options.map((o) => (
        <option key={o} value={o}>{o}</option>
      ))}
    </select>
  );
}

/**
 * Fills the modal coordinates of a mode-shapes binding from a block that records `<Block>/eta[1..n]`: all
 * of them, but no more than `limit` (the mesh's morph targets when known).
 */
function ModalFill({ blocks, limit, label, testId, onFill }: { blocks: readonly ModalBlock[]; limit: number; label: string; testId: string; onFill: (next: string[]) => void }): ReactElement | null {
  if (blocks.length === 0) return null;
  return (
    <select
      aria-label={`Fill the modal coordinates of ${label} from a block`}
      data-testid={`${testId}-fill`}
      value=""
      onChange={(e) => {
        const b = blocks.find((x) => x.block === e.target.value);
        if (b !== undefined) onFill(modalSignals(b.block, Math.min(b.count, limit)));
      }}
    >
      <option value="">Fill eta[1..n] from…</option>
      {blocks.map((b) => (
        <option key={b.block} value={b.block}>{`${b.block} (eta[1..${String(Math.min(b.count, limit))}])`}</option>
      ))}
    </select>
  );
}

/** The modal coordinates of a deformation or mode-shapes binding: one signal per mode, with buttons to add and remove a mode. */
function ModeSignals({ names, choices, blocks, label, testId, max, fillLimit, onChange }: { names: readonly string[]; choices: ComboChoices | null; blocks: readonly ModalBlock[]; label: string; testId: string; max: number; fillLimit?: number; onChange: (next: string[]) => void }): ReactElement {
  return (
    <div className="bindings__modes">
      {fillLimit !== undefined ? <ModalFill blocks={blocks} limit={fillLimit} label={label} testId={testId} onFill={onChange} /> : null}
      {names.map((name, k) => (
        <SignalField
          key={k}
          value={name}
          choices={choices}
          label={`Mode ${String(k + 1)} signal of ${label}`}
          testId={`${testId}-${String(k)}`}
          onChange={(v) => { onChange(names.map((s, j) => (j === k ? v : s))); }}
        />
      ))}
      <div className="bindings__mode-buttons">
        <button type="button" className="playback__button playback__button--text" data-testid={`${testId}-add-mode`} disabled={names.length >= max} onClick={() => { onChange([...names, ""]); }} aria-label={`Add a mode to ${label}`}>
          + mode
        </button>
        <button type="button" className="playback__button playback__button--text" data-testid={`${testId}-remove-mode`} disabled={names.length <= 1} onClick={() => { onChange(names.slice(0, -1)); }} aria-label={`Remove the last mode of ${label}`}>
          − mode
        </button>
      </div>
    </div>
  );
}

/** Family, basis, beam mapping and strain colouring of a deformation binding row. */
function DeformationSettings({ binding, index, onChange }: { binding: DeformationBinding; index: number; onChange: (next: DeformationBinding) => void }): ReactElement {
  const i = String(index);
  const n = String(index + 1);
  const beam = binding.beam;
  const setBeam = (next: BeamMapping): void => {
    onChange({ ...binding, beam: next });
  };
  const yOptions = SHAPE_AXES.filter((a) => a.slice(1) !== beam.axis.slice(1));
  const strain = binding.strain;
  return (
    <div className="bindings__deform">
      <Choose value={binding.family} options={FAMILIES} label={`Family of binding ${n}`} testId={`binding-family-${i}`} onChange={(v) => { onChange(withFamilyBasis(binding, v, binding.basis)); }} />
      <Choose
        value={binding.basis}
        options={basesFor(binding.family)}
        label={`Basis of binding ${n}`}
        testId={`binding-basis-${i}`}
        onChange={(v) => {
          const next = withFamilyBasis(binding, binding.family, v);
          // the linear basis has one coordinate (the twist of end B relative to end A)
          onChange(v === "linear" && binding.signal.length > 1 ? { ...next, signal: [binding.signal[0]] } : next);
        }}
      />
      <label className="bindings__inline">
        <span>axis</span>
        <Choose
          value={beam.axis}
          options={SHAPE_AXES}
          label={`Beam axis of binding ${n}`}
          testId={`binding-axis-${i}`}
          onChange={(v) => {
            const { y, ...rest } = beam;
            setBeam(y !== undefined && y.slice(1) !== v.slice(1) ? { ...rest, axis: v, y } : { ...rest, axis: v });
          }}
        />
      </label>
      <label className="bindings__inline">
        <span>y</span>
        <Choose
          value={beam.y ?? defaultBeamY(beam.axis)}
          options={yOptions}
          label={`Beam y axis of binding ${n}`}
          testId={`binding-beam-y-${i}`}
          onChange={(v) => { setBeam({ ...beam, y: v }); }}
        />
      </label>
      <label className="bindings__inline">
        <span>L</span>
        <OptionalNumberField
          value={beam.length}
          placeholder="shape"
          label={`Beam length of binding ${n} (empty: the shape's length)`}
          testId={`binding-length-${i}`}
          onCommit={(v) => {
            const { length: _drop, ...rest } = beam;
            void _drop;
            setBeam(v === undefined ? rest : { ...rest, length: v });
          }}
        />
      </label>
      {([0, 1] as const).map((k) => (
        <label className="bindings__inline" key={k}>
          <span>{k === 0 ? "NA y" : "NA z"}</span>
          <OptionalNumberField
            value={beam.neutral?.[k]}
            placeholder="0"
            label={`Neutral axis ${k === 0 ? "y" : "z"} offset of binding ${n} in m (empty: the shape's centre line)`}
            testId={`binding-neutral-${k === 0 ? "y" : "z"}-${i}`}
            signed
            onCommit={(v) => {
              const { neutral: old, ...rest } = beam;
              const next: [number, number] = [old?.[0] ?? 0, old?.[1] ?? 0];
              next[k] = v ?? 0;
              setBeam(next[0] === 0 && next[1] === 0 ? rest : { ...rest, neutral: next });
            }}
          />
        </label>
      ))}
      {binding.family !== "torsion" ? (
        <label className="bindings__inline">
          <input
            type="checkbox"
            checked={strain !== undefined}
            aria-label={`Colour binding ${n} by bending strain`}
            data-testid={`binding-strain-${i}`}
            onChange={(e) => {
              const { strain: _old, ...rest } = binding;
              void _old;
              onChange(e.target.checked ? { ...rest, strain: { colormap: "heat", range: DEFAULT_STRAIN_RANGE } } : rest);
            }}
          />
          <span>strain</span>
        </label>
      ) : null}
      {strain !== undefined && binding.family !== "torsion" ? (
        <div className="bindings__color">
          <Choose value={strain.colormap} options={COLORMAPS} label={`Strain colormap of binding ${n}`} onChange={(v) => { onChange({ ...binding, strain: { ...strain, colormap: v } }); }} />
          <span className="bindings__swatch" style={{ background: colormapGradient(strain.colormap) }} aria-hidden="true" />
          <NumberField value={strain.range[0]} label={`Strain range minimum of binding ${n}`} testId={`binding-strain-min-${i}`} onCommit={(v) => { onChange({ ...binding, strain: { ...strain, range: [v, strain.range[1]] } }); }} />
          <NumberField value={strain.range[1]} label={`Strain range maximum of binding ${n}`} testId={`binding-strain-max-${i}`} onCommit={(v) => { onChange({ ...binding, strain: { ...strain, range: [strain.range[0], v] } }); }} />
        </div>
      ) : null}
    </div>
  );
}

/** Plane and depth (planar end points), stretch axis, failure flag and broken style of a segment binding row. */
function SegmentSettings({ binding, index, choices, onChange }: { binding: SegmentBinding; index: number; choices: ComboChoices | null; onChange: (next: SegmentBinding) => void }): ReactElement {
  const i = String(index);
  const n = String(index + 1);
  const planar = binding.signal.length === 4;
  const withoutAxis = (): SegmentBinding => {
    const { axis: _drop, ...rest } = binding;
    void _drop;
    return rest;
  };
  const withoutBroken = (): SegmentBinding => {
    const { broken: _drop, brokenStyle: _style, ...rest } = binding;
    void _drop;
    void _style;
    return rest;
  };
  return (
    <div className="bindings__deform">
      {planar ? (
        <>
          <label className="bindings__inline">
            <span>plane</span>
            <Choose value={binding.plane ?? "xz"} options={PLANES} label={`Plane of binding ${n}`} testId={`binding-plane-${i}`} onChange={(v) => { onChange({ ...binding, plane: v }); }} />
          </label>
          <label className="bindings__inline">
            <span>depth</span>
            <NumberField value={binding.depth ?? 0} label={`Depth of binding ${n}`} testId={`binding-depth-${i}`} onCommit={(v) => { onChange({ ...binding, depth: v }); }} />
          </label>
        </>
      ) : null}
      <label className="bindings__inline">
        <span>axis</span>
        <select
          aria-label={`Segment axis of binding ${n}`}
          data-testid={`binding-axis-${i}`}
          value={binding.axis ?? ""}
          onChange={(e) => { onChange(e.target.value === "" ? withoutAxis() : { ...binding, axis: e.target.value as ShapeAxis }); }}
        >
          <option value="">shape</option>
          {SHAPE_AXES.map((a) => (
            <option key={a} value={a}>{a}</option>
          ))}
        </select>
      </label>
      <label className="bindings__inline">
        <span>broken</span>
        <SignalField
          optional
          value={binding.broken ?? ""}
          choices={choices}
          label={`Failure flag of binding ${n}`}
          testId={`binding-broken-${i}`}
          onChange={(v) => { onChange(v === "" ? withoutBroken() : { ...binding, broken: v }); }}
        />
      </label>
      {binding.broken !== undefined ? (
        <Choose value={binding.brokenStyle ?? "snapped"} options={BROKEN_STYLES} label={`Broken style of binding ${n}`} testId={`binding-broken-style-${i}`} onChange={(v) => { onChange({ ...binding, brokenStyle: v }); }} />
      ) : null}
    </div>
  );
}

interface DeformDraft {
  family: DeformationFamily;
  basis: DeformationBasis;
  axis: ShapeAxis;
}

/** A complete binding from the add form, or null while something is missing. */
function makeBinding(property: Property, target: string, signal: readonly string[], colormap: Colormap, range: [number, number], deform: DeformDraft): Binding | null {
  if (target === "" || signal.some((s) => s === "") || signal.length === 0) return null;
  switch (property) {
    case "position":
      return { target, property, signal: signal[0] ?? "" };
    case "pose":
      return signal.length === 7 ? { target, property, signal: signal as [string, ...string[]] } : null;
    case "scale.x":
    case "scale.y":
    case "scale.z":
      return { target, property, signal: signal[0] ?? "" };
    case "color":
      return { target, property, signal: signal[0] ?? "", colormap, range };
    case "visible":
      return { target, property, signal: signal[0] ?? "" };
    case "deformation":
      return signal.length <= maxModes(deform.basis)
        ? { target, property, family: deform.family, basis: deform.basis, beam: { axis: deform.axis }, signal: signal as DeformationBinding["signal"] }
        : null;
    case "mode-shapes":
      return signal.length <= MAX_MESH_MODES ? { target, property, signal: signal as ModeShapeBinding["signal"] } : null;
    case "segment":
      return signal.length === 4 || signal.length === 6 ? { target, property, signal: signal as SegmentBinding["signal"] } : null;
  }
}

/** The number of mode shapes (morph targets) the mesh of a mode-shapes binding has, when it is loaded. */
function MeshModesNote({ built, target, testId }: { built: BuiltScene | null; target: string; testId: string }): ReactElement | null {
  const n = built?.morphTargetCount(target) ?? null;
  if (n === null) return null;
  return (
    <span className="bindings__none" data-testid={testId} title="Morph targets of the GLB: one per elastic mode, in mode order">
      {`mesh: ${String(n)} mode shape${n === 1 ? "" : "s"}`}
    </span>
  );
}

const MPA = 1e6;
/** Pa to the editor's MPa and back (no float noise in the stored value). */
const toMpa = (pa: number): number => Number((pa / MPA).toPrecision(12));
const toPa = (mpa: number): number => Number((mpa * MPA).toPrecision(12));

/** The von Mises stress colouring of a mode-shapes binding row: on/off, colormap and range (shown in MPa, stored in Pa). */
function StressSettings({ binding, index, onChange }: { binding: ModeShapeBinding; index: number; onChange: (next: ModeShapeBinding) => void }): ReactElement {
  const i = String(index);
  const n = String(index + 1);
  const stress = binding.stress;
  return (
    <div className="bindings__deform">
      <label className="bindings__inline">
        <input
          type="checkbox"
          checked={stress !== undefined}
          aria-label={`Colour binding ${n} by von Mises stress`}
          data-testid={`binding-stress-${i}`}
          onChange={(e) => {
            const { stress: _old, ...rest } = binding;
            void _old;
            onChange(e.target.checked ? { ...rest, stress: { colormap: "heat", range: DEFAULT_STRESS_RANGE } } : rest);
          }}
        />
        <span>stress</span>
      </label>
      {stress !== undefined ? (
        <div className="bindings__color">
          <Choose value={stress.colormap} options={COLORMAPS} label={`Stress colormap of binding ${n}`} testId={`binding-stress-colormap-${i}`} onChange={(v) => { onChange({ ...binding, stress: { ...stress, colormap: v } }); }} />
          <span className="bindings__swatch" style={{ background: colormapGradient(stress.colormap) }} aria-hidden="true" />
          <NumberField value={toMpa(stress.range[0])} label={`Stress range minimum of binding ${n} in MPa`} testId={`binding-stress-min-${i}`} onCommit={(v) => { onChange({ ...binding, stress: { ...stress, range: [toPa(v), stress.range[1]] } }); }} />
          <NumberField value={toMpa(stress.range[1])} label={`Stress range maximum of binding ${n} in MPa`} testId={`binding-stress-max-${i}`} onCommit={(v) => { onChange({ ...binding, stress: { ...stress, range: [stress.range[0], toPa(v)] } }); }} />
          <span>MPa</span>
        </div>
      ) : null}
    </div>
  );
}

/** How many modal coordinates a mode-shapes binding of a visual can use: its mesh's morph targets when known. */
function meshModeLimit(built: BuiltScene | null, target: string): number {
  const n = built?.morphTargetCount(target) ?? null;
  return n !== null && n > 0 ? Math.min(n, MAX_MESH_MODES) : MAX_MESH_MODES;
}

function emptySignals(property: Property, spatial = false): string[] {
  return Array<string>(property === "pose" ? 7 : property === "segment" ? (spatial ? 6 : 4) : 1).fill("");
}

/** The labels of the signal fields of a binding row or of the add form. */
function partLabels(property: string, n: number): readonly string[] {
  return property === "pose" ? POSE_PARTS : property === "segment" ? segmentParts(n) : ["signal"];
}

const NO_PROBLEMS: readonly Diagnostic[] = [];

/** A table with more rows than this renders only the rows in and near view (an empty row of the same height stands in for the others). */
export const WINDOW_ROWS = 150;
/** Rows within this distance of the view (px) are rendered too, so scrolling and Tab find them ready. */
const OVERSCAN_PX = 600;
/** The view height while it cannot be measured (px). */
const FALLBACK_VIEW_PX = 800;

const NO_MEASURE = (): void => undefined;
/** How long the mouse rests on a row before its target is outlined, ms. */
const HOVER_DELAY_MS = 60;

/** The height of a row before it was measured, px. */
function estimatedHeight(b: Binding, problems: number): number {
  const base = b.property === "pose" || b.property === "segment" ? 64 : b.property === "deformation" || b.property === "mode-shapes" ? 100 : 34;
  return base + (problems > 0 ? 8 + 20 * problems : 0);
}

/** A run of rows to render, or the height of the rows left out between them. */
type Slice = { readonly kind: "row"; readonly index: number } | { readonly kind: "gap"; readonly key: string; readonly height: number };

/**
 * The rows of a long table to render: those within `OVERSCAN_PX` of the view `[top, top + height)` and the
 * row with the focus, with the heights of the rows in between.
 */
export function windowRows(heights: readonly number[], top: number, height: number, keep: number | null): Slice[] {
  const lo = top - OVERSCAN_PX;
  const hi = top + height + OVERSCAN_PX;
  const shown: number[] = [];
  let y = 0;
  heights.forEach((h, i) => {
    if ((y + h >= lo && y <= hi) || i === keep) shown.push(i);
    y += h;
  });
  const out: Slice[] = [];
  let next = 0;
  const gap = (from: number, to: number): void => {
    if (to <= from) return;
    let sum = 0;
    for (let k = from; k < to; k++) sum += heights[k] ?? 0;
    out.push({ kind: "gap", key: `gap-${String(from)}`, height: sum });
  };
  for (const i of shown) {
    gap(next, i);
    out.push({ kind: "row", index: i });
    next = i + 1;
  }
  gap(next, heights.length);
  return out;
}

interface BindingRowProps {
  readonly binding: Binding;
  readonly index: number;
  readonly problems: readonly Diagnostic[];
  /** The scene entities the binding's property can drive. */
  readonly targets: ComboChoices;
  readonly signals: ComboChoices | null;
  readonly blocks: readonly ModalBlock[];
  readonly built: BuiltScene | null;
  readonly onReplace: (index: number, next: Binding) => void;
  readonly onRemove: (index: number) => void;
  /** Outline the row's target in 3D now (focus). */
  readonly onHover: (target: string | null) => void;
  /** Outline it once the mouse rests on the row (`HOVER_DELAY_MS`). */
  readonly onPointHover: (target: string | null) => void;
  /** The row holds the focus (index) or lost it (null): a long table keeps that row rendered. */
  readonly onFocusRow: (index: number | null) => void;
  /** The rendered height of the row and its problems, px (a long table places the rows out of view by it). */
  readonly onMeasure: (binding: Binding, height: number) => void;
}

/**
 * One binding of the table (and its problems below it). Memoised: an edit replaces one binding, so only
 * that row renders again; the shared lists (targets, signals, modal blocks) keep their identity.
 */
const BindingRow = memo(function BindingRow({ binding: b, index: i, problems, targets, signals, blocks, built, onReplace, onRemove, onHover, onPointHover, onFocusRow, onMeasure }: BindingRowProps): ReactElement {
  const names = signalsOf(b);
  const n = String(i + 1);
  const replace = onReplace;
  const rowRef = useRef<HTMLTableRowElement>(null);
  const problemRef = useRef<HTMLTableRowElement>(null);
  useLayoutEffect(() => {
    if (onMeasure !== NO_MEASURE) onMeasure(b, (rowRef.current?.offsetHeight ?? 0) + (problemRef.current?.offsetHeight ?? 0));
  });
  return (
    <>
      <tr
        ref={rowRef}
        className="bindings__row"
        data-testid={`binding-row-${String(i)}`}
        data-invalid={problems.length > 0 ? "true" : undefined}
        onMouseEnter={() => { onPointHover(b.target); }}
        onMouseLeave={() => { onPointHover(null); }}
        onFocus={() => {
          onHover(b.target);
          onFocusRow(i);
        }}
        onBlur={() => {
          onHover(null);
          onFocusRow(null);
        }}
      >
        <td>
          <Combobox
            className="bindings__target"
            value={b.target}
            choices={targets}
            label={`Target of binding ${n}`}
            testId={`binding-target-${String(i)}`}
            unknownNote="not in scene"
            onChange={(v) => { replace(i, { ...b, target: v } as Binding); }}
          />
        </td>
        <td data-testid={`binding-property-${String(i)}`}>{b.property}</td>
        <td>
          {b.property === "deformation" ? (
            <ModeSignals
              names={names}
              choices={signals}
              blocks={blocks}
              label={`binding ${n}`}
              testId={`binding-signal-${String(i)}`}
              max={maxModes(b.basis)}
              onChange={(next) => { replace(i, { ...b, signal: next as DeformationBinding["signal"] }); }}
            />
          ) : b.property === "mode-shapes" ? (
            <ModeSignals
              names={names}
              choices={signals}
              blocks={blocks}
              label={`binding ${n}`}
              testId={`binding-signal-${String(i)}`}
              max={meshModeLimit(built, b.target)}
              fillLimit={meshModeLimit(built, b.target)}
              onChange={(next) => { replace(i, { ...b, signal: next as ModeShapeBinding["signal"] }); }}
            />
          ) : (
            <div className={b.property === "pose" || b.property === "segment" ? "bindings__pose" : undefined}>
              {partLabels(b.property, names.length).map((part, k) => (
                <SignalField
                  key={part}
                  value={names[k] ?? ""}
                  choices={signals}
                  label={b.property === "pose" || b.property === "segment" ? `${part} signal of binding ${n}` : `Signal of binding ${n}`}
                  testId={`binding-signal-${String(i)}${b.property === "pose" || b.property === "segment" ? `-${String(k)}` : ""}`}
                  onChange={(v) => {
                    if (b.property === "pose" || b.property === "segment") {
                      const list = [...names];
                      list[k] = v;
                      replace(i, { ...b, signal: list } as Binding);
                    } else {
                      replace(i, { ...b, signal: v } as Binding);
                    }
                  }}
                />
              ))}
            </div>
          )}
        </td>
        <td>
          <NumberField value={b.gain ?? 1} label={`Gain of binding ${n}`} testId={`binding-gain-${String(i)}`} onCommit={(v) => { replace(i, { ...b, gain: v }); }} />
        </td>
        <td>
          {b.property === "deformation" || b.property === "mode-shapes" ? (
            <span className="bindings__none" title="A deformation has no offset">—</span>
          ) : (
            <NumberField value={b.offset ?? 0} label={`Offset of binding ${n}`} testId={`binding-offset-${String(i)}`} onCommit={(v) => { replace(i, { ...b, offset: v }); }} />
          )}
        </td>
        <td>
          {b.property === "color" ? (
            <div className="bindings__color">
              <select
                aria-label={`Colormap of binding ${n}`}
                value={b.colormap}
                onChange={(e) => { replace(i, { ...b, colormap: e.target.value as Colormap }); }}
              >
                {COLORMAPS.map((c) => (
                  <option key={c} value={c}>{c}</option>
                ))}
              </select>
              <span className="bindings__swatch" style={{ background: colormapGradient(b.colormap) }} aria-hidden="true" />
              <NumberField value={b.range[0]} label={`Range minimum of binding ${n}`} testId={`binding-min-${String(i)}`} onCommit={(v) => { replace(i, { ...b, range: [v, b.range[1]] }); }} />
              <NumberField value={b.range[1]} label={`Range maximum of binding ${n}`} testId={`binding-max-${String(i)}`} onCommit={(v) => { replace(i, { ...b, range: [b.range[0], v] }); }} />
            </div>
          ) : b.property === "deformation" ? (
            <DeformationSettings binding={b} index={i} onChange={(next) => { replace(i, next); }} />
          ) : b.property === "mode-shapes" ? (
            <>
              <MeshModesNote built={built} target={b.target} testId={`binding-mesh-modes-${String(i)}`} />
              <StressSettings binding={b} index={i} onChange={(next) => { replace(i, next); }} />
            </>
          ) : b.property === "segment" ? (
            <SegmentSettings binding={b} index={i} choices={signals} onChange={(next) => { replace(i, next); }} />
          ) : null}
        </td>
        <td>
          <button type="button" className="playback__button" aria-label={`Remove binding ${n}`} data-testid={`binding-remove-${String(i)}`} onClick={() => { onRemove(i); }}>
            <span aria-hidden="true">{"✕"}</span>
          </button>
        </td>
      </tr>
      {problems.length > 0 ? (
        <tr ref={problemRef} className="bindings__problem-row">
          <td className="bindings__problem" colSpan={7} data-testid={`binding-problem-${String(i)}`} role="alert">
            {problems.map((d) => (
              <p key={`${d.code}${d.message}`}>
                <strong>{d.code}</strong> {d.message}. {d.hint}
              </p>
            ))}
          </td>
        </tr>
      ) : null}
    </>
  );
});

/**
 * The binding table of the 3D View (plan 7.6): target from the scene tree, property, signal from the model's
 * signals, gain and offset, colormap and range for colour, family, basis, beam mapping and modes for a
 * beam deformation, and the modal coordinates of a mesh's mode shapes (filled from a block's eta[1..n] in
 * one step). Every edit is one undo step of the model document. Hovering or focusing a row outlines
 * its target in 3D; a row with a problem shows its diagnostic (E301-E304) with the hint.
 */
export const BindingsEditor = memo(function BindingsEditor({ built, bindings, signals, onHover }: BindingsEditorProps): ReactElement {
  const setBindings = useDocumentStore((s) => s.setBindings);
  const tree = built?.resolved.tree;
  const [property, setProperty] = useState<Property>("position");
  const [target, setTarget] = useState("");
  const [signal, setSignal] = useState<string[]>([""]);
  const [colormap, setColormap] = useState<Colormap>("heat");
  const [range, setRange] = useState<[number, number]>(DEFAULT_RANGE);
  const [deform, setDeform] = useState<DeformDraft>({ family: "bending-y", basis: "clamped-free", axis: "+x" });
  const [spatial, setSpatial] = useState(false);

  // shared by every row, computed once per scene and signal list
  const targetsByProperty = useMemo(() => {
    const out = new Map<string, { list: Choice[]; choices: ComboChoices }>();
    for (const p of PROPERTIES) {
      const list = tree === undefined ? [] : targetsFor(tree, p, built);
      out.set(p, { list, choices: comboChoices(list.map((c) => c.ref), list.map((c) => c.label)) });
    }
    return out;
  }, [tree, built]);
  const choices = targetsByProperty.get(property)?.list ?? [];
  const sigChoices = useMemo(() => signalChoices(signals), [signals]);
  const blocks = useMemo(() => modalBlocks(signals), [signals]);
  // a row's diagnostics are reused while its binding is unchanged, so only an edited row renders again
  const diagnosticsCache = useMemo(() => new WeakMap<Binding, Diagnostic[]>(), [built, signals]);
  const rowDiagnostics = useMemo(
    () => (built === null ? bindings.map(() => NO_PROBLEMS) : validateBindingRows(bindings, built, signals, diagnosticsCache)),
    [bindings, built, signals, diagnosticsCache],
  );

  // stable row callbacks: they read the bindings of the last render
  const latest = useRef(bindings);
  useLayoutEffect(() => {
    latest.current = bindings;
  }, [bindings]);
  const replace = useCallback(
    (index: number, next: Binding): void => {
      setBindings(latest.current.map((b, i) => (i === index ? next : b)));
    },
    [setBindings],
  );
  // the mouse outline follows after a short pause: a wheel scroll moves many rows under the pointer,
  // and every outline change draws the 3D view again
  const hoverTimer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const hoverSoon = useCallback(
    (t: string | null): void => {
      if (hoverTimer.current !== null) clearTimeout(hoverTimer.current);
      hoverTimer.current = setTimeout(() => {
        hoverTimer.current = null;
        onHover(t);
      }, HOVER_DELAY_MS);
    },
    [onHover],
  );
  const hoverNow = useCallback(
    (t: string | null): void => {
      if (hoverTimer.current !== null) clearTimeout(hoverTimer.current);
      hoverTimer.current = null;
      onHover(t);
    },
    [onHover],
  );
  useLayoutEffect(
    () => () => {
      if (hoverTimer.current !== null) clearTimeout(hoverTimer.current);
    },
    [],
  );
  const [focused, setFocused] = useState<number | null>(null);
  const remove = useCallback(
    (index: number): void => {
      setBindings(latest.current.filter((_, i) => i !== index));
      hoverNow(null);
      setFocused(null);
    },
    [setBindings, hoverNow],
  );

  // a long table renders the rows in and near view only (WINDOW_ROWS)
  const windowed = bindings.length > WINDOW_ROWS;
  const scrollerRef = useRef<HTMLElement>(null);
  const [view, setView] = useState({ top: 0, height: FALLBACK_VIEW_PX });
  const readView = useCallback((): void => {
    const el = scrollerRef.current;
    if (el === null) return;
    // in steps of a third of the overscan: the rows rendered change (and the table renders) only every few wheel notches
    const step = OVERSCAN_PX / 3;
    const next = { top: Math.floor(el.scrollTop / step) * step, height: el.clientHeight > 0 ? el.clientHeight + step : FALLBACK_VIEW_PX };
    setView((v) => (v.top === next.top && v.height === next.height ? v : next));
  }, []);
  useLayoutEffect(() => {
    const el = scrollerRef.current;
    if (!windowed || el === null) return;
    readView();
    const observer = new ResizeObserver(readView);
    observer.observe(el);
    return () => {
      observer.disconnect();
    };
  }, [windowed, readView]);
  const measured = useRef(new WeakMap<Binding, number>());
  const [, setMeasures] = useState(0);
  const remeasure = useRef<number | null>(null);
  const onMeasure = useCallback((binding: Binding, height: number): void => {
    if (height <= 0 || measured.current.get(binding) === height) return;
    measured.current.set(binding, height);
    // one re-render for all the rows measured in a frame
    remeasure.current ??= requestAnimationFrame(() => {
      remeasure.current = null;
      setMeasures((k) => k + 1);
    });
  }, []);
  useLayoutEffect(
    () => () => {
      if (remeasure.current !== null) cancelAnimationFrame(remeasure.current);
    },
    [],
  );
  const slices: Slice[] = windowed
    ? windowRows(bindings.map((b, i) => measured.current.get(b) ?? estimatedHeight(b, rowDiagnostics[i]?.length ?? 0)), view.top, view.height, focused)
    : bindings.map((_, i) => ({ kind: "row", index: i }));
  const pickProperty = (p: Property): void => {
    setProperty(p);
    setTarget("");
    setSignal(emptySignals(p, spatial));
  };
  const pickTarget = (ref: string): void => {
    setTarget(ref);
    const g = built?.visualGeometry(ref) ?? null;
    if (property === "deformation" && g !== null) setDeform({ ...deform, axis: defaultBeamAxis(g) });
  };
  const candidate = makeBinding(property, target, signal, colormap, range, deform);

  return (
    <section ref={scrollerRef} className="bindings" aria-label="Bindings" data-testid="bindings-editor" data-windowed={windowed ? "true" : undefined} onScroll={windowed ? readView : undefined}>
      <table className="bindings__table">
        <thead>
          <tr>
            <th scope="col">Target</th>
            <th scope="col">Property</th>
            <th scope="col">Signal</th>
            <th scope="col">Gain</th>
            <th scope="col">Offset</th>
            <th scope="col">Options</th>
            <th scope="col"><span className="visually-hidden">Remove</span></th>
          </tr>
        </thead>
        <tbody>
          {slices.map((s) => {
            if (s.kind === "gap") {
              return (
                <tr key={s.key} className="bindings__gap" aria-hidden="true" style={{ height: s.height }}>
                  <td colSpan={7} />
                </tr>
              );
            }
            const i = s.index;
            const b = bindings[i];
            if (b === undefined) return null;
            return (
              <BindingRow
                key={`${b.target}|${b.property}|${String(i)}`}
                binding={b}
                index={i}
                problems={rowDiagnostics[i] ?? NO_PROBLEMS}
                targets={targetsByProperty.get(b.property)?.choices ?? NO_CHOICES}
                signals={sigChoices}
                blocks={blocks}
                built={built}
                onReplace={replace}
                onRemove={remove}
                onHover={hoverNow}
                onPointHover={hoverSoon}
                onFocusRow={setFocused}
                onMeasure={windowed ? onMeasure : NO_MEASURE}
              />
            );
          })}
        </tbody>
      </table>
      {bindings.length === 0 ? <p className="bindings__empty">No bindings. Pick a target, a property and a signal below, then add.</p> : null}
      <form
        className="bindings__add"
        aria-label="Add a binding"
        onSubmit={(e) => {
          e.preventDefault();
          if (candidate === null) return;
          setBindings([...bindings, candidate]);
          setTarget("");
          setSignal(emptySignals(property, spatial));
        }}
      >
        <label>
          <span className="playback__label">Property</span>
          <select aria-label="New binding property" data-testid="add-property" value={property} onChange={(e) => { pickProperty(e.target.value as Property); }}>
            {PROPERTIES.map((p) => (
              <option key={p} value={p}>{p}</option>
            ))}
          </select>
        </label>
        <label>
          <span className="playback__label">Target</span>
          <select aria-label="New binding target" data-testid="add-target" value={target} onChange={(e) => { pickTarget(e.target.value); }}>
            <option value="">{property === "deformation" || property === "segment" ? "Choose a box or cylinder" : property === "mode-shapes" ? "Choose a mesh" : "Choose a target"}</option>
            {choices.map((c) => (
              <option key={c.ref} value={c.ref}>{c.label}</option>
            ))}
          </select>
        </label>
        {property === "deformation" ? (
          <>
            <label>
              <span className="playback__label">Family</span>
              <Choose value={deform.family} options={FAMILIES} label="New binding family" testId="add-family" onChange={(v) => { setDeform(withFamilyBasis(deform, v, deform.basis)); }} />
            </label>
            <label>
              <span className="playback__label">Basis</span>
              <Choose
                value={deform.basis}
                options={basesFor(deform.family)}
                label="New binding basis"
                testId="add-basis"
                onChange={(v) => {
                  setDeform(withFamilyBasis(deform, deform.family, v));
                  if (v === "linear" && signal.length > 1) setSignal(signal.slice(0, 1));
                }}
              />
            </label>
            <label>
              <span className="playback__label">Beam axis</span>
              <Choose value={deform.axis} options={SHAPE_AXES} label="New binding beam axis" testId="add-axis" onChange={(v) => { setDeform({ ...deform, axis: v }); }} />
            </label>
            <div>
              <span className="playback__label">{deform.basis === "linear" ? "Twist (B relative to A)" : "Modal coordinates"}</span>
              <ModeSignals names={signal} choices={sigChoices} blocks={blocks} label="the new binding" testId="add-signal" max={maxModes(deform.basis)} onChange={setSignal} />
            </div>
          </>
        ) : property === "mode-shapes" ? (
          <div>
            <span className="playback__label">Modal coordinates</span>
            <ModeSignals
              names={signal}
              choices={sigChoices}
              blocks={blocks}
              label="the new binding"
              testId="add-signal"
              max={meshModeLimit(built, target)}
              fillLimit={meshModeLimit(built, target)}
              onChange={setSignal}
            />
          </div>
        ) : (
          <>
          {property === "segment" ? (
            <label>
              <span className="playback__label">End points</span>
              <Choose
                value={spatial ? "spatial" : "planar"}
                options={POINT_KINDS}
                label="New binding end points"
                testId="add-points"
                onChange={(v) => {
                  setSpatial(v === "spatial");
                  setSignal(emptySignals("segment", v === "spatial"));
                }}
              />
            </label>
          ) : null}
          {signal.map((value, k) => (
            <label key={k}>
              <span className="playback__label">{property === "pose" || property === "segment" ? partLabels(property, signal.length)[k] : "Signal"}</span>
              <SignalField
                value={value}
                choices={sigChoices}
                label={property === "pose" || property === "segment" ? `New binding ${partLabels(property, signal.length)[k] ?? "signal"}` : "New binding signal"}
                testId={`add-signal-${String(k)}`}
                onChange={(v) => { setSignal(signal.map((s, j) => (j === k ? v : s))); }}
              />
            </label>
          ))}
          </>
        )}
        {property === "color" ? (
          <>
            <label>
              <span className="playback__label">Colormap</span>
              <select aria-label="New binding colormap" value={colormap} onChange={(e) => { setColormap(e.target.value as Colormap); }}>
                {COLORMAPS.map((c) => (
                  <option key={c} value={c}>{c}</option>
                ))}
              </select>
            </label>
            <NumberField value={range[0]} label="New binding range minimum" testId="add-min" onCommit={(v) => { setRange([v, range[1]]); }} />
            <NumberField value={range[1]} label="New binding range maximum" testId="add-max" onCommit={(v) => { setRange([range[0], v]); }} />
          </>
        ) : null}
        <button type="submit" className="playback__button playback__button--text" disabled={candidate === null} data-testid="add-binding">
          Add binding
        </button>
      </form>
    </section>
  );
});
