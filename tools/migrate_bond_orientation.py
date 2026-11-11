# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""Migrate model documents to the declared port orientations (plan/PORT_ORIENTATION_PLAN.md, O9, O19).

Usage::

    uv run tools/migrate_bond_orientation.py [--check] [--catalog FILE] [--project DIR]
                                             [--no-law-changes] PATH [PATH ...]

``PATH`` is a model document (``*.bgmodel.json`` or any ``bgsim.model`` JSON) or an example /
project directory (every ``models/*.bgmodel.json`` in it). The project directory of a model is
``--project``, else the folder above ``models/`` when it holds ``bgsim.project.json``; its
``library/`` blocks join the catalog and its ``expected.json`` is updated with the model.

The catalog (the ``orientation`` field of every block) comes from ``--catalog`` (a catalog JSON
as the worker returns it) or from the Julia library (``julia --project=julia/BGSim``, one call per
project directory).

What the tool does, per model:

1. **Bonds.** A bond whose end at an ``in`` port is its tail, or whose end at an ``out`` port is
   its head, is reversed. A ``through`` pair (O13) whose two bonds both arrive or both leave gets
   one of its bonds reversed, the one whose other end is free. A bond between two ``in`` (or two
   ``out``) ports cannot be fixed by reversing it: it is reported (``review``, "put a junction in
   between") and left.
2. **Signs, junction-aware (O19).** Reversing a bond on a 1-junction negates ``(e, f)`` of that
   port; on a 0-junction or between two element ports it changes nothing. A negation travels along
   a *chain*: element-to-element bonds and the two sides of a ``through`` two-port. A block whose
   law changed (``LAW_CHANGES``: ``Sf`` and ``MSf`` impose ``+f`` at the tail since O15; the
   mechanics blocks of WP-O3a, O7, on the ports of ``LAW_PORTS``: a joint's ``child``, a contact's
   ports, the gravity, external-wrench and planar/spatial flow sources) negates its own port too.
   The face of a body composite (``JUNCTION_FACES``: ``RigidBody2D``/``3D``, ``Free2D``, the flexible
   bodies) is an internal 1-junction whose contents changed sign with O7: the tool treats it as a
   junction with a virtual element inside that must keep its sign (else ``review``).
   Per connected group of junctions and chains the tool picks the cheaper of the two
   equivalent sign choices (renaming a junction's flow or effort is free), then classifies every
   element whose port sign flips:

   * **neutral**: nothing to do (the chain does not flip), or an odd element (linear ``C``, ``I``,
     ``R``, ``MR``, a detector or a one-terminal sensor whose output feeds nothing, an iconic
     ground, or a linear iconic two-terminal element such as a ``Spring``, ``Mass``, ``Inertia`` or
     ``Resistor`` whose terminals *all* flip, ``ODD_MULTI``) whose start values are negated;
   * **source**: a source (``Se``, ``Sf``, ``MSe``, ``MSf``, an iconic ``SpeedSource``,
     ``VelocitySource`` or ``PressureSource``, or a two-terminal iconic source whose terminals all
     flip, ``SOURCES_MULTI``) whose value expression is negated;
   * **review**: anything else (an asymmetric law, a multi-port block on two chains, an iconic
     two-terminal element with only one terminal flipped, a detector whose output drives a
     controller, an inline block, ...). The tool never guesses: every edit of that group is
     withheld and reported.

   Iconic (wire-domain) power ports are ``in`` (O20): a bond to one ends at the port, which then
   behaves exactly as if it were wired to that junction.
3. **Signal references.** A port variable ``<path>/<port>.e|.f`` on a flipped chain, and an odd
   variable of a flipped element, change sign in recorded results (O18). The tool negates a
   binding's ``gain``, and in ``expected.json`` the ``value`` of ``final_value`` /
   ``cursor_value``, the ``level`` and ``direction`` of ``zero_crossing`` and the ``value`` of a
   ``ratio`` with one flipped signal; sign-free checks (``max_abs``, ``max_abs_le``, ``period``,
   ``fft_peak``, ``ripple``, ``damping``, a comparison of two flipped signals) stay. Plots and
   dashboard cards cannot hold a sign: they are listed. A check it cannot negate is ``review``.

A node whose law change has been accounted for gets a ``$comment`` marker
(``migrate_bond_orientation: O15``), so a second run changes nothing: the tool is idempotent.
``--no-law-changes`` skips the law step (for a model written after the change).

Files are edited in place, keeping their formatting (only the changed values are rewritten).
``--check`` writes nothing. Exit status: 0 nothing to do (or done), 1 with ``--check`` when there
are changes to make, 2 when a ``review`` case is left.
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
import tempfile
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parents[1]
JULIA_PROJECT = REPO / "julia" / "BGSim"

# Blocks whose port law changed sign, with the decision that changed it. A model written before
# the change sees the block's port negated (WP-O3a adds the planar and spatial ones).
LAW_CHANGES: dict[str, str] = {
    "stdlib:bondgraph/Sf": "O15",
    "stdlib:bondgraph/MSf": "O15",
}

# WP-O3a (O7): the multibond mechanics blocks whose port law changed sign, with the ports it
# changed on (port flow = the true body twist, port effort = minus the wrench on the body; a
# joint's `child` side: `V_c = -child.f`, `W_c = -child.e`).
_JOINTS = [f"stdlib:spatial/{j}" for j in (
    "Free3D", "Revolute3D", "Revolute3DCompliant", "Revolute3DFriction", "Revolute3DLimit",
    "Revolute3DRigid", "Prismatic3D", "Prismatic3DCompliant", "Prismatic3DFriction",
    "Prismatic3DLimit", "Cylindrical3D", "Helical3D", "Planar3D", "Spherical3D", "Universal3D")] + [
    "stdlib:multibond/Revolute2D", "stdlib:planar/Prismatic2D", "stdlib:planar/Revolute2DCompliant",
    "stdlib:planar/Revolute2DFriction", "stdlib:planar/Revolute2DLimit", "stdlib:contact/SwitchedPivot3D"]
LAW_PORTS: dict[str, tuple[str, ...]] = {
    **{j: ("child",) for j in _JOINTS},
    "stdlib:contact/ContactPoint": ("p",),
    "stdlib:contact/MovingPlaneContact": ("p",),
    "stdlib:contact/RollingDisk": ("p",),
    "stdlib:contact/RollingSphere": ("a", "b"),
    "stdlib:contact/SuctionCup": ("a", "b"),
    "stdlib:contact/Tyre": ("p",),
    "stdlib:contact/ImpactBody3D": ("p",),
    "stdlib:spatial/Rotor3D": ("p",),
    "stdlib:multibond/GravityPlanar": ("p",),
    "stdlib:multibond/GravitySpatial": ("p",),
    "stdlib:multibond/ExternalWrenchPlanar": ("p",),
    "stdlib:multibond/ExternalWrenchSpatial": ("p",),
    "stdlib:multibond/SfPlanar": ("p",),
    "stdlib:multibond/SfSpatial": ("p",),
    "stdlib:multibond/MSfPlanar": ("p",),
}
LAW_CHANGES.update({ref: "O7" for ref in LAW_PORTS})

# The faces of the body composites: each is an internal 1-junction whose contents (inertia,
# Coriolis, twist sensor, gravity, beam or modal core) changed sign with O7. Old junction flow =
# minus the body twist, new = the body twist. The tool resolves such a face to a junction
# `<path>#<port>` with a virtual element inside (law change O7 on its port `p`).
JUNCTION_FACES: dict[str, tuple[str, ...]] = {
    "stdlib:spatial/RigidBody3D": ("p",),
    "stdlib:planar/RigidBody2D": ("p",),
    "stdlib:planar/Free2D": ("p",),
    "stdlib:planar/PinNode2D": ("p",),
    "stdlib:planar/Bar2D": ("a", "b"),
    "stdlib:planar/FlexibleBeam2D": ("A", "B"),
    "stdlib:spatial/FlexibleBeam3D": ("A", "B"),
    "stdlib:spatial/ModalBody3D": ("A", "B", "C", "D", "E", "S"),
}
FACE = "face:"
for _ref in JUNCTION_FACES:
    LAW_CHANGES[FACE + _ref] = "O7"
    LAW_PORTS[FACE + _ref] = ("p",)

# Internal signals of a composite that change sign in recorded results once its O7 change is
# accounted for (the composite keeps its motion; these port variables are negated).
COMPOSITE_FLIPS: dict[str, tuple[str, ...]] = {
    "stdlib:spatial/RigidBody3D": ("gravity/p",),
    "stdlib:planar/RigidBody2D": ("gravity/p",),
    "stdlib:planar/Free2D": ("body/gravity/p",),
    "stdlib:contact/ImpactBody3D": ("gravity/p", "mount/a", "mount/b"),
}

# Blocks the tool never edits around: their migration needs a decision by hand.
REVIEW_ALWAYS: dict[str, str] = {
    "stdlib:planar/Revolute2DRigid": ("its internal rate sensor was reversed (WP-O3a), so a torque "
                                      "source on `drive` now acts with the opposite sign; check the "
                                      "drive value and the child bond by hand"),
}

# Blocks whose port flip cannot be absorbed by a parameter: the value comes from a signal input
# (or from a physical constant) and has to be negated by hand.
SIGNAL_SOURCES: dict[str, str] = {
    "stdlib:multibond/SePlanar": "its input `u`",
    "stdlib:multibond/SeSpatial": "its input `u`",
    "stdlib:multibond/MSePlanar": "its inputs `ur`, `ux`, `uy`",
    "stdlib:multibond/SfPlanar": "its input `u`",
    "stdlib:multibond/SfSpatial": "its input `u`",
    "stdlib:multibond/MSfPlanar": "its inputs `vr`, `vx`, `vy`",
    "stdlib:multibond/ExternalWrenchPlanar": "its inputs `wr`, `wx`, `wy`",
    "stdlib:multibond/ExternalWrenchSpatial": "its wrench inputs",
    "stdlib:multibond/GravityPlanar": "gravity (it cannot be negated)",
    "stdlib:multibond/GravitySpatial": "gravity (it cannot be negated)",
}
MARKER = "migrate_bond_orientation: {decision}"

# Sources: the parameter whose negation restores the model when the port flips.
SOURCES: dict[str, str] = {
    "stdlib:bondgraph/Se": "e",
    "stdlib:bondgraph/Sf": "f",
    "stdlib:bondgraph/MSe": "gain",
    "stdlib:bondgraph/MSf": "gain",
    # O20: the one-terminal iconic sources (their value factor; the input `u` multiplies it).
    "stdlib:rotation/SpeedSource": "w",
    "stdlib:translation/VelocitySource": "v",
    "stdlib:hydraulic/PressureSource": "p",
}

# Odd one-ports: (e, f) -> (-e, -f) maps the law onto itself when these variables are negated too.
# A start value of such a variable is negated; an output among them must feed nothing.
ODD: dict[str, tuple[str, ...]] = {
    "stdlib:bondgraph/C": ("q",),
    "stdlib:bondgraph/I": ("P",),
    "stdlib:bondgraph/R": (),
    "stdlib:bondgraph/MR": (),
    "stdlib:bondgraph/De": ("y",),
    "stdlib:bondgraph/Df": ("y",),
    "stdlib:converters/SpeedSensor": ("y",),
    "stdlib:converters/AngleSensor": ("y", "phi"),
    "stdlib:converters/PositionSensor": ("y", "x"),
    "stdlib:converters/VelocitySensor": ("y",),
    "stdlib:converters/AccelerationSensor": ("y", "v"),
    "stdlib:converters/PressureSensor": ("y",),
    # WP-O3a: the linear multibond one-ports (an output that feeds a block makes it review).
    "stdlib:multibond/IPlanar": ("P", "Pm", "wout"),
    "stdlib:multibond/ISpatial": ("P", "Pm", "twout"),
    "stdlib:multibond/CPlanar": ("qr", "qx", "qy"),
    "stdlib:multibond/CSpatial": ("qrx", "qry", "qrz", "qx", "qy", "qz"),
    "stdlib:multibond/RPlanar": (),
    "stdlib:multibond/RSpatial": (),
    "stdlib:multibond/DePlanar": ("y",),
    "stdlib:multibond/DeSpatial": ("y",),
    "stdlib:multibond/DfPlanar": ("y",),
    "stdlib:multibond/DfSpatial": ("y",),
    # O20: the one-terminal iconic grounds (a.f = 0 or p.e = 0 is sign-symmetric).
    "stdlib:translation/Fixed": (),
    "stdlib:rotation/FixedShaft": (),
    "stdlib:electrical/Ground": (),
}
ODD_OUTPUTS = {"y"}

# O20: iconic (wire-domain) blocks with several power ports, all `in`. A linear two-terminal
# element is odd-symmetric only as a whole: negating (e, f) of *every* power port together with
# these variables maps the law onto itself, so reversing the bonds of all its terminals on their
# 1-junctions is neutral, while reversing one terminal is not (review). A port that is wired or
# not bonded keeps its sign.
ODD_MULTI: dict[str, tuple[str, ...]] = {
    "stdlib:translation/Spring": ("x",),
    "stdlib:translation/Damper": (),
    "stdlib:translation/SpringDamper": ("x",),
    "stdlib:translation/Mass": ("x", "v"),
    "stdlib:rotation/TorsionSpring": ("phi",),
    "stdlib:rotation/RotationalDamper": (),
    "stdlib:rotation/ElasticShaft": ("phi",),
    "stdlib:rotation/Inertia": ("phi", "w"),
    "stdlib:rotation/IdealGear": (),
    "stdlib:electrical/Resistor": (),
    "stdlib:electrical/Capacitor": ("v",),
    "stdlib:electrical/Inductor": ("i",),
    "stdlib:thermal/ThermalConductor": ("dT", "Q"),
    "stdlib:converters/EMConverter": (),
    "stdlib:converters/RackAndPinion": (),
    "stdlib:converters/Wheel": (),
    "stdlib:converters/ForceSensor": ("y",),
    "stdlib:converters/TorqueSensor": ("y",),
    "stdlib:converters/CurrentSensor": ("y",),
    "stdlib:converters/VoltageSensor": ("y",),
    "stdlib:converters/FlowSensor": ("y",),
    "stdlib:thermal/HeatFlowSensor": ("y",),
}
# O20: the two-terminal iconic sources: with every terminal reversed, negating the value restores
# the model.
SOURCES_MULTI: dict[str, str] = {
    "stdlib:translation/ForceSource": "F",
    "stdlib:rotation/TorqueSource": "T",
    "stdlib:electrical/VoltageSource": "V",
    "stdlib:electrical/CurrentSource": "I",
    "stdlib:hydraulic/FlowSource": "Q",
}
# A spring with a rest deflection is odd only when the rest is zero (else review).
ODD_REST: dict[str, tuple[str, ...]] = {
    "stdlib:translation/Spring": ("x_free",),
    "stdlib:rotation/TorsionSpring": ("phi_free",),
    "stdlib:multibond/CPlanar": ("qr0", "qx0", "qy0"),
    "stdlib:multibond/CSpatial": ("qrx0", "qry0", "qrz0", "qx0", "qy0", "qz0"),
}

# The cost of a sign choice. A review case is the last resort; negating a source value keeps every
# other signal of the model, so it is preferred to flipping an odd element, whose variables (a
# state, a sensed value) change sign in the results (O18 keeps states and physical outputs).
# One lookup for the start/variable and value edits of single- and multi-port blocks.
ODD_ALL: dict[str, tuple[str, ...]] = {**ODD, **ODD_MULTI}
SOURCE_PARAM: dict[str, str] = {**SOURCES, **SOURCES_MULTI}

COST_REVIEW = 1000.0
COST_SOURCE = 1.0
COST_ODD = 20.0
COST_ODD_VAR = 5.0
COST_THROUGH = 2.0
COST_PORT = 0.1
COST_REFERENCED = 1.0


# ---------------------------------------------------------------------------------------------
# A JSON parser that keeps the source span of every value, for format-preserving edits
# ---------------------------------------------------------------------------------------------


@dataclass
class Span:
    start: int
    end: int
    kind: str  # "object" | "array" | "scalar"
    children: Any = None  # object: {key: Span}; array: [Span]


class SpanParser:
    _ws = re.compile(r"[ \t\r\n]*")
    _num = re.compile(r"-?(?:0|[1-9]\d*)(?:\.\d+)?(?:[eE][+-]?\d+)?")

    def __init__(self, text: str):
        self.t = text
        self.i = 0

    def skip(self) -> None:
        self.i = self._ws.match(self.t, self.i).end()

    def parse(self) -> Span:
        self.skip()
        span = self.value()
        self.skip()
        if self.i != len(self.t):
            raise ValueError("trailing data")
        return span

    def string_end(self, i: int) -> int:
        assert self.t[i] == '"'
        i += 1
        while True:
            c = self.t[i]
            if c == "\\":
                i += 2
            elif c == '"':
                return i + 1
            else:
                i += 1

    def value(self) -> Span:
        c = self.t[self.i]
        start = self.i
        if c == "{":
            self.i += 1
            kids: dict[str, Span] = {}
            self.skip()
            if self.t[self.i] == "}":
                self.i += 1
                return Span(start, self.i, "object", kids)
            while True:
                self.skip()
                kend = self.string_end(self.i)
                key = json.loads(self.t[self.i:kend])
                self.i = kend
                self.skip()
                assert self.t[self.i] == ":"
                self.i += 1
                self.skip()
                kids[key] = self.value()
                self.skip()
                if self.t[self.i] == ",":
                    self.i += 1
                    continue
                assert self.t[self.i] == "}"
                self.i += 1
                return Span(start, self.i, "object", kids)
        if c == "[":
            self.i += 1
            items: list[Span] = []
            self.skip()
            if self.t[self.i] == "]":
                self.i += 1
                return Span(start, self.i, "array", items)
            while True:
                self.skip()
                items.append(self.value())
                self.skip()
                if self.t[self.i] == ",":
                    self.i += 1
                    continue
                assert self.t[self.i] == "]"
                self.i += 1
                return Span(start, self.i, "array", items)
        if c == '"':
            self.i = self.string_end(self.i)
        elif self.t.startswith("true", self.i):
            self.i += 4
        elif self.t.startswith("false", self.i):
            self.i += 5
        elif self.t.startswith("null", self.i):
            self.i += 4
        else:
            m = self._num.match(self.t, self.i)
            if not m:
                raise ValueError(f"bad JSON at {self.i}")
            self.i = m.end()
        return Span(start, self.i, "scalar")


class JsonDoc:
    """A JSON file with its parsed value and a list of pending, format-preserving edits."""

    def __init__(self, path: Path):
        self.path = path
        self.text = path.read_text(encoding="utf-8")
        self.data = json.loads(self.text)
        self.root = SpanParser(self.text).parse()
        self.edits: list[tuple[int, int, str]] = []

    def span(self, path: tuple) -> Span:
        s = self.root
        for k in path:
            s = s.children[k]
        return s

    def get(self, path: tuple) -> Any:
        v = self.data
        for k in path:
            v = v[k]
        return v

    def _set(self, path: tuple, value: Any) -> None:
        v = self.data
        for k in path[:-1]:
            v = v[k]
        v[path[-1]] = value

    def replace(self, path: tuple, value: Any) -> None:
        s = self.span(path)
        self.edits.append((s.start, s.end, json.dumps(value, ensure_ascii=False)))
        self._set(path, value)

    def swap(self, path_a: tuple, path_b: tuple) -> None:
        sa, sb = self.span(path_a), self.span(path_b)
        ta, tb = self.text[sa.start:sa.end], self.text[sb.start:sb.end]
        self.edits.append((sa.start, sa.end, tb))
        self.edits.append((sb.start, sb.end, ta))
        va, vb = self.get(path_a), self.get(path_b)
        self._set(path_a, vb)
        self._set(path_b, va)

    def set_key(self, obj_path: tuple, key: str, value: Any) -> None:
        obj = self.get(obj_path)
        if key in obj:
            self.replace(obj_path + (key,), value)
            return
        s = self.span(obj_path)
        entry = f"{json.dumps(key)}: {json.dumps(value, ensure_ascii=False)}"
        if not obj:
            self.edits.append((s.start, s.end, "{ " + entry + " }"))
        else:
            first = next(iter(s.children.values()))
            # insert before the first key, keeping its line layout
            key_start = self.text.rfind('"', s.start, first.start)
            key_start = self.text.rfind('"', s.start, key_start)
            prefix = self.text[s.start + 1:key_start]
            sep = "," + prefix if "\n" in prefix else ", "
            self.edits.append((key_start, key_start, entry + sep))
        obj[key] = value

    def save(self) -> bool:
        if not self.edits:
            return False
        text = self.text
        for start, end, new in sorted(self.edits, key=lambda e: (e[0], e[1]), reverse=True):
            text = text[:start] + new + text[end:]
        if json.loads(text) != self.data:
            raise RuntimeError(f"{self.path}: the edited text does not match the edited document")
        self.path.write_text(text, encoding="utf-8", newline="\n")
        return True


# ---------------------------------------------------------------------------------------------
# Catalog
# ---------------------------------------------------------------------------------------------


@dataclass
class BlockInfo:
    ref: str
    ports: list[str]
    orientation: dict[str, tuple[str, str | None]]  # port -> (kind, through partner)
    defaults: dict[str, str]
    outputs: list[str]


def catalog_from_json(doc: dict) -> dict[str, BlockInfo]:
    out = {}
    for b in doc["blocks"]:
        orient: dict[str, tuple[str, str | None]] = {}
        for entry in b.get("orientation", []):
            ports = entry["ports"]
            if entry["kind"] == "through":
                orient[ports[0]] = ("through", ports[1])
                orient[ports[1]] = ("through", ports[0])
            else:
                orient[ports[0]] = (entry["kind"], None)
        out[b["ref"]] = BlockInfo(
            ref=b["ref"],
            ports=[p["name"] for p in b.get("ports", [])],
            orientation=orient,
            defaults={p["name"]: p.get("default") for p in b.get("parameters", [])},
            outputs=[o["name"] for o in b.get("outputs", [])],
        )
    return out


_JULIA_DUMP = """
using BGSim, JSON3
for (i, proj) in enumerate(ARGS[2:end])
    c = proj == "-" ? BGSim.Library.catalog() : BGSim.Library.catalog(proj)
    open(io -> JSON3.write(io, c), joinpath(ARGS[1], "catalog$i.json"), "w")
end
"""


def catalogs_from_julia(projects: list[Path | None]) -> dict[Path | None, dict[str, BlockInfo]]:
    """The catalog of each project directory (None: the stdlib alone), from one Julia process."""
    with tempfile.TemporaryDirectory() as tmp:
        cmd = ["julia", f"--project={JULIA_PROJECT}", "-e", _JULIA_DUMP, tmp]
        cmd += ["-" if p is None else str(p) for p in projects]
        proc = subprocess.run(cmd, capture_output=True, text=True, check=False)
        if proc.returncode != 0:
            raise SystemExit(f"catalog dump failed:\n{proc.stdout}\n{proc.stderr}")
        return {p: catalog_from_json(json.loads((Path(tmp) / f"catalog{i + 1}.json").read_text(encoding="utf-8")))
                for i, p in enumerate(projects)}


# ---------------------------------------------------------------------------------------------
# The model graph
# ---------------------------------------------------------------------------------------------


@dataclass
class Inst:
    path: str
    ref: str | None  # None: inline block
    node_path: tuple  # JSON path of the node in the document
    node: dict
    consumed_outputs: set = field(default_factory=set)


@dataclass
class End:
    kind: str  # "J" | "P"
    path: str  # junction or instance path
    port: str | None = None
    jkind: int | None = None


@dataclass
class Bond:
    cid: str
    conn_path: tuple
    tail: End
    head: End
    reverse: bool = False
    review: str | None = None


class Model:
    def __init__(self, doc: JsonDoc):
        self.doc = doc
        self.insts: dict[str, Inst] = {}
        self.juncs: dict[str, int] = {}
        self.bonds: list[Bond] = []
        self._walk(("diagram",), "")

    def _face(self, path: str, port: str) -> End:
        """The junction behind a body composite's face, with its virtual inside element."""
        jpath = f"{path}#{port}"
        if jpath not in self.juncs:
            inst = self.insts[path]
            self.juncs[jpath] = 1
            vpath = jpath + "#inside"
            self.insts[vpath] = Inst(vpath, FACE + (inst.ref or ""), inst.node_path, inst.node)
            self.bonds.append(Bond(f"{jpath}(inside)", (), End("J", jpath, None, 1), End("P", vpath, "p")))
        return End("J", jpath, None, 1)

    def _walk(self, dpath: tuple, prefix: str) -> None:
        diagram = self.doc.get(dpath)
        nodes = {n["id"]: (i, n) for i, n in enumerate(diagram.get("nodes", []))}
        for i, n in nodes.values():
            path = prefix + n["name"]
            block = n["block"]
            npath = dpath + ("nodes", i)
            if "junction" in block:
                self.juncs[path] = int(block["junction"])
            elif "subsystem" in block:
                self._walk(npath + ("block", "subsystem", "diagram"), path + "/")
            else:
                self.insts[path] = Inst(path, block.get("ref"), npath, n)
        for ci, c in enumerate(diagram.get("connections", [])):
            if c["kind"] == "signal":
                src = self._resolve(dpath, prefix, c["from"], signal=True)
                if src is not None and src.kind == "P" and src.path in self.insts:
                    self.insts[src.path].consumed_outputs.add(src.port)
                continue
            if c["kind"] != "bond":
                continue
            tail = self._resolve(dpath, prefix, c["from"])
            head = self._resolve(dpath, prefix, c["to"])
            if tail is None or head is None:
                continue
            label = prefix + c["id"]
            self.bonds.append(Bond(label, dpath + ("connections", ci), tail, head))
        # a subsystem output port exposes an inner output: count it as consumed
        for sp in diagram.get("subsystemPorts", []) or []:
            if sp.get("kind") == "signal":
                inner = nodes.get(sp["node"])
                if inner is not None:
                    p = prefix + inner[1]["name"]
                    if p in self.insts:
                        self.insts[p].consumed_outputs.add(sp["port"])

    def _resolve(self, dpath: tuple, prefix: str, ep: dict, signal: bool = False) -> End | None:
        diagram = self.doc.get(dpath)
        for i, n in enumerate(diagram.get("nodes", [])):
            if n["id"] != ep["node"]:
                continue
            path = prefix + n["name"]
            block = n["block"]
            if "junction" in block:
                return End("J", path, None, int(block["junction"]))
            if "subsystem" in block:
                sub = block["subsystem"]
                for p in sub["ports"]:
                    if p["name"] == ep.get("port"):
                        inner_d = dpath + ("nodes", i, "block", "subsystem", "diagram")
                        return self._resolve(inner_d, path + "/",
                                             {"node": p["node"], "port": p.get("port")}, signal)
                return None
            if not signal and block.get("ref") in JUNCTION_FACES \
                    and ep.get("port") in JUNCTION_FACES[block["ref"]] and path in self.insts:
                return self._face(path, ep["port"])
            return End("P", path, ep.get("port"))
        return None


# ---------------------------------------------------------------------------------------------
# Sign analysis
# ---------------------------------------------------------------------------------------------


class ParityUF:
    def __init__(self):
        self.parent: dict = {}
        self.par: dict = {}  # parity to parent
        self.bad: set = set()

    def find(self, x):
        if x not in self.parent:
            self.parent[x] = x
            self.par[x] = 0
        if self.parent[x] == x:
            return x, 0
        root, p = self.find(self.parent[x])
        self.par[x] ^= p
        self.parent[x] = root
        return root, self.par[x]

    def union(self, a, b, parity: int) -> None:
        ra, pa = self.find(a)
        rb, pb = self.find(b)
        if ra == rb:
            if pa ^ pb != parity:
                self.bad.add(ra)
            return
        self.parent[ra] = rb
        self.par[ra] = pa ^ pb ^ parity
        if ra in self.bad:
            self.bad.discard(ra)
            self.bad.add(rb)


class UF:
    def __init__(self):
        self.p: dict = {}

    def find(self, x):
        self.p.setdefault(x, x)
        while self.p[x] != x:
            self.p[x] = self.p[self.p[x]]
            x = self.p[x]
        return x

    def union(self, a, b):
        self.p[self.find(a)] = self.find(b)


@dataclass
class Change:
    cls: str  # neutral | source | review
    text: str


@dataclass
class Result:
    label: str
    changes: list[Change] = field(default_factory=list)
    flipped: set = field(default_factory=set)  # signal ids whose sign changes
    notes: list[str] = field(default_factory=list)

    @property
    def review(self) -> bool:
        return any(c.cls == "review" for c in self.changes)


def _orient(cat: dict[str, BlockInfo], m: Model, end: End) -> tuple[str, str | None]:
    if end.kind != "P":
        return ("junction", None)
    inst = m.insts.get(end.path)
    if inst is None or inst.ref is None or inst.ref not in cat:
        return ("any", None)
    return cat[inst.ref].orientation.get(end.port, ("any", None))


def _role(b: Bond, end_is_tail: bool) -> str:
    """'tail' or 'head' of that end after the planned reversal."""
    tail = end_is_tail != b.reverse
    return "tail" if tail else "head"


def plan_reversals(m: Model, cat: dict[str, BlockInfo]) -> None:
    fixed = ("in", "out")
    for b in m.bonds:
        ot, oh = _orient(cat, m, b.tail)[0], _orient(cat, m, b.head)[0]
        if ot in fixed and ot == oh:
            b.review = (f"bond `{b.cid}` joins two `{ot}` ports: no direction satisfies both; "
                        "put a junction in between")
            continue
        if ot == "in" or oh == "out":
            b.reverse = True
    # through pairs: one bond arrives, the other leaves
    at: dict[tuple[str, str], list[tuple[Bond, bool]]] = defaultdict(list)
    for b in m.bonds:
        for end, is_tail in ((b.tail, True), (b.head, False)):
            if end.kind == "P":
                at[(end.path, end.port)].append((b, is_tail))
    pairs = set()
    for path, port in at:
        o, partner = _orient(cat, m, End("P", path, port))
        if o == "through" and partner is not None:
            pairs.add((path,) + tuple(sorted((port, partner))))
    locked: set[int] = {id(b) for b in m.bonds
                        if any(_orient(cat, m, e)[0] in fixed for e in (b.tail, b.head))}
    for _ in range(len(pairs) + 2):
        changed = False
        for path, p, q in sorted(pairs):
            bp, bq = at.get((path, p), []), at.get((path, q), [])
            if len(bp) != 1 or len(bq) != 1:
                continue
            (b1, t1), (b2, t2) = bp[0], bq[0]
            if b1 is b2 or _role(b1, t1) != _role(b2, t2):
                continue
            cand = [b for b in (b2, b1) if id(b) not in locked and b.review is None]
            if not cand:
                for b in (b1, b2):
                    b.review = (f"the through pair ({p}, {q}) of `{path}` has both bonds "
                                f"{'arriving' if _role(b1, t1) == 'head' else 'leaving'} and "
                                "neither can be reversed: put a junction in between")
                continue
            # prefer a bond whose other end is a junction or an `any` port
            def other_free(b, path=path):
                ends = [e for e in (b.tail, b.head) if not (e.kind == "P" and e.path == path)]
                return all(_orient(cat, m, e)[0] in ("junction", "any") for e in ends)
            cand.sort(key=lambda b: (not other_free(b),))
            pick = cand[0]
            pick.reverse = not pick.reverse
            locked.add(id(pick))
            changed = True
        if not changed:
            break


def _nonzero(v) -> bool:
    """Whether a parameter value is set to something other than zero (an expression counts)."""
    if v is None:
        return False
    try:
        return float(str(v)) != 0.0
    except ValueError:
        return True


def _negate_expr(s: str) -> str:
    t = s.strip()
    if re.fullmatch(r"[+-]?(\d+\.?\d*|\.\d+)([eE][+-]?\d+)?", t):
        if t.startswith("-"):
            return t[1:]
        return "-" + t.removeprefix("+")
    m = re.fullmatch(r"-\((.*)\)", t)
    if m and _balanced(m.group(1)):
        return m.group(1)
    if t.startswith("-") and not _has_top_level_sum(t[1:]):
        return t[1:].strip()
    if not _has_top_level_sum(t):
        return "-" + t
    return f"-({t})"


def _has_top_level_sum(s: str) -> bool:
    """Whether `s` has a binary + or - outside parentheses (so a leading unary minus does not
    negate the whole expression)."""
    depth = 0
    prev = ""
    for i, c in enumerate(s):
        if c in "([":
            depth += 1
        elif c in ")]":
            depth -= 1
        elif c in "+-" and depth == 0 and i > 0 and (
            prev not in "*/^(,eE" or (prev in "eE" and not re.search(r"\d[eE]$", s[:i]))
        ):
            return True
        if not c.isspace():
            prev = c
    return False


def _balanced(s: str) -> bool:
    d = 0
    for c in s:
        d += c == "("
        d -= c == ")"
        if d < 0:
            return False
    return d == 0


def analyse(m: Model, cat: dict[str, BlockInfo], label: str, law_changes: bool) -> tuple[Result, dict]:
    """Plan the reversals and the sign edits. Returns the report and the edit plan."""
    res = Result(label)
    plan_reversals(m, cat)

    # chains of ports
    chains = UF()
    bonded: set[tuple[str, str]] = set()
    for b in m.bonds:
        for e in (b.tail, b.head):
            if e.kind == "P":
                bonded.add((e.path, e.port))
                chains.find((e.path, e.port))
        if b.tail.kind == "P" and b.head.kind == "P":
            chains.union((b.tail.path, b.tail.port), (b.head.path, b.head.port))
    for path, port in list(bonded):
        o, partner = _orient(cat, m, End("P", path, port))
        if o == "through" and partner and (path, partner) in bonded:
            chains.union((path, port), (path, partner))

    puf = ParityUF()
    for b in m.bonds:
        t, h = b.tail, b.head
        if t.kind == "J" and h.kind == "J":
            puf.union(("J", t.path), ("J", h.path), 0)
        elif t.kind == "J" or h.kind == "J":
            j, p = (t, h) if t.kind == "J" else (h, t)
            rev = 1 if (b.reverse and j.jkind == 1 and b.review is None) else 0
            puf.union(("C", chains.find((p.path, p.port))), ("J", j.path), rev)
        else:
            puf.find(("C", chains.find((t.path, t.port))))

    def s_port(path, port, sigma: dict) -> int:
        if (path, port) not in bonded:
            return 1
        root, par = puf.find(("C", chains.find((path, port))))
        return sigma.get(root, 1) * (-1 if par else 1)

    def marked(inst: Inst) -> bool:
        decision = LAW_CHANGES.get(inst.ref or "")
        return decision is not None and MARKER.format(decision=decision) in inst.node.get("$comment", "")

    def law_flip(inst: Inst) -> bool:
        return law_changes and inst.ref in LAW_CHANGES and not marked(inst)

    def law_ports(inst: Inst) -> set[str]:
        """The ports whose law changed sign (all ports when the table names none)."""
        if not law_flip(inst):
            return set()
        return set(LAW_PORTS.get(inst.ref or "", iports(inst)))

    inst_ports: dict[str, list[str]] = defaultdict(list)
    for path, port in sorted(bonded):
        inst_ports[path].append(port)

    def iports(inst: Inst) -> list[str]:
        return inst_ports.get(inst.path, [])

    relevant = [i for i in m.insts.values() if iports(i)]
    comps = sorted({puf.find(("C", chains.find(k)))[0] for k in bonded} |
                   {puf.find(("J", j))[0] for j in m.juncs}, key=str)

    def element(inst: Inst, sigma: dict) -> tuple[str, str]:
        """(class, detail) of one element under the sign choice."""
        ports = [p for p in iports(inst) if (inst.path, p) in bonded]
        lp = law_ports(inst)
        # the sign of each port relative to the block's law: the junction sign choice, the
        # reversal, and the law change of the port itself
        signs = {p: s_port(inst.path, p, sigma) * (-1 if p in lp else 1) for p in ports}
        info = cat.get(inst.ref or "")
        through = info is not None and all(info.orientation.get(p, ("", None))[0] == "through" for p in ports) \
            and len(ports) == 2
        if inst.ref in REVIEW_ALWAYS:
            return ("review", f"`{inst.path}` ({inst.ref}): {REVIEW_ALWAYS[inst.ref]}")
        if all(s == 1 for s in signs.values()):
            return ("neutral", "")
        if (inst.ref or "").startswith(FACE):
            return ("review", f"the inside of `{inst.path.split('#')[0]}` ({inst.ref[len(FACE):]}) "
                              "would change sign: its face bonds cannot be migrated by sign")
        if through:
            if len(set(signs.values())) == 1 and not lp:
                return ("neutral", "")
            return ("review", f"`{inst.path}`: the two sides of the through pair get opposite signs")
        if inst.ref in ODD_MULTI or inst.ref in SOURCES_MULTI:
            # every power port of the block counts; an unbonded (wired) port keeps its sign
            allp = info.ports if info is not None else ports
            every = {p: signs.get(p, 1) for p in allp}
            if all(v == 1 for v in every.values()):
                return ("neutral", "")
            if any(v == 1 for v in every.values()):
                return ("review", (f"`{inst.path}` ({inst.ref}): only some of its terminals flip "
                                   "sign; reversing one terminal of a two-terminal element is not "
                                   "neutral"))
            if inst.ref in SOURCES_MULTI:
                return ("source", "")
            if inst.ref in ODD_REST and any(_nonzero(inst.node.get("params", {}).get(r))
                                            for r in ODD_REST[inst.ref]):
                return ("review", f"`{inst.path}` ({inst.ref}) flips sign and has a rest deflection")
            used = [o for o in inst.consumed_outputs if o in ODD_MULTI[inst.ref] or o in ODD_OUTPUTS]
            if used:
                return ("review", (f"`{inst.path}` ({inst.ref}) flips sign and its output "
                                   f"`{used[0]}` drives other blocks"))
            starts = [v for v in ODD_MULTI[inst.ref] if v in inst.node.get("starts", {})]
            return ("neutral_start" if starts else "neutral", "")
        if len(ports) != 1:
            return ("review", f"`{inst.path}` ({inst.ref}): multi-port block with a flipped port")
        s_elem = signs[ports[0]]
        if s_elem == 1:
            return ("neutral", "")
        if inst.ref is None:
            return ("review", f"`{inst.path}` (inline block) flips sign")
        if inst.ref in SOURCES:
            return ("source", "")
        if inst.ref in SIGNAL_SOURCES:
            return ("review", f"`{inst.path}` ({inst.ref}) flips sign: negate {SIGNAL_SOURCES[inst.ref]} by hand")
        if inst.ref in ODD_REST and any(_nonzero(inst.node.get("params", {}).get(r))
                                        for r in ODD_REST[inst.ref]):
            return ("review", f"`{inst.path}` ({inst.ref}) flips sign and has a rest deflection")
        if inst.ref in ODD:
            used = [o for o in inst.consumed_outputs if o in ODD[inst.ref] or o in ODD_OUTPUTS]
            if used:
                return ("review", (f"`{inst.path}` ({inst.ref}) flips sign and its output "
                                   f"`{used[0]}` drives other blocks"))
            starts = [v for v in ODD[inst.ref] if v in inst.node.get("starts", {})]
            return ("neutral_start" if starts else "neutral", "")
        return ("review", f"`{inst.path}` ({inst.ref}) flips sign and its law is not known to be odd")

    sigma: dict = {c: 1 for c in comps}
    by_comp: dict = defaultdict(list)
    for inst in relevant:
        for p in iports(inst):
            if (inst.path, p) in bonded:
                by_comp[puf.find(("C", chains.find((inst.path, p))))[0]].append(inst)
    referenced = _referenced_signals(m.doc.data)

    def comp_cost(c) -> float:
        total = 0.0
        for inst in {id(i): i for i in by_comp[c]}.values():
            cls = element(inst, sigma)[0]
            flipped = [p for p in iports(inst) if s_port(inst.path, p, sigma) == -1]
            if cls == "review":
                total += COST_REVIEW
            elif cls == "source":
                total += COST_SOURCE
            elif flipped and inst.ref in ODD_ALL:
                total += COST_ODD + COST_ODD_VAR * len(ODD_ALL[inst.ref])
            elif flipped and len(iports(inst)) == 2:
                total += COST_THROUGH
            for p in flipped:
                total += COST_PORT
                total += sum(COST_REFERENCED for v in ("e", "f") if f"{inst.path}/{p}.{v}" in referenced)
        return total

    for _ in range(4):
        moved = False
        for c in comps:
            if c in puf.bad:
                continue
            before = comp_cost(c)
            sigma[c] = -sigma[c]
            if comp_cost(c) < before - 1e-12:
                moved = True
            else:
                sigma[c] = -sigma[c]
        if not moved:
            break

    # classify and collect edits
    review_comps = set(puf.bad)
    elem_class: dict[str, tuple[str, str]] = {}
    for inst in relevant:
        cls = element(inst, sigma)
        elem_class[inst.path] = cls
        if cls[0] == "review":
            for p in iports(inst):
                if (inst.path, p) in bonded:
                    review_comps.add(puf.find(("C", chains.find((inst.path, p))))[0])

    def comp_of_bond(b: Bond):
        e = b.tail if b.tail.kind == "P" else b.head
        if e.kind == "P":
            return puf.find(("C", chains.find((e.path, e.port))))[0]
        return puf.find(("J", e.path))[0]

    plan = {"reverse": [], "params": [], "starts": [], "markers": []}
    for c in sorted(puf.bad, key=str):
        res.changes.append(Change("review", f"inconsistent signs around `{c[1]}`: left unchanged"))
    for b in m.bonds:
        if b.review:
            res.changes.append(Change("review", b.review))
            continue
        if not b.reverse:
            continue
        comp = comp_of_bond(b)
        if comp in review_comps:
            res.changes.append(Change("review", f"bond `{b.cid}` violates an orientation, but its "
                                                "sign group needs review: left unchanged"))
            continue
        plan["reverse"].append(b)
        # the class of the bond is that of the elements on its own chain (the element ends)
        cls = "neutral"
        roots = {chains.find((e.path, e.port)) for e in (b.tail, b.head) if e.kind == "P"}
        for inst in by_comp[comp]:
            if not any(chains.find((inst.path, p)) in roots for p in iports(inst)):
                continue
            if elem_class.get(inst.path, ("neutral", ""))[0] == "source":
                cls = "source"
        res.changes.append(Change(cls, f"reverse bond `{b.cid}` ({_end(b.tail)} -> {_end(b.head)})"))

    done: set[str] = set()
    for inst in relevant:
        if inst.path in done:
            continue
        done.add(inst.path)
        cls, detail = elem_class[inst.path]
        comps_i = {puf.find(("C", chains.find((inst.path, p))))[0]
                   for p in iports(inst) if (inst.path, p) in bonded}
        if cls == "review":
            res.changes.append(Change("review", detail + ": left unchanged"))
            continue
        if comps_i & review_comps:
            if law_flip(inst):
                res.changes.append(Change("review", f"`{inst.path}` ({inst.ref}) changed its law "
                                                    f"({LAW_CHANGES[inst.ref]}), but its sign group needs review"))
            continue
        port_signs = {p: s_port(inst.path, p, sigma) for p in iports(inst) if (inst.path, p) in bonded}
        for p, s in port_signs.items():
            if s == -1 and "#" not in inst.path:
                res.flipped.update({f"{inst.path}/{p}.e", f"{inst.path}/{p}.f"})
        if law_flip(inst):
            owner = inst.path.split("#")[0]
            base = (inst.ref or "").removeprefix(FACE)
            for sig in COMPOSITE_FLIPS.get(base, ()):
                res.flipped.update({f"{owner}/{sig}.e", f"{owner}/{sig}.f"})
        if cls == "source":
            pname = SOURCE_PARAM[inst.ref]
            old = inst.node.get("params", {}).get(pname)
            if old is None:
                old = cat[inst.ref].defaults.get(pname) or "1.0"
            new = _negate_expr(str(old))
            plan["params"].append((inst, pname, new))
            why = (f"law changed ({LAW_CHANGES[inst.ref]})" if law_flip(inst) and
                   list(port_signs.values()) == [1] else "its port flips")
            res.changes.append(Change("source", f"negate `{inst.path}`.{pname}: {old} -> {new} ({why})"))
        elif cls == "neutral_start":
            for v in ODD_ALL[inst.ref]:
                if v in inst.node.get("starts", {}):
                    old = inst.node["starts"][v]
                    new = _negate_expr(str(old))
                    plan["starts"].append((inst, v, new))
                    res.changes.append(Change("neutral", f"negate start `{inst.path}/{v}`: {old} -> {new}"))
        if cls in ("neutral_start",) or (cls == "neutral" and inst.ref in ODD_ALL and
                                         any(s == -1 for s in port_signs.values())):
            res.flipped.update(f"{inst.path}/{v}" for v in ODD_ALL[inst.ref])
        if law_flip(inst):
            plan["markers"].append(inst)
            if cls == "neutral":
                res.changes.append(Change("neutral", f"`{inst.path}` ({inst.ref}): law change "
                                                     f"{LAW_CHANGES[inst.ref]} cancelled by the reversal"))
    return res, plan


def _end(e: End) -> str:
    return e.path if e.kind == "J" else f"{e.path}.{e.port}"


def _referenced_signals(doc: dict) -> set[str]:
    out: set[str] = set()

    def walk(v):
        if isinstance(v, str):
            out.add(re.sub(r"\[[\d,]+\]$", "", v))
        elif isinstance(v, list):
            for x in v:
                walk(x)
        elif isinstance(v, dict):
            for x in v.values():
                walk(x)

    walk(doc.get("plots", []))
    walk(doc.get("bindings", []))
    walk(doc.get("dashboard", {}))
    return out


# ---------------------------------------------------------------------------------------------
# Signal references
# ---------------------------------------------------------------------------------------------

_SIGN_FREE = {"max_abs", "max_abs_le", "period", "fft_peak", "ripple", "damping", "no_diagnostics",
              "scene_bindings"}


def _sig_strings(v) -> list[str]:
    if isinstance(v, str):
        return [v]
    if isinstance(v, list):
        return [x for x in v if isinstance(x, str)]
    return []


def _flips(sig: str, flipped: set[str]) -> bool:
    return re.sub(r"\[[\d,]+\]$", "", sig) in flipped


def update_model_refs(doc: JsonDoc, res: Result, apply: bool) -> None:
    data = doc.data
    for i, b in enumerate(data.get("bindings", []) or []):
        sigs = _sig_strings(b.get("signal"))
        hit = [s for s in sigs if _flips(s, res.flipped)]
        if not hit:
            continue
        if isinstance(b.get("signal"), str):
            new = -float(b.get("gain", 1.0))
            res.changes.append(Change("neutral", f"binding {b.get('target')}.{b.get('property')}: "
                                                 f"gain -> {new:g} ({hit[0]} changes sign)"))
            if apply:
                doc.set_key(("bindings", i), "gain", new)
        else:
            res.changes.append(Change("review", f"binding {b.get('target')}.{b.get('property')} "
                                                f"reads {hit[0]}, which changes sign"))
    for p in data.get("plots", []) or []:
        for s in _sig_strings(p.get("signals")) + _sig_strings(p.get("x")):
            if _flips(s, res.flipped):
                res.notes.append(f"plot `{p.get('id')}` shows {s}, which changes sign")
    for c in (data.get("dashboard") or {}).get("cards", []):
        for s in _sig_strings(c.get("signals")) + _sig_strings(c.get("x")):
            if _flips(s, res.flipped):
                res.notes.append(f"dashboard card `{c.get('id')}` shows {s}, which changes sign")


def update_expected(exp: JsonDoc, model_key: str, res: Result, apply: bool,
                    flipped_by_model: dict[str, set[str]]) -> None:
    models = exp.data.get("models", {})
    if model_key in models:
        entry = models[model_key]
        base = ("models", model_key) + (("checks",) if isinstance(entry, dict) else ())
        checks = entry["checks"] if isinstance(entry, dict) else entry
        for k, c in enumerate(checks):
            _update_check(exp, base + (k,), c, res.flipped, res, apply)
    comps = exp.data.get("compare")
    if comps is None:
        return
    lst = comps if isinstance(comps, list) else [comps]
    for c in lst:
        if model_key not in (c.get("a"), c.get("b")):
            continue
        fa = _flips(c.get("signal_a", ""), flipped_by_model.get(c.get("a"), set()))
        fb = _flips(c.get("signal_b", ""), flipped_by_model.get(c.get("b"), set()))
        if fa != fb:
            res.changes.append(Change("review", f"expected.json compare {c.get('a')}:{c.get('signal_a')} "
                                                f"vs {c.get('b')}:{c.get('signal_b')}: one side changes sign"))


def _update_check(exp: JsonDoc, path: tuple, c: dict, flipped: set[str], res: Result, apply: bool) -> None:
    kind = c.get("kind")
    keys = [k for k, v in c.items() if k.startswith("signal") and isinstance(v, str)]
    hit = [k for k in keys if _flips(c[k], flipped)]
    if not hit:
        return
    where = f"expected.json {path[1]} check #{path[-1]} ({kind} {c[hit[0]]})"
    if kind in _SIGN_FREE:
        return
    if kind in ("final_value", "cursor_value") and "value" in c:
        new = -c["value"]
        res.changes.append(Change("neutral", f"{where}: value {c['value']} -> {new}"))
        if apply:
            exp.replace(path + ("value",), new)
        return
    if kind == "zero_crossing":
        level = -float(c.get("level", 0.0))
        direction = {"down": "up", "up": "down"}[c.get("direction", "down")]
        res.changes.append(Change("neutral", f"{where}: level -> {level:g}, direction -> {direction}"))
        if apply:
            if "level" in c:
                exp.replace(path + ("level",), level)
            exp.set_key(path, "direction", direction)
        return
    if kind == "ratio" and len(keys) == 2:
        if len(hit) == 2:
            return
        new = -c["value"]
        res.changes.append(Change("neutral", f"{where}: value {c['value']} -> {new}"))
        if apply:
            exp.replace(path + ("value",), new)
        return
    if kind in ("compare_signals", "rms_difference") and len(hit) == len(keys):
        return
    res.changes.append(Change("review", f"{where}: the signal changes sign and the check cannot be "
                                        "negated: left unchanged"))


# ---------------------------------------------------------------------------------------------
# Driver
# ---------------------------------------------------------------------------------------------


def apply_plan(doc: JsonDoc, plan: dict) -> None:
    for b in plan["reverse"]:
        doc.swap(b.conn_path + ("from",), b.conn_path + ("to",))
        conn = doc.get(b.conn_path)
        if conn.get("route"):
            doc.replace(b.conn_path + ("route",), list(reversed(conn["route"])))
    for inst, pname, new in plan["params"]:
        if "params" not in inst.node:
            raise RuntimeError(f"{inst.path} has no params object")
        doc.set_key(inst.node_path + ("params",), pname, new)
    for inst, var, new in plan["starts"]:
        doc.replace(inst.node_path + ("starts", var), new)
    seen: set[tuple] = set()
    for inst in plan["markers"]:
        if inst.node_path in seen:
            continue
        seen.add(inst.node_path)
        marker = MARKER.format(decision=LAW_CHANGES[inst.ref])
        old = inst.node.get("$comment")
        doc.set_key(inst.node_path, "$comment", marker if not old else f"{old} [{marker}]")


def project_of(model: Path) -> Path | None:
    if model.parent.name == "models" and (model.parent.parent / "bgsim.project.json").exists():
        return model.parent.parent
    return None


def model_key(model: Path) -> str:
    name = model.name
    for suffix in (".bgmodel.json", ".json"):
        if name.endswith(suffix):
            return name[: -len(suffix)]
    return name


def collect(paths: list[str]) -> list[Path]:
    out = []
    for p in map(Path, paths):
        if p.is_dir():
            out.extend(sorted((p / "models").glob("*.bgmodel.json")) if (p / "models").is_dir()
                       else sorted(p.glob("*.bgmodel.json")))
        else:
            out.append(p)
    return out


def run(paths: list[str], *, check: bool, catalog: dict[str, BlockInfo] | None = None,
        project: Path | None = None, law_changes: bool = True, out=sys.stdout) -> int:
    models = collect(paths)
    status = 0
    # group by project, so one expected.json is edited once
    groups: dict = defaultdict(list)
    for mp in models:
        groups[project or project_of(mp)].append(mp)
    catalogs = {} if catalog is not None else catalogs_from_julia(list(groups))
    for proj, mps in groups.items():
        cat = catalog if catalog is not None else catalogs[proj]
        exp_path = proj / "expected.json" if proj is not None else None
        exp = JsonDoc(exp_path) if exp_path is not None and exp_path.exists() else None
        results = []
        for mp in mps:
            doc = JsonDoc(mp)
            if doc.data.get("format") != "bgsim.model":
                continue
            m = Model(doc)
            res, plan = analyse(m, cat, str(mp), law_changes)
            update_model_refs(doc, res, apply=not check)
            if not check:
                apply_plan(doc, plan)
                doc.save()
            results.append((mp, res))
        flipped_by_model = {model_key(mp): r.flipped for mp, r in results}
        for mp, res in results:
            if exp is not None:
                update_expected(exp, model_key(mp), res, not check, flipped_by_model)
            _report(res, out)
            edits = [c for c in res.changes]
            if res.review:
                status = 2
            elif check and edits and status == 0:
                status = 1
        if exp is not None and not check:
            exp.save()
    return status


def _report(res: Result, out) -> None:
    if not res.changes and not res.notes:
        print(f"{res.label}: nothing to do", file=out)
        return
    counts = {k: sum(1 for c in res.changes if c.cls == k) for k in ("neutral", "source", "review")}
    print(f"{res.label}: neutral {counts['neutral']}, source {counts['source']}, review {counts['review']}",
          file=out)
    for c in res.changes:
        print(f"  [{c.cls}] {c.text}", file=out)
    for n in res.notes:
        print(f"  [note] {n}", file=out)
    if res.flipped:
        print(f"  signals that change sign: {', '.join(sorted(res.flipped))}", file=out)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("paths", nargs="+")
    ap.add_argument("--check", action="store_true", help="report only; write nothing")
    ap.add_argument("--catalog", type=Path, help="a catalog JSON instead of the Julia library")
    ap.add_argument("--project", type=Path, help="the project directory of every model given")
    ap.add_argument("--no-law-changes", action="store_true",
                    help="do not compensate the law changes of LAW_CHANGES")
    a = ap.parse_args(argv)
    cat = catalog_from_json(json.loads(a.catalog.read_text(encoding="utf-8"))) if a.catalog else None
    return run(a.paths, check=a.check, catalog=cat, project=a.project, law_changes=not a.no_law_changes)


if __name__ == "__main__":
    sys.exit(main())
