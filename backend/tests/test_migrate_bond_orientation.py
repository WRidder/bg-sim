"""The bond-orientation migration tool ``tools/migrate_bond_orientation.py`` (port orientation O9, O19).

``tools/migrate_bond_orientation.py`` is an inline ``uv`` script, so the tests load it by path (like
``test_energy_balance.py``). Every case is a small model document in a temporary project folder
with a hand-made catalog (the orientations of plan/PORT_ORIENTATION_PLAN.md: storage and
dissipation ``in``, sources ``out``, ``TF`` a ``through`` pair), so no Julia process runs. The
three classes of the plan are covered: **neutral** (a reversal that changes nothing, or an odd
element whose start value is negated), **source** (a source value negated, also for the ``Sf``
law change on a conforming bond) and **review** (left unchanged, exit status 2). The tool must be
idempotent and keep the file's formatting.
"""

from __future__ import annotations

import importlib.util
import io
import json
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
TOOL = REPO / "tools" / "migrate_bond_orientation.py"


def _load():
    spec = importlib.util.spec_from_file_location("bgsim_migrate_bond_orientation", TOOL)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def mig():
    return _load()


def _block(ref, ports, orientation=(), params=(), outputs=()):
    return {
        "ref": ref,
        "ports": [{"name": p, "domain": "Generic", "size": [], "frame": None} for p in ports],
        "orientation": [{"ports": list(ps), "kind": k} for ps, k in orientation],
        "parameters": [{"name": n, "default": d} for n, d in params],
        "outputs": [{"name": o} for o in outputs],
    }


CATALOG = {
    "blocks": [
        _block("stdlib:bondgraph/C", ["p"], [(("p",), "in")], [("c", "1.0")]),
        _block("stdlib:bondgraph/I", ["p"], [(("p",), "in")], [("i", "1.0")]),
        _block("stdlib:bondgraph/R", ["p"], [(("p",), "in")], [("r", "1.0")]),
        _block("stdlib:bondgraph/Df", ["p"], [(("p",), "in")], outputs=["y"]),
        _block("stdlib:bondgraph/Se", ["p"], [(("p",), "out")], [("e", "1.0")]),
        _block("stdlib:bondgraph/MSe", ["p"], [(("p",), "out")], [("gain", "1.0")]),
        _block("stdlib:bondgraph/Sf", ["p"], [(("p",), "out")], [("f", "1.0")]),
        _block("stdlib:bondgraph/TF", ["p1", "p2"], [(("p1", "p2"), "through")], [("n", "1.0")]),
        _block("stdlib:sources/Constant", [], outputs=["y"]),
        _block("stdlib:continuous/Gain", []),
        # a project one-port `in` whose law the tool does not know to be odd
        _block("project:Strut", ["j"], [(("j",), "in")]),
    ]
}


def _node(nid, name, block, params=None, starts=None):
    return {
        "id": nid,
        "name": name,
        "block": block,
        "position": {"x": 0, "y": 0},
        "rotation": 0,
        "flipX": False,
        "params": params or {},
        "constants": {},
        "starts": starts or {},
        "ui": {"showLabel": True, "color": None},
    }


def ref(r):
    return {"ref": r}


def junction(k):
    return {"junction": str(k)}


def bond(cid, a, b):
    def ep(x):
        return {"node": x[0], "port": x[1]} if isinstance(x, tuple) else {"node": x}

    return {"id": cid, "kind": "bond", "from": ep(a), "to": ep(b), "route": [], "label": None}


def signal(cid, a, b):
    return {"id": cid, "kind": "signal", "from": {"node": a[0], "port": a[1]},
            "to": {"node": b[0], "port": b[1]}, "route": [], "label": None}


def model(name, nodes, connections, plots=(), bindings=()):
    return {
        "format": "bgsim.model",
        "language": "0.1.0",
        "name": name,
        "diagram": {"nodes": nodes, "connections": connections, "subsystemPorts": [], "annotations": []},
        "settings": {"t_start": 0.0, "t_end": 1.0},
        "plots": list(plots),
        "scene": None,
        "bindings": list(bindings),
    }


