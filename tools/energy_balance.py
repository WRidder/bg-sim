# /// script
# requires-python = ">=3.11"
# dependencies = ["numpy>=2.0"]
# ///
"""Port-power energy ledger of a finished run (plan 9.2, X-MB6).

Post-processing only: the ledger is computed from the signals the run already
recorded (``<run>/manifest.json`` + ``columns.f64``, plan 3.5); there is no second
state model.  Every power port records ``<path>/<port>.P`` (kind ``power``), the
power flowing *into* the element at that port in W (a multibond port records the
scalar ``sum_k e[k] f[k]``).  For each element (the instance path) the ledger
integrates the sum of its ports with the trapezoid rule on the solver grid::

    W_element = integral p.P dt          (sum over the element's ports)

and groups the elements:

``storage``      I/C-type elements, bodies (inertia, Coriolis, gravity) and the
                 compliant joints (their strain state): ``W`` is the energy gained.
``dissipation``  R-type elements, dampers, orifices: ``W`` is the heat produced.
``source``       Se/Sf/MSe/MSf, ground, drives' sources: ``W`` is minus the energy
                 delivered.
``mixed``        elements that store *and* dissipate behind one set of ports
                 (contact, hard stop, spring-damper): only the sum is observable.
``conversion``   power-conserving transforms, gyrators and junction-like blocks
                 (``W`` is zero up to the integrator), and ``measure`` taps.

Because every bond connects two ports with opposite power, ``sum_all W`` is zero
(Tellegen's theorem): the **residual** measures the integrator order and any
recorder inconsistency.  When the caller names stored-energy signals (``stored``)
two further balances are computed against ``E(t)``::

    storage balance  E(t) - E(0) - integral P_storage
    supply  balance  E(t) - E(0) + integral (P_source + P_dissipation + P_mixed)
                     = Delta E - integral (P_in - P_diss)  with P_in = -P_source

each as the largest deviation over the run (a running check, not only the end
value, so a periodic orbit cannot hide a drift).  All residuals are normalised by
the ledger's throughput ``1/2 sum |W|`` (``integral |P| dt`` per element).

Classification comes from the model: the run manifest records the model name and
each signal's owning instance path, the project's ``models/<name>.bgmodel.json``
maps the path to a block ref, and the block's type is classified by the rules in
:data:`TYPE_CLASS` (composites are resolved through the ``@components`` of their
source in ``julia/BGSim/stdlib`` or the project ``library/``).  ``overrides``
(``{glob: class}`` on instance paths, first match wins) takes precedence.

Usage::

    uv run tools/energy_balance.py <run-dir> [--tol 1e-6] [--json out.json]
        [--override 'Gear*=conversion'] [--stored stored.json] [--strict]

Exit status: 0 within tolerance, 1 above it, 2 on usage or input errors.
"""

from __future__ import annotations

import argparse
import fnmatch
import json
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import numpy as np

ROOT = Path(__file__).resolve().parent.parent
STDLIB = ROOT / "julia" / "BGSim" / "stdlib"

CLASSES = (
    "storage",
    "dissipation",
    "source",
    "mixed",
    "conversion",
    "measure",
    "unclassified",
)

# --------------------------------------------------------------------------- classification

#: Exact block type names (the short name of ``stdlib:<domain>/<Type>``).
_EXACT: dict[str, str] = {}
for _name in (
    "I C IPlanar ISpatial CPlanar CSpatial GravityPlanar GravitySpatial CoriolisPlanar "
    "CoriolisSpatial Inertia Mass Spring Capacitor Inductor ElasticShaft Accumulator "
    "Volume Compliance"
).split():
    _EXACT[_name] = "storage"
for _name in (
    "R RPlanar RSpatial MR Resistor RotationalDamper Damper TranslationalDamper "
    "Orifice VariableOrifice LaminarResistance"
).split():
    _EXACT[_name] = "dissipation"
