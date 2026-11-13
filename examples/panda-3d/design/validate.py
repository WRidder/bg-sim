# /// script
# requires-python = ">=3.11"
# dependencies = ["numpy>=2.0", "scipy>=1.13", "mujoco>=3.3"]
# ///
"""Independent reference for `panda-3d`: MuJoCo on an MJCF with the Gaz et al. 2019 parameters.

    uv run examples/panda-3d/design/validate.py [--free <run_dir>] [--panda <run_dir>] [--json <out>]

* writes `reference/panda_gaz.xml` (MJCF) and `reference/panda_gaz.urdf` (the same robot for
  URDF tools): franka_description kinematics, the inertials of `panda.py`, no limits, no
  damping, no armature. Pinocchio (the first choice) has no Windows wheel on PyPI (`pin` builds
  from source and fails), so the reference engine is MuJoCo (`mujoco` wheels exist for
  Windows): `qfrc_bias` at zero rate is the gravity torque, `mj_fullM` the mass matrix and
  `qacc` from `mj_forward` the forward dynamics;
* gravity torques: MuJoCo against `panda.gravity` (the
  Newton-Euler of the design, which the controller block unrolls) at the named poses and at
  1000 random poses;
* the IK round trip (`panda.ik_flange`) at 20000 random poses;
* with `--free`: the free swing of the `panda-free` run (columns.f64 + manifest.json, as written
  by `run_model.jl` or the backend) against MuJoCo's forward dynamics integrated with DOP853 (rtol 1e-12);
* with `--panda`: the closed-loop `panda` run: settled measured joint torques against the
  MuJoCo gravity torque at the reached pose, TCP tracking error along the trajectory, and the
  run's own IK flag.

The printed numbers are the README's validation table; `--json` stores them.
"""

from __future__ import annotations

import argparse
import json
import math
import sys
from pathlib import Path

import numpy as np

import design as dz
import panda as pz

ROOT = Path(__file__).resolve().parent.parent
URDF = ROOT / "reference" / "panda_gaz.urdf"
MJCF = ROOT / "reference" / "panda_gaz.xml"


def make_urdf(path: Path) -> None:
    lines = ['<?xml version="1.0"?>', '<robot name="panda_gaz2019">',
             '  <!-- written by examples/panda-3d/design/validate.py: franka_description kinematics, '
             'Gaz et al. 2019 feasible inertials (panda.py) -->',
             '  <link name="panda_link0"/>']  # fmt: skip
    for i in range(pz.NJ):
        (r, p) = pz.URDF_JOINTS[i]
        xx, xy, xz, yy, yz, zz = pz.INERTIA6[i].tolist()
        c = pz.COM[i].tolist()
        lines += [
            f'  <link name="panda_link{i + 1}">',
            "    <inertial>",
            f'      <origin xyz="{c[0]!r} {c[1]!r} {c[2]!r}" rpy="0 0 0"/>',
            f'      <mass value="{float(pz.MASS[i])!r}"/>',
            f'      <inertia ixx="{xx!r}" ixy="{xy!r}" ixz="{xz!r}" iyy="{yy!r}" iyz="{yz!r}" izz="{zz!r}"/>',
            "    </inertial>",
            "  </link>",
            f'  <joint name="panda_joint{i + 1}" type="revolute">',
            f'    <origin xyz="{p[0]!r} {p[1]!r} {p[2]!r}" rpy="{r[0]!r} {r[1]!r} {r[2]!r}"/>',
            f'    <parent link="panda_link{i}"/>',
            f'    <child link="panda_link{i + 1}"/>',
            '    <axis xyz="0 0 1"/>',
            f'    <limit lower="{float(pz.Q_MIN[i])!r}" upper="{float(pz.Q_MAX[i])!r}" effort="{float(pz.TAU_MAX[i])!r}" velocity="{float(pz.QD_MAX[i])!r}"/>',
            "  </joint>",
        ]
    lines += ['  <link name="panda_link8"/>',
              '  <joint name="panda_joint8" type="fixed">',
              f'    <origin xyz="0 0 {pz.D_FLANGE!r}" rpy="0 0 0"/>',
              '    <parent link="panda_link7"/>', '    <child link="panda_link8"/>', "  </joint>",
              "</robot>"]  # fmt: skip
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8", newline="\n")