def _project(tmp_path: Path, models: dict, expected: dict | None = None, indent=2) -> Path:
    proj = tmp_path / "proj"
    (proj / "models").mkdir(parents=True)
    (proj / "bgsim.project.json").write_text("{}\n", encoding="utf-8")
    for key, doc in models.items():
        (proj / "models" / f"{key}.bgmodel.json").write_text(json.dumps(doc, indent=indent) + "\n",
                                                             encoding="utf-8")
    if expected is not None:
        (proj / "expected.json").write_text(json.dumps(expected, indent=2) + "\n", encoding="utf-8")
    return proj


def _run(mig, proj, check=False, law_changes=True):
    out = io.StringIO()
    cat = mig.catalog_from_json(CATALOG)
    status = mig.run([str(proj)], check=check, catalog=cat, law_changes=law_changes, out=out)
    return status, out.getvalue()


def _read(proj, key):
    return json.loads((proj / "models" / f"{key}.bgmodel.json").read_text(encoding="utf-8"))


def _conn(doc, cid):
    return next(c for c in doc["diagram"]["connections"] if c["id"] == cid)


# ---------------------------------------------------------------------------------------------


def test_negate_expr(mig):
    n = mig._negate_expr
    assert n("2943.0") == "-2943.0"
    assert n("-1.0") == "1.0"
    assert n("c_rr*m_veh*g_n") == "-c_rr*m_veh*g_n"
    assert n("-m_b*g0") == "m_b*g0"
    assert n("-v_b") == "v_b"
    assert n("a + b") == "-(a + b)"
    assert n("-(a + b)") == "a + b"
    assert n("-a + b") == "-(-a + b)"
    assert n("1e-3*x") == "-1e-3*x"


def test_neutral_reversals(mig, tmp_path):
    """A C at the tail of a 0-junction and an R at the tail of a 1-junction: both bonds are
    reversed. On the 0-junction nothing else changes; on the 1-junction the R's port flips (an odd
    element: neutral, its port signals change sign), and the sources and storage of that junction
    are untouched because the tool keeps the junction's own sign."""
    doc = model("m", [
        _node("n1", "Src", ref("stdlib:bondgraph/Se"), {"e": "2.0"}),
        _node("n2", "J1", junction(1)),
        _node("n3", "Mass", ref("stdlib:bondgraph/I"), {"i": "1.0"}, {"P": "0.5"}),
        _node("n4", "Drag", ref("stdlib:bondgraph/R"), {"r": "3.0"}),
        _node("n5", "J0", junction(0)),
        _node("n6", "Spring", ref("stdlib:bondgraph/C"), {"c": "0.1"}, {"q": "0.2"}),
    ], [
        bond("b1", ("n1", "p"), "n2"),
        bond("b2", "n2", ("n3", "p")),
        bond("b3", ("n4", "p"), "n2"),       # R at the tail: violates `in`
        bond("b4", "n2", "n5"),
        bond("b5", ("n6", "p"), "n5"),       # C at the tail of a 0-junction: violates, neutral
    ], plots=[{"id": "p1", "title": "drag", "signals": ["Drag/p.e"]}])
    proj = _project(tmp_path, {"m": doc})
    before = (proj / "models" / "m.bgmodel.json").read_text(encoding="utf-8")

    status, report = _run(mig, proj, check=True)
    assert status == 1
    assert "[neutral] reverse bond `b3`" in report and "[neutral] reverse bond `b5`" in report
    assert "source" not in report.split("\n", 1)[1] and "[review]" not in report
    assert "plot `p1` shows Drag/p.e" in report
    assert (proj / "models" / "m.bgmodel.json").read_text(encoding="utf-8") == before   # --check

    status, report = _run(mig, proj)
    assert status == 0
    after = _read(proj, "m")
    assert _conn(after, "b3")["from"] == {"node": "n2"} and _conn(after, "b3")["to"] == {"node": "n4", "port": "p"}
    assert _conn(after, "b5")["from"] == {"node": "n5"}
    assert after["diagram"]["nodes"][0]["params"] == {"e": "2.0"}
    assert after["diagram"]["nodes"][2]["starts"] == {"P": "0.5"}
    assert after["diagram"]["nodes"][5]["starts"] == {"q": "0.2"}

    # idempotent
    status, report = _run(mig, proj)
    assert status == 0 and "nothing to do" in report


