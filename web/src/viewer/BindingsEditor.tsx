import { Fragment, useMemo, useState, type ReactElement } from "react";

import type { Binding, Colormap } from "../contracts/model";
import type { BuiltScene } from "../scene/build";
import type { TreeEntry } from "../scene/resolve";
import { useDocumentStore } from "../state/documentStore";
import { COLORMAPS, colormapGradient } from "./bindingsColormaps";
import { allowedKinds, signalsOf, validateBindings, type SignalUnits } from "./bindingsValidate";

export interface BindingsEditorProps {
  readonly built: BuiltScene | null;
  readonly bindings: readonly Binding[];
  /** The signals to pick from; null while no check or run has listed them. */
  readonly signals: SignalUnits | null;
  /** The entity to outline in 3D while a row is hovered or focused. */
  readonly onHover: (target: string | null) => void;
}

const PROPERTIES = ["position", "pose", "scale.x", "scale.y", "scale.z", "color", "visible"] as const;
type Property = (typeof PROPERTIES)[number];
const POSE_PARTS = ["q_w", "q_x", "q_y", "q_z", "x", "y", "z"] as const;
const DEFAULT_RANGE: [number, number] = [0, 1];

interface Choice {
  readonly ref: string;
  readonly label: string;
}

/** Entities of the scene tree a property can take as target. */
function targetsFor(tree: readonly TreeEntry[], property: Property): Choice[] {
  const kinds = allowedKinds(property);
  const out: Choice[] = [];
  const walk = (entries: readonly TreeEntry[]): void => {
    for (const e of entries) {
      if (kinds.includes(e.kind) && !(e.kind === "joint" && e.detail === "fixed")) {
        out.push({ ref: e.ref, label: e.detail !== "" ? `${e.ref} (${e.detail})` : e.ref });
      }
      walk(e.children);
    }
  };
  walk(tree);
  return out;
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

/** A complete binding from the add form, or null while something is missing. */
function makeBinding(property: Property, target: string, signal: readonly string[], colormap: Colormap, range: [number, number]): Binding | null {
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
  }
}

/**
 * The binding table of the 3D View (plan 7.6): target from the scene tree, property, signal from the model's
 * signals, gain and offset, and colormap and range for colour. Every edit is one undo step of the model
 * document. Hovering or focusing a row outlines its target in 3D; a row with a problem shows its diagnostic
 * (E301-E304) with the hint.
 */
export function BindingsEditor({ built, bindings, signals, onHover }: BindingsEditorProps): ReactElement {
  const setBindings = useDocumentStore((s) => s.setBindings);
  const tree = built?.resolved.tree;
  const [property, setProperty] = useState<Property>("position");
  const [target, setTarget] = useState("");
  const [signal, setSignal] = useState<string[]>([""]);
  const [colormap, setColormap] = useState<Colormap>("heat");
  const [range, setRange] = useState<[number, number]>(DEFAULT_RANGE);

  const choices = useMemo(() => (tree === undefined ? [] : targetsFor(tree, property)), [tree, property]);
  const rowDiagnostics = useMemo(
    () => bindings.map((b) => (built === null ? [] : validateBindings([b], built, signals))),
    [bindings, built, signals],
  );

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
    setSignal(Array<string>(p === "pose" ? 7 : 1).fill(""));
  };
  const candidate = makeBinding(property, target, signal, colormap, range);

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
            <th scope="col">Colour</th>
            <th scope="col"><span className="visually-hidden">Remove</span></th>
          </tr>
        </thead>
        <tbody>
          {bindings.map((b, i) => {
            const names = signalsOf(b);
            const problems = rowDiagnostics[i] ?? [];
            const targets = tree === undefined ? [] : targetsFor(tree, b.property as Property);
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
                    aria-label={`Target of binding ${String(i + 1)}`}
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
                  <div className={b.property === "pose" ? "bindings__pose" : undefined}>
                    {(b.property === "pose" ? POSE_PARTS : ["signal"]).map((part, k) => (
                      <SignalSelect
                        key={part}
                        value={names[k] ?? ""}
                        signals={signals}
                        label={b.property === "pose" ? `${part} signal of binding ${String(i + 1)}` : `Signal of binding ${String(i + 1)}`}
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
                </td>
                <td>
                  <NumberField value={b.gain ?? 1} label={`Gain of binding ${String(i + 1)}`} testId={`binding-gain-${String(i)}`} onCommit={(v) => { replace(i, { ...b, gain: v }); }} />
                </td>
                <td>
                  <NumberField value={b.offset ?? 0} label={`Offset of binding ${String(i + 1)}`} testId={`binding-offset-${String(i)}`} onCommit={(v) => { replace(i, { ...b, offset: v }); }} />
                </td>
                <td>
                  {b.property === "color" ? (
                    <div className="bindings__color">
                      <select
                        aria-label={`Colormap of binding ${String(i + 1)}`}
                        value={b.colormap}
                        onChange={(e) => { replace(i, { ...b, colormap: e.target.value as Colormap }); }}
                      >
                        {COLORMAPS.map((c) => (
                          <option key={c} value={c}>{c}</option>
                        ))}
                      </select>
                      <span className="bindings__swatch" style={{ background: colormapGradient(b.colormap) }} aria-hidden="true" />
                      <NumberField value={b.range[0]} label={`Range minimum of binding ${String(i + 1)}`} testId={`binding-min-${String(i)}`} onCommit={(v) => { replace(i, { ...b, range: [v, b.range[1]] }); }} />
                      <NumberField value={b.range[1]} label={`Range maximum of binding ${String(i + 1)}`} testId={`binding-max-${String(i)}`} onCommit={(v) => { replace(i, { ...b, range: [b.range[0], v] }); }} />
                    </div>
                  ) : null}
                </td>
                <td>
                  <button type="button" className="playback__button" aria-label={`Remove binding ${String(i + 1)}`} data-testid={`binding-remove-${String(i)}`} onClick={() => { remove(i); }}>
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
          setSignal(Array<string>(property === "pose" ? 7 : 1).fill(""));
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
          <select aria-label="New binding target" data-testid="add-target" value={target} onChange={(e) => { setTarget(e.target.value); }}>
            <option value="">Choose a target</option>
            {choices.map((c) => (
              <option key={c.ref} value={c.ref}>{c.label}</option>
            ))}
          </select>
        </label>
        {signal.map((value, k) => (
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
        ))}
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
