"""Block links of the docs lint ``tools/example_docs/docs_lint.py`` (X5.10).

The lint is a plain script next to ``build.py``, so the tests load it by path (like
``test_energy_balance.py`` does for its tool).  The cases cover ``block:`` paths through a drawn
subsystem and through instances of library subsystems (``library/<Name>.bgsub.json``), which the
compiler puts in place of the instance: a path inside the definition is a node of the model, a
wrong one is still reported.
"""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
LINT = REPO / "tools" / "example_docs" / "docs_lint.py"
FIXTURE = REPO / "contracts" / "fixtures" / "model" / "valid" / "model.linked-subsystem.json"


@pytest.fixture(scope="module")
def lint():
    spec = importlib.util.spec_from_file_location("bgsim_docs_lint", LINT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules["bgsim_docs_lint"] = module
    spec.loader.exec_module(module)
    return module


def _node(name: str, block: dict) -> dict:
    return {"id": name.lower(), "name": name, "block": block, "position": {"x": 0, "y": 0}}


def _definition(name: str, nodes: list[dict]) -> dict:
    return {"format": "bgsim.subsystem", "name": name, "ports": [],
            "diagram": {"nodes": nodes, "connections": []}}


LINK = _definition("Link", [
    _node("J", {"ref": "stdlib:spatial/Revolute3D"}),
    _node("B", {"ref": "stdlib:spatial/RigidBody3D"}),
    _node("Drive", {"ref": "project:Actuator"}),
])
ACTUATOR = _definition("Actuator", [_node("rotor", {"ref": "stdlib:bondgraph/I"})])
MODEL = {"diagram": {"nodes": [
    _node("L1", {"ref": "project:Link"}),
    _node("L2", {"ref": "project:Link"}),
    _node("Ctrl", {"ref": "project:ArmCtrl"}),
    _node("Sub", {"subsystem": {"ports": [], "diagram": {"nodes": [
        _node("Inner", {"ref": "stdlib:bondgraph/R"}),
        _node("L", {"ref": "project:Link"}),
    ], "connections": []}}}),
], "connections": []}}
DEFINITIONS = {"Link": LINK, "Actuator": ACTUATOR}


def test_find_block_follows_instances_of_library_subsystems(lint):
    for reference in ("L1", "L1/J", "L2/B", "L1/Drive", "L1/Drive/rotor", "Sub/Inner", "Sub/L/J",
                      "Sub/L/Drive/rotor"):
        assert lint.find_block(MODEL, reference, DEFINITIONS), reference
    for reference in ("L1/Ghost", "L1/J/x", "L1/rotor", "Link/J", "J", "Ctrl/x", "Sub/J",
                      "L1/Drive/ghost", "L3/J", ""):
        assert not lint.find_block(MODEL, reference, DEFINITIONS), reference
    # Without the definitions an instance is a plain block: nothing inside it can be named.
    assert lint.find_block(MODEL, "L1")
    assert not lint.find_block(MODEL, "L1/J")
    # The definitions a document carries take precedence over the library files.
    carried = {**MODEL, "definitions": {"Link": _definition("Link", [_node("Other", {"junction": "1"})])}}
    assert lint.find_block(carried, "L1/Other", DEFINITIONS)
    assert not lint.find_block(carried, "L1/J", DEFINITIONS)


def test_find_block_on_the_contract_fixture(lint):
    document = json.loads(FIXTURE.read_text(encoding="utf-8"))
    assert lint.find_block(document, "A/R1") and lint.find_block(document, "B/C1")
    assert not lint.find_block(document, "A/Ghost")


def _project(root: Path, page: str) -> Path:
    (root / "library").mkdir(parents=True)
    for name, definition in DEFINITIONS.items():
        (root / "library" / f"{name}.bgsub.json").write_text(json.dumps(definition), encoding="utf-8")
    # Not definitions: a file that does not parse, and a name that is also a code block.
    (root / "library" / "Broken.bgsub.json").write_text("{", encoding="utf-8")
    (root / "library" / "ArmCtrl.bgsub.json").write_text(json.dumps(ACTUATOR), encoding="utf-8")
    (root / "library" / "ArmCtrl.jl").write_text("# a code block\n", encoding="utf-8")
    docs = root / "models" / "arm.docs"
    (docs / "pages").mkdir(parents=True)
    (root / "models" / "arm.bgmodel.json").write_text(json.dumps(MODEL), encoding="utf-8")
    (docs / "docs.json").write_text(json.dumps({
        "format": "bgsim.docs", "version": 1,
        "pages": [{"id": "overview", "title": "Overview", "file": "pages/overview.md", "children": []}],
    }), encoding="utf-8")
    (docs / "pages" / "overview.md").write_text(page, encoding="utf-8")
    return docs


def test_lint_reads_the_library_of_the_example(lint, tmp_path):
    assert set(lint.library_definitions(_project(tmp_path / "a", "x").parent.parent)) == {"Actuator", "Link"}
    good = _project(
        tmp_path / "good",
        "The joint [J](block:L1/J) of [L1](block:L1), its rotor [r](block:L2/Drive/rotor) "
        "and [Inner](block:Sub/Inner), [J](block:Sub/L/J).\n",
    )
    assert lint.lint_model_docs(good, MODEL, None) == []
    bad = _project(
        tmp_path / "bad",
        "[ok](block:L1/B)\n[ghost](block:L1/Ghost)\n[deep](block:L1/Drive/ghost)\n[code](block:Ctrl/rotor)\n",
    )
    problems = lint.lint_model_docs(bad, MODEL, None)
    assert [problem.split(": ", 1)[0].rsplit(":", 1)[1] for problem in problems] == ["2", "3", "4"]
    assert all("names no node of the model" in problem for problem in problems)
    assert "block:L1/Ghost" in problems[0] and "library subsystem" in problems[0]
    # Explicit definitions replace the library lookup.
    assert len(lint.lint_model_docs(good, MODEL, None, definitions={})) == 3
