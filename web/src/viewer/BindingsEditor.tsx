import { Fragment, useMemo, useState, type ReactElement } from "react";

import type { BeamMapping, Binding, Colormap, DeformationBasis, DeformationBinding, DeformationFamily, ShapeAxis } from "../contracts/model";
import { defaultBeamAxis, defaultBeamY, isBeamCapable } from "../scene/beamMesh";
import type { BuiltScene } from "../scene/build";
import type { TreeEntry } from "../scene/resolve";
import { useDocumentStore } from "../state/documentStore";
import { MAX_MODES } from "./beamModes";
import { COLORMAPS, colormapGradient } from "./bindingsColormaps";
import { allowedKinds, signalsOf, validateBindingRows, type SignalUnits } from "./bindingsValidate";

export interface BindingsEditorProps {
  readonly built: BuiltScene | null;
  readonly bindings: readonly Binding[];
  /** The signals to pick from; null while no check or run has listed them. */
  readonly signals: SignalUnits | null;
  /** The entity to outline in 3D while a row is hovered or focused. */
  readonly onHover: (target: string | null) => void;
}

const PROPERTIES = ["position", "pose", "scale.x", "scale.y", "scale.z", "color", "visible", "deformation"] as const;
type Property = (typeof PROPERTIES)[number];
const POSE_PARTS = ["q_w", "q_x", "q_y", "q_z", "x", "y", "z"] as const;
const DEFAULT_RANGE: [number, number] = [0, 1];
const DEFAULT_STRAIN_RANGE: [number, number] = [0, 0.001];
const FAMILIES: readonly DeformationFamily[] = ["bending-y", "bending-z", "torsion"];
const BASES: readonly DeformationBasis[] = ["clamped-free", "free-free"];
const SHAPE_AXES: readonly ShapeAxis[] = ["+x", "-x", "+y", "-y", "+z", "-z"];

interface Choice {
  readonly ref: string;
  readonly label: string;
}

/** Entities of the scene tree a property can take as target (deformation: box and cylinder visuals only). */
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
  if (property !== "deformation" || built === null) return true;
  const g = built.visualGeometry(ref);
  return g !== null && isBeamCapable(g);
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