for _name in (
    "Se Sf MSe MSf SePlanar SfPlanar SeSpatial SfSpatial MSePlanar MSfPlanar MSeSpatial "
    "MSfSpatial GroundPlanar GroundSpatial Ground FixedShaft FixedPoint VoltageSource "
    "CurrentSource TorqueSource ForceSource VelocitySource AngularVelocitySource "
    "PressureSource FlowSource ExternalWrenchPlanar ExternalWrenchSpatial"
).split():
    _EXACT[_name] = "source"
for _name in (
    "SpringDamper HardStop ContactPoint ContactSurface ImpactBody3D ImpactInertia3D "
    "SwitchedPivot3D"
).split():
    _EXACT[_name] = "mixed"
for _name in (
    "TF GY MTF MGY TFPlanar GYPlanar MTFPlanar MGYPlanar TFSpatial GYSpatial MTFSpatial "
    "MGYSpatial TFPlanarMat MTFPlanarMat TFSpatialMat TFAd TFAdNeutral ScrewTF "
    "FixedTransform2D FixedTransform3D FixedTransform3DNeutral JointTransform2D "
    "JointTransform3D EMConverter BallScrew Gearbox Junction"
).split():
    _EXACT[_name] = "conversion"
for _name in (
    "De Df DePlanar DfPlanar DeSpatial DfSpatial PowerSensor FlowSensor ForceSensor "
    "CurrentSensor PositionSensor AngleSensor AccelerationSensor PressureSensor "
    "SpeedSensor TorqueSensor VoltageSensor"
).split():
    _EXACT[_name] = "measure"

#: Pattern rules for families (compliant joints store strain energy: D-MB, plan 6).
_PATTERNS: tuple[tuple[re.Pattern[str], str], ...] = (
    (re.compile(r"^(Revolute|Prismatic|Spherical|Universal|Cylindrical|Helical|Planar3D|Free)"),
     "storage"),
    (re.compile(r"^Fixed(Joint|Transform)"), "conversion"),
)

TYPE_CLASS = _EXACT


def classify_type(type_name: str) -> str | None:
    """The class of a block type name, or ``None`` when no rule applies."""
    if type_name in _EXACT:
        return _EXACT[type_name]
    for pattern, cls in _PATTERNS:
        if pattern.match(type_name):
            return cls
    return None


_COMPONENT = re.compile(r"^\s*([A-Za-z_]\w*)\s*=\s*([A-Za-z_]\w*)\s*\(")


