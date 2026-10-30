# /// script
# requires-python = ">=3.11"
# dependencies = ["numpy>=2.0", "httpx>=0.28", "matplotlib>=3.9"]
# ///
"""Design data, trim identification and verification of the Robird example (X5.15).

    uv run examples/robird/design/design.py sizing     # the figure-eight from a turn-radius estimate
    uv run examples/robird/design/design.py trim       # cycle-averaged trim from the full flapping model (writes trim.json)
    uv run examples/robird/design/design.py identify   # cycle-averaged sensitivities from short full-model runs (writes identify.json)
    uv run examples/robird/design/design.py verify     # the full run: metrics, expected.json, plots for the docs
    uv run examples/robird/design/build_model.py       # models and scene from the numbers below

The module level (SIZE, GAINS, TRIM) is plain data that build_model.py imports; the heavy parts import lazily.
"""

from __future__ import annotations

import json
import math
import sys
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import params as P  # noqa: E402
import path as PATH  # noqa: E402

ROOT = HERE.parent
RUNS = HERE / "_runs"

# --------------------------------------------------------------------------- the mission
SIZE = dict(
    A=110.0,        # m  half extent of the figure along x       x = A sin(th)
    B=42.0,         # m  half extent along y                    y = B sin(2 th)
    Cz=1.5,         # m  gentle altitude Lissajous              z = z0 + Cz sin(th)
    z0=25.0,        # m  cruise altitude
    U=12.0,         # m/s cruise speed (ground speed command)
    t_go=3.0,       # s  the bird flies straight (trim) until the path following starts
    t_end=60.0,     # s
    t_stat=8.0,     # s  the acceptance statistics start here (convergence)
)

# --------------------------------------------------------------------------- controller data (see README "Design")
GAINS = dict(
    fc=dict(Kth=1.2, Kq=0.12),      # the remaining gains are the defaults of library/FlightCtrl.jl
    guide=dict(kchi=1.0, Llook=25.0, tlead=0.6),
)

_trim_file = HERE / "trim.json"
TRIM = json.loads(_trim_file.read_text()) if _trim_file.exists() else dict(f0=3.4, th0=0.10, de0=-0.14)


def sizing() -> dict:
    st = PATH.stats(SIZE["A"], SIZE["B"])
    U = SIZE["U"]
    return dict(
        lap_length=st["length"], rmin=st["rmin"], period=st["length"] / U,
        bank_at_rmin_deg=math.degrees(math.atan(U**2 / (P.G * st["rmin"]))),
        turn_rate_max=U / st["rmin"],
    )


# --------------------------------------------------------------------------- model builders used by the sim scripts
def closed_loop_doc(t_end: float, tag: str = "robird", trim: dict | None = None, gains: dict | None = None,
                    points_per_s: int = 20, size: dict | None = None, t_go: float | None = None, comment: str = ""):
    import build_model as bm
    sz = {**SIZE, **(size or {})}
    tr = {**TRIM, **(trim or {})}
    g = {k: dict(v) for k, v in (gains or GAINS).items()}
    tab = PATH.table(sz["A"], sz["B"], sz["Cz"], sz["z0"], ds=2.0)
    ctl = dict(guide=dict(t_go=sz["t_go"] if t_go is None else t_go, **g["guide"]),
               fc=dict(f0=tr["f0"], th0=tr["th0"], de0=tr["de0"], **g["fc"]))
    init = dict(U=sz["U"], heading=float(tab["psi"][0]), pitch=tr["th0"], z0=sz["z0"], f0=tr["f0"])
    b, ctx, plots = bm.build(tag, init, t_end, controller=bm.closed_loop(tab, ctl, sz["U"], stat_from=sz["t_stat"]))
    return bm.finish(b, ctx, tag, init, t_end, plots, comment, int(t_end * points_per_s) + 1), tab


