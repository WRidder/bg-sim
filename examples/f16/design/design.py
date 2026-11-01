# /// script
# requires-python = ">=3.11"
# dependencies = ["numpy>=2.0", "scipy>=1.13"]
# ///
"""Design and reference numbers of the `f16` example.

    uv run examples/f16/design/design.py

Writes `design/design.json`: every number the models, the checks and the docs use. Then
`uv run examples/f16/design/build_model.py` writes the models, the scenes and `expected.json`.

1. The reference model (`f16_ref.py`, the book's F16 subroutine in ft units) is checked against
   the book's own derivative check and its Table 3.6-3 trims (xcg = 0.30, 0.35, 0.38).
2. Linearisation at the book's trim point (502 ft/s, sea level): the open-loop modes per CG.
3. The tables in the bg-sim layout (square Lookup2D grids, refined without changing the
   bilinear function), the SI constants and the principal axes of the inertia.
4. The fly-by-wire design (`fbw.py`) and the scenario references (`scenarios.py`).
"""

from __future__ import annotations

import json
import math
import sys
from pathlib import Path

import numpy as np
from scipy.optimize import fsolve

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import f16_ref as F  # noqa: E402
import f16_si as SI  # noqa: E402
from f16_lin import LON, classify, linearise, modes, state13, trim_level  # noqa: E402,F401

# The book's Table 3.6-3 (Stevens & Lewis, 2nd ed.): level flight at 502 ft/s, sea level.
BOOK_TRIM = {
    0.30: {"alpha": 0.03936, "throttle": 0.1485, "el": -1.931},
    0.35: {"alpha": 0.03691, "throttle": 0.1385, "el": -0.7588},
    0.38: {"alpha": 0.03544, "throttle": 0.1325, "el": -0.0559},
}
# The book's linearisation example at xcg = 0.30 (502 ft/s, sea level): longitudinal modes.
BOOK_SHORT_PERIOD_030 = complex(-1.2039, 1.4922)
BOOK_PHUGOID_030 = complex(-0.0087, 0.0740)   # as reproduced by the archimedes F-16 tutorial
VT_BOOK = 502.0
H_BOOK = 0.0


def bgsim_tables():
    """The NASA tables on the square grids of the bg-sim Lookup2D blocks (rows = the second input).

    The grids are refined by adding breakpoints; a bilinear function stays bilinear on every
    sub-rectangle, so the refined table is the same function inside the data. The elevator axis
    runs to +-25 deg (the actuator limit) with the book's linear extrapolation; CL and CN are
    tabulated over signed beta (odd in beta) so no sign switch is needed in the model."""
    F.CLAMP_AB = False
    alpha12 = [float(a) for a in F.ALPHA_GRID]
    alpha13 = sorted(alpha12 + [42.5])
    el12 = [-25.0, -24.0, -18.0, -12.0, -6.0, 0.0, 3.0, 6.0, 12.0, 18.0, 24.0, 25.0]
    beta13 = [float(b) for b in np.arange(-30.0, 30.0 + 1e-9, 5.0)]
    beta12 = [-30.0, -20.0, -15.0, -10.0, -5.0, 0.0, 5.0, 10.0, 15.0, 20.0, 25.0, 30.0]
    t = {}
    t["CX"] = {"x": alpha12, "y": el12, "table": [[F.cx(a, e) for a in alpha12] for e in el12]}
    t["CM"] = {"x": alpha12, "y": el12, "table": [[F.cm(a, e) for a in alpha12] for e in el12]}
    t["CL"] = {"x": alpha13, "y": beta13, "table": [[F.cl(a, b) for a in alpha13] for b in beta13]}
    t["CN"] = {"x": alpha13, "y": beta13, "table": [[F.cn(a, b) for a in alpha13] for b in beta13]}
    for name, fn in (("DLDA", F.dlda), ("DLDR", F.dldr), ("DNDA", F.dnda), ("DNDR", F.dndr)):
        t[name] = {"x": alpha12, "y": beta12, "table": [[fn(a, b) for a in alpha12] for b in beta12]}
    t["CZ"] = {"x": alpha12, "table": [float(v) for v in F.CZ]}
    names = ["CXq", "CYr", "CYp", "CZq", "Clr", "Clp", "Cmq", "Cnr", "Cnp"]
    t["DAMP"] = {"x": alpha12, "names": names, "tables": [[float(v) for v in F.DAMP[i]] for i in range(9)]}
    alt_m = [float(a) * SI.FT for a in F.ALT_GRID]
    mach = [float(m) for m in F.MACH_GRID]
    for name, arr in (("T_IDLE", F.T_IDLE), ("T_MIL", F.T_MIL), ("T_MAX", F.T_MAX)):
        t[name] = {"x": alt_m, "y": mach, "table": [[float(v) * SI.LBF for v in row] for row in arr]}
    # self-check: the refined tables reproduce the book's function at random interior points
    rng = np.random.default_rng(1)
    for _ in range(200):
        a, e, b = rng.uniform(-10, 45), rng.uniform(-25, 25), rng.uniform(-30, 30)
        assert abs(F.interp2(a, e, np.array(alpha12), np.array(el12), np.array(t["CX"]["table"]), False, False) - F.cx(a, e)) < 1e-12
        assert abs(F.interp2(a, b, np.array(alpha13), np.array(beta13), np.array(t["CL"]["table"]), False, False) - F.cl(a, b)) < 1e-12
        assert abs(F.interp2(a, b, np.array(alpha12), np.array(beta12), np.array(t["DNDR"]["table"]), False, False) - F.dndr(a, b)) < 1e-12
    return t