def test_neutral_start_value_negated(mig, tmp_path):
    """A C whose bond is reversed on a 1-junction and whose other bonds are its only neighbours
    (the junction carries a source that is cheaper to keep): the C's start value is negated and its
    displacement signal changes sign; an expected.json final value of it is negated."""
    doc = model("m", [
        _node("n1", "Src", ref("stdlib:bondgraph/Se"), {"e": "2.0"}),
        _node("n2", "J1", junction(1)),
        _node("n3", "Spring", ref("stdlib:bondgraph/C"), {"c": "0.1"}, {"q": "0.25"}),
        _node("n4", "Mass", ref("stdlib:bondgraph/I"), {"i": "1.0"}),
    ], [
        bond("b1", ("n1", "p"), "n2"),
        bond("b2", ("n3", "p"), "n2"),
        bond("b3", "n2", ("n4", "p")),
    ])
    expected = {"project": "proj", "models": {"m": {"checks": [
        {"kind": "final_value", "signal": "Spring/q", "t": 1.0, "value": 0.125, "rtol": 1e-3},
        {"kind": "max_abs", "signal": "Spring/q", "value": 0.3, "rtol": 1e-3},
        {"kind": "final_value", "signal": "Mass/p.f", "t": 1.0, "value": 2.0, "rtol": 1e-3},
    ]}}}
    proj = _project(tmp_path, {"m": doc}, expected)
    status, report = _run(mig, proj)
    assert status == 0, report
    assert "negate start `Spring/q`: 0.25 -> -0.25" in report
    after = _read(proj, "m")
    assert after["diagram"]["nodes"][2]["starts"] == {"q": "-0.25"}
    checks = json.loads((proj / "expected.json").read_text(encoding="utf-8"))["models"]["m"]["checks"]
    assert checks[0]["value"] == -0.125          # Spring/q flips
    assert checks[1]["value"] == 0.3             # sign-free
    assert checks[2]["value"] == 2.0             # Mass is untouched


def test_source_negated(mig, tmp_path):
    """Effort sources drawn at the head of their junction (the old load convention) are reversed
    and their value negated, a numeric value and an expression alike; a binding of the source's
    port variable gets its gain negated."""
    doc = model("m", [
        _node("n1", "Weight", ref("stdlib:bondgraph/Se"), {"e": "m*g"}),
        _node("n2", "J1", junction(1)),
        _node("n3", "Mass", ref("stdlib:bondgraph/I"), {"i": "1.0"}),
        _node("n4", "Load", ref("stdlib:bondgraph/MSe"), {"gain": "2.5"}),
        _node("n5", "One", ref("stdlib:sources/Constant")),
    ], [
        bond("b1", "n2", ("n1", "p")),
        bond("b2", "n2", ("n3", "p")),
        bond("b3", "n2", ("n4", "p")),
        signal("s1", ("n5", "y"), ("n4", "u")),
    ], bindings=[{"target": "visual:arrow", "property": "scale", "signal": "Weight/p.e"}])
    proj = _project(tmp_path, {"m": doc})
    status, report = _run(mig, proj)
    assert status == 0, report
    assert "[source] negate `Weight`.e: m*g -> -m*g" in report
    assert "[source] negate `Load`.gain: 2.5 -> -2.5" in report
    after = _read(proj, "m")
    assert _conn(after, "b1")["from"] == {"node": "n1", "port": "p"}
    assert after["diagram"]["nodes"][0]["params"] == {"e": "-m*g"}
    assert after["diagram"]["nodes"][3]["params"] == {"gain": "-2.5"}
    assert after["bindings"][0]["gain"] == -1.0
    status, report = _run(mig, proj)
    assert status == 0 and "nothing to do" in report