def make_mjcf(path: Path) -> None:
    """The arm as nested MJCF bodies: body i = link frame i, its pose in body i-1 = the URDF joint
    origin, a hinge about its z, the Gaz inertial with `fullinertia` (MuJoCo diagonalises it)."""
    lines = ['<mujoco model="panda_gaz2019">',
             '  <!-- written by examples/panda-3d/design/validate.py -->',
             '  <compiler angle="radian" autolimits="false"/>',
             f'  <option gravity="0 0 {-pz.G0!r}" timestep="1e-4"/>',
             "  <worldbody>"]  # fmt: skip
    indent = "    "
    for i in range(pz.NJ):
        r, p = pz.URDF_JOINTS[i]
        q = pz.quat_of(pz.rpy(*r)).tolist()
        xx, xy, xz, yy, yz, zz = pz.INERTIA6[i].tolist()
        c = pz.COM[i].tolist()
        lines += [
            f'{indent}<body name="panda_link{i + 1}" pos="{p[0]!r} {p[1]!r} {p[2]!r}" quat="{q[0]!r} {q[1]!r} {q[2]!r} {q[3]!r}">',
            f'{indent}  <inertial pos="{c[0]!r} {c[1]!r} {c[2]!r}" mass="{float(pz.MASS[i])!r}" fullinertia="{xx!r} {yy!r} {zz!r} {xy!r} {xz!r} {yz!r}"/>',
            f'{indent}  <joint name="panda_joint{i + 1}" type="hinge" axis="0 0 1" limited="false" damping="0" armature="0"/>',
        ]
        indent += "  "
    lines += [f'{indent}<site name="flange" pos="0 0 {pz.D_FLANGE!r}"/>']
    for i in range(pz.NJ):
        indent = indent[:-2]
        lines.append(f"{indent}</body>")
    lines += ["  </worldbody>", "</mujoco>"]
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8", newline="\n")


class Reference:
    """Gravity, mass matrix and forward dynamics from MuJoCo."""

    def __init__(self, path: Path) -> None:
        import mujoco

        self.mj = mujoco
        self.model = mujoco.MjModel.from_xml_path(str(path))
        self.data = mujoco.MjData(self.model)
        assert self.model.nv == 7

    def _set(self, q, v) -> None:
        self.data.qpos[:] = q
        self.data.qvel[:] = v
        self.data.qfrc_applied[:] = 0.0
        self.data.ctrl[:] = 0.0

    def gravity(self, q) -> np.ndarray:
        self._set(q, np.zeros(7))
        self.mj.mj_forward(self.model, self.data)
        return self.data.qfrc_bias.copy()

    def mass(self, q) -> np.ndarray:
        self._set(q, np.zeros(7))
        self.mj.mj_forward(self.model, self.data)
        m = np.zeros((7, 7))
        self.mj.mj_fullM(self.model, self.data, m)  # MuJoCo >= 3.3 signature
        return m

    def qacc(self, q, v, tau) -> np.ndarray:
        self._set(q, v)
        self.data.qfrc_applied[:] = tau
        self.mj.mj_forward(self.model, self.data)
        return self.data.qacc.copy()

    def flange(self, q) -> np.ndarray:
        self._set(q, np.zeros(7))
        self.mj.mj_kinematics(self.model, self.data)
        return self.data.site("flange").xpos.copy()


