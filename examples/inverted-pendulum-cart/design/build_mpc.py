# /// script
# requires-python = ">=3.11"
# ///
"""Build the constrained-MPC models from `design/mpc.json`.

Two models are written next to the existing LQR sample:

* `inverted-pendulum-cart-mpc` — the same plant and 0.3 m step, with the `MPC` project
  block (25 ms horizon, |u| <= 20 N, |du| <= 0.2 N per 1 ms tick);
* `inverted-pendulum-cart-rate` — the existing LQR followed by a 200 N/s rate limiter,
  the fair comparison for the MPC.

The MPC block source is generated here because its QP matrices are design data.

Run it with ``uv run examples/inverted-pendulum-cart/design/build_mpc.py``.
"""

from __future__ import annotations

import copy
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
DATA = json.loads((HERE / "mpc.json").read_text(encoding="utf-8"))
BASE = json.loads((ROOT / "models" / "inverted-pendulum-cart.bgmodel.json").read_text(encoding="utf-8"))


def mat_literal(rows: list[list[float]]) -> str:
    return "[" + "; ".join(" ".join(f"{value:.15g}" for value in row) for row in rows) + "]"


def vec_literal(values: list[float]) -> str:
    return "[" + ", ".join(f"{value:.15g}" for value in values) + "]"


def write_block() -> Path:
    matrices = DATA["matrices"]
    mpc = DATA["mpc"]
    zeros = vec_literal([0.0] * mpc["N"])
    columns = [[row[j] for row in matrices["F"]] for j in range(4)]
    source = f"""@block MPC begin
    # Constrained model-predictive controller for the cart-pole (design/mpc.py).
    #
    # The prediction is the discrete linearisation at upright, condensed over N samples:
    #   H = Gamma' Qbar Gamma + Rbar,  F = Gamma' Qbar Phi,  U = u_prev*1 + L*dU.
    # The decision variable is dU; the box constraints |dU| <= du_max are solved by ADMM,
    # with a warm start from the previous tick.  The actuator force is then clamped to
    # +-u_max.  Hinv, F1..F4 and c_prev are the scaled QP matrices written by the design
    # script (a single scale factor keeps the ADMM step well conditioned).  F is split into
    # its four columns so that each product has the unit of force and the sum is legal.
    @constants begin
        N::Int = {mpc["N"]}
        iterations::Int = {mpc["iterations"]}
    end
    @inputs begin
        x::Real, [unit = "m"]
        v::Real, [unit = "m/s"]
        theta::Real, [unit = "rad"]
        w::Real, [unit = "rad/s"]
        x_ref::Real, [unit = "m"]
    end
    @outputs u::Real = 0.0, [unit = "N"]
    @parameters begin
        Hinv::Mat{{N,N}} = {mat_literal(matrices["Hinv"])}, [description = "Inverse of Hd + rho*I, scaled by the design script"]
        F1::Vec{{N}} = {vec_literal(columns[0])}, [unit = "N/m", description = "Condensed linear term on the position error"]
        F2::Vec{{N}} = {vec_literal(columns[1])}, [unit = "N*s/m", description = "Condensed linear term on the cart speed"]
        F3::Vec{{N}} = {vec_literal(columns[2])}, [unit = "N/rad", description = "Condensed linear term on the pendulum angle"]
        F4::Vec{{N}} = {vec_literal(columns[3])}, [unit = "N*s/rad", description = "Condensed linear term on the pendulum rate"]
        c_prev::Vec{{N}} = {vec_literal(matrices["c_prev"])}, [unit = "1", description = "The condensed linear term on the previous force, scaled"]
        rho::Real = {mpc["rho"]:.15g}, [min = 1.0e-9, description = "ADMM penalty"]
        du_max::Real = {mpc["du_max"]}, [unit = "N", min = 0, description = "Force increment per sample"]
        u_max::Real = {mpc["u_max"]}, [unit = "N", min = 0, description = "Force limit"]
    end
    @variables begin
        z::Vec{{N}} = {zeros}, [unit = "N", description = "Force increments, the constrained ADMM variable"]
        y::Vec{{N}} = {zeros}, [unit = "N", description = "ADMM dual variable"]
        u_prev::Real = 0.0, [unit = "N", description = "Force applied on the previous tick"]
    end
    @discrete Ts = 1e-3 begin
        fd = F1 * (x - x_ref) + F2 * v + F3 * theta + F4 * w + c_prev * u_prev
        for it in 1:iterations
            Uc = Hinv * (rho * (z - y) - fd)
            for k in 1:N
                z[k] = clamp(Uc[k] + y[k], -du_max, du_max)
            end
            y = y + Uc - z
        end
        u = clamp(u_prev + z[1], -u_max, u_max)
        u_prev = u
    end
end
"""
    path = ROOT / "library" / "MPC.jl"
    path.write_text(source, encoding="utf-8", newline="\n")
    return path