def test_flow_source_law_change(mig, tmp_path):
    """O15: `Sf` imposes +f at its tail now. A conforming Sf (the silent chain) gets its value
    negated and a marker; at the head of a 1-junction the reversal and the law change cancel,
    so only the marker is written. A second run changes nothing; without the law step the
    conforming Sf is left alone."""
    doc = model("m", [
        _node("n1", "Belt", ref("stdlib:bondgraph/Sf"), {"f": "-v_b"}),
        _node("n2", "J0", junction(0)),
        _node("n3", "Spring", ref("stdlib:bondgraph/C")),
        _node("n4", "Drive", ref("stdlib:bondgraph/Sf")),
        _node("n5", "J1", junction(1)),
        _node("n6", "Damper", ref("stdlib:bondgraph/R")),
    ], [
        bond("b1", ("n1", "p"), "n2"),
        bond("b2", "n2", ("n3", "p")),
        bond("b3", "n5", ("n4", "p")),      # Sf at the head of a 1-junction
        bond("b4", "n5", ("n6", "p")),
    ])
    proj = _project(tmp_path, {"m": doc})
    status, report = _run(mig, proj, law_changes=False)
    assert "Belt" not in report and "reverse bond `b3`" in report

    proj2 = _project(tmp_path / "second", {"m": doc})
    status, report = _run(mig, proj2)
    assert status == 0, report
    assert "[source] negate `Belt`.f: -v_b -> v_b (law changed (O15))" in report
    assert "`Drive` (stdlib:bondgraph/Sf): law change O15 cancelled by the reversal" in report
    after = _read(proj2, "m")
    belt, drive = after["diagram"]["nodes"][0], after["diagram"]["nodes"][3]
    assert belt["params"] == {"f": "v_b"}
    assert "migrate_bond_orientation: O15" in belt["$comment"]
    assert drive["params"] == {} and "migrate_bond_orientation: O15" in drive["$comment"]
    assert _conn(after, "b3")["from"] == {"node": "n4", "port": "p"}
    status, report = _run(mig, proj2)
    assert status == 0 and "nothing to do" in report


def test_through_pair(mig, tmp_path):
    """Both bonds of a TF arrive at it: the one whose other end is free (a 0-junction) is
    reversed, which is notation only."""
    doc = model("m", [
        _node("n1", "Src", ref("stdlib:bondgraph/Se")),
        _node("n2", "J1", junction(1)),
        _node("n3", "Gear", ref("stdlib:bondgraph/TF"), {"n": "2.0"}),
        _node("n4", "J0", junction(0)),
        _node("n5", "Spring", ref("stdlib:bondgraph/C")),
    ], [
        bond("b1", ("n1", "p"), "n2"),
        bond("b2", "n2", ("n3", "p1")),
        bond("b3", "n4", ("n3", "p2")),
        bond("b4", "n4", ("n5", "p")),
    ])
    proj = _project(tmp_path, {"m": doc})
    status, report = _run(mig, proj)
    assert status == 0, report
    assert "[neutral] reverse bond `b3`" in report
    after = _read(proj, "m")
    assert _conn(after, "b3")["from"] == {"node": "n3", "port": "p2"}
    assert _conn(after, "b2")["from"] == {"node": "n2"}


def test_review_is_left_unchanged(mig, tmp_path):
    """An `in` project block of unknown law at the tail of a 1-junction, a detector whose output
    drives a block, and two `in` ports bonded to each other: all three are reported as review and
    nothing in their sign groups is written; the exit status is 2. Each junction's other element
    is of the same kind, so renaming the junction's sign cannot avoid the flip either."""
    doc = model("m", [
        _node("n1", "Strut2", ref("project:Strut")),
        _node("n2", "J1", junction(1)),
        _node("n3", "Strut", ref("project:Strut")),
        _node("n4", "Speed", ref("stdlib:bondgraph/Df")),
        _node("n5", "K", ref("stdlib:continuous/Gain")),
        _node("n6", "R1", ref("stdlib:bondgraph/R")),
        _node("n7", "R2", ref("stdlib:bondgraph/R")),
        _node("n8", "J1b", junction(1)),
        _node("n9", "Speed2", ref("stdlib:bondgraph/Df")),
    ], [
        bond("b1", "n2", ("n1", "j")),
        bond("b2", ("n3", "j"), "n2"),        # unknown law: review
        bond("b3", ("n6", "p"), ("n7", "p")),  # in-in: review
        bond("b4", "n8", ("n9", "p")),
        bond("b5", ("n4", "p"), "n8"),        # detector at the tail, its output is used: review
        signal("s1", ("n4", "y"), ("n5", "u")),
        signal("s2", ("n9", "y"), ("n5", "u")),
    ])
    proj = _project(tmp_path, {"m": doc}, indent=1)
    before = (proj / "models" / "m.bgmodel.json").read_text(encoding="utf-8")
    status, report = _run(mig, proj)
    assert status == 2
    assert "`Strut` (project:Strut) flips sign and its law is not known to be odd" in report
    assert "joins two `in` ports" in report
    assert "output `y` drives other blocks" in report
    assert (proj / "models" / "m.bgmodel.json").read_text(encoding="utf-8") == before


