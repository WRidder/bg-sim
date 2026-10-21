"""bg-sim Python backend.

M0.2 laid down this package with the generated contract models
(`bgsim_server.contracts`, written by `tools/gen_contracts.py`). M0.4 adds the
FastAPI app (`bgsim_server.app`), the worker supervisor (`bgsim_server.worker`)
and the `bgsim` entry point (`bgsim_server.__main__`).
"""

from __future__ import annotations


def main() -> None:
    """Entry point for the `bgsim-server` script; delegates to `bgsim_server.__main__`."""
    from .__main__ import main as run

    run()