/** An optional positive number: empty means the default (shown as the placeholder). */
function OptionalNumberField({ value, placeholder, label, testId, onCommit }: { value: number | undefined; placeholder: string; label: string; testId: string; onCommit: (v: number | undefined) => void }): ReactElement {
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
    if (Number.isFinite(v) && v > 0 && v !== value) onCommit(v);
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

function SignalSelect({ value, signals, label, testId, onChange }: { value: string; signals: SignalUnits | null; label: string; testId: string; onChange: (v: string) => void }): ReactElement {
  if (signals === null) {
    return (
      <input type="text" className="bindings__signal" aria-label={label} data-testid={testId} value={value} placeholder="Plant/Arm/phi1" onChange={(e) => { onChange(e.target.value); }} />
    );
  }
  const ids = [...signals.keys()];
  return (
    <select className="bindings__signal" aria-label={label} data-testid={testId} value={value} onChange={(e) => { onChange(e.target.value); }}>
      {value === "" ? <option value="">Choose a signal</option> : null}
      {value !== "" && !signals.has(value) ? <option value={value}>{`${value} (unknown)`}</option> : null}
      {ids.map((id) => {
        const unit = signals.get(id);
        return (
          <option key={id} value={id}>
            {unit !== undefined && unit !== null && unit !== "" ? `${id} [${unit}]` : id}
          </option>
        );
      })}
    </select>
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

/** The modal coordinates of a deformation binding: one signal per mode, with buttons to add and remove a mode. */
function ModeSignals({ names, signals, label, testId, onChange }: { names: readonly string[]; signals: SignalUnits | null; label: string; testId: string; onChange: (next: string[]) => void }): ReactElement {
  return (
    <div className="bindings__modes">
      {names.map((name, k) => (
        <SignalSelect
          key={k}
          value={name}
          signals={signals}
          label={`Mode ${String(k + 1)} signal of ${label}`}
          testId={`${testId}-${String(k)}`}
          onChange={(v) => { onChange(names.map((s, j) => (j === k ? v : s))); }}
        />
      ))}
      <div className="bindings__mode-buttons">
        <button type="button" className="playback__button playback__button--text" data-testid={`${testId}-add-mode`} disabled={names.length >= MAX_MODES} onClick={() => { onChange([...names, ""]); }} aria-label={`Add a mode to ${label}`}>
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
      <Choose value={binding.family} options={FAMILIES} label={`Family of binding ${n}`} testId={`binding-family-${i}`} onChange={(v) => { onChange({ ...binding, family: v }); }} />
      <Choose value={binding.basis} options={BASES} label={`Basis of binding ${n}`} testId={`binding-basis-${i}`} onChange={(v) => { onChange({ ...binding, basis: v }); }} />
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
      return signal.length <= MAX_MODES
        ? { target, property, family: deform.family, basis: deform.basis, beam: { axis: deform.axis }, signal: signal as DeformationBinding["signal"] }
        : null;
  }
}

function emptySignals(property: Property): string[] {
  return Array<string>(property === "pose" ? 7 : 1).fill("");
}

/**
 * The binding table of the 3D View (plan 7.6): target from the scene tree, property, signal from the model's
 * signals, gain and offset, colormap and range for colour, and family, basis, beam mapping and modes for a
 * beam deformation. Every edit is one undo step of the model document. Hovering or focusing a row outlines
 * its target in 3D; a row with a problem shows its diagnostic (E301-E304) with the hint.
 */
export function BindingsEditor({ built, bindings, signals, onHover }: BindingsEditorProps): ReactElement {
  const setBindings = useDocumentStore((s) => s.setBindings);
  const tree = built?.resolved.tree;
  const [property, setProperty] = useState<Property>("position");
  const [target, setTarget] = useState("");
  const [signal, setSignal] = useState<string[]>([""]);
  const [colormap, setColormap] = useState<Colormap>("heat");
  const [range, setRange] = useState<[number, number]>(DEFAULT_RANGE);
  const [deform, setDeform] = useState<DeformDraft>({ family: "bending-y", basis: "clamped-free", axis: "+x" });

  const choices = useMemo(() => (tree === undefined ? [] : targetsFor(tree, property, built)), [tree, property, built]);
  const rowDiagnostics = useMemo(() => (built === null ? bindings.map(() => []) : validateBindingRows(bindings, built, signals)), [bindings, built, signals]);

  const replace = (index: number, next: Binding): void => {
    setBindings(bindings.map((b, i) => (i === index ? next : b)));
  };
  const remove = (index: number): void => {
    setBindings(bindings.filter((_, i) => i !== index));
    onHover(null);
  };
  const pickProperty = (p: Property): void => {
    setProperty(p);
    setTarget("");
    setSignal(emptySignals(p));
  };
  const pickTarget = (ref: string): void => {
    setTarget(ref);
    const g = built?.visualGeometry(ref) ?? null;
    if (property === "deformation" && g !== null) setDeform({ ...deform, axis: defaultBeamAxis(g) });
  };
  const candidate = makeBinding(property, target, signal, colormap, range, deform);

  return (
    <section className="bindings" aria-label="Bindings" data-testid="bindings-editor">
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
          {bindings.map((b, i) => {
            const names = signalsOf(b);
            const problems = rowDiagnostics[i] ?? [];
            const targets = tree === undefined ? [] : targetsFor(tree, b.property as Property, built);
            const n = String(i + 1);
            return (
              <Fragment key={`${b.target}|${b.property}|${String(i)}`}>
              <tr
                className="bindings__row"
                data-testid={`binding-row-${String(i)}`}
                data-invalid={problems.length > 0 ? "true" : undefined}
                onMouseEnter={() => { onHover(b.target); }}
                onMouseLeave={() => { onHover(null); }}
                onFocus={() => { onHover(b.target); }}
                onBlur={() => { onHover(null); }}
              >
                <td>
                  <select
                    aria-label={`Target of binding ${n}`}
                    data-testid={`binding-target-${String(i)}`}
                    value={b.target}
                    onChange={(e) => { replace(i, { ...b, target: e.target.value } as Binding); }}
                  >
                    {!targets.some((t) => t.ref === b.target) ? <option value={b.target}>{`${b.target} (not in scene)`}</option> : null}
                    {targets.map((t) => (
                      <option key={t.ref} value={t.ref}>{t.label}</option>
                    ))}
                  </select>
                </td>
                <td data-testid={`binding-property-${String(i)}`}>{b.property}</td>
                <td>
                  {b.property === "deformation" ? (
                    <ModeSignals
                      names={names}
                      signals={signals}
                      label={`binding ${n}`}
                      testId={`binding-signal-${String(i)}`}
                      onChange={(next) => { replace(i, { ...b, signal: next as DeformationBinding["signal"] }); }}
                    />
                  ) : (
                    <div className={b.property === "pose" ? "bindings__pose" : undefined}>
                      {(b.property === "pose" ? POSE_PARTS : ["signal"]).map((part, k) => (
                        <SignalSelect
                          key={part}
                          value={names[k] ?? ""}
                          signals={signals}
                          label={b.property === "pose" ? `${part} signal of binding ${n}` : `Signal of binding ${n}`}
                          testId={`binding-signal-${String(i)}${b.property === "pose" ? `-${String(k)}` : ""}`}
                          onChange={(v) => {
                            if (b.property === "pose") {
                              const list = [...names];
                              list[k] = v;
                              replace(i, { ...b, signal: list as [string, ...string[]] });
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
                  {b.property === "deformation" ? (
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
                  ) : null}
                </td>
                <td>
                  <button type="button" className="playback__button" aria-label={`Remove binding ${n}`} data-testid={`binding-remove-${String(i)}`} onClick={() => { remove(i); }}>
                    <span aria-hidden="true">{"✕"}</span>
                  </button>
                </td>
              </tr>
              {problems.length > 0 ? (
                <tr className="bindings__problem-row">
                  <td className="bindings__problem" colSpan={7} data-testid={`binding-problem-${String(i)}`} role="alert">
                    {problems.map((d) => (
                      <p key={`${d.code}${d.message}`}>
                        <strong>{d.code}</strong> {d.message}. {d.hint}
                      </p>
                    ))}
                  </td>
                </tr>
              ) : null}
              </Fragment>
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
          setSignal(emptySignals(property));
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
            <option value="">{property === "deformation" ? "Choose a box or cylinder" : "Choose a target"}</option>
            {choices.map((c) => (
              <option key={c.ref} value={c.ref}>{c.label}</option>
            ))}
          </select>
        </label>
        {property === "deformation" ? (
          <>
            <label>
              <span className="playback__label">Family</span>
              <Choose value={deform.family} options={FAMILIES} label="New binding family" testId="add-family" onChange={(v) => { setDeform({ ...deform, family: v }); }} />
            </label>
            <label>
              <span className="playback__label">Basis</span>
              <Choose value={deform.basis} options={BASES} label="New binding basis" testId="add-basis" onChange={(v) => { setDeform({ ...deform, basis: v }); }} />
            </label>
            <label>
              <span className="playback__label">Beam axis</span>
              <Choose value={deform.axis} options={SHAPE_AXES} label="New binding beam axis" testId="add-axis" onChange={(v) => { setDeform({ ...deform, axis: v }); }} />
            </label>
            <div>
              <span className="playback__label">Modal coordinates</span>
              <ModeSignals names={signal} signals={signals} label="the new binding" testId="add-signal" onChange={setSignal} />
            </div>
          </>
        ) : (
          signal.map((value, k) => (
            <label key={k}>
              <span className="playback__label">{property === "pose" ? POSE_PARTS[k] : "Signal"}</span>
              <SignalSelect
                value={value}
                signals={signals}
                label={property === "pose" ? `New binding ${POSE_PARTS[k] ?? "signal"}` : "New binding signal"}
                testId={`add-signal-${String(k)}`}
                onChange={(v) => { setSignal(signal.map((s, j) => (j === k ? v : s))); }}
              />
            </label>
          ))
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
}