def test_formatting_is_kept(mig, tmp_path):
    """Only the changed values are rewritten: a hand-formatted document keeps its layout."""
    text = (
        '{\n  "format": "bgsim.model",\n  "language": "0.1.0",\n  "name": "m",\n  "diagram": {\n'
        '    "nodes": [\n'
        '      { "id": "n1", "name": "Weight", "block": { "ref": "stdlib:bondgraph/Se" }, '
        '"position": { "x": 0, "y": 0 }, "params": { "e": "9.81" } },\n'
        '      { "id": "n2", "name": "J", "block": { "junction": "1" }, "position": { "x": 0, "y": 0 } },\n'
        '      { "id": "n3", "name": "M", "block": { "ref": "stdlib:bondgraph/I" }, '
        '"position": { "x": 0, "y": 0 }, "params": {} }\n'
        '    ],\n'
        '    "connections": [\n'
        '      { "id": "b1", "kind": "bond", "from": { "node": "n2" }, "to": { "node": "n1", "port": "p" } },\n'
        '      { "id": "b2", "kind": "bond", "from": { "node": "n2" }, "to": { "node": "n3", "port": "p" } }\n'
        '    ]\n  }\n}\n'
    )
    proj = tmp_path / "proj"
    (proj / "models").mkdir(parents=True)
    (proj / "bgsim.project.json").write_text("{}\n", encoding="utf-8")
    path = proj / "models" / "m.bgmodel.json"
    path.write_text(text, encoding="utf-8")
    status, report = _run(mig, proj)
    assert status == 0, report
    new = path.read_text(encoding="utf-8")
    assert new == text.replace('"9.81"', '"-9.81"').replace(
        '"from": { "node": "n2" }, "to": { "node": "n1", "port": "p" }',
        '"from": { "node": "n1", "port": "p" }, "to": { "node": "n2" }')


# ---------------------------------------------------------------------------------------------
# WP-O3a: multibond mechanics (O7 law changes, body composite faces)
# ---------------------------------------------------------------------------------------------

MECH_CATALOG = {
    "blocks": CATALOG["blocks"] + [
        _block("stdlib:multibond/GroundSpatial", ["p"], [(("p",), "out")]),
        _block("stdlib:spatial/Revolute3D", ["parent", "child", "drive"],
               [(("parent",), "in"), (("child",), "out"), (("drive",), "in")]),
        _block("stdlib:spatial/Free3D", ["parent", "child"], [(("parent",), "in"), (("child",), "out")]),
        _block("stdlib:spatial/RigidBody3D", ["p"], outputs=["V", "P"]),
        _block("stdlib:multibond/ISpatial", ["p"], [(("p",), "in")], [("m", "1.0")], ["Pm", "twout"]),
        _block("stdlib:multibond/CoriolisSpatial", ["p"], [(("p",), "in")]),
        _block("stdlib:multibond/DfSpatial", ["p"], [(("p",), "in")], outputs=["y"]),
        _block("stdlib:multibond/GravitySpatial", ["p"], [(("p",), "out")], [("m", "1.0")]),
        _block("stdlib:multibond/ExternalWrenchSpatial", ["p"], [(("p",), "out")]),
        _block("stdlib:multibond/SeSpatial", ["p"], [(("p",), "out")]),
        _block("stdlib:multibond/FixedTransform3DNeutral", ["a", "b"], [(("a", "b"), "through")]),
        _block("stdlib:contact/ContactPoint", ["p"], [(("p",), "in")]),
        _block("stdlib:planar/Revolute2DRigid", ["parent", "child", "drive"], [(("child",), "out")]),
        _block("stdlib:multibond/GroundPlanar", ["p"], [(("p",), "out")]),
        _block("stdlib:planar/RigidBody2D", ["p"], outputs=["V", "P"]),
    ]
}


def _run_mech(mig, proj, check=False):
    out = io.StringIO()
    cat = mig.catalog_from_json(MECH_CATALOG)
    status = mig.run([str(proj)], check=check, catalog=cat, out=out)
    return status, out.getvalue()


