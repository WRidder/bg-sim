"""Backend settings (plan sections 2.1, 3.7 and 6).

Everything the backend needs to know about its environment: the HTTP bind address,
the projects root, how to find the repository and the Julia executable, the fake
worker switch, the worker log and the built web app.

Environment variables (all optional):

* ``BGSIM_PORT_HTTP`` — the HTTP port, default 8765;
* ``BGSIM_PROJECTS_ROOT`` — the projects root, default ``~/bgsim-projects``;
* ``BGSIM_JULIA`` — the Julia executable, default ``julia`` on PATH;
* ``BGSIM_FAKE_WORKER`` — ``1``/``true``/``yes``/``on`` runs the fixture-driven fake;
* ``BGSIM_REPO`` — the repository root, when it cannot be discovered.
"""

from __future__ import annotations

import os
import shutil
from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path

# The build stamp of plan section 1.3; it doubles as the backend version in /api/health.
BACKEND_VERSION = "0.1.0"

DEFAULT_HOST = "127.0.0.1"
DEFAULT_HTTP_PORT = 8765
DEFAULT_PROJECTS_ROOT = "~/bgsim-projects"

_TRUTHY = {"1", "true", "yes", "on"}


def _truthy(value: str | None) -> bool:
    return value is not None and value.strip().lower() in _TRUTHY


def find_repo_root(
    env: Mapping[str, str] | None = None, start: Path | None = None
) -> Path:
    """The bg-sim repository root.

    Uses ``BGSIM_REPO`` when set, otherwise walks up from this file (and the current
    directory) to the first directory that holds ``julia/BGSim/Project.toml``.
    """
    environment = os.environ if env is None else env
    override = environment.get("BGSIM_REPO")
    if override:
        root = Path(override).expanduser().resolve()
        if not (root / "julia" / "BGSim" / "Project.toml").exists():
            raise FileNotFoundError(
                f"BGSIM_REPO={override!r} does not look like the bg-sim repository"
            )
        return root
    anchor = (start or Path(__file__)).resolve()
    for candidate in (*anchor.parents, Path.cwd().resolve()):
        if (candidate / "julia" / "BGSim" / "Project.toml").exists():
            return candidate
    raise FileNotFoundError(
        "cannot find the bg-sim repository root (julia/BGSim/Project.toml); set BGSIM_REPO"
    )


def default_julia(env: Mapping[str, str] | None = None) -> str:
    """The Julia executable: ``BGSIM_JULIA``, else ``julia`` on PATH.

    On this machine ``shutil.which("julia")`` finds the juliaup shim
    (``%LOCALAPPDATA%\\Microsoft\\WindowsApps\\julia.EXE``).
    """
    environment = os.environ if env is None else env
    return environment.get("BGSIM_JULIA") or shutil.which("julia") or "julia"


@dataclass(frozen=True)
class Settings:
    """Immutable settings; build with :meth:`from_env` or directly in tests."""

    repo_root: Path
    host: str = DEFAULT_HOST
    port: int = DEFAULT_HTTP_PORT
    projects_root: Path = field(default_factory=lambda: Path.home() / "bgsim-projects")
    julia: str = field(default_factory=default_julia)
    fake_worker: bool = False
    worker_log: Path | None = None
    web_dist: Path | None = None

    @property
    def worker_log_path(self) -> Path:
        return (
            self.worker_log
            if self.worker_log is not None
            else self.repo_root / "backend" / "logs" / "worker.log"
        )

    @property
    def web_dist_path(self) -> Path:
        return (
            self.web_dist
            if self.web_dist is not None
            else self.repo_root / "web" / "dist"
        )

    @property
    def julia_project(self) -> Path:
        return self.repo_root / "julia" / "BGSim"

    @classmethod
    def from_env(cls, env: Mapping[str, str] | None = None) -> Settings:
        environment = os.environ if env is None else env
        port_text = environment.get("BGSIM_PORT_HTTP")
        projects_root = environment.get("BGSIM_PROJECTS_ROOT") or DEFAULT_PROJECTS_ROOT
        return cls(
            repo_root=find_repo_root(environment),
            host=DEFAULT_HOST,
            port=int(port_text) if port_text else DEFAULT_HTTP_PORT,
            projects_root=Path(projects_root).expanduser(),
            julia=default_julia(environment),
            fake_worker=_truthy(environment.get("BGSIM_FAKE_WORKER")),
        )