class Classifier:
    """Maps an instance path to a ledger class.

    ``model`` is the model document (or ``None``); ``project_dir`` locates
    ``library/<Name>.jl`` for ``project:`` refs; ``overrides`` maps instance-path
    globs to classes and is consulted first.
    """

    def __init__(
        self,
        model: dict[str, Any] | None = None,
        project_dir: Path | None = None,
        overrides: dict[str, str] | None = None,
    ) -> None:
        self.model = model
        self.project_dir = project_dir
        self.overrides = dict(overrides or {})
        for pattern, cls in self.overrides.items():
            if cls not in CLASSES or cls == "unclassified":
                raise ValueError(f"override {pattern!r}: unknown class {cls!r}")
        self._components: dict[str, dict[str, str] | None] = {}

    # -- source lookup

    def _source(self, name: str, domain: str | None, project: bool) -> Path | None:
        if project:
            if self.project_dir is None:
                return None
            candidate = self.project_dir / "library" / f"{name}.jl"
            return candidate if candidate.is_file() else None
        if domain is not None:
            candidate = STDLIB / domain / f"{name}.jl"
            if candidate.is_file():
                return candidate
        hits = sorted(STDLIB.glob(f"*/{name}.jl"))
        if hits:
            return hits[0]
        if self.project_dir is not None:
            candidate = self.project_dir / "library" / f"{name}.jl"
            if candidate.is_file():
                return candidate
        return None

    def _components_of(self, key: str, path: Path | None) -> dict[str, str] | None:
        """``{component name: type}`` of a composite block, ``None`` for a leaf."""
        if key in self._components:
            return self._components[key]
        result: dict[str, str] | None = None
        if path is not None:
            lines = path.read_text(encoding="utf-8").splitlines()
            collected: dict[str, str] = {}
            inside = False
            for line in lines:
                code = line.split("#", 1)[0]
                if not inside:
                    if code.strip().startswith("@components"):
                        inside = True
                    continue
                if code.strip() == "end":
                    break
                match = _COMPONENT.match(code)
                if match:
                    collected[match.group(1)] = match.group(2)
            result = collected or None
        self._components[key] = result
        return result

    # -- resolution

    def _node(self, nodes: list[dict[str, Any]], name: str) -> dict[str, Any] | None:
        for node in nodes:
            if node.get("name") == name:
                return node
        return None

    def _resolve(self, instance: str) -> tuple[str | None, str]:
        """``(type name or None, why)`` for an instance path through the model."""
        if self.model is None:
            return None, "no model document"
        parts = instance.split("/")
        diagram = self.model.get("diagram") or {}
        index = 0
        while index < len(parts):
            node = self._node(diagram.get("nodes") or [], parts[index])
            if node is None:
                return None, f"no node {parts[index]!r} in the model"
            index += 1
            block = node.get("block") or {}
            if "subsystem" in block:
                diagram = block["subsystem"].get("diagram") or {}
                continue
            if "junction" in block:
                return "Junction", "junction"
            ref = str(block.get("ref") or "")
            project = ref.startswith("project:")
            body = ref.split(":", 1)[1] if ":" in ref else ref
            domain, _, name = body.rpartition("/")
            return self._descend(name, domain or None, project, parts[index:], ref)
        return None, "the path ends on a subsystem"

    def _descend(
        self, name: str, domain: str | None, project: bool, rest: list[str], ref: str
    ) -> tuple[str | None, str]:
        """Follow the composite's ``@components`` along the remaining path."""
        while rest:
            source = self._source(name, domain, project)
            components = self._components_of(f"{project}:{domain}/{name}", source)
            if components is None or rest[0] not in components:
                return None, f"{name} has no component {rest[0]!r}"
            name = components[rest[0]]
            domain, project = None, False
            rest = rest[1:]
            if name == "Junction":
                return "Junction", "junction"
        return name, ref or name

    def classify(self, instance: str) -> tuple[str, str]:
        """``(class, reason)`` of the element at an instance path."""
        for pattern, cls in self.overrides.items():
            if fnmatch.fnmatchcase(instance, pattern):
                return cls, f"override {pattern}"
        type_name, why = self._resolve(instance)
        if type_name is None:
            return "unclassified", why
        cls = classify_type(type_name)
        if cls is None:
            return "unclassified", f"no rule for type {type_name}"
        return cls, f"type {type_name}"


# --------------------------------------------------------------------------- run files


@dataclass
class RunData:
    manifest: dict[str, Any]
    time: np.ndarray
    signals: dict[str, np.ndarray]
    run_dir: Path | None = None
    meta: dict[str, dict[str, Any]] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.meta:
            self.meta = {str(s["id"]): s for s in self.manifest.get("signals") or []}


def read_run(run_dir: Path) -> RunData:
    """Manifest and columnar data of a run directory (plan 3.5)."""
    run_dir = Path(run_dir)
    manifest = json.loads((run_dir / "manifest.json").read_text(encoding="utf-8"))
    metadata = manifest.get("signals") or []
    n = int(manifest["time"]["n"])
    raw = np.fromfile(run_dir / "columns.f64", dtype="<f8")
    if raw.size != n * (len(metadata) + 1):
        raise ValueError(
            f"{run_dir / 'columns.f64'} holds {raw.size} Float64 values, "
            f"expected {n} x {len(metadata) + 1}"
        )
    table = raw.reshape(len(metadata) + 1, n)
    signals = {str(s["id"]): table[i + 1] for i, s in enumerate(metadata)}
    meta = {str(s["id"]): s for s in metadata}
    return RunData(manifest, table[0], signals, run_dir, meta)


