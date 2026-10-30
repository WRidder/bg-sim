# /// script
# requires-python = ">=3.10,<3.13"
# dependencies = ["numpy<2", "roboticstoolbox-python"]
# ///
"""Reference data for the Planar Links example.

Evaluates the user's closed-form planar robots (``planar_robot.py``, copied unchanged next
to this script) and Peter Corke's Robotics Toolbox (``DHRobot.rne_python``) on the
trajectories of the original ``main()`` (1-link ``quintic(0, 1)``, 2/3-link ``jtraj`` from
zeros to ones, 1 s), sampled at 1 kHz, and writes one CSV per arm to ``../data``.

Convention. The columns are the joint angles, rates and accelerations *after*
``transform_joint_data`` (q -> -q, joint 1 offset -pi/2), i.e. exactly the arguments the
analytical ``tau(q, qd, qdd)`` and ``rne_python`` receive. That is also the bond-graph
model's convention: a counter-clockwise angle from +x in the x-y plane, gravity along -y,
joint 1 hanging down (-pi/2) at t = 0. Torques are joint-side torques including the
reflected motor terms G^2 Jm qdd + B G^2 qd.

Run: ``uv run reference/generate.py`` (pinned to Python < 3.13 for roboticstoolbox-python).
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import planar_robot as pr  # noqa: E402  (the user's script, unchanged)

DATA = HERE.parent / "data"
N = 1001  # 1 kHz over 1 s


def build():
    from roboticstoolbox import DHLink, DHRobot

    def link(a, m, r, izz, b, g, jm):
        return DHLink(d=0, a=a, alpha=0, m=m, r=np.array([r, 0, 0]),
                      I=np.array([[0, 0, 0], [0, 0, 0], [0, 0, izz]]), B=b, G=g, Jm=jm)

    l1 = link(0.675, 3.815, -0.291, 0.310, 0.02, 12, 0.000492)
    l2 = link(0.525, 3.690, -0.182, 0.146, 0.02, 9.33, 0.0004845)
    l3 = link(0.370, 4.0, -0.360, 0.016, 0.01, 9.25, 0.0001859)
    l4 = DHLink(a=0.1, m=1.0, r=np.array([0, 0, 0]), I=np.zeros((3, 3)))
    g = 9.81
    r1, r2, r3, r4 = DHRobot([l1]), DHRobot([l1, l2]), DHRobot([l1, l2, l3]), DHRobot([l1, l2, l3, l4])
    for r in (r2, r3, r4):
        r.gravity = [0, -g, 0]
    pay = dict(pay_m=1, pay_I=0, pay_r=[0.1, 0])
    a1 = pr.OneLinkRobot(link1=l1, gravity=0, **pay)
    a2 = pr.TwoLinkRobot(link1=l1, link2=l2, gravity=g, **pay)
    a3 = pr.ThreeLinkRobot(link1=l1, link2=l2, link3=l3, pay_m=0, pay_I=0, pay_r=[0, 0], gravity=g)
    a3p = pr.ThreeLinkRobot(link1=l1, link2=l2, link3=l3, gravity=g, **pay)
    return (r1, r2, r3, r4), (a1, a2, a3, a3p)


def write(name, t, q, qd, qdd, tau_a, tau_r):
    n = q.shape[1]
    head = ["t [s]"]
    cols = [t]
    for tag, arr, unit in (("q", q, "rad"), ("qd", qd, "rad/s"), ("qdd", qdd, "rad/s^2"),
                           ("tau_analytical", tau_a, "N*m"), ("tau_rtb", tau_r, "N*m")):
        for j in range(n):
            head.append(f"{tag}{j + 1} [{unit}]")
            cols.append(arr[:, j])
    data = np.column_stack(cols)
    DATA.mkdir(exist_ok=True)
    with open(DATA / f"{name}.csv", "w", newline="\n") as f:
        f.write(",".join(head) + "\n")
        for row in data:
            f.write(",".join(repr(float(x)) for x in row) + "\n")


def main():
    from roboticstoolbox import jtraj, quintic

    (r1, r2, r3, r4), (a1, a2, a3, a3p) = build()
    t = np.linspace(0, 1, N)
    report = {}

    tg = quintic(0, 1, t)
    q, qd, qdd = pr.transform_joint_data(tg.q, tg.qd, tg.qdd)
    # transform_joint_data adds the -pi/2 offset to element 0 only for a 1-D array (a quirk of
    # the original script: q[0] += offset), i.e. to the first *sample* of the 1-link
    # trajectory. The intended convention is the offset on the whole joint-1 trajectory, as in
    # the 2D case; the torque does not depend on it (the 1-link robot has no gravity).
    tau_user = np.asarray(a1.tau(q, qd, qdd))
    q = -np.asarray(tg.q) - np.pi / 2
    tau_a = np.asarray(a1.tau(q, qd, qdd)).reshape(-1, 1)
    assert np.allclose(tau_a[:, 0], tau_user)
    q, qd, qdd = (np.asarray(x).reshape(-1, 1) for x in (q, qd, qdd))
    tau_r = np.asarray(r1.rne_python(q, qd, qdd)).reshape(-1, 1)
    write("arm1", t, q, qd, qdd, tau_a, tau_r)
    report["1-link"] = np.abs(tau_a - tau_r).max(axis=0)

    for name, ana, rtb, n, ndof in (("arm2", a2, r2, 2, 2), ("arm3", a3, r3, 3, 3)):
        tg = jtraj([0] * n, [1] * n, t)
        q, qd, qdd = pr.transform_joint_data(tg.q, tg.qd, tg.qdd)
        tau_a = np.asarray(ana.tau(q, qd, qdd))[:, :n]
        tau_r = np.asarray(rtb.rne_python(q, qd, qdd))[:, :n]
        write(name, t, q, qd, qdd, tau_a, tau_r)
        report[name] = np.abs(tau_a - tau_r).max(axis=0)

    # 3-link + 1 kg payload: analytical class vs the 4-link RTB robot (dummy 4th DoF held at 0)
    tg = jtraj([0, 0, 0], [1, 1, 1], t)
    q, qd, qdd = pr.transform_joint_data(tg.q, tg.qd, tg.qdd)
    tau_a = np.asarray(a3p.tau(q, qd, qdd))[:, :3]
    tg4 = jtraj([0, 0, 0, 0], [1, 1, 1, 0], t)
    q4, qd4, qdd4 = pr.transform_joint_data(tg4.q, tg4.qd, tg4.qdd)
    tau_r = np.asarray(r4.rne_python(q4, qd4, qdd4))[:, :3]
    write("arm3p", t, q, qd, qdd, tau_a, tau_r)
    report["3-link+payload"] = np.abs(tau_a - tau_r).max(axis=0)

    for k, v in report.items():
        print(f"max |analytical - RTB| {k}: " + ", ".join(f"{x:.3e} N*m" for x in v))
    print(f"wrote {DATA}")


if __name__ == "__main__":
    main()
