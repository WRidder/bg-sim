"""config.py tests: repository discovery and the environment variables of plan 6."""

from __future__ import annotations

from pathlib import Path

import pytest

from bgsim_server.config import Settings, find_repo_root

REPO = Path(__file__).resolve().parents[2]


def test_repo_root_is_discovered_from_the_source_tree() -> None:
    assert find_repo_root({}) == REPO
    assert (REPO / "julia" / "BGSim" / "Project.toml").is_file()


def test_repo_root_honours_the_env_override(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError):
        find_repo_root({"BGSIM_REPO": str(tmp_path)})
    assert find_repo_root({"BGSIM_REPO": str(REPO)}) == REPO


def test_from_env_reads_the_documented_variables(tmp_path: Path) -> None:
    env = {
        "BGSIM_PORT_HTTP": "9000",
        "BGSIM_PROJECTS_ROOT": str(tmp_path / "projects"),
        "BGSIM_JULIA": "C:/julia/bin/julia.exe",
        "BGSIM_FAKE_WORKER": "1",
        "BGSIM_REPO": str(REPO),
    }
    settings = Settings.from_env(env)
    assert settings.host == "127.0.0.1"
    assert settings.port == 9000
    assert settings.projects_root == tmp_path / "projects"
    assert settings.julia == "C:/julia/bin/julia.exe"
    assert settings.fake_worker is True
    assert settings.julia_project == REPO / "julia" / "BGSim"
    assert settings.worker_log_path == REPO / "backend" / "logs" / "worker.log"
    assert settings.web_dist_path == REPO / "web" / "dist"


def test_from_env_defaults() -> None:
    settings = Settings.from_env({})
    assert settings.host == "127.0.0.1"
    assert settings.port == 8765
    assert settings.projects_root == Path.home() / "bgsim-projects"
    assert settings.fake_worker is False
    assert settings.julia, "the juliaup shim on PATH (or the fallback name) is used"
