# /// script
# requires-python = ">=3.11"
# dependencies = ["numpy>=2.0", "scipy>=1.13", "casadi>=3.6", "matplotlib>=3.8", "httpx>=0.28"]
# ///
"""Run the models of `pendulum-double-rotary`, measure them and write `expected.json`.

    uv run examples/pendulum-double-rotary/design/finish.py [--no-run]
"""

from __future__ import annotations

import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import rotary_finish as rf  # noqa: E402

if __name__ == "__main__":
    rf.run(HERE.parent, 2, sys.argv[1:])