def _comment(doc, nid):
    return next(n for n in doc["diagram"]["nodes"] if n["id"] == nid).get("$comment", "")


def test_mech_library_body_needs_no_reversal(mig, tmp_path):
    """The documented `RigidBody3D` rig (joint child into the body, the body into a contact mount,
    a wrench into the body) already conforms. The body face is a junction whose contents changed
    sign (O7); the joint child, the contact and the wrench changed theirs too, so every change
    cancels: no reversal, no value edit, a marker on each block, and the port variables of the
    attachments (and the body's internal gravity port) change sign in recorded results."""
    doc = model("m", [
        _node("n1", "World", ref("stdlib:multibond/GroundSpatial")),
        _node("n2", "Joint", ref("stdlib:spatial/Revolute3D")),
        _node("n3", "Body", ref("stdlib:spatial/RigidBody3D")),
        _node("n4", "Mount", ref("stdlib:multibond/FixedTransform3DNeutral")),
        _node("n5", "Pad", ref("stdlib:contact/ContactPoint")),
        _node("n6", "Thrust", ref("stdlib:multibond/ExternalWrenchSpatial")),
    ], [
        bond("b1", ("n1", "p"), ("n2", "parent")),
        bond("b2", ("n2", "child"), ("n3", "p")),
        bond("b3", ("n3", "p"), ("n4", "b")),
        bond("b4", ("n4", "a"), ("n5", "p")),
        bond("b5", ("n6", "p"), ("n3", "p")),
    ], plots=[{"id": "p1", "title": "contact", "signals": ["Pad/p.e[6]"]}])
    proj = _project(tmp_path, {"m": doc})
    status, report = _run_mech(mig, proj)
    assert status == 0, report
    assert "reverse bond" not in report and "[review]" not in report and "[source]" not in report
    assert "plot `p1` shows Pad/p.e[6]" in report
    for sig in ("Joint/child.e", "Pad/p.f", "Thrust/p.e", "Body/gravity/p.e", "Mount/a.f"):
        assert sig in report
    assert "Joint/parent.e" not in report
    after = _read(proj, "m")
    assert after["diagram"]["connections"] == doc["diagram"]["connections"]
    for nid in ("n2", "n3", "n5", "n6"):
        assert "migrate_bond_orientation: O7" in _comment(after, nid)
    assert _comment(after, "n4") == "" and _comment(after, "n1") == ""
    # idempotent
    status, report = _run_mech(mig, proj)
    assert status == 0 and "nothing to do" in report


def _hand_body(inner_out: bool):
    """A hand-built body junction with inertia, Coriolis, twist sensor and gravity, on a `Free3D`,
    a contact through a mount and a wrench through a mount. `inner_out`: the lunar-module way
    (every element bonded from the junction, the contact mount into it and the thrust mount from
    it); else the `RigidBody3D` way (the other way round). These are the consistent pairs of the
    W218 check."""
    def att(cid, end):
        return bond(cid, "j", end) if inner_out else bond(cid, end, "j")

    def mnt(cid, end, into):
        return bond(cid, end, "j") if into else bond(cid, "j", end)

    return model("m", [
        _node("w", "World", ref("stdlib:multibond/GroundSpatial")),
        _node("f", "Free", ref("stdlib:spatial/Free3D")),
        _node("j", "Body", junction(1)),
        _node("i", "Inertia", ref("stdlib:multibond/ISpatial"), {"m": "2.0"}, {"P": "[0, 0, 0, 0, 0, 0]"}),
        _node("co", "Coriolis", ref("stdlib:multibond/CoriolisSpatial")),
        _node("tw", "Twist", ref("stdlib:multibond/DfSpatial")),
        _node("gr", "Gravity", ref("stdlib:multibond/GravitySpatial"), {"m": "2.0"}),
        _node("m", "Mount", ref("stdlib:multibond/FixedTransform3DNeutral")),
        _node("p", "Pad", ref("stdlib:contact/ContactPoint")),
        _node("tm", "ThrustMount", ref("stdlib:multibond/FixedTransform3DNeutral")),
        _node("t", "Thrust", ref("stdlib:multibond/ExternalWrenchSpatial")),
    ], [
        bond("cw", ("w", "p"), ("f", "parent")),
        att("ci", ("i", "p")),
        att("cco", ("co", "p")),
        att("ctw", ("tw", "p")),
        att("cgr", ("gr", "p")),
        att("cfree", ("f", "child")),
        mnt("cmount", ("m", "b"), inner_out),
        bond("cpad", ("m", "a"), ("p", "p")),
        mnt("cthrust", ("tm", "b"), not inner_out),
        bond("cthw", ("t", "p"), ("tm", "a")),
        signal("cP", ("i", "Pm"), ("co", "P")),
        signal("cv", ("tw", "y"), ("f", "tw")),
    ])


