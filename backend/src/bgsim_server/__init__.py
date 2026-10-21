"""bg-sim Python backend.

M0.2 lays down this package with the generated contract models
(`bgsim_server.contracts`, written by `tools/gen_contracts.py`) and their tests.
The FastAPI app, the Julia worker supervisor, run storage and the `bgsim` entry
point arrive in M0.4.
"""

from __future__ import annotations


def main() -> None:
    raise SystemExit(
        "the bgsim backend app arrives in M0.4; this package currently holds only the contracts harness"
    )
