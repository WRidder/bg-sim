# /// script
# requires-python = ">=3.11"
# dependencies = ["numpy>=2.0", "scipy>=1.13"]
# ///
"""The reference numbers of `humanoid-dual-arm` (no bg-sim involved), cached in
`design/references.json`.

    uv run examples/humanoid-dual-arm/design/references.py       # recompute and print

* `page`: the interactive page's IK as the page runs it (`srs.solve`, the 1 deg finite-difference
  Jacobian, 8 iterations per frame from the home posture, until it settles) at the default object
  pose, 7-DOF and 6-DOF, stacked and ideal, and with the elbow bias of the scenario;
* `twin`: the in-model firmware tick by tick (`humanoid.twin`: the scenario trajectory and the
  ArmIK step with the exact Jacobian and the step scaled to at most 0.05 deg per joint and tick), 7-DOF and 6-DOF, sampled at
  the check instants;
* `fk`: the forward kinematics of the start posture (the fixed pose every run starts from) in the
  bg-sim world: hands, elbows, the box.
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np

import humanoid as dz
import srs

HERE = Path(__file__).resolve().parent
CACHE = HERE / "references.json"


def tolist(x):
    if isinstance(x, dict):
        return {k: tolist(v) for k, v in x.items()}
    if isinstance(x, (list, tuple)):
        return [tolist(v) for v in x]
    if isinstance(x, np.ndarray):
        return x.tolist()
    if isinstance(x, (np.floating, np.integer, np.bool_)):
        return x.item()
    return x


def page_refs() -> dict:
    p, r = srs.OBJ_DEFAULT
    out = {}
    for lock, dof in ((-1, "7dof"), (srs.LOCK, "6dof")):
        for ideal in (False, True):
            for bias in (0.0, dz.BIAS):
                key = f"{dof}_{'ideal' if ideal else 'stacked'}_bias{bias:g}"
                q, res = srs.solve(p, r, 1, ideal, lock, bias=bias)
                out[key] = {"q": q, **res, "elbow_world": srs.point_world(srs.elbow(q, 1, ideal))}
    return out


def twin_refs() -> dict:
    out = {}
    times = {"t_first": dz.TS, "t_hold": dz.T_HOLD, "t_bias": dz.T_BIAS}
    for dof6 in (False, True):
        tw = dz.twin(dof6=dof6)
        entry = {}
        for name, t in times.items():
            i = int(round(t / dz.TS)) - 1
            entry[name] = {
                key: {
                    "q": tw[key]["q"][i], "pe": tw[key]["pe"][i], "oe": tw[key]["oe"][i], "lim": tw[key]["lim"][i],
                    "elbow": tw[key]["elbow"][i],
                    "elbow_world": srs.point_world(tw[key]["elbow"][i]) + (
                        [0.0, dz.GHOST_DY, 0.0] if key.startswith("I") else 0.0),
                }  # fmt: skip
                for key in ("L", "R", "IL", "IR")
            }
        # windows: the largest readouts over the dwell and over the bias ramp + hold
        t = tw["t"]
        for wname, (a, b) in {"dwell": (dz.T_HOLD - 0.45, dz.T_HOLD + 0.05), "bias": (dz.T_HOLD + 0.05, dz.T_END)}.items():
            m = (t >= a) & (t <= b)
            entry[f"max_{wname}"] = {k: {"pe": float(tw[k]["pe"][m].max()), "oe": float(tw[k]["oe"][m].max()),
                                         "lim_min": float(tw[k]["lim"][m].min())} for k in ("L", "R", "IL", "IR")}  # fmt: skip
        out["6dof" if dof6 else "7dof"] = entry
    return out


def fk_refs() -> dict:
    out = {}
    for p, s in (("L", 1), ("R", -1)):
        f = dz.chain_fk(dz.Q_START, s)
        out[p] = {"hand": srs.pose7(f["hand"]), "elbow": f["W"][3][:3, 3], "q_rad": dz.Q_START * srs.D}
    p0, r0 = dz.OBJ_START
    out["box"] = dz.object_pose_world(p0, r0)
    out["box_from_left"] = srs.pose7(dz.chain_fk(dz.Q_START, 1)["hand"] @ np.linalg.inv(srs.grasp(1)))
    return out


def compute() -> dict:
    refs = {"page": page_refs(), "twin": twin_refs(), "fk": fk_refs(),
            "t_hold": dz.T_HOLD, "t_bias": dz.T_BIAS, "t_end": dz.T_END, "q_start": dz.Q_START}  # fmt: skip
    CACHE.write_text(json.dumps(tolist(refs), indent=1) + "\n", encoding="utf-8", newline="\n")
    return refs


def load() -> dict:
    return json.loads(CACHE.read_text(encoding="utf-8"))


def main() -> None:
    refs = tolist(compute())
    pg = refs["page"]
    print("page IK at the default pose (stacked left arm):")
    for key, v in pg.items():
        print(f"  {key:28s} pe {v['pe_mm']:.4f} mm  oe {v['oe_deg']:.4f} deg  limit {v['limit_pct']:.1f}% (J{v['limit_joint']})"
              f"  q {np.round(v['q'], 3)}")  # fmt: skip
    for dof in ("7dof", "6dof"):
        e = refs["twin"][dof]
        print(f"twin {dof}:")
        for tname in ("t_hold", "t_bias"):
            for k in ("L", "IL"):
                v = e[tname][k]
                print(f"  {tname} {k:2s} pe {v['pe']:.4f} mm  oe {v['oe']:.4f} deg  lim {v['lim']:.2f}%  q {np.round(v['q'], 4)}"
                      f"  elbow {np.round(v['elbow_world'], 4)}")  # fmt: skip
        print("  max over windows", e["max_dwell"]["L"], e["max_bias"]["L"])
    print("fk", refs["fk"]["L"]["hand"], refs["fk"]["box"], refs["fk"]["box_from_left"])


if __name__ == "__main__":
    main()
