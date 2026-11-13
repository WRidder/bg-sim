# /// script
# requires-python = ">=3.11"
# dependencies = ["numpy>=2.0", "mujoco>=3.2"]
# ///
"""MuJoCo reference for the XL330Backlash benches: the microduck_rl play hinge run in MuJoCo itself.

    uv run examples/microduck/design/backlash_bench.py [--dt S] [--write]

The bench of xl330-backlash-step / xl330-backlash-reversal built as microduck_rl builds its
backlash robots (add_backlash.py at 0daab16): one body (the 100 g test arm) on two hinges about the
same axis, the servo hinge (armature = BAM's, damping and frictionloss written by the actuator)
and `passive_servo_backlash` with the `backlash` class of add_backlash.py (range +-1 deg, armature
0.001, damping 0.01, solreflimit 0.01 1, solimplimit 0.95 0.999 0.0001 0.5 2). The actuator is
BAM's, as bam.mjlab.BamActuator and microduck_rl's BacklashEncoderBamActuator apply it each physics
step (design/xl330.py holds the same firmware law and motor equation):

* the firmware P law reads the encoder through the play (qpos[servo] + qpos[backlash]) and the
  back-EMF the servo hinge's speed;
* the M6 friction budget (prev. actuator torque, external torque = -qfrc_bias + qfrc_constraint
  minus the friction rows' own force) goes to dof_frictionloss, the viscous part to dof_damping,
  with BAM's stiff friction solref/solimp;
* the goal reaches the firmware t_latency = 20 ms late (a pure delay).

The integrator is implicitfast. `--dt` (default 0.0005 s) is the MuJoCo step; the training step is
0.005 s (run with --dt 0.005 to see what discretisation does). `--write` stores the trajectories
in design/backlash_reference.json, which design/checks.py reads (nothing reads a bg-sim run).
"""

from __future__ import annotations

import argparse
import json
import math
from pathlib import Path

import numpy as np

import build_model as bm
import xl330 as xl

HERE = Path(__file__).resolve().parent
OUT = HERE / "backlash_reference.json"

SOLREF_FRICTION = (-5.0e4, -2.0e2)  # bam.mjlab.BamActuator._STIFF_SOLREF_FRICTION
SOLIMP_FRICTION = (0.99, 0.9999, 0.001, 0.5, 2.0)


def mjcf(dt: float, vertical: bool, gap: float = xl.PLAY["gap"]) -> str:
    p = xl.PLAY
    quat = "1 0 0 0" if vertical else f"{math.cos(math.pi / 4)!r} {math.sin(math.pi / 4)!r} 0 0"
    j = bm.BENCH["J"]
    return f"""
<mujoco>
  <compiler angle="radian"/>
  <option timestep="{dt!r}" integrator="implicitfast" gravity="0 0 -{bm.G0!r}"/>
  <worldbody>
    <body name="arm" pos="0 0 0.3" quat="{quat}">
      <joint name="servo" type="hinge" axis="0 0 1" armature="{xl.BAM['armature']!r}" damping="0" frictionloss="0"
             solreffriction="{SOLREF_FRICTION[0]!r} {SOLREF_FRICTION[1]!r}"
             solimpfriction="{' '.join(repr(v) for v in SOLIMP_FRICTION)}"/>
      <joint name="passive_servo_backlash" type="hinge" axis="0 0 1" armature="{p['jb']!r}" damping="{p['c']!r}"
             frictionloss="0" limited="true" range="{-gap / 2!r} {gap / 2!r}"
             solreflimit="{p['tc']!r} {p['zeta']!r}"
             solimplimit="{p['dmin']!r} {p['dmax']!r} {p['width']!r} {p['mid']!r} {p['power']!r}"/>
      <inertial pos="0 {-bm.BENCH['l']!r} 0" mass="{bm.BENCH['m']!r}" diaginertia="{j[0]!r} {j[1]!r} {j[2]!r}"/>
    </body>
  </worldbody>
  <actuator><motor name="servo" joint="servo" gear="1"/></actuator>
</mujoco>"""


