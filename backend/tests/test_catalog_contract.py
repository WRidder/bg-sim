"""The catalog the Julia library emits against `catalog.schema.json` (C-MB2).

Marked `julia` (deselected by default; run with `uv run pytest -m julia backend/tests/test_catalog_contract.py`).
One Julia process serialises `Library.catalog()` -- the exact value the worker returns for
`catalog.get` -- to JSON; the tests then validate it against the schema and check the
multibond shape rules the schema cannot express across documents: every `Planar`/`Spatial`
port has the domain's size and a domain entry with per-component units, and every block that
has such a port carries the matching `dimension`.
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest

from bgsim_server.config import default_julia

pytestmark = pytest.mark.julia

REPO = Path(__file__).resolve().parents[2]
DUMP = (
    "using BGSim, JSON3; "
    "open(ARGS[1], \"w\") do io; JSON3.write(io, BGSim.Library.catalog()); end"
)
NEW_GROUPS = {"Spatial mechanics", "Drives", "Contact"}
DOMAIN_SIZE = {"Planar": 3, "Spatial": 6}
DOMAIN_DIM = {"Planar": 2, "Spatial": 3}


@pytest.fixture(scope="module")
def catalog(tmp_path_factory: pytest.TempPathFactory) -> dict:
    out = tmp_path_factory.mktemp("catalog") / "catalog.json"
    proc = subprocess.run(
        [str(default_julia()), "--project=julia/BGSim", "-e", DUMP, str(out)],
        cwd=str(REPO),
        capture_output=True,
        text=True,
        check=False,
        timeout=900,
    )
    assert proc.returncode == 0, f"catalog dump failed:\n{proc.stdout}\n{proc.stderr}"
    return json.loads(out.read_text(encoding="utf-8"))


def test_stdlib_catalog_validates_against_the_schema(catalog, schema_validate) -> None:
    schema_validate("catalog", catalog)


def test_new_m3_groups_are_present(catalog) -> None:
    groups = {block["group"] for block in catalog["blocks"]}
    assert NEW_GROUPS <= groups, sorted(NEW_GROUPS - groups)


def test_multibond_domains_carry_components(catalog) -> None:
    domains = {d["name"]: d for d in catalog["domains"]}
    for name, size in DOMAIN_SIZE.items():
        domain = domains[name]
        assert domain["size"] == size
        assert len(domain["components"]["effort"]) == size, name
        assert len(domain["components"]["flow"]) == size, name
        assert all(unit for unit in domain["components"]["effort"] + domain["components"]["flow"])
    for name in set(domains) - set(DOMAIN_SIZE):
        assert domains[name]["size"] == 1
        assert "components" not in domains[name]


def test_every_multibond_port_has_units_and_dimension(catalog) -> None:
    domains = {d["name"]: d for d in catalog["domains"]}
    seen = {"Planar": 0, "Spatial": 0}
    for block in catalog["blocks"]:
        for port in block["ports"]:
            domain = port["domain"]
            if domain not in DOMAIN_SIZE:
                continue
            seen[domain] += 1
            where = f"{block['ref']}.{port['name']}"
            assert port["size"] in ([], [DOMAIN_SIZE[domain]]), where
            components = domains[domain]["components"]
            assert len(components["effort"]) == len(components["flow"]) == DOMAIN_SIZE[domain]
            assert block.get("dimension") == DOMAIN_DIM[domain], where
    assert seen["Planar"] > 0 and seen["Spatial"] > 0


def test_block_dimension_never_mixes_domains(catalog) -> None:
    for block in catalog["blocks"]:
        dims = {DOMAIN_DIM[p["domain"]] for p in block["ports"] if p["domain"] in DOMAIN_DIM}
        assert len(dims) <= 1, block["ref"]