def discover_model(run_dir: Path, manifest: dict[str, Any]) -> tuple[dict[str, Any] | None, Path | None]:
    """The project's model document of a run: ``<project>/models/<model>.bgmodel.json``."""
    project = Path(run_dir).resolve().parent.parent
    name = manifest.get("model")
    if name:
        candidate = project / "models" / f"{name}.bgmodel.json"
        if candidate.is_file():
            return json.loads(candidate.read_text(encoding="utf-8")), project
    return None, project if (project / "models").is_dir() else None


# --------------------------------------------------------------------------- ledger


def trapezoid(t: np.ndarray, y: np.ndarray) -> float:
    """``integral y dt`` by the trapezoid rule on the (possibly repeated-time) grid."""
    if t.size < 2:
        return 0.0
    return float(np.sum(0.5 * (y[1:] + y[:-1]) * np.diff(t)))


def cumulative(t: np.ndarray, y: np.ndarray) -> np.ndarray:
    """Running trapezoid integral, starting at 0."""
    out = np.zeros(t.size)
    if t.size > 1:
        out[1:] = np.cumsum(0.5 * (y[1:] + y[:-1]) * np.diff(t))
    return out


_FUNCTIONS = {
    "id": lambda x: x,
    "sin": np.sin,
    "cos": np.cos,
    "abs": np.abs,
}


