# /// script
# requires-python = ">=3.11"
# dependencies = ["numpy>=2.0", "httpx>=0.28"]
# ///
"""Offline check of the scene kinematics: the SDF kinematic tree (scale 1) driven by the bound joint signals must reproduce the
world poses of the wing segments and the tail flaps that the multibond model composes (axis signs, mounting frames).

    uv run examples/robird/design/check_scene.py
"""

from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(HERE))
import build_model as bm  # noqa: E402
import params as P  # noqa: E402
import sim  # noqa: E402

rc = sim.rc


def qmat(q):
    return P.matrix_from_quat(np.asarray(q) / np.linalg.norm(q))


def main() -> int:
    doc = json.loads((ROOT / "models" / "robird-trim.bgmodel.json").read_text(encoding="utf-8"))
    tmp = Path(tempfile.mkdtemp()) / "scale1.sdf"
    tmp.write_text(bm.build_scene(scale=1.0), encoding="utf-8")
    sdf = rc._read_sdf(tmp)
    s = sim.Sim()
    try:
        r = s.run(doc)
    finally:
        s.close()
    S = r.signals
    pairs = {  # sdf link -> (pose signal base of the multibond body frame, point of the link frame that is the body CoM)
        "wing_in_L": ("PoseBL1/g", [P.L1 / 2, 0, 0]), "wing_out_L": ("PoseBL2/g", [P.L2 / 2, 0, 0]),
        "wing_in_R": ("PoseBR1/g", [P.L1 / 2, 0, 0]), "wing_out_R": ("PoseBR2/g", [P.L2 / 2, 0, 0]),
        "elevon_L_link": ("PoseBTL/g", [0, 0, 0]), "elevon_R_link": ("PoseBTR/g", [0, 0, 0]), "rudder_link": ("PoseBTV/g", [0, 0, 0]),
    }
    jmap = {"flap_L": "JL1/qout", "torsion_L": "JL1/dang[1]", "bend_L": "JL2/qout", "torsion2_L": "JL2/dang[1]", "torsion2_R": "JR2/dang[1]", "flap_R": "JR1/qout", "torsion_R": "JR1/dang[1]",
            "bend_R": "JR2/qout", "elevon_L": "JTL/qout", "elevon_R": "JTR/qout", "rudder": "JTV/qout"}
    worst_p, worst_r = 0.0, 0.0
    per = {}
    for idx in np.linspace(0, r.time.size - 1, 40).astype(int):
        q = {j: float(S[k][idx]) for j, k in jmap.items()}
        worlds = rc._sdf_link_worlds(sdf, q)
        Rf = qmat([S[f"Truth/q[{i}]"][idx] for i in (1, 2, 3, 4)])
        pf = np.array([S["Truth/x"][idx], S["Truth/y"][idx], S["Truth/z"][idx]])
        Wf = np.eye(4)
        Wf[:3, :3], Wf[:3, 3] = Rf, pf
        for link, (base, pt) in pairs.items():
            W = Wf @ worlds[link]
            model_R = qmat([S[f"{base}[{i}]"][idx] for i in (1, 2, 3, 4)])
            model_p = np.array([S[f"{base}[{i}]"][idx] for i in (5, 6, 7)])
            p = (W @ np.array([*pt, 1.0]))[:3]
            per[link] = (max(per.get(link, (0, 0))[0], float(np.abs(p - model_p).max())), max(per.get(link, (0, 0))[1], float(np.abs(W[:3, :3] - model_R).max())))
            worst_p = max(worst_p, float(np.abs(p - model_p).max()))
            worst_r = max(worst_r, float(np.abs(W[:3, :3] - model_R).max()))
    print({k: (round(a, 4), round(b, 4)) for k, (a, b) in per.items()})
    print(f"max position error {worst_p:.2e} m, max rotation-matrix error {worst_r:.2e}")
    return 0 if worst_p < 1.5e-2 and worst_r < 5e-2 else 1  # the sweep deflection (about 0.02 rad) and the Gibbs chart of the torsion have no scene joint


if __name__ == "__main__":
    sys.exit(main())
