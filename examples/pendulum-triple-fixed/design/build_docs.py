# /// script
# requires-python = ">=3.11"
# dependencies = ["casadi>=3.6", "numpy>=2.0", "scipy>=1.13"]
# ///
"""Write the docs source bundle tools/example_docs/src/pendulum-triple-fixed.md, then build the docs with

    uv run examples/pendulum-triple-fixed/design/design.py        (results.json first)
    uv run examples/pendulum-triple-fixed/design/build_docs.py
    uv run tools/example_docs/build.py --only pendulum-triple-fixed
"""

from __future__ import annotations

import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(1, str(HERE.parents[1] / "pendulum-double-fixed" / "design"))

import params as prm  # noqa: E402
from pendulum_docs import render  # noqa: E402

if __name__ == "__main__":
    out = HERE.parents[2] / "tools" / "example_docs" / "src" / f"{prm.EXAMPLE}.md"
    out.write_text(render(prm), encoding="utf-8", newline="\n")
    print("wrote", out)
