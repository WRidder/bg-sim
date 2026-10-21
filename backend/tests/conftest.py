"""Shared fixtures for the backend tests (M0.4).

The tests import `bgsim_server` from `backend/src` (the M0.2 contract tests do the
same), so they behave identically whether or not the package is installed in the
virtual environment.
"""

from __future__ import annotations

import asyncio
import json
import sys
from collections.abc import Callable
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator
from referencing import Registry, Resource

TESTS_DIR = Path(__file__).resolve().parent
REPO = TESTS_DIR.parents[1]
SRC = TESTS_DIR.parent / "src"
SCHEMA_DIR = REPO / "contracts" / "schemas"
FIXTURE_DIR = REPO / "contracts" / "fixtures"

if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from bgsim_server.config import Settings, default_julia


def _load_schemas() -> dict[str, dict]:
    return {
        path.name[: -len(".schema.json")]: json.loads(path.read_text(encoding="utf-8"))
        for path in sorted(SCHEMA_DIR.glob("*.schema.json"))
    }


@pytest.fixture(scope="session")
def schema_validate() -> Callable[[str, object], None]:
    """Validate a document against one of the `contracts/schemas` documents."""
    schemas = _load_schemas()
    registry = Registry().with_resources(
        [(doc["$id"], Resource.from_contents(doc)) for doc in schemas.values()]
    )

    def validate(schema_name: str, document: object) -> None:
        validator = Draft202012Validator(schemas[schema_name], registry=registry)
        errors = sorted(validator.iter_errors(document), key=lambda e: list(e.path))
        assert not errors, "\n".join(f"{list(e.path)}: {e.message}" for e in errors)

    return validate


@pytest.fixture
def wait_until() -> Callable[..., object]:
    """Poll a sync predicate from an async test until it is true."""

    async def wait(predicate: Callable[[], bool], timeout: float = 5.0, interval: float = 0.02):
        loop = asyncio.get_running_loop()
        deadline = loop.time() + timeout
        while loop.time() < deadline:
            if predicate():
                return
            await asyncio.sleep(interval)
        raise AssertionError(f"condition not reached within {timeout:g} s")

    return wait


@pytest.fixture
def fake_settings(tmp_path: Path) -> Settings:
    """Isolated settings for a fake-worker run (nothing shared between tests)."""
    return Settings(
        repo_root=REPO,
        projects_root=tmp_path / "projects",
        julia=default_julia(),
        fake_worker=True,
        worker_log=tmp_path / "logs" / "worker.log",
        web_dist=tmp_path / "web-dist",
    )


@pytest.fixture
def real_settings(tmp_path: Path) -> Settings:
    """Settings for the real Julia worker (only used by the julia-marked tests)."""
    return Settings(
        repo_root=REPO,
        projects_root=tmp_path / "projects",
        julia=default_julia(),
        fake_worker=False,
        worker_log=tmp_path / "logs" / "worker.log",
        web_dist=tmp_path / "web-dist",
    )
