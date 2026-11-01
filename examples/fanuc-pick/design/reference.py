# /// script
# requires-python = ">=3.11"
# dependencies = ["numpy>=2.0", "scipy>=1.13", "numba>=0.60"]
# ///
"""Independent reference numbers of the fanuc-pick checks (`build_expected.py` turns them into
expected.json); writes design/reference.json and prints a summary.

    uv run examples/fanuc-pick/design/reference.py

1. Kinematics: the closed-form planner kinematics (`fk_down` of the PickPlanner block, the
   gripper pose `gref`) against the URDF joint chain (`fanuc.fk_flange`, the frames of the ROS
   description) along every model's reference trajectory: position, yaw and tool-down errors.
2. Vacuum: the operating vacuum of one zone where the ejector curve meets the leak demand
   (lip roughness leak + Darcy flow through the carton), and the vacuum at the lift start of the
   seal ODE (contact to lift, the ejector on).
3. Static holding (model `static-hold`): the cup forces of a rigid carton hanging still on five
   bellows, by hand: axial springs k_ax in series with the cylinder end stop, tilt springs
   k_tilt in series with the rod bending, and the CoM below the lip plane (a pendulum term):
       K = 2 k_s a^2 + 5 k_t + m g d,  phi_x = m g cx / K,  phi_y = m g cy / K,
       T_i = m g / 5 + k_s (x_i phi_x + y_i phi_y).
4. Cycle time and timeline of every model (`planner.reference`).
5. The reduced model's holding margin and drop of every model (the margins the optimiser used).
"""

from __future__ import annotations

import json
import math
import sys
from pathlib import Path

import numpy as np
from scipy.optimize import brentq

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import build_models as B  # noqa: E402
import fanuc as fz  # noqa: E402
import params as P  # noqa: E402
import planner  # noqa: E402
import reduced as Rd  # noqa: E402

NL = "\n"


def model_globals(name: str) -> tuple[dict, str]:
    kind, _c, ov = B.all_scenarios()[name]
    return P.eval_globals(P.global_rows() + B.extra_rows(kind), {**B.kind_overrides(kind), **ov}), kind


def fk_errors(ref: dict, every: int = 5) -> dict:
    """URDF chain against the planner's gripper pose along a reference."""
    q, g = ref["q"], ref["g"]
    e_pos = e_yaw = e_down = 0.0
    for k in range(0, q.shape[1], every):
        t = fz.fk_flange(q[:, k])
        e_pos = max(e_pos, float(np.linalg.norm(t[:3, 3] - g[4:7, k])))
        r_g = t[:3, :3] @ fz.R_FLANGE_G
        yaw = math.atan2(r_g[1, 0], r_g[0, 0])
        psi = 2 * math.atan2(g[3, k], g[0, k])
        e_yaw = max(e_yaw, abs((yaw - psi + math.pi) % (2 * math.pi) - math.pi))
        e_down = max(e_down, math.acos(min(1.0, r_g[2, 2])))
    return {"pos": e_pos, "yaw": e_yaw, "down": e_down}


def operating_vacuum(g: dict) -> float:
    """Vacuum where the ejector flow equals the lip leak plus the Darcy flow (sealed lip)."""
    c = Rd.CUP_DEF

    def balance(dp: float) -> float:
        q_gen = g["Q_max"] * (1.0 - dp / g["dp_max"])
        q_leak = c["Cd"] * g["A_lip0"] * dp * math.sqrt(2.0 / (c["rho"] * math.sqrt(dp * dp + c["p_tr"] ** 2)))
        return q_gen - q_leak - g["perm"] * g["A_eff"] * dp

    return float(brentq(balance, 1.0, g["dp_max"]))