def mpc_model() -> dict:
    doc = copy.deepcopy(BASE)
    doc["name"] = "inverted-pendulum-cart-mpc"
    doc["$comment"] = (
        "Constrained MPC on the same bond-graph cart-pole: 25 ms horizon, force |u| <= 20 N "
        "and slew |du| <= 0.2 N per 1 ms tick. The 0.3 m step at 1.5 s is outside the "
        "unconstrained LQR's 20 N authority (it asks for about 26.8 N); the MPC solves the "
        "box-constrained QP online by ADMM (library/MPC.jl). The plant is unchanged from "
        "inverted-pendulum-cart."
    )
    for node in doc["diagram"]["nodes"]:
        if node["name"] == "XRef":
            node["params"]["final"] = str(DATA["plant"]["x_step"])
        if node["name"] == "LQR1":
            node["name"] = "MPC1"
            node["block"] = {"ref": "project:MPC"}
            node["params"] = {"du_max": str(DATA["mpc"]["du_max"]), "u_max": str(DATA["mpc"]["u_max"])}
    doc["settings"]["t_end"] = DATA["plant"]["t_end"]
    doc["settings"]["output"]["points"] = 5001
    doc["settings"]["event_limit"] = 10000
    doc["plots"] = [
        {"id": "p1", "title": "Pendulum angle", "signals": ["ThetaInt/y"]},
        {"id": "p2", "title": "Cart position", "signals": ["XInt/y", "XRef/y"]},
        {"id": "p3", "title": "Applied force", "signals": ["MSe1/p.e"]},
        {"id": "p4", "title": "MPC force", "signals": ["MPC1/u"]},
    ]
    return doc


def rate_model() -> dict:
    doc = copy.deepcopy(BASE)
    doc["name"] = "inverted-pendulum-cart-rate"
    doc["$comment"] = (
        "The existing LQR with the actuator's 200 N/s slew limit in the 1 ms firmware, on "
        "the same 0.3 m step as the MPC model. It is the fair comparison: the LQR only sees "
        "the current error, while the MPC plans the force increment over its 20 ms horizon."
    )
    for node in doc["diagram"]["nodes"]:
        if node["name"] == "XRef":
            node["params"]["final"] = str(DATA["plant"]["x_step"])
        if node["name"] == "LQR1":
            node["name"] = "RateLimitedLQR1"
            node["block"] = {"ref": "project:RateLimitedLQR"}
            node["params"] = {
                "K_x": "-89.442719", "K_v": "-54.686555",
                "K_theta": "-175.121631", "K_omega": "-39.152990",
                "u_max": str(DATA["mpc"]["u_max"]), "du_max": str(DATA["mpc"]["du_max"]),
            }
    doc["settings"]["t_end"] = DATA["plant"]["t_end"]
    doc["settings"]["output"]["points"] = 5001
    doc["settings"]["event_limit"] = 10000
    doc["plots"] = [
        {"id": "p1", "title": "Pendulum angle", "signals": ["ThetaInt/y"]},
        {"id": "p2", "title": "Cart position", "signals": ["XInt/y", "XRef/y"]},
        {"id": "p3", "title": "Applied force", "signals": ["MSe1/p.e"]},
        {"id": "p4", "title": "Rate-limited LQR force", "signals": ["RateLimitedLQR1/u"]},
    ]
    return doc


def main() -> None:
    block = write_block()
    print(f"wrote {block}")
    for name, document in (("inverted-pendulum-cart-mpc", mpc_model()),
                           ("inverted-pendulum-cart-rate", rate_model())):
        path = ROOT / "models" / f"{name}.bgmodel.json"
        path.write_text(json.dumps(document, indent=2) + "\n", encoding="utf-8", newline="\n")
        print(f"wrote {path}")
    project_path = ROOT / "bgsim.project.json"
    project = json.loads(project_path.read_text(encoding="utf-8"))
    for name in ("inverted-pendulum-cart-mpc", "inverted-pendulum-cart-rate"):
        if name not in project["models"]:
            project["models"].append(name)
    project_path.write_text(json.dumps(project, indent=2) + "\n", encoding="utf-8", newline="\n")
    print(f"updated {project_path}")


if __name__ == "__main__":
    main()