@pytest.mark.parametrize("inner_out", [True, False])
def test_mech_hand_built_body(mig, tmp_path, inner_out):
    """Both old hand-built conventions migrate without a value edit. The lunar-module way keeps
    the inertia, Coriolis and twist bonds and reverses gravity, the joint child and the two mount
    bonds; the `RigidBody3D` way reverses the inertia, Coriolis and twist bonds (the junction is
    renamed, so their port signals keep their sign) and keeps the rest."""
    proj = _project(tmp_path, {"m": _hand_body(inner_out)})
    status, report = _run_mech(mig, proj)
    assert status == 0, report
    assert "[review]" not in report and "[source]" not in report
    after = _read(proj, "m")
    flipped = {"cgr", "cfree", "cmount", "cthrust"} if inner_out else {"ci", "cco", "ctw"}
    before = _hand_body(inner_out)
    for c in before["diagram"]["connections"]:
        a = _conn(after, c["id"])
        if c["id"] in flipped:
            assert (a["from"], a["to"]) == (c["to"], c["from"]), c["id"]
        else:
            assert (a["from"], a["to"]) == (c["from"], c["to"]), c["id"]
    assert _comment(after, "i") == ""                     # the inertia keeps its law and sign
    assert after["diagram"]["nodes"][3]["starts"] == {"P": "[0, 0, 0, 0, 0, 0]"}
    assert "Inertia/p.f" not in report
    for nid in ("f", "gr", "p", "t"):
        assert "migrate_bond_orientation: O7" in _comment(after, nid)
    status, report = _run_mech(mig, proj)
    assert status == 0 and "nothing to do" in report


def test_mech_signal_source_on_body_is_review(mig, tmp_path):
    """A `SeSpatial` bonded into a `RigidBody3D`: the body face junction is renamed (its contents
    changed sign), so the source would have to push the other way. Its value is a signal input
    the tool cannot negate: review, nothing written."""
    doc = model("m", [
        _node("n1", "Push", ref("stdlib:multibond/SeSpatial")),
        _node("n2", "Body", ref("stdlib:spatial/RigidBody3D")),
        _node("n3", "Joint", ref("stdlib:spatial/Free3D")),
        _node("n4", "World", ref("stdlib:multibond/GroundSpatial")),
    ], [
        bond("b1", ("n1", "p"), ("n2", "p")),
        bond("b2", ("n3", "child"), ("n2", "p")),
        bond("b3", ("n4", "p"), ("n3", "parent")),
    ])
    proj = _project(tmp_path, {"m": doc})
    before = (proj / "models" / "m.bgmodel.json").read_text(encoding="utf-8")
    status, report = _run_mech(mig, proj)
    assert status == 2
    assert "`Push` (stdlib:multibond/SeSpatial) flips sign: negate its input `u` by hand" in report
    assert (proj / "models" / "m.bgmodel.json").read_text(encoding="utf-8") == before


def test_mech_revolute2drigid_is_review(mig, tmp_path):
    """`Revolute2DRigid` changed inside (its rate sensor): always review."""
    doc = model("m", [
        _node("n1", "World", ref("stdlib:multibond/GroundPlanar")),
        _node("n2", "Joint", ref("stdlib:planar/Revolute2DRigid")),
        _node("n3", "Body", ref("stdlib:planar/RigidBody2D")),
    ], [
        bond("b1", ("n1", "p"), ("n2", "parent")),
        bond("b2", ("n2", "child"), ("n3", "p")),
    ])
    proj = _project(tmp_path, {"m": doc})
    status, report = _run_mech(mig, proj)
    assert status == 2
    assert "`Joint` (stdlib:planar/Revolute2DRigid)" in report