def read_run(run_dir: Path) -> tuple[np.ndarray, dict[str, np.ndarray]]:
    manifest = json.loads((run_dir / "manifest.json").read_text(encoding="utf-8"))
    ids = [s["id"] for s in manifest["signals"]]
    n = int(manifest["time"]["n"])
    raw = np.fromfile(run_dir / "columns.f64", dtype="<f8").reshape(len(ids) + 1, n)
    t, cols = raw[0], {sid: raw[k + 1] for k, sid in enumerate(ids)}
    # event instants are recorded twice: keep the last sample of equal times
    keep = np.r_[np.diff(t) > 0, True]
    return t[keep], {k: v[keep] for k, v in cols.items()}


def gravity_table(ref: Reference) -> dict:
    rows = {}
    for name, q in dz.NAMED_POSES.items():
        g_ref = ref.gravity(np.asarray(q, dtype=float))
        rows[name] = {"q": list(map(float, q)), "mujoco": g_ref.tolist(),
                      "design_rnea": pz.gravity(q).tolist(),
                      "max_diff": float(np.abs(g_ref - pz.gravity(q)).max())}  # fmt: skip
    rng = np.random.default_rng(3)
    worst = 0.0
    for _ in range(1000):
        q = rng.uniform(pz.Q_MIN, pz.Q_MAX)
        worst = max(worst, float(np.abs(ref.gravity(q) - pz.gravity(q)).max()))
    worst_m = 0.0
    for _ in range(200):
        q = rng.uniform(pz.Q_MIN, pz.Q_MAX)
        worst_m = max(worst_m, float(np.abs(ref.mass(q) - pz.mass_matrix(q)).max()))
    return {"poses": rows, "random_1000_max_diff": worst, "mass_matrix_200_max_diff": worst_m}


def free_swing(ref: Reference, run_dir: Path) -> dict:
    from scipy.integrate import solve_ivp

    t, cols = read_run(run_dir)

    def rhs(_t, x):
        q, v = x[:7], x[7:]
        a = ref.qacc(q, v, np.zeros(7))
        return np.r_[v, a]

    x0 = np.r_[dz.Q_FREE, np.zeros(7)]
    sol = solve_ivp(rhs, (t[0], t[-1]), x0, method="DOP853", rtol=1e-12, atol=1e-12, t_eval=t, dense_output=False)
    q_ref = sol.y[:7]
    q_bg = np.array([cols[f"L{k}/J/qout"] for k in range(1, 8)])
    dq = np.abs(q_bg - q_ref)
    tcp = np.array([ref.flange(q_ref[:, j]) for j in range(len(t))]).T
    tcp_bg = np.array([cols[f"TCP/g[{k}]"] for k in (5, 6, 7)])
    out = {
        "t_end": float(t[-1]),
        "max_abs_dq_per_joint": dq.max(axis=1).tolist(),
        "max_abs_dq": float(dq.max()),
        "max_tcp_diff_m": float(np.linalg.norm(tcp - tcp_bg, axis=0).max()),
        "q_final_ref": q_ref[:, -1].tolist(),
        "q_final_bg": q_bg[:, -1].tolist(),
        "checkpoints": {},
    }
    for tc in dz.FREE_CHECK_TIMES:
        j = int(np.argmin(np.abs(t - tc)))
        out["checkpoints"][f"{t[j]:.3f}"] = {"ref": q_ref[:, j].tolist(), "bg": q_bg[:, j].tolist()}
    return out