def static_hold(g: dict) -> dict:
    """Hand calculation of the cup forces of the hanging carton (see the module docstring)."""
    m, a = g["m_p"], g["r_p"]
    k_s = 1.0 / (1.0 / g["k_ax"] + 1.0 / g["k_stop"])
    k_t = 1.0 / (1.0 / g["k_tilt"] + 1.0 / g["kr_rod"])
    d = g["H_p"] / 2 - g["cz"]
    W = m * P.G0
    K = 2 * k_s * a * a + 5 * k_t + W * d
    # the CoM offset seen from the grip point, gripper frame (psig = 0, lay = 0 in this model)
    cx, cy = g["cx"] - g["gx"], g["cy"] - g["gy"]
    phx, phy = W * cx / K, W * cy / K
    T = [W / 5 + k_s * (a * dx * phx + a * dy * phy) for dx, dy in P.ZONE_DIRS]
    # utilisation at rest: every bellows carries the moment k_t |phi| (its share of the series
    # tilt), no shear; the capacity is A_eff at the operating vacuum
    M = k_t * math.hypot(phx, phy)
    cap = g["A_eff"] * operating_vacuum(g) + Rd.CUP_DEF["F_eps"]
    U = [(Ti + 4 * M / g["D_lip"]) / cap for Ti in T]
    return {"T": T, "U": U, "M_tilt": M, "k_s": k_s, "k_t": k_t, "K": K, "phi": [phx, phy], "d": d, "sum": sum(T),
            "W": W}


def main() -> int:
    out: dict = {"models": {}}
    scen = B.all_scenarios()
    for name, (kind, _c, _ov) in scen.items():
        g, kind = model_globals(name)
        ref = planner.reference(g)
        tl = ref["tl"]
        fk = fk_errors(ref)
        pk = Rd.Pick(g, kind, ref)
        res = pk.run()
        # peak gripper acceleration while carried (gravity not included)
        held = ref["held"] > 0.5
        acc = np.gradient(np.gradient(ref["g"][4:7], ref["t"], axis=1), ref["t"], axis=1)
        a_carry = float(np.max(np.linalg.norm(acc[:, held], axis=0))) if np.any(held) else 0.0
        entry = {
            "kind": kind, "T_cyc": ref["T_cyc"], "tL": tl["tL"], "tE": tl["tE"], "tF": tl["tF"], "tB": tl["tB"],
            "t2s": tl["t2s"], "T2": tl["T2"], "util_max": ref["util_max"], "fk": fk,
            "dp_lift": res["dp_lift"], "M_tot": res["M_tot"], "margins": res["margins"], "dropped": res["dropped"],
            "sep_max": res["sep_max"], "M_req": g["M_req"], "act": pk.act, "a_carry": a_carry,
        }
        out["models"][name] = entry
        print(f"{name:24s} T_cyc {ref['T_cyc']:.4f}  util {100 * ref['util_max']:5.1f} %  fk pos {fk['pos']:.1e} yaw "
              f"{fk['yaw']:.1e} down {fk['down']:.1e}  M_tot {res['M_tot']:+.3f}  dropped {res['dropped']}  "
              f"a_carry {a_carry:.2f} m/s^2", flush=True)
    g, _ = model_globals("static-hold")
    out["vacuum"] = {"dp_op": operating_vacuum(g)}
    sh = static_hold(g)
    m = out["models"]["static-hold"]
    sh["t_mid"] = m["t2s"] + 0.5 * m["T2"]
    out["static_hold"] = sh
    print(f"operating vacuum {out['vacuum']['dp_op']:.1f} Pa; static hold at t = {sh['t_mid']:.3f} s: T = "
          + ", ".join(f"{x:.3f}" for x in sh["T"]) + f" N (sum {sh['sum']:.3f} = m g {sh['W']:.3f}); U = "
          + ", ".join(f"{x:.3f}" for x in sh["U"]) + f"; tilt {math.degrees(math.hypot(*sh['phi'])):.2f} deg")
    (HERE / "reference.json").write_text(json.dumps(out, indent=2) + NL, encoding="utf-8", newline=NL)
    print("wrote design/reference.json")
    return 0


if __name__ == "__main__":
    sys.exit(main())