def expand_terms(terms: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Expand the ``for`` shorthand: ``{"coeff", "signals": ["{b}/P[{k}]", "{b}/V[{k}]"],
    "for": {"b": ["Body", "Wheel1"], "k": [1, 2, 3]}}`` becomes one term per
    combination, with the placeholders filled by ``str.format``."""
    out: list[dict[str, Any]] = []
    for term in terms:
        loops = term.get("for")
        if not loops:
            out.append(term)
            continue
        combos: list[dict[str, Any]] = [{}]
        for name, values in loops.items():
            combos = [{**c, name: v} for c in combos for v in values]
        for combo in combos:
            clone = {k: v for k, v in term.items() if k != "for"}
            for key in ("signal", "signals"):
                if key in clone:
                    clone[key] = (
                        clone[key].format(**combo)
                        if isinstance(clone[key], str)
                        else [name.format(**combo) for name in clone[key]]
                    )
            out.append(clone)
    return out


def stored_energy(signals: dict[str, np.ndarray], terms: list[dict[str, Any]], mask: np.ndarray) -> np.ndarray:
    """``E(t) = sum_terms coeff * prod_factors fn(signal)**pow`` over the window.

    A term is ``{"coeff": c, "signal": s}`` (``c * s``), ``{"coeff": c, "signals":
    [a, b]}`` (the product ``c * a * b``, e.g. ``1/2 P . V``), or ``{"coeff": c,
    "factors": [{"signal": s, "pow": 2, "fn": "id"|"sin"|"cos"|"abs"}, ...]}``;
    ``pow`` defaults to 1.  Kinetic energy ``P^2 / (2 J)`` is ``{"coeff": 1/(2J),
    "signal": "Body/P[1]", "pow": 2}``.  :func:`expand_terms` documents the ``for``
    shorthand that writes a family of terms once.
    """
    terms = expand_terms(terms)
    if not terms:
        raise ValueError("'stored' needs at least one term")
    total = np.zeros(int(np.count_nonzero(mask)))
    for term in terms:
        factors = term.get("factors")
        if factors is None and "signals" in term:
            factors = [{"signal": name} for name in term["signals"]]
        elif factors is None:
            factors = [{k: v for k, v in term.items() if k in ("signal", "pow", "fn")}]
        value = np.full_like(total, float(term["coeff"]))
        for factor in factors:
            name = str(factor["signal"])
            if name not in signals:
                raise ValueError(f"stored energy: unknown signal {name!r}")
            fn = str(factor.get("fn", "id"))
            if fn not in _FUNCTIONS:
                raise ValueError(f"stored energy: unknown fn {fn!r}")
            value = value * _FUNCTIONS[fn](signals[name][mask]) ** float(factor.get("pow", 1.0))
        total = total + value
    return total


def _pose_y(signal: str) -> str:
    return signal if signal.endswith("]") else f"{signal}[3]"


def terms_from_energy_spec(spec: dict[str, Any]) -> list[dict[str, Any]]:
    """Stored-energy terms of an ``examples/run_checks.py`` ``energy`` check.

    The pendulum form (``p``, ``q``, ``pose``, ``d``, ``J``, ``m``, ``g0``, ``kt``) and
    the multi-body form (``bodies``/``springs``) both describe
    ``E = 1/2 p^T M^-1 p + m g h + 1/2 kt |d|^2``; this writes the same energy as
    :func:`stored_energy` terms so the ledger and the energy check share one budget.
    """
    g0 = float(spec.get("g0", 9.81))
    terms: list[dict[str, Any]] = []

    def body(momenta: list[str], inertia: float, mass: float, pose: str,
             corrections: list[tuple[str, list[str]]]) -> None:
        for signal, weight in zip(momenta, (inertia, mass, mass)):
            terms.append({"coeff": 0.5 / weight, "signal": signal, "pow": 2})
        terms.append({"coeff": mass * g0, "signal": _pose_y(pose)})
        for q, d in corrections:
            terms.append({"coeff": mass * g0, "factors": [
                {"signal": q, "fn": "sin"}, {"signal": d[0]}]})
            terms.append({"coeff": mass * g0, "factors": [
                {"signal": q, "fn": "cos"}, {"signal": d[1]}]})

    def spring(stiffness: float, d: list[str]) -> None:
        for signal in d:
            terms.append({"coeff": 0.5 * stiffness, "signal": signal, "pow": 2})

    if "bodies" in spec:
        for b in spec["bodies"]:
            body(list(b["p"]), float(b["J"]), float(b["m"]), str(b["pose"]),
                 [(str(c["q"]), list(c["d"])) for c in b.get("corrections") or []])
        for sp in spec.get("springs") or []:
            spring(float(sp["kt"]), list(sp["d"]))
    else:
        body(list(spec["p"]), float(spec["J"]), float(spec["m"]), str(spec["pose"]),
             [(str(spec["q"]), list(spec["d"]))])
        spring(float(spec["kt"]), list(spec["d"]))
    return terms


def ledger(
    run: RunData,
    classifier: Classifier,
    *,
    stored: list[dict[str, Any]] | None = None,
    from_t: float | None = None,
    to_t: float | None = None,
) -> dict[str, Any]:
    """The port-power ledger of a run (see the module docstring)."""
    t_all = run.time
    lower = float(t_all[0]) if from_t is None else float(from_t)
    upper = float(t_all[-1]) if to_t is None else float(to_t)
    mask = (t_all >= lower) & (t_all <= upper)
    if int(np.count_nonzero(mask)) < 2:
        raise ValueError(f"no samples in [{lower:g}, {upper:g}]")
    t = t_all[mask]

    ports: dict[str, list[str]] = {}
    for signal_id, entry in run.meta.items():
        if entry.get("kind") == "power" or signal_id.endswith(".P"):
            ports.setdefault(str(entry.get("path", signal_id.rsplit("/", 1)[0])), []).append(signal_id)
    if not ports:
        raise ValueError("the run records no power (.P) signals")

    elements: list[dict[str, Any]] = []
    power: dict[str, np.ndarray] = {}
    for path in sorted(ports):
        p = np.zeros(t.size)
        for signal_id in ports[path]:
            p = p + run.signals[signal_id][mask]
        if not np.all(np.isfinite(p)):
            raise ValueError(f"{path}: the power signals hold a non-finite sample")
        cls, why = classifier.classify(path)
        power[path] = p
        elements.append(
            {
                "path": path,
                "class": cls,
                "why": why,
                "ports": sorted(ports[path]),
                "integral": trapezoid(t, p),
                "throughput": trapezoid(t, np.abs(p)),
            }
        )

    classes = {
        cls: {
            "count": sum(1 for e in elements if e["class"] == cls),
            "integral": float(sum(e["integral"] for e in elements if e["class"] == cls)),
        }
        for cls in CLASSES
    }
    total = np.sum([power[e["path"]] for e in elements], axis=0)
    residual = trapezoid(t, total)
    residual_max = float(np.max(np.abs(cumulative(t, total))))
    throughput = 0.5 * float(sum(e["throughput"] for e in elements))
    scale = throughput if throughput > 0.0 else 1.0
    result: dict[str, Any] = {
        "run": run.manifest.get("id"),
        "window": [lower, upper],
        "samples": int(t.size),
        "elements": elements,
        "classes": classes,
        "residual": residual,
        "residual_running_max": residual_max,
        "throughput": throughput,
        "residual_rel": residual_max / scale,
        "unclassified": [e["path"] for e in elements if e["class"] == "unclassified"],
        "stored": None,
    }

    if stored is not None:
        energy = stored_energy(run.signals, stored, mask)
        gain = energy - energy[0]

        def running(classes_: tuple[str, ...], sign: float) -> np.ndarray:
            acc = np.zeros(t.size)
            for e in elements:
                if e["class"] in classes_:
                    acc = acc + power[e["path"]]
            return gain - sign * cumulative(t, acc)

        storage_dev = running(("storage",), 1.0)
        supply_dev = running(("source", "dissipation", "mixed"), -1.0)
        result["stored"] = {
            "delta_E": float(energy[-1] - energy[0]),
            "storage_balance": float(storage_dev[-1]),
            "storage_balance_max": float(np.max(np.abs(storage_dev))),
            "supply_balance": float(supply_dev[-1]),
            "supply_balance_max": float(np.max(np.abs(supply_dev))),
            "storage_balance_rel": float(np.max(np.abs(storage_dev))) / scale,
            "supply_balance_rel": float(np.max(np.abs(supply_dev))) / scale,
        }
    return result


def worst_ratio(result: dict[str, Any]) -> float:
    """The largest normalised residual of a ledger (Tellegen and, if present, the balances)."""
    ratios = [result["residual_rel"]]
    if result["stored"] is not None:
        ratios += [result["stored"]["storage_balance_rel"], result["stored"]["supply_balance_rel"]]
    return max(ratios)


def energy_balance(
    run_dir: Path,
    *,
    tol: float = 1e-6,
    stored: list[dict[str, Any]] | None = None,
    overrides: dict[str, str] | None = None,
    model: dict[str, Any] | None = None,
    project_dir: Path | None = None,
    from_t: float | None = None,
    to_t: float | None = None,
) -> dict[str, Any]:
    """Read a run directory and return its ledger with ``tol`` and ``ok`` set."""
    run = read_run(Path(run_dir))
    return balance_run(run, tol=tol, stored=stored, overrides=overrides, model=model,
                       project_dir=project_dir, from_t=from_t, to_t=to_t)


def balance_run(
    run: RunData,
    *,
    tol: float = 1e-6,
    stored: list[dict[str, Any]] | None = None,
    overrides: dict[str, str] | None = None,
    model: dict[str, Any] | None = None,
    project_dir: Path | None = None,
    from_t: float | None = None,
    to_t: float | None = None,
) -> dict[str, Any]:
    """The ledger of an in-memory run; the model is discovered from the run dir if needed."""
    if model is None and run.run_dir is not None:
        model, found = discover_model(run.run_dir, run.manifest)
        project_dir = project_dir or found
    classifier = Classifier(model, project_dir, overrides)
    result = ledger(run, classifier, stored=stored, from_t=from_t, to_t=to_t)
    result["tol"] = tol
    result["ratio"] = worst_ratio(result)
    result["ok"] = bool(result["ratio"] <= tol)
    return result


# --------------------------------------------------------------------------- output


def format_table(result: dict[str, Any]) -> str:
    """A readable ledger table."""
    lines = [
        f"energy ledger of run {result['run']} over [{result['window'][0]:g}, "
        f"{result['window'][1]:g}] s ({result['samples']} samples); W = integral P dt, "
        "power into the element",
        f"{'class':<12} {'element':<34} {'W [J]':>14} {'throughput [J]':>15}",
    ]
    for cls in CLASSES:
        rows = [e for e in result["elements"] if e["class"] == cls]
        if not rows:
            continue
        for e in rows:
            if e["throughput"] == 0.0 and e["integral"] == 0.0:
                continue
            lines.append(f"{cls:<12} {e['path']:<34} {e['integral']:>14.6e} {e['throughput']:>15.6e}")
        lines.append(f"{cls:<12} {'= total (' + str(result['classes'][cls]['count']) + ' elements)':<34} "
                     f"{result['classes'][cls]['integral']:>14.6e}")
    lines.append(f"{'residual':<12} {'sum_all W (Tellegen)':<34} {result['residual']:>14.6e}")
    lines.append(
        f"running max |integral sum P| {result['residual_running_max']:.6e} J; throughput "
        f"{result['throughput']:.6e} J; relative {result['residual_rel']:.3e}"
    )
    if result["stored"] is not None:
        s = result["stored"]
        lines.append(
            f"stored energy: Delta E {s['delta_E']:.6e} J; storage balance max "
            f"{s['storage_balance_max']:.3e} J (rel {s['storage_balance_rel']:.3e}); supply balance "
            f"max {s['supply_balance_max']:.3e} J (rel {s['supply_balance_rel']:.3e})"
        )
    if result["unclassified"]:
        lines.append("unclassified (use --override): " + ", ".join(result["unclassified"]))
    lines.append(
        f"{'PASS' if result['ok'] else 'FAIL'}: worst relative ratio {result['ratio']:.3e} "
        f"(tol {result['tol']:g})"
    )
    return "\n".join(lines)


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description="Port-power energy ledger of a run directory")
    parser.add_argument("run_dir", type=Path)
    parser.add_argument("--tol", type=float, default=1e-6, help="relative tolerance (default 1e-6)")
    parser.add_argument("--json", type=Path, default=None, help="write the JSON summary here")
    parser.add_argument("--override", action="append", default=[], metavar="GLOB=CLASS")
    parser.add_argument("--stored", type=Path, default=None, help="JSON list of stored-energy terms")
    parser.add_argument("--model", type=Path, default=None, help="model document (default: discovered)")
    parser.add_argument("--from-t", type=float, default=None)
    parser.add_argument("--to-t", type=float, default=None)
    parser.add_argument("--strict", action="store_true", help="fail when an element is unclassified")
    args = parser.parse_args(argv)
    try:
        overrides: dict[str, str] = {}
        for item in args.override:
            pattern, _, cls = item.rpartition("=")
            if not pattern:
                raise ValueError(f"--override {item!r}: expected GLOB=CLASS")
            overrides[pattern] = cls
        stored = json.loads(args.stored.read_text(encoding="utf-8")) if args.stored else None
        model = json.loads(args.model.read_text(encoding="utf-8")) if args.model else None
        result = energy_balance(
            args.run_dir, tol=args.tol, stored=stored, overrides=overrides, model=model,
            from_t=args.from_t, to_t=args.to_t,
        )
    except (OSError, ValueError, KeyError) as exc:
        print(f"energy_balance: {exc}", file=sys.stderr)
        return 2
    print(format_table(result))
    if args.json:
        args.json.write_text(json.dumps(result, indent=2), encoding="utf-8")
    if args.strict and result["unclassified"]:
        return 1
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