def run(goal, t_end: float, dt: float, vertical: bool, gap: float = xl.PLAY["gap"], every: float = 0.001):
    import mujoco  # only the reference run needs it; checks.py imports load_reference

    m = mujoco.MjModel.from_xml_string(mjcf(dt, vertical, gap))
    d = mujoco.MjData(m)
    js, jb = m.joint("servo").dofadr[0], m.joint("passive_servo_backlash").dofadr[0]
    out = []
    n = int(round(t_end / dt))
    k_every = max(1, int(round(every / dt)))
    for k in range(n + 1):
        t = k * dt
        q_enc = d.qpos[0] + d.qpos[1]
        w_m = d.qvel[js]
        g = goal(t - xl.LATENCY) if t >= xl.LATENCY else goal(0.0)
        duty = xl.duty(g, q_enc, w_m, xl.V_NOMINAL)
        tau_m = xl.motor_torque(duty, w_m, xl.V_NOMINAL)
        # external torque on the servo hinge without the friction rows' own force (bam.mjlab)
        fr = 0.0
        for r in range(d.nefc):
            if d.efc_type[r] == mujoco.mjtConstraint.mjCNSTR_FRICTION_DOF and d.efc_id[r] == js:
                fr += d.efc_force[r]
        tau_e = -d.qfrc_bias[js] + d.qfrc_constraint[js] - fr
        fl, fv = xl.bam_friction(d.qfrc_actuator[js], tau_e, w_m)
        m.dof_frictionloss[js] = fl
        m.dof_damping[js] = fv
        d.ctrl[0] = tau_m
        if k % k_every == 0:
            out.append((t, q_enc, d.qpos[0], d.qpos[1], w_m, d.qvel[js] + d.qvel[jb], tau_m))
        mujoco.mj_step(m, d)
    a = np.array(out)
    return {"t": a[:, 0], "q": a[:, 1], "q_gear": a[:, 2], "q_play": a[:, 3], "w_gear": a[:, 4],
            "w_horn": a[:, 5], "tau_m": a[:, 6], "invweight0": float(m.dof_invweight0[jb])}


def reversal_goal(t: float) -> float:
    p = bm.REVERSAL
    return p["amplitude"] if p["t_start"] <= t < p["t_start"] + p["duty"] * p["period"] else 0.0


CASES = {
    "xl330-backlash-reversal": (reversal_goal, bm.REVERSAL_T_END, True),
    "xl330-backlash-step": (bm.bench_goal, 1.6, False),
}


STORED = ("q", "q_play", "w_gear", "w_horn", "tau_m")  # every 1 ms, 7 significant digits


def load_reference() -> dict:
    """design/backlash_reference.json as numpy arrays (checks.py reads it)."""
    ref = json.loads(OUT.read_text(encoding="utf-8"))
    for r in ref["models"].values():
        for k in ("t",) + STORED:
            r[k] = np.array(r[k])
    return ref


def compare(run_dir: str, name: str) -> None:
    """A bg-sim run of `name` against the stored MuJoCo reference (bg-sim's play angle is gear minus
    horn, MuJoCo's play hinge horn minus gear)."""
    from readrun import read_run

    run = read_run(run_dir)
    r = load_reference()["models"][name]
    q = np.interp(r["t"], run["t"], run["J/qout"])
    play = -np.interp(r["t"], run["t"], run["Servo/Backlash/phi"])
    for label, a, b in (("encoder q", q, r["q"]), ("play", play, r["q_play"])):
        err = np.abs(a - b)
        k = int(np.argmax(err))
        print(f"{name} {label:10s} max |bgsim - MuJoCo| {err[k]:.5f} rad at {r['t'][k]:.3f} s, mean {err.mean():.5f}")
    for tt in (0.13, 0.15, 0.2, 0.3, 0.55, 0.62, 0.63, 0.65, 0.7, 0.9):
        i = int(round(tt / 0.001))
        print(f"  t {tt:5.2f}  q {q[i]:9.5f} / {r['q'][i]:9.5f}   play {play[i]:9.5f} / {r['q_play'][i]:9.5f}")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dt", type=float, default=0.0005)
    ap.add_argument("--write", action="store_true")
    ap.add_argument("--compare", nargs=2, metavar=("RUN_DIR", "MODEL"))
    args = ap.parse_args()
    if args.compare:
        compare(*args.compare)
        return 0
    store = {"dt": args.dt, "integrator": "implicitfast", "source": "design/backlash_bench.py", "models": {}}
    for name, (goal, t_end, vertical) in CASES.items():
        r = run(goal, t_end, args.dt, vertical)
        print(f"{name}: invweight0 of the play hinge {r['invweight0']:.3f} (bench_invweight {bm.bench_invweight():.3f})")
        for tt in (0.12, 0.15, 0.2, 0.3, 0.55, 0.62, 0.63, 0.64, 0.65, 0.7, 0.9):
            i = int(round(tt / 0.001))
            print(f"  t {tt:5.2f}  q {r['q'][i]:9.5f}  play(horn-gear) {r['q_play'][i]:9.5f}  w_gear {r['w_gear'][i]:8.4f}"
                  f"  w_horn {r['w_horn'][i]:8.4f}  tau_m {r['tau_m'][i]:8.4f}")
        rec = {"invweight0": r["invweight0"], "t": [round(float(v), 6) for v in r["t"]]}
        for k in STORED:
            rec[k] = [float(f"{v:.7g}") for v in r[k]]
        store["models"][name] = rec
    if args.write:
        OUT.write_text(json.dumps(store) + "\n", encoding="utf-8", newline="\n")
        print("wrote", OUT)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
