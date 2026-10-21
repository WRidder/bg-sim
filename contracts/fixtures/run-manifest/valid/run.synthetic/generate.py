# /// script
# requires-python = ">=3.11"
# dependencies = ["numpy"]
# ///
"""Generate the data files of the synthetic run fixture (plan 3.5).

    uv run contracts/fixtures/run-manifest/valid/run.synthetic/generate.py [output-dir]

Writes two files next to this script (or into the directory given as argv[1]):

* ``columns.f64`` - the time column, then one column per signal in manifest
  order, each ``n`` Float64 values (the spec's playback file);
* ``stream.f64`` - row-major ``[t, v1 ... vn]`` Float64 rows (the spec's frame
  layout, appended while a simulation runs).

Both are little-endian Float64 and deterministic: running the script twice
writes identical bytes. The four signals are ``Synthetic/sine`` (1 Hz sine, V),
``Synthetic/step`` (0 -> 2 V at t = 0.25 s), ``Synthetic/counter`` (Int, floor
of t / 0.1 s) and ``Synthetic/flag`` (Bool, 0 -> 1 at t = 0.5 s).
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np

N = 1001
T0 = 0.0
T1 = 1.0
SINE_FREQ = 1.0
STEP_T = 0.25
STEP_V = 2.0
COUNTER_DT = 0.1
FLAG_T = 0.5


def signal_matrix() -> np.ndarray:
    """The five columns (time plus four signals) as a (5, N) little-endian array."""
    t = np.linspace(T0, T1, N)
    sine = np.sin(2.0 * np.pi * SINE_FREQ * t)
    step = np.where(t >= STEP_T, STEP_V, 0.0)
    counter = np.floor(t / COUNTER_DT)
    flag = np.where(t >= FLAG_T, 1.0, 0.0)
    return np.stack([t, sine, step, counter, flag], axis=0).astype("<f8")


def main() -> int:
    out = Path(sys.argv[1]).resolve() if len(sys.argv) > 1 else Path(__file__).resolve().parent
    out.mkdir(parents=True, exist_ok=True)
    data = signal_matrix()
    # Columnar: time column, then one contiguous column per signal.
    data.tofile(out / "columns.f64")
    # Row-major frames: [t, v1 ... vn] per row.
    np.ascontiguousarray(data.T).tofile(out / "stream.f64")
    print(f"wrote columns.f64 and stream.f64 ({data.shape[1]} rows, {data.shape[0]} columns) into {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
