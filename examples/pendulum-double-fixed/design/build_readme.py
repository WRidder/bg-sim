# /// script
# requires-python = ">=3.11"
# dependencies = ["casadi>=3.6", "numpy>=2.0", "scipy>=1.13"]
# ///
"""Write README.md of pendulum-double-fixed from params.py, results.json and measured.json.

measured.json holds the numbers read from a real-worker run of the model (catch time, upright band,
peak deflection, recovery time, peak voltage, compile and run times, the difference to the design
prediction); regenerate it after a change of the model with the run of ``uv run examples/run_checks.py``.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(1, str(HERE.parents[1] / "pendulum-double-fixed" / "design"))

import params as prm  # noqa: E402
from pendulum_readme import render_readme  # noqa: E402

if __name__ == "__main__":
    measured = json.loads((HERE / "measured.json").read_text(encoding="utf-8"))
    out = HERE.parent / "README.md"
    out.write_text(render_readme(prm, measured), encoding="utf-8", newline="\n")
    print("wrote", out)