def main() -> int:
    out: dict = {"units": "SI (m, kg, s, N, Pa); table angles and control-law angles in deg"}
    # 1. the book's derivative check
    xd, _ = F.f16(np.array(F.CHECK_X), F.CHECK_U, F.CHECK_XCG, book_constants=True)
    rel = [abs(a - b) / abs(b) for a, b in zip(xd, F.CHECK_XD)]
    out["book_check"] = {"xd": list(map(float, xd)), "book": F.CHECK_XD, "max_rel": max(rel)}
    print(f"book derivative check: max relative error {max(rel):.2e}")
    assert max(rel) < 1e-6

    # 2. trims and modes at the book's point
    trims = {}
    for xcg, book in BOOK_TRIM.items():
        tr = trim_level(VT_BOOK, H_BOOK, xcg)
        A, Bm = linearise(tr)
        lam, vec = modes(A)
        tr["book"] = book
        tr["modes"] = classify(lam)
        tr["A"] = A.tolist()
        tr["B"] = Bm.tolist()
        tr["eigvals"] = [[l.real, l.imag] for l in lam]
        tr["eigvecs_re"] = vec.real.tolist()
        tr["eigvecs_im"] = vec.imag.tolist()
        trims[f"{xcg:.2f}"] = tr
        print(f"xcg {xcg:.2f}: alpha {tr['alpha']:.5f} (book {book['alpha']}), throttle {tr['throttle']:.4f} "
              f"(book {book['throttle']}), el {tr['el']:.4f} (book {book['el']})")
        print(f"          modes {np.round(lam, 4)}")
        assert abs(tr["alpha"] - book["alpha"]) < 1e-5 and abs(tr["throttle"] - book["throttle"]) < 1e-4
        assert abs(tr["el"] - book["el"]) < 1e-3
    sp = trims["0.30"]["modes"]["short_period"]
    assert abs(complex(*sp) - BOOK_SHORT_PERIOD_030) < 2e-3 * abs(BOOK_SHORT_PERIOD_030)
    out["trims"] = trims
    out["book_modes_030"] = {"short_period": [BOOK_SHORT_PERIOD_030.real, BOOK_SHORT_PERIOD_030.imag],
                             "phugoid": [BOOK_PHUGOID_030.real, BOOK_PHUGOID_030.imag]}

    # 3. SI constants and tables
    out["si"] = {"mass": SI.MASS, "g0": SI.G0, "S": SI.S, "b": SI.B, "cbar": SI.CBAR, "he": SI.HE,
                 "Jxx": SI.JXX, "Jyy": SI.JYY, "Jzz": SI.JZZ, "Jxz": SI.JXZ,
                 "J_principal": SI.J_PRINCIPAL.tolist(), "eps": SI.EPS,
                 "q_bp": [math.cos(SI.EPS / 2), 0.0, math.sin(SI.EPS / 2), 0.0],
                 "rho0": SI.RHO0, "klapse": SI.KLAPSE, "h_trop": SI.H_TROP, "a_gas": SI.A_GAS,
                 "xcgr": F.XCGR}
    out["tables"] = bgsim_tables()

    import fbw
    import scenarios
    out["fbw"] = fbw.design(out)
    out["scenarios"] = scenarios.run(out)

    (HERE / "design.json").write_text(json.dumps(out, indent=1) + "\n", encoding="utf-8", newline="\n")
    print(f"wrote {HERE / 'design.json'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
