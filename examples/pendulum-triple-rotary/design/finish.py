# /// script
# requires-python = ">=3.11"
# dependencies = ["numpy>=2.0", "scipy>=1.13", "casadi>=3.6", "matplotlib>=3.8", "httpx>=0.28"]
# ///
"""Run the models of `pendulum-triple-rotary`, measure them and write `expected.json`.

    uv run examples/pendulum-triple-rotary/design/finish.py [--no-run]
    uv run examples/pendulum-triple-rotary/design/finish.py --docs

The backend runner (`runner.py`) is the double's, imported unchanged from
`examples/pendulum-double-rotary/design/`.
"""

from __future__ import annotations

import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.append(str(HERE.parents[1] / "pendulum-double-rotary" / "design"))

import triple_finish as tf

if __name__ == "__main__":
    tf.run(HERE.parent, 3, sys.argv[1:])