# --------------------------------------------------------------------------- stage: trim
def stage_trim() -> None:
    """Level-flight trim from the full flapping model: the closed loop with the path following switched off flies
    straight; the cycle-averaged flapping frequency, pitch attitude and elevator over the second half are the trim."""
    import sim
    s = sim.Sim()
    try:
        doc, _ = closed_loop_doc(34.0, "trim", t_go=1e9, points_per_s=50, size=dict(Cz=0.0))
        r = s.run(doc)
        t, S = r.time, r.signals
        m = t > 24.0
        tr = dict(f0=float(np.mean(S["Fctl/f_cmd"][m])), th0=float(np.mean(S["Fctl/theta"][m])),
                  de0=float(np.mean(S["Fctl/de"][m])), speed=float(np.mean(S["Fctl/speed"][m])),
                  vz=float(np.mean(S["Truth/vw[3]"][m])), P_el=float(np.mean(S["Drv/source/u"][m] * S["Drv/isense/y"][m])),
                  P_air=float(np.mean(S["PaSum/P"][m])), I_mean=float(np.mean(S["Drv/isense/y"][m])))
        print("trim:", json.dumps(tr, indent=1))
        _trim_file.write_text(json.dumps(tr, indent=1))
    finally:
        s.close()


# --------------------------------------------------------------------------- stage: identify (cycle-averaged sensitivities)
def stage_identify() -> None:
    """Short open-loop runs of the full flapping model around the trim: the cycle-averaged accelerations
    (change of the world velocity and of the body rates over two flapping cycles, started after the wing has settled)
    for a perturbation of each input in turn. The table is the gain schedule the loops were designed with."""
    import build_model as bm
    import sim
    f0, th0, de0 = TRIM["f0"], TRIM["th0"], TRIM["de0"]
    U = SIZE["U"]

    def one(s, f=f0, th=th0, de=de0, da=0.0, dr=0.0, aL=1.0, aR=1.0):
        init = dict(U=U, heading=0.0, pitch=th, z0=SIZE["z0"], f0=f)
        t_end = 0.3 + 2.0 / f + 0.05
        b, ctx, plots = bm.build("id", init, t_end, controller=bm.open_loop(f, de, da, dr, aL, aR))
        doc = bm.finish(b, ctx, "robird", init, t_end, plots, "identification", int(t_end * 100) + 1)
        r = s.run(doc)
        t, S = r.time, r.signals
        T = 2.0 / f
        at = lambda k, tt: float(np.interp(tt, t, S[k]))
        d = lambda k: (at(k, 0.3 + T) - at(k, 0.3)) / T
        m = (t >= 0.3) & (t <= 0.3 + T)
        return dict(ax=d("Truth/vw[1]"), az=d("Truth/vw[3]"), ay=d("Truth/vw[2]"), pdot=d("Truth/wb[1]"), qdot=-d("Truth/wb[2]"),
                    rdot=d("Truth/wb[3]"), P_air=float(np.mean(S["PaSum/P"][m])))

    s = sim.Sim()
    try:
        base = one(s)
        steps = dict(f=0.3, th=0.05, de=0.05, da=0.05, dr=0.05, eta=0.1)
        rows = {"base": base}
        for k, h in steps.items():
            kw = {"f": dict(f=f0 + h), "th": dict(th=th0 + h), "de": dict(de=de0 + h), "da": dict(da=h), "dr": dict(dr=h),
                  "eta": dict(aL=1 + h, aR=1 - h)}[k]
            r = one(s, **kw)
            rows[k] = {q: (r[q] - base[q]) / h for q in base if q != "P_air"} | {"dP_air": (r["P_air"] - base["P_air"]) / h}
            print(k, {q: round(v, 3) for q, v in rows[k].items()}, flush=True)
        (HERE / "identify.json").write_text(json.dumps(rows, indent=1))
    finally:
        s.close()


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "sizing"
    if cmd == "sizing":
        print(json.dumps(sizing(), indent=1))
    elif cmd == "trim":
        stage_trim()
    elif cmd == "identify":
        stage_identify()
    elif cmd == "verify":
        import verify
        verify.main()
    else:
        sys.exit(__doc__)
