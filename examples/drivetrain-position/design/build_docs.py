# /// script
# requires-python = ">=3.11"
# dependencies = ["httpx>=0.28", "numpy>=2.0", "matplotlib>=3.9"]
# ///
"""Build the docs of this example (`models/*.docs`) from `design/docs.md`.

It is the docs builder of the repository (`tools/example_docs/build.py`, X5.10) pointed at this example's
own bundle, so the example is self-contained. `docs.md` uses the bundle format of that tool
(`@@ page`, `@@ figures`) with one extension for the comparison plot: a plot series may carry
``"model": "<other model>"`` and ``"signal_in": "<signal of that model>"``; the other model's real run is
interpolated onto the time axis of the figure's own run.

    uv run examples/drivetrain-position/design/build_docs.py [--no-shots] [--refresh]

It starts one real-worker backend (stopped at the end), needs a current `web/dist` for the diagram and
3D screenshots, and lints the docs the way `examples/run_checks.py` does.
"""

from __future__ import annotations

import copy
import shutil
import sys
import tempfile
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
EXAMPLE = HERE.parent
REPO = EXAMPLE.parent.parent
sys.path.insert(0, str(REPO / "tools" / "example_docs"))

import build  # noqa: E402  (tools/example_docs/build.py)

state: dict = {}
original_cached_run = build.cached_run
original_plot = build.plot_png


def cached_run(backend, example, model, settings, overrides=None):
    state["backend"] = backend
    return original_cached_run(backend, example, model, settings, overrides)


def plot_png(spec, time_column, signals, out):
    spec = copy.deepcopy(spec)
    signals = dict(signals)
    for row in spec["rows"]:
        for series in row["series"]:
            if "model" in series:
                other_time, other = original_cached_run(state["backend"], EXAMPLE.name, series["model"], None)
                signals[series["signal"]] = np.interp(time_column, other_time, other[series["signal_in"]])
    original_plot(spec, time_column, signals, out)


def main() -> int:
    scratch = Path(tempfile.mkdtemp(prefix="dp-docs-src-"))
    try:
        shutil.copy(HERE / "docs.md", scratch / f"{EXAMPLE.name}.md")
        build.SRC = scratch
        build.cached_run = cached_run
        build.plot_png = plot_png
        sys.argv = [sys.argv[0], "--only", EXAMPLE.name, *sys.argv[1:]]
        return build.main()
    finally:
        shutil.rmtree(scratch, ignore_errors=True)


if __name__ == "__main__":
    sys.exit(main())