def closed_loop(ref: Reference, run_dir: Path) -> dict:
    t, cols = read_run(run_dir)
    q = np.array([cols[f"Robot/L{k}/J/qout"] for k in range(1, 8)])
    tau = np.array([cols[f"Robot/TauSense{k}/y"] for k in range(1, 8)])
    out = {}
    # settled: measured torque at the end against the gravity torque of the reached pose
    g_end = ref.gravity(q[:, -1])
    out["settled_tauJ"] = tau[:, -1].tolist()
    out["gravity_at_settled_q"] = g_end.tolist()
    out["settled_tauJ_minus_gravity"] = (tau[:, -1] - g_end).tolist()
    # TCP: flange position of the measured chain against the trajectory output
    tcp = np.array([cols[f"Robot/TCP/g[{k}]"] for k in (5, 6, 7)])
    target = np.array([cols[f"Traj/p{c}"] for c in "xyz"])
    err = np.linalg.norm(tcp - target, axis=0)
    out["tcp_err_max_m"] = float(err.max())
    out["tcp_err_end_m"] = float(err[-1])
    out["tcp_err_rms_m"] = float(np.sqrt(np.mean(err**2)))
    out["ik_flag_max"] = float(np.max(cols["IK/flag"]))
    for tc in dz.WAYPOINT_TIMES:
        j = int(np.argmin(np.abs(t - tc)))
        out.setdefault("tcp_at_waypoints", {})[f"{t[j]:.3f}"] = {"tcp": tcp[:, j].tolist(), "target": target[:, j].tolist(), "err": float(err[j])}
        k = int(np.argmin(np.abs(t - (tc + dz.T_DWELL - 1e-3))))
        out.setdefault("tcp_after_dwell", {})[f"{t[k]:.3f}"] = float(err[k])
    # the in-model IK (Julia, IK/qr) against the target it was given (Traj/g) and against the
    # Python port of the same solver, at every output sample after the first tick
    qr = np.array([cols[f"IK/qr{k}"] for k in range(1, 8)])
    g = np.array([cols[f"Traj/g[{k}]"] for k in range(1, 8)])
    pos_err = rot_err = py_diff = 0.0
    for j in np.nonzero(t >= dz.TS)[0]:
        t_f = np.eye(4)
        t_f[:3, :3] = pz.rot_of_quat(g[:4, j])
        t_f[:3, 3] = g[4:, j]
        fk = pz.fk_flange(qr[:, j])
        pos_err = max(pos_err, float(np.linalg.norm(fk[:3, 3] - t_f[:3, 3])))
        rot_err = max(rot_err, float(np.abs(fk[:3, :3] - t_f[:3, :3]).max()))
        q_py, code = pz.ik_flange(t_f, dz.Q7_REF, q[:, j])
        if code == 0:
            py_diff = max(py_diff, float(np.abs(np.asarray(q_py) - qr[:, j]).max()))
    out["ik_model_fk_pos_err_m"] = pos_err
    out["ik_model_fk_rot_err"] = rot_err
    out["ik_model_vs_python_rad"] = py_diff
    return out


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--free", type=Path)
    parser.add_argument("--panda", type=Path)
    parser.add_argument("--json", type=Path)
    args = parser.parse_args(argv)
    make_urdf(URDF)
    make_mjcf(MJCF)
    ref = Reference(MJCF)
    np.set_printoptions(precision=6, suppress=True, linewidth=140)
    report: dict = {"gravity": gravity_table(ref)}
    print("gravity: design RNEA vs MuJoCo, max |diff| over 1000 random poses:",
          report["gravity"]["random_1000_max_diff"], "N m; mass matrix (200 poses):",
          report["gravity"]["mass_matrix_200_max_diff"])  # fmt: skip
    for name, row in report["gravity"]["poses"].items():
        print(f"  {name}: G = {np.array(row['mujoco'])}  (|diff| {row['max_diff']:.2e})")
    report["ik"] = pz.ik_roundtrip()
    print("IK round trip:", report["ik"])
    if args.free:
        report["free"] = free_swing(ref, args.free)
        print("free swing: max |q_bg - q_mujoco| per joint", np.array(report["free"]["max_abs_dq_per_joint"]),
              "TCP", report["free"]["max_tcp_diff_m"])  # fmt: skip
    if args.panda:
        report["panda"] = closed_loop(ref, args.panda)
        print(json.dumps(report["panda"], indent=1))
    if args.json:
        args.json.write_text(json.dumps(report, indent=1) + "\n", encoding="utf-8", newline="\n")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
