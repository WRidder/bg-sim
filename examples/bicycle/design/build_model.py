# /// script
# requires-python = ">=3.11"
# dependencies = ["numpy>=2.0", "scipy>=1.13"]
# ///
"""Writes the models of the `bicycle` example (``models/*.bgmodel.json``).

    uv run examples/bicycle/design/design.py        # first: design.json
    uv run examples/bicycle/design/build_model.py   # then: the models

The benchmark bicycle of Meijaard, Papadopoulos, Ruina and Schwab (Proc. R. Soc. A, 2007), in
two forms:

* ``whipple`` and ``balance``: the full nonlinear bicycle as a 3D multibond bond graph. Four
  ``RigidBody3D`` bodies (rear frame with rider, fork with handlebar, two wheels), three
  ``Revolute3D`` joints (rear hub, steer axis, front hub) and two knife-edge ``RollingDisk``
  contacts on a ``ContactSurface``. The rear frame is the floating base (``PoseIntegrator3D``);
  the other bodies compose their poses through the joints (``ComposePose3D``).
* ``linear`` and ``balance-linear``: the paper's linearised equations
  ``M q'' + v C1 q' + (g K0 + v^2 K2) q = f`` as a signal diagram (integrators, gains, sums),
  the gains being expressions of the global forward speed ``v``.

World frame: x forward, y to the LEFT, z UP. The paper's frame (x forward, y right, z down) is
the world frame turned by pi about x, a proper rotation, so the paper's lean and steer angles
keep their signs (lean and steer to the right positive) and the paper's yaw is minus the world
yaw. All coordinates below are world coordinates.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
import benchmark as b  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
MODELS = ROOT / "models"
P = b.PARAMS
DESIGN = json.loads((Path(__file__).resolve().parent / "design.json").read_text(encoding="utf-8"))
CT = DESIGN["contact"]
LAM = P["lam"]

# Rolling radius of the compliant tyres: the contact radius is the wheel radius plus the static
# deflection, so the loaded wheel centre sits at the paper's height rR (rF) above the ground.
RHO_R = P["rR"] + CT["delta_rear"]
RHO_F = P["rF"] + CT["delta_front"]

# The stiff held directions of the three compliant joints (kr = kt = 1e6) get the damping of
# the gyrover example; it removes the kHz ringing of the joint springs and dissipates far below
# a millijoule in these runs.
JOINT_DAMP = {"br": 20.0, "bt": 500.0}
SOLVER = "Rodas5P"


# ------------------------------------------------------------------ small helpers
def num(x) -> str:
    return repr(float(x))


def vec(v) -> str:
    return "[" + ", ".join(num(x) for x in v) + "]"


def Rx(a):
    c, s = np.cos(a), np.sin(a)
    return np.array([[1, 0, 0], [0, c, -s], [0, s, c]])


def quat(R):
    """(w, x, y, z) of a rotation matrix, w >= 0."""
    t = np.trace(R)
    if t > 0:
        s = 0.5 / np.sqrt(t + 1.0)
        q = np.array([0.25 / s, (R[2, 1] - R[1, 2]) * s, (R[0, 2] - R[2, 0]) * s, (R[1, 0] - R[0, 1]) * s])
    else:
        i = int(np.argmax(np.diag(R)))
        j, k = (i + 1) % 3, (i + 2) % 3
        s = 2.0 * np.sqrt(1.0 + R[i, i] - R[j, j] - R[k, k])
        q = np.zeros(4)
        q[0] = (R[k, j] - R[j, k]) / s
        q[1 + i] = 0.25 * s
        q[1 + j] = (R[j, i] + R[i, j]) / s
        q[1 + k] = (R[k, i] + R[i, k]) / s
    q /= np.linalg.norm(q)
    return q if q[0] >= 0 else -q


def T(R, p):
    M = np.eye(4)
    M[:3, :3], M[:3, 3] = R, p
    return M


def inv(M):
    R, p = M[:3, :3], M[:3, 3]
    return T(R.T, -R.T @ p)


def pose_params(M) -> dict:
    q = quat(M[:3, :3])
    p = M[:3, 3]
    return {"qw": num(q[0]), "qx": num(q[1]), "qy": num(q[2]), "qz": num(q[3]),
            "x": num(p[0]), "y": num(p[1]), "z": num(p[2])}


def principal(I):
    """Principal moments and a rotation (columns = principal axes) closest to the world axes."""
    w, V = np.linalg.eigh(I)
    order = [int(np.argmax(np.abs(V[k, :]))) for k in range(3)]
    assert sorted(order) == [0, 1, 2]
    V, w = V[:, order], w[order]
    for k in range(3):
        if V[k, k] < 0:
            V[:, k] = -V[:, k]
    assert np.linalg.det(V) > 0
    return w, V


# ------------------------------------------------------------------ geometry (world, upright)
S = np.diag([1.0, -1.0, -1.0])            # paper frame -> world frame (pi about x)


def inertia_world(xx, yy, zz, xz):
    return S @ np.array([[xx, 0, xz], [0, yy, 0], [xz, 0, zz]]) @ S


def geometry() -> dict:
    """World frames of the bodies and joints with the bicycle upright, straight, steer zero."""
    w, c = P["w"], P["c"]
    JB, RB = principal(inertia_world(P["IBxx"], P["IByy"], P["IBzz"], P["IBxz"]))
    JH, RH = principal(inertia_world(P["IHxx"], P["IHyy"], P["IHzz"], P["IHxz"]))
    axle = Rx(-np.pi / 2)                  # x forward, y down, z = axle to the left
    zs = np.array([np.sin(LAM), 0.0, -np.cos(LAM)])          # down the steer axis (paper's l)
    xs = np.array([np.cos(LAM), 0.0, np.sin(LAM)])
    RS = np.column_stack([xs, np.cross(zs, xs), zs])
    s0 = np.array([w + c, 0.0, 0.0])                          # steer axis meets the ground
    hubF = np.array([w, 0.0, P["rF"]])
    foot = s0 + ((hubF - s0) @ zs) * zs                       # axis point nearest the front hub
    g = {
        "B": T(RB, [P["xB"], 0.0, -P["zB"]]), "JB": JB,
        "H": T(RH, [P["xH"], 0.0, -P["zH"]]), "JH": JH,
        "JR": T(axle, [0.0, 0.0, P["rR"]]),
        "JS": T(RS, foot),
        "JF": T(axle, hubF),
        "Ref": T(np.eye(3), [0.0, 0.0, P["rR"]]),
        "fork_offset": float(np.linalg.norm(np.cross(hubF - s0, zs))),
    }
    g["R"] = g["JR"]                       # wheel body frames = joint child frames at q = 0
    g["F"] = g["JF"]
    return g


GEO = geometry()
KR = KT = 1.0e6                            # Revolute3D default stiffness of the held directions


def joint_chart(dth, dl):
    """The Revolute3D chart at q = 0: H = (Rg, Rg dl), Rg the rotation of the quaternion (1, dth/2)."""
    q = np.array([1.0, 0.5 * dth[0], 0.5 * dth[1], 0.0])
    q /= np.linalg.norm(q)
    w, x, y, z = q
    Rg = np.array([[1 - 2 * (y * y + z * z), 2 * (x * y - w * z), 2 * (x * z + w * y)],
                   [2 * (x * y + w * z), 1 - 2 * (x * x + z * z), 2 * (y * z - w * x)],
                   [2 * (x * z - w * y), 2 * (y * z + w * x), 1 - 2 * (x * x + y * y)]])
    return T(Rg, Rg @ np.asarray(dl, float))


def preload() -> dict:
    """Static deflections of the three compliant joints and the matching start frames.

    In steady upright rolling the joints carry the static loads: each hub the tyre's normal force
    less the wheel's weight, the steer joint the front normal force less the weight of fork and
    front wheel, plus the moment of these forces about the joint origin. A compliant joint
    deflects by load / stiffness (child frame; the sign was confirmed against a settled run).
    Starting the joints undeflected makes the bicycle drop by half a millimetre and ring for
    0.2 s; with these deflections and the rear frame lowered and pitched so that both wheel
    centres sit at the paper's heights, the run starts in equilibrium."""
    g0 = P["g"]
    NR, NF = CT["N_rear"], CT["N_front"]
    ez = np.array([0.0, 0, 1.0])
    dl_R = np.array([0.0, -(NR - P["mR"] * g0) / KT, 0.0])        # child y = down
    dl_F = np.array([0.0, -(NF - P["mF"] * g0) / KT, 0.0])
    O = GEO["JS"][:3, 3]
    RS = GEO["JS"][:3, :3]
    F = (NF - (P["mF"] + P["mH"]) * g0) * ez
    M = (np.cross(np.array([P["w"], 0, 0]) - O, NF * ez) + np.cross(GEO["H"][:3, 3] - O, -P["mH"] * g0 * ez)
         + np.cross(GEO["JF"][:3, 3] - O, -P["mF"] * g0 * ez))
    dl_S = RS.T @ F / KT
    dth_S = (RS.T @ M)[:2] / KR
    HR, HS, HF = joint_chart([0, 0], dl_R), joint_chart(dth_S, dl_S), joint_chart([0, 0], dl_F)

    def frames(dz, th):
        C = T(np.array([[np.cos(th), 0, np.sin(th)], [0, 1, 0], [-np.sin(th), 0, np.cos(th)]]), [0, 0, dz])
        B = C @ GEO["B"]
        Rw = C @ GEO["JR"] @ HR
        H = C @ GEO["JS"] @ HS @ inv(GEO["JS"]) @ GEO["H"]
        Fw = H @ inv(GEO["H"]) @ GEO["JF"] @ HF
        return B, H, Rw, Fw

    x = np.zeros(2)
    for _ in range(20):                    # Newton on (dz, pitch): wheel centres at rR, rF
        def res(x):
            _, _, Rw, Fw = frames(*x)
            return np.array([Rw[2, 3] - P["rR"], Fw[2, 3] - P["rF"]])
        r0 = res(x)
        Jm = np.column_stack([(res(x + e) - r0) / 1e-7 for e in (np.array([1e-7, 0]), np.array([0, 1e-7]))])
        x = x - np.linalg.solve(Jm, r0)
    B, H, Rw, Fw = frames(*x)
    return {"B": B, "H": H, "R": Rw, "F": Fw, "dl_R": dl_R, "dl_S": dl_S, "dth_S": dth_S, "dl_F": dl_F,
            "dz": x[0], "pitch": x[1]}


PRE = preload()
BODIES = {
    # name: (start frame, principal moments in the body frame, mass, rolling radius of a wheel)
    "RearFrame": (PRE["B"], GEO["JB"], P["mB"], None),
    "Fork": (PRE["H"], GEO["JH"], P["mH"], None),
    "RearWheel": (PRE["R"], np.array([P["IRxx"], P["IRxx"], P["IRyy"]]), P["mR"], RHO_R),
    "FrontWheel": (PRE["F"], np.array([P["IFxx"], P["IFxx"], P["IFyy"]]), P["mF"], RHO_F),
}


def momentum_start(name) -> str:
    """Body momentum [J w_b; m v_b] of the upright bicycle rolling at speed `v` with lean rate
    `phid0` about the ground line through both contacts (steer rate zero): every body turns at
    (phid0, 0, 0) and moves at (v, 0, 0) + w x p; the wheels also spin at v / rolling radius.
    This is the paper's figure 4 start; it satisfies the rolling constraints of both wheels.
    The momentum is linear in (v, phid0), so the start is an expression of the two globals."""
    M, J, m, rho = BODIES[name]
    R, p = M[:3, :3], M[:3, 3]
    ex, ey = np.array([1.0, 0, 0]), np.array([0, 1.0, 0])
    w_v = ey / rho if rho else np.zeros(3)              # per unit v
    w_p = ex                                            # per unit phid0
    v_v, v_p = ex, np.cross(ex, p)
    Pv = np.concatenate([J * (R.T @ w_v), m * (R.T @ v_v)])
    Pp = np.concatenate([J * (R.T @ w_p), m * (R.T @ v_p)])
    terms = []
    for a, bb in zip(Pv, Pp):
        parts = []
        if abs(a) > 1e-13:
            parts.append(f"{float(a)!r}*v")
        if abs(bb) > 1e-13:
            parts.append(f"{float(bb)!r}*phid0")
        terms.append(" + ".join(parts).replace("+ -", "- ") if parts else "0.0")
    return "[" + ", ".join(terms) + "]"


# ------------------------------------------------------------------ diagram builder
class Diagram:
    def __init__(self):
        self.nodes, self.conns = [], []
        self._ids = {}

    def node(self, name, ref, x, y, params=None, starts=None, constants=None):
        nid = f"n{len(self.nodes) + 1:02d}"
        self._ids[name] = nid
        self.nodes.append({
            "id": nid, "name": name, "block": {"ref": ref}, "position": {"x": int(x), "y": int(y)},
            "rotation": 0, "flipX": False, "params": params or {}, "constants": constants or {},
            "starts": starts or {}, "ui": {"showLabel": True, "color": None},
        })

    def _c(self, kind, a, pa, b_, pb):
        # node names are resolved to ids in doc(), so a wire may name a node added later
        self.conns.append({"id": f"c{len(self.conns) + 1:03d}", "kind": kind,
                           "from": {"node": a, "port": pa}, "to": {"node": b_, "port": pb},
                           "label": None})

    def bond(self, a, pa, b_, pb):
        self._c("bond", a, pa, b_, pb)

    def sig(self, a, pa, b_, pb):
        self._c("signal", a, pa, b_, pb)

    def doc(self):
        conns = [{**c, "from": {**c["from"], "node": self._ids[c["from"]["node"]]},
                  "to": {**c["to"], "node": self._ids[c["to"]["node"]]}} for c in self.conns]
        return {"nodes": self.nodes, "connections": conns, "subsystemPorts": [], "annotations": []}

    def add(self, name, sources, x, y):
        """`name` = the sum of 2 to 4 scalar signals (a Mux feeding a Sum, the stdlib way to
        add signals); returns the (node, port) of the result."""
        n = len(sources)
        assert 2 <= n <= 4
        self.node(name + "Mux", f"stdlib:continuous/Mux{n}", x, y)
        self.node(name, "stdlib:continuous/Sum", x + 120, y, constants={"N": str(n)},
                  params={"signs": vec([1.0] * n)})
        for k, src in enumerate(sources):
            self.sig(*src, name + "Mux", f"u{k + 1}")
        self.sig(name + "Mux", "y", name, "u")
        return (name, "y")


def settings(t_end, points, reltol=1e-7, abstol=1e-9, solver=SOLVER):
    return {"t_start": 0.0, "t_end": float(t_end), "solver": solver, "reltol": reltol, "abstol": abstol,
            "max_step": None, "output": {"mode": "points", "points": int(points)}, "event_limit": 10000}


def globals_(v, phid0):
    return [
        {"name": "v", "value": num(v), "unit": "m/s",
         "description": "Forward speed at the start (the paper's v). Self-stable between the weave speed 4.29 m/s "
                        "and the capsize speed 6.02 m/s"},
        {"name": "phid0", "value": num(phid0), "unit": "rad/s",
         "description": "Lean rate at the start (a sideways push; the paper's figure 4 uses 0.5 rad/s)"},
    ]


# ------------------------------------------------------------------ 3D bond graph
def mech3d(D: Diagram, steer_input=None):
    """The bicycle's bodies, joints, contacts, sensing and energy book. `steer_input` is the
    (node, port) of a steer torque signal, or None for a free steer."""
    g = GEO
    jd = {k: num(v) for k, v in JOINT_DAMP.items()}

    def body(name, x, y):
        M, J, m, _ = BODIES[name]
        D.node(name, "stdlib:spatial/RigidBody3D", x, y,
               params={"m": num(m), "J": vec(J), "g0": num(P["g"])}, starts={"inertia/P": momentum_start(name)})

    # rear frame (floating base)
    body("RearFrame", 600, 400)
    qB = quat(PRE["B"][:3, :3])
    pB = PRE["B"][:3, 3]
    D.node("PoseB", "stdlib:multibond/PoseIntegrator3D", 600, 560,
           starts={"qw": num(qB[0]), "qx": num(qB[1]), "qy": num(qB[2]), "qz": num(qB[3]),
                   "px": num(pB[0]), "py": num(pB[1]), "pz": num(pB[2])})
    D.sig("RearFrame", "V", "PoseB", "tw")
    D.sig("PoseB", "g", "RearFrame", "g")
    D.node("Ground", "stdlib:contact/ContactSurface", 100, 700)
    # rear hub and rear wheel
    D.node("MountR", "stdlib:multibond/FixedTransform3DNeutral", 380, 400, params=pose_params(inv(g["JR"]) @ g["B"]))
    D.node("RearHub", "stdlib:spatial/Revolute3D", 380, 240, params={"q0": "0.0", **jd},
           starts={"dl": vec(PRE["dl_R"])})
    D.node("LinkRW", "stdlib:multibond/FixedTransform3DNeutral", 380, 100)
    body("RearWheel", 160, 100)
    D.node("FreeR", "stdlib:bondgraph/Se", 560, 240, params={"e": "0.0"})
    D.bond("RearFrame", "p", "MountR", "b")
    D.bond("MountR", "a", "RearHub", "parent")
    D.bond("RearHub", "child", "LinkRW", "a")
    D.bond("LinkRW", "b", "RearWheel", "p")
    D.bond("FreeR", "p", "RearHub", "drive")
    D.node("LocalJR", "stdlib:spatial/LocalPose3D", 380, 560, params=pose_params(inv(g["B"]) @ g["JR"]))
    D.node("PoseJR", "stdlib:multibond/ComposePose3D", 380, 700)
    D.node("PoseR", "stdlib:multibond/ComposePose3D", 160, 560)
    D.sig("PoseB", "g", "PoseJR", "gp")
    D.sig("LocalJR", "g", "PoseJR", "gl")
    D.sig("PoseJR", "g", "PoseR", "gp")
    D.sig("RearHub", "pose", "PoseR", "gl")
    D.sig("PoseR", "g", "RearWheel", "g")
    D.node("TyreR", "stdlib:contact/RollingDisk", 160, 260,
           params={"radius": num(RHO_R), "k": num(CT["k"]), "xref": num(CT["xref"]), "c": num(CT["c"]),
                   "mu": num(CT["mu"]), "vs": num(CT["vs"])})
    D.bond("RearWheel", "p", "TyreR", "p")
    D.sig("PoseR", "g", "TyreR", "g")
    D.sig("Ground", "o", "TyreR", "o")
    D.sig("Ground", "fr", "TyreR", "fr")
    # steer axis and fork
    D.node("MountS", "stdlib:multibond/FixedTransform3DNeutral", 820, 400, params=pose_params(inv(g["JS"]) @ g["B"]))
    D.node("Steer", "stdlib:spatial/Revolute3D", 820, 240, params={"q0": "0.0", **jd},
           starts={"dl": vec(PRE["dl_S"]), "dth": vec(PRE["dth_S"])})
    D.node("LinkH", "stdlib:multibond/FixedTransform3DNeutral", 1040, 240, params=pose_params(inv(g["JS"]) @ g["H"]))
    body("Fork", 1040, 400)
    D.bond("RearFrame", "p", "MountS", "b")
    D.bond("MountS", "a", "Steer", "parent")
    D.bond("Steer", "child", "LinkH", "a")
    D.bond("LinkH", "b", "Fork", "p")
    if steer_input is None:
        D.node("FreeS", "stdlib:bondgraph/Se", 820, 80, params={"e": "0.0"})
        D.bond("FreeS", "p", "Steer", "drive")
    else:
        D.node("SteerMotor", "stdlib:bondgraph/MSe", 820, 80)
        D.bond("SteerMotor", "p", "Steer", "drive")
        D.sig(*steer_input, "SteerMotor", "u")
    D.node("LocalJS", "stdlib:spatial/LocalPose3D", 820, 560, params=pose_params(inv(g["B"]) @ g["JS"]))
    D.node("PoseJS", "stdlib:multibond/ComposePose3D", 820, 700)
    D.node("PoseJSc", "stdlib:multibond/ComposePose3D", 1040, 700)
    D.node("LocalH", "stdlib:spatial/LocalPose3D", 1040, 560, params=pose_params(inv(g["JS"]) @ g["H"]))
    D.node("PoseH", "stdlib:multibond/ComposePose3D", 1260, 700)
    D.sig("PoseB", "g", "PoseJS", "gp")
    D.sig("LocalJS", "g", "PoseJS", "gl")
    D.sig("PoseJS", "g", "PoseJSc", "gp")
    D.sig("Steer", "pose", "PoseJSc", "gl")
    D.sig("PoseJSc", "g", "PoseH", "gp")
    D.sig("LocalH", "g", "PoseH", "gl")
    D.sig("PoseH", "g", "Fork", "g")
    # front hub and front wheel
    D.node("MountF", "stdlib:multibond/FixedTransform3DNeutral", 1260, 400, params=pose_params(inv(g["JF"]) @ g["H"]))
    D.node("FrontHub", "stdlib:spatial/Revolute3D", 1260, 240, params={"q0": "0.0", **jd},
           starts={"dl": vec(PRE["dl_F"])})
    D.node("LinkFW", "stdlib:multibond/FixedTransform3DNeutral", 1480, 240)
    body("FrontWheel", 1480, 100)
    D.node("FreeF", "stdlib:bondgraph/Se", 1260, 80, params={"e": "0.0"})
    D.bond("Fork", "p", "MountF", "b")
    D.bond("MountF", "a", "FrontHub", "parent")
    D.bond("FrontHub", "child", "LinkFW", "a")
    D.bond("LinkFW", "b", "FrontWheel", "p")
    D.bond("FreeF", "p", "FrontHub", "drive")
    D.node("LocalJF", "stdlib:spatial/LocalPose3D", 1260, 560, params=pose_params(inv(g["H"]) @ g["JF"]))
    D.node("PoseJF", "stdlib:multibond/ComposePose3D", 1480, 700)
    D.node("PoseF", "stdlib:multibond/ComposePose3D", 1700, 560)
    D.sig("PoseH", "g", "PoseJF", "gp")
    D.sig("LocalJF", "g", "PoseJF", "gl")
    D.sig("PoseJF", "g", "PoseF", "gp")
    D.sig("FrontHub", "pose", "PoseF", "gl")
    D.sig("PoseF", "g", "FrontWheel", "g")
    D.node("TyreF", "stdlib:contact/RollingDisk", 1700, 260,
           params={"radius": num(RHO_F), "k": num(CT["k"]), "xref": num(CT["xref"]), "c": num(CT["c"]),
                   "mu": num(CT["mu"]), "vs": num(CT["vs"])})
    D.bond("FrontWheel", "p", "TyreF", "p")
    D.sig("PoseF", "g", "TyreF", "g")
    D.sig("Ground", "o", "TyreF", "o")
    D.sig("Ground", "fr", "TyreF", "fr")
    # sensing (the paper's coordinates) and the energy book
    D.node("LocalRef", "stdlib:spatial/LocalPose3D", 600, 860, params=pose_params(inv(g["B"]) @ g["Ref"]))
    D.node("PoseRef", "stdlib:multibond/ComposePose3D", 600, 1000)
    D.sig("PoseB", "g", "PoseRef", "gp")
    D.sig("LocalRef", "g", "PoseRef", "gl")
    D.node("Sense", "project:BikeSense", 820, 1000, params={"rR": num(RHO_R)})
    D.sig("PoseRef", "g", "Sense", "gr")
    D.sig("PoseB", "g", "Sense", "gB")
    D.sig("RearFrame", "V", "Sense", "VB")
    D.sig("Steer", "qout", "Sense", "q_steer")
    D.sig("Steer", "qdout", "Sense", "qd_steer")
    D.sig("RearHub", "qdout", "Sense", "qd_rear")
    D.node("Energy", "project:BikeEnergy", 1260, 1000,
           params={"mB": num(P["mB"]), "mH": num(P["mH"]), "mR": num(P["mR"]), "mF": num(P["mF"]), "g0": num(P["g"])})
    for body_, k, pose in (("RearFrame", "B", "PoseB"), ("Fork", "H", "PoseH"), ("RearWheel", "R", "PoseR"),
                           ("FrontWheel", "F", "PoseF")):
        D.sig(body_, "V", "Energy", "V" + k)
        D.sig(body_, "P", "Energy", "P" + k)
        D.sig(pose, "g", "Energy", "g" + k)
    D.sig("TyreR", "Ec", "Energy", "EcR")
    D.sig("TyreF", "Ec", "Energy", "EcF")
    D.sig("TyreR", "Pd", "Energy", "PdR")
    D.sig("TyreF", "Pd", "Energy", "PdF")
    D.sig("Steer", "qdout", "Energy", "qd_s")
    for joint, k in (("RearHub", "R"), ("Steer", "S"), ("FrontHub", "F")):
        D.sig(joint, "dang", "Energy", "ang" + k)
        D.sig(joint, "dlin", "Energy", "lin" + k)
    if steer_input is None:
        D.node("NoTorque", "stdlib:sources/Constant", 1040, 1000, params={"value": "0.0"})
        D.sig("NoTorque", "y", "Energy", "tau_s")
    else:
        D.sig(*steer_input, "Energy", "tau_s")


def bindings():
    def pose(sig):
        return [f"{sig}/g[{i}]" for i in range(1, 8)]
    return [
        {"target": "link:rear_frame", "property": "pose",
         "signal": ["PoseB/qw", "PoseB/qx", "PoseB/qy", "PoseB/qz", "PoseB/px", "PoseB/py", "PoseB/pz"]},
        {"target": "link:fork", "property": "pose", "signal": pose("PoseH")},
        {"target": "link:rear_wheel", "property": "pose", "signal": pose("PoseR")},
        {"target": "link:front_wheel", "property": "pose", "signal": pose("PoseF")},
    ]


# ------------------------------------------------------------------ linear model (signal diagram)
def expr(c0, c1=0.0, var="v", power=1) -> str:
    """'c0 + c1*v' (power 1) or 'c0 + c1*v*v' (power 2), without zero terms."""
    parts = []
    if abs(c0) > 1e-15:
        parts.append(repr(float(c0)))
    if abs(c1) > 1e-15:
        parts.append(f"{float(c1)!r}*" + "*".join([var] * power))
    s = " + ".join(parts) if parts else "0.0"
    return s.replace("+ -", "- ")


def linear_plant(D: Diagram, x0=0, y0=0, torque=None):
    """phi'' and delta'' from the paper's matrices: q'' = M^-1 (f - v C1 q' - (g K0 + v^2 K2) q).
    The integrators are named after their outputs (Lean = phi, LeanRate = phid, ...)."""
    m = b.matrices()
    Minv = np.linalg.inv(m["M"])
    A0 = -Minv @ (P["g"] * m["K0"])          # constant part of the stiffness gains
    A2 = -Minv @ m["K2"]                     # times v^2
    A1 = -Minv @ m["C1"]                     # times v
    names = (("Lean", "LeanRate", "LeanAcc", "phi"), ("Steer", "SteerRate", "SteerAcc", "delta"))
    for i, (pos, rate, acc, r) in enumerate(names):
        yy = y0 + 400 * i
        D.node(rate, "stdlib:continuous/Integrator", x0 + 900, yy,
               starts={"x": "phid0" if i == 0 else "0.0"})
        D.node(pos, "stdlib:continuous/Integrator", x0 + 1080, yy)
        D.sig(rate, "y", pos, "u")
        gains = (
            (f"K_{r}_phi", expr(A0[i, 0], A2[i, 0], power=2)),
            (f"K_{r}_delta", expr(A0[i, 1], A2[i, 1], power=2)),
            (f"C_{r}_phid", expr(0.0, A1[i, 0])),
            (f"C_{r}_deltad", expr(0.0, A1[i, 1])),
        )
        for k, (gname, value) in enumerate(gains):
            D.node(gname, "stdlib:continuous/Gain", x0 + 300, yy - 150 + 70 * k, params={"k": value})
        free = D.add(acc + "Free", [(g[0], "y") for g in gains], x0 + 460, yy - 60)
        D.node(f"B_{r}", "stdlib:continuous/Gain", x0 + 300, yy + 140, params={"k": repr(float(Minv[i, 1]))})
        D.sig(*D.add(acc, [free, (f"B_{r}", "y")], x0 + 700, yy), rate, "u")
    for _, _, _, r in names:
        D.sig("Lean", "y", f"K_{r}_phi", "u")
        D.sig("Steer", "y", f"K_{r}_delta", "u")
        D.sig("LeanRate", "y", f"C_{r}_phid", "u")
        D.sig("SteerRate", "y", f"C_{r}_deltad", "u")
    if torque is None:
        D.node("SteerTorque", "stdlib:sources/Constant", x0 + 60, y0 + 160, params={"value": "0.0"})
        torque = ("SteerTorque", "y")
    D.sig(*torque, "B_phi", "u")
    D.sig(*torque, "B_delta", "u")
    # heading (paper eq. for the yaw rate, linear): psi' = (v delta + c delta') cos(lam) / w
    D.node("YawV", "stdlib:continuous/Gain", x0 + 1060, y0 + 660,
           params={"k": f"{float(np.cos(LAM) / P['w'])!r}*v"})
    D.node("YawC", "stdlib:continuous/Gain", x0 + 1060, y0 + 760, params={"k": repr(float(P["c"] * np.cos(LAM) / P["w"]))})
    D.node("Heading", "stdlib:continuous/Integrator", x0 + 1500, y0 + 700)
    D.sig("Steer", "y", "YawV", "u")
    D.sig("SteerRate", "y", "YawC", "u")
    D.sig(*D.add("YawRate", [("YawV", "y"), ("YawC", "y")], x0 + 1240, y0 + 700), "Heading", "u")


# ------------------------------------------------------------------ balance controller
def controller(D: Diagram, states, x0, y0):
    """Steer torque u = -K x + N phi_ref (LQR on the linear model at 3 m/s, design.py), with a
    lean set-point step. `states` = signal sources of (phi, delta, phid, deltad)."""
    bal = DESIGN["balance"]
    D.node("LeanRef", "stdlib:sources/Step", x0, y0 + 300,
           params={"t_step": "2.0", "initial": "0.0", "final": "lean_ref"})
    labels = ("phi", "delta", "phid", "deltad")
    for k, (lab, src) in enumerate(zip(labels, states)):
        D.node(f"L_{lab}", "stdlib:continuous/Gain", x0 + 200, y0 + 70 * k, params={"k": num(-bal["K"][k])})
        D.sig(*src, f"L_{lab}", "u")
    fb = D.add("Feedback", [(f"L_{lab}", "y") for lab in labels], x0 + 360, y0 + 100)
    D.node("N_ref", "stdlib:continuous/Gain", x0 + 200, y0 + 300, params={"k": num(bal["N"])})
    D.sig("LeanRef", "y", "N_ref", "u")
    return D.add("Ctrl", [fb, ("N_ref", "y")], x0 + 620, y0 + 150)


def balance_globals():
    bal = DESIGN["balance"]
    return [
        {"name": "v", "value": num(bal["v"]), "unit": "m/s",
         "description": "Forward speed at the start; below the weave speed (4.29 m/s) the free bicycle falls over"},
        {"name": "phid0", "value": "0.3", "unit": "rad/s", "description": "Lean rate at the start (a sideways push)"},
        {"name": "lean_ref", "value": num(bal["lean_ref"]), "unit": "rad",
         "description": "Lean set-point after 2 s (positive = to the right): the bicycle settles in a steady right turn"},
    ]


# ------------------------------------------------------------------ models
def plots_3d(extra=()):
    return [
        {"id": "lean", "title": "Lean and steer angle (paper signs: to the right positive)",
         "signals": ["Sense/phi", "Sense/delta"]},
        {"id": "rates", "title": "Lean rate and steer rate (the paper's figure 4)",
         "signals": ["Sense/phid", "Sense/deltad"]},
        {"id": "speed", "title": "Forward speed", "signals": ["Sense/v"]},
        {"id": "path", "title": "Path of the rear hub (world y, to the left, against x)",
         "signals": ["Sense/y"], "x": "Sense/x", "equalAspect": True},
        {"id": "tyres", "title": "Tyre normal forces", "signals": ["TyreR/f_n", "TyreF/f_n"]},
        {"id": "energy", "title": "Energy book (Ebal = E + loss - work stays constant)",
         "signals": ["Energy/E", "Energy/Ebal"]},
        *extra,
    ]


def plots_linear(extra=()):
    return [
        {"id": "lean", "title": "Lean and steer angle (linearised benchmark)", "signals": ["Lean/y", "Steer/y"]},
        {"id": "rates", "title": "Lean rate and steer rate", "signals": ["LeanRate/y", "SteerRate/y"]},
        {"id": "heading", "title": "Heading (linear kinematics)", "signals": ["Heading/y"]},
        *extra,
    ]


def speed_slider(lo=0.5, hi=10.0):
    return {"id": "v", "kind": "slider", "size": "2x1", "title": "Forward speed v (global)",
            "parameter": "global:v", "options": {"min": lo, "max": hi, "step": 0.1, "decimals": 1, "unit": "m/s"}}


def push_slider():
    return {"id": "push", "kind": "slider", "size": "2x1", "title": "Initial lean rate (push)",
            "parameter": "global:phid0", "options": {"min": -1.0, "max": 1.0, "step": 0.05, "decimals": 2, "unit": "rad/s"}}


def lean_gauge(sig):
    return {"id": "lean", "kind": "gauge", "size": "1x1", "title": "Lean", "signals": [sig],
            "options": {"min": -0.5, "max": 0.5, "decimals": 3, "unit": "rad",
                        "zones": [{"from": -0.5, "to": -0.3, "tone": "bad"}, {"from": -0.3, "to": -0.15, "tone": "warn"},
                                  {"from": -0.15, "to": 0.15, "tone": "good"}, {"from": 0.15, "to": 0.3, "tone": "warn"},
                                  {"from": 0.3, "to": 0.5, "tone": "bad"}]}}


def model_whipple():
    D = Diagram()
    mech3d(D)
    return {
        "format": "bgsim.model", "language": "0.1.0", "name": "whipple",
        "$comment": "The benchmark bicycle (Meijaard et al. 2007) as a nonlinear 3D bond graph: four RigidBody3D "
                    "bodies, three Revolute3D joints and two knife-edge RollingDisk tyres. Uncontrolled, hands off; "
                    "started like the paper's figure 4 (4.6 m/s, lean rate 0.5 rad/s).",
        "parameters": globals_(4.6, 0.5),
        "diagram": D.doc(),
        "settings": settings(5.0, 1001, reltol=1e-6, abstol=1e-8),
        "plots": plots_3d(),
        "scene": {"file": "scenes/bicycle.sdf"},
        "bindings": bindings(),
        "dashboard": {"autoRerun": False, "cards": [
            speed_slider(), push_slider(), lean_gauge("Sense/phi"),
            {"id": "speed", "kind": "value", "size": "1x1", "title": "Speed", "signals": ["Sense/v"],
             "options": {"decimals": 3, "unit": "m/s", "sparkline": True}},
            {"id": "steer", "kind": "value", "size": "1x1", "title": "Steer", "signals": ["Sense/delta"],
             "options": {"decimals": 3, "unit": "rad", "sparkline": True}},
            {"id": "ebal", "kind": "value", "size": "1x1", "title": "Energy book", "signals": ["Energy/Ebal"],
             "options": {"decimals": 3, "unit": "J"}},
            {"id": "rates", "kind": "plot", "size": "2x1", "title": "Lean and steer rate", "signals": ["Sense/phid", "Sense/deltad"]},
            {"id": "path", "kind": "plot", "size": "2x1", "title": "Lean and steer angle", "signals": ["Sense/phi", "Sense/delta"]},
        ]},
    }


def model_linear():
    D = Diagram()
    linear_plant(D)
    return {
        "format": "bgsim.model", "language": "0.1.0", "name": "linear",
        "$comment": "The linearised benchmark bicycle of Meijaard et al. (2007), eq. (5.3): M q'' + v C1 q' + "
                    "(g K0 + v^2 K2) q = f with q = (lean, steer). The gains are the matrices of the paper's "
                    "appendix A as expressions of the global forward speed v.",
        "parameters": globals_(4.6, 0.5),
        "diagram": D.doc(),
        "settings": settings(5.0, 1001, reltol=1e-9, abstol=1e-12, solver="Tsit5"),
        "plots": plots_linear(),
        "dashboard": {"autoRerun": True, "cards": [
            speed_slider(), push_slider(), lean_gauge("Lean/y"),
            {"id": "steer", "kind": "value", "size": "1x1", "title": "Steer", "signals": ["Steer/y"],
             "options": {"decimals": 3, "unit": "rad", "sparkline": True}},
            {"id": "lean_plot", "kind": "plot", "size": "2x1", "title": "Lean and steer angle", "signals": ["Lean/y", "Steer/y"]},
            {"id": "rates", "kind": "plot", "size": "2x1", "title": "Lean and steer rate", "signals": ["LeanRate/y", "SteerRate/y"]},
        ]},
    }


def balance_dashboard(lean, steer, torque, extra=()):
    return {"autoRerun": False, "cards": [
        {"id": "ref", "kind": "slider", "size": "2x1", "title": "Lean set-point after 2 s (global)",
         "parameter": "global:lean_ref", "options": {"min": -0.3, "max": 0.3, "step": 0.01, "decimals": 2, "unit": "rad"}},
        push_slider(), lean_gauge(lean),
        {"id": "steer", "kind": "value", "size": "1x1", "title": "Steer", "signals": [steer],
         "options": {"decimals": 3, "unit": "rad", "sparkline": True}},
        {"id": "torque", "kind": "value", "size": "1x1", "title": "Steer torque", "signals": [torque],
         "options": {"decimals": 2, "unit": "N m", "sparkline": True}},
        *extra,
        {"id": "lean_plot", "kind": "plot", "size": "2x1", "title": "Lean and set-point", "signals": [lean, "LeanRef/y"]},
        {"id": "torque_plot", "kind": "plot", "size": "2x1", "title": "Steer torque", "signals": [torque]},
    ]}


def model_balance():
    D = Diagram()
    ctrl = controller(D, [("Sense", "phi"), ("Sense", "delta"), ("Sense", "phid"), ("Sense", "deltad")], 100, 1200)
    mech3d(D, steer_input=ctrl)
    return {
        "format": "bgsim.model", "language": "0.1.0", "name": "balance",
        "$comment": "The 3D bicycle at 3 m/s, below the weave speed where the hands-off bicycle falls, balanced by a "
                    "steer torque (LQR on the linearised benchmark, design.py) and turned by a lean set-point.",
        "parameters": balance_globals(),
        "diagram": D.doc(),
        "settings": settings(10.0, 1001, reltol=1e-6, abstol=1e-8),
        "plots": plots_3d([{"id": "torque", "title": "Steer torque", "signals": ["Ctrl/y"]},
                           {"id": "heading", "title": "Heading (paper sign: to the right)", "signals": ["Sense/psi"]}]),
        "scene": {"file": "scenes/bicycle-turn.sdf"},
        "bindings": bindings(),
        "dashboard": balance_dashboard("Sense/phi", "Sense/delta", "Ctrl/y",
                                       [{"id": "speed", "kind": "value", "size": "1x1", "title": "Speed",
                                         "signals": ["Sense/v"], "options": {"decimals": 3, "unit": "m/s"}}]),
    }


def model_balance_linear():
    D = Diagram()
    ctrl = controller(D, [("Lean", "y"), ("Steer", "y"), ("LeanRate", "y"), ("SteerRate", "y")], 100, 900)
    linear_plant(D, torque=ctrl)
    return {
        "format": "bgsim.model", "language": "0.1.0", "name": "balance-linear",
        "$comment": "The balance controller of model `balance` on the linearised benchmark bicycle.",
        "parameters": balance_globals(),
        "diagram": D.doc(),
        "settings": settings(10.0, 1001, reltol=1e-9, abstol=1e-12, solver="Tsit5"),
        "plots": plots_linear([{"id": "torque", "title": "Steer torque", "signals": ["Ctrl/y"]}]),
        "dashboard": balance_dashboard("Lean/y", "Steer/y", "Ctrl/y"),
    }


def write(name, model):
    MODELS.mkdir(parents=True, exist_ok=True)
    path = MODELS / f"{name}.bgmodel.json"
    path.write_text(json.dumps(model, indent=2) + "\n", encoding="utf-8", newline="\n")
    print("wrote", path.relative_to(ROOT))


ALL = {"whipple": model_whipple, "linear": model_linear, "balance": model_balance,
       "balance-linear": model_balance_linear}


# ------------------------------------------------------------------ acceptance checks
DIAG = {"kind": "no_diagnostics", "codes": ["W201", "W202", "E101", "E102", "E103", "E106", "E007", "W206"],
        "note": "compliant joints and explicit contacts: no derivative causality, connected and frame-consistent"}
NO_JOINT_DAMPING = [{"target": f"{j}/{k}", "value": 0.0} for j in ("RearHub", "Steer", "FrontHub") for k in ("br", "bt")]


def run_at(v, phid0, t_end, points, model="whipple", extra=None):
    e = {"model": model, "overrides": [{"target": "global:v", "value": v}, {"target": "global:phid0", "value": phid0}],
         "settings": {"t_end": t_end, "output": {"points": points}}}
    e.update(extra or {})
    return e


def weave(v, signal, from_t, to_t, zeta_abs=0.01, wn_rtol=0.01, measured=""):
    """A damping check against the paper's table 2 weave pair at the integer speed v."""
    row = next(r for r in b.load_table2()["weave"] if r["v"] == v)
    wn = float(np.hypot(row["re"], row["im"]))
    return {"kind": "damping", "signal": signal, "from_t": from_t, "to_t": to_t,
            "zeta": round(-row["re"] / wn, 5), "zeta_abs": zeta_abs, "wn": round(wn, 5), "wn_rtol": wn_rtol,
            "note": f"weave eigenvalue at {v} m/s from Meijaard et al. 2007 table 2: {row['re']:.5f} +- "
                    f"{row['im']:.5f} i (zeta {-row['re'] / wn:.4f}, wn {wn:.4f} rad/s){measured}"}


def expected():
    t2 = b.load_table2()
    r46 = DESIGN["responses"]["v4.6_phid0.5"]
    r8 = DESIGN["responses"]["v8_phid0.05"]
    bal = DESIGN["balance"]
    st = bal["steady"]
    vw, lw = t2["special"]["v_w"], t2["special"]["lambda_w_imag"]

    def at(r, key, t):
        return float(r[key][r["t"].index(t)])

    models = {
        "whipple": {"checks": [
            {"kind": "scene_bindings", "note": "rear frame, fork and both wheels follow their composed body poses"},
            DIAG,
            {"kind": "max_abs_le", "signal": "Sense/v", "value": 4.70,
             "note": "the paper's figure 4 (same start: 4.6 m/s, lean rate 0.5 rad/s) plots the forward speed on a "
                     "4.60-4.70 m/s axis; measured 4.599 to 4.688 m/s (the figure is not tabulated, so this is "
                     "only its range)"},
            {"kind": "min_ge", "signal": "Sense/v", "value": 4.59, "note": "lower end of the figure 4 speed axis (measured 4.599)"},
            {"kind": "max_abs_le", "signal": "Sense/phi", "from_t": 4.0, "value": 0.025,
             "note": "self-stable at 4.6 m/s (between the weave speed 4.29 and the capsize speed 6.02 m/s): the lean "
                     "of 0.116 rad after the push has decayed to at most 0.018 rad after 4 s"},
            {"kind": "min_ge", "signal": "TyreR/f_n", "value": 550.0,
             "note": "the rear tyre stays loaded (static 612.8 N; measured 588 to 623 N)"},
            {"kind": "min_ge", "signal": "TyreF/f_n", "value": 250.0,
             "note": "the front tyre stays loaded (static 309.3 N; measured 296 to 324 N)"},
            {"kind": "max_abs_le", "signal": "TyreR/s_lat", "value": 5e-4,
             "note": "rolling without slip up to a creep below 0.5 mm/s (measured 0.36 mm/s at the start: the lean rate "
                     "turns the 0.7 mm deep contact point sideways)"},
            {"kind": "max_abs_le", "signal": "TyreF/s_lon", "value": 1e-5, "note": "longitudinal creep (measured 3.6 um/s)"},
            {"kind": "invariant", "terms": [{"signal": "Energy/Ebal", "coeff": 1.0}], "tol": 2e-4,
             "note": "energy book with the joint dampers on: E + tyre loss stays within 0.37 J of 1837 J (measured "
                     "drift 0.24 J, the work of the dampers of the joints' held directions, not counted in the book)"},
        ]},
        "whipple-energy": {"model": "whipple", "overrides": NO_JOINT_DAMPING, "checks": [
            {"kind": "invariant", "terms": [{"signal": "Energy/Ebal", "coeff": 1.0}], "tol": 1e-6,
             "note": "joint dampers off: the Whipple bicycle is conservative, so kinetic + potential + tyre and joint "
                     "springs + tyre loss is constant to 1.8 mJ in 1837 J (measured 0.07 mJ while the tyres "
                     "dissipate 2.8 J)"},
        ]},
        "whipple-3ms": run_at(3.0, 0.002, 3.0, 601, extra={"checks": [
            weave(3, "Sense/delta", 0.3, 3.0, measured="; measured zeta -0.5935, wn 2.8801")]}),
        "whipple-4ms": run_at(4.0, 0.01, 5.0, 1001, extra={"checks": [
            weave(4, "Sense/deltad", 0.3, 5.0, measured="; measured zeta -0.1353, wn 3.1045")]}),
        "whipple-5ms": run_at(5.0, 0.05, 6.0, 1201, extra={"checks": [
            weave(5, "Sense/deltad", 0.3, 6.0, measured="; measured zeta 0.1702, wn 4.5153")]}),
        "whipple-6ms": run_at(6.0, 0.05, 4.0, 801, extra={"checks": [
            weave(6, "Sense/phid", 0.2, 4.0, measured="; measured zeta 0.2508, wn 6.0596")]}),
        "whipple-8ms": run_at(8.0, 0.05, 12.0, 1201, extra={"checks": [
            {"kind": "cursor_value", "signal": "Sense/phi", "t": 6.0, "value": at(r8, "phi", 6.0), "rtol": 0.01,
             "note": "above the capsize speed the lean grows slowly (table 2: capsize eigenvalue +0.14328/s at 8 m/s); "
                     "value: the linearised benchmark from the same start (design.py, matrix exponential); measured "
                     "0.0071575 (-0.3 %)"},
            {"kind": "cursor_value", "signal": "Sense/phi", "t": 12.0, "value": at(r8, "phi", 12.0), "rtol": 0.01,
             "note": "the same at 12 s (measured 0.0168516, -0.6 %)"},
        ]}),
        "linear": {"checks": [
            *[{"kind": "cursor_value", "signal": "Lean/y", "t": t, "value": at(r46, "phi", t), "abs": 1e-8,
               "note": "the paper's matrices (6.1)-(6.4) at 4.6 m/s from a 0.5 rad/s lean rate, exact solution by the "
                       "matrix exponential in design.py"} for t in (0.5, 1.0, 2.0, 3.0)],
            {"kind": "cursor_value", "signal": "Steer/y", "t": 1.0, "value": at(r46, "delta", 1.0), "abs": 1e-8,
             "note": "steer angle, same reference"},
        ]},
        "linear-weave-speed": run_at(vw, 0.1, 10.0, 2001, model="linear", extra={"checks": [
            {"kind": "damping", "signal": "LeanRate/y", "from_t": 3.0, "to_t": 10.0, "zeta": 0.0, "zeta_abs": 0.002,
             "wn": lw, "wn_rtol": 0.002,
             "note": f"at the weave speed v_w = {vw} m/s (Meijaard et al. 2007 table 2a) the weave pair sits on the "
                     f"imaginary axis at +- {lw} i: an undamped oscillation once the capsize and castering modes "
                     "have died out"}]}),
        "linear-5ms": run_at(5.0, 0.05, 6.0, 1201, model="linear", extra={"checks": [
            weave(5, "SteerRate/y", 0.3, 6.0, zeta_abs=0.005, wn_rtol=0.005, measured="; measured zeta 0.1713, wn 4.5258")]}),
        "balance": {"checks": [
            {"kind": "scene_bindings", "note": "rear frame, fork and both wheels follow their composed body poses"},
            DIAG,
            {"kind": "final_value", "signal": "Sense/phi", "t": 10.0, "value": bal["lean_ref"], "abs": 0.003,
             "note": "the lean settles on the set-point; the LQR has no integral action, and on the nonlinear bicycle "
                     "(which speeds up to 3.05 m/s as it leans) it settles 1.6 % high (measured 0.10160)"},
            {"kind": "final_value", "signal": "Sense/delta", "t": 10.0, "value": st["delta"], "abs": 0.004,
             "note": f"steady-turn steer angle of the linearised benchmark at 3 m/s and 0.1 rad lean "
                     f"({st['delta']:.5f} rad, design.py); measured 0.11767 at 3.05 m/s"},
            {"kind": "final_value", "signal": "Sense/psid", "t": 10.0, "value": 0.33816, "abs": 0.001,
             "note": "heading rate of the steady turn from the measured speed, steer and lean through the rolling "
                     "kinematics v tan(delta) cos(lambda) / (w cos(phi)) = 3.05196 tan(0.117668) cos(pi/10) / (1.02 "
                     "cos(0.101602)) = 0.33816 rad/s (measured 0.33809); the linear model gives 0.33460 at 3 m/s"},
            {"kind": "max_abs_le", "signal": "Ctrl/y", "value": 2.5,
             "note": "steer torque (measured peak 2.30 N m, the reaction to the 0.3 rad/s push)"},
            {"kind": "min_ge", "signal": "TyreF/f_n", "value": 250.0, "note": "the front tyre stays loaded (measured 305 N)"},
            {"kind": "invariant", "terms": [{"signal": "Energy/Ebal", "coeff": 1.0}], "tol": 3e-4,
             "note": "energy book with the steer torque's work counted: constant within 0.37 J of 1237 J (measured drift "
                     "0.21 J, the joint dampers)"},
        ]},
        "balance-linear": {"checks": [
            {"kind": "final_value", "signal": "Lean/y", "t": 10.0, "value": bal["lean_ref"], "abs": 1e-4,
             "note": "the reference gain N of design.py makes the set-point the closed loop's steady state"},
            {"kind": "final_value", "signal": "Steer/y", "t": 10.0, "value": st["delta"], "abs": 1e-4,
             "note": "steady-turn steer angle from the paper's matrices (design.py)"},
            {"kind": "final_value", "signal": "YawRate/y", "t": 10.0, "value": st["psid"], "abs": 1e-4,
             "note": "heading rate v delta cos(lambda) / w of that steady turn (design.py)"},
            {"kind": "final_value", "signal": "Ctrl/y", "t": 10.0, "value": st["T"], "abs": 1e-3,
             "note": "steady steer torque (design.py): negative, i.e. the rider holds the bar against the turn"},
        ]},
    }
    doc = {
        "project": "bicycle",
        "description": "Acceptance of the bicycle example: the benchmark bicycle of Meijaard, Papadopoulos, Ruina and "
                       "Schwab (Proc. R. Soc. A 463, 2007). The linear model is checked against the matrix exponential "
                       "of the paper's matrices and the weave speed of table 2; the 3D multibond bond graph against "
                       "the table 2 weave eigenvalues at 3 to 6 m/s, the linearised capsize growth at 8 m/s, the "
                       "linear model at a small push (compare) and its own energy book.",
        "models": models,
        "compare": [
            {"a": "whipple-5ms", "b": "linear-5ms", "signal_a": "Sense/phi", "signal_b": "Lean/y", "from_t": 0.0,
             "max_abs": 2e-4,
             "note": "3D bond graph against the linearised benchmark at 5 m/s after a 0.05 rad/s push: lean within "
                     "2e-4 rad of a 0.0106 rad motion (measured 7.5e-5)"},
            {"a": "whipple-5ms", "b": "linear-5ms", "signal_a": "Sense/delta", "signal_b": "Steer/y", "from_t": 0.0,
             "max_abs": 2e-4, "note": "steer angle, same runs (measured 7.4e-5 of 0.0115 rad)"},
            {"a": "balance", "b": "balance-linear", "signal_a": "Sense/phi", "signal_b": "Lean/y", "from_t": 0.0,
             "max_abs": 0.003, "note": "the controller on the 3D bicycle and on the linear model (measured 0.0016 rad)"},
        ],
    }
    path = ROOT / "expected.json"
    path.write_text(json.dumps(doc, indent=2) + "\n", encoding="utf-8", newline="\n")
    print("wrote", path.relative_to(ROOT))


def main(only=None):
    for k, f in ALL.items():
        if only and k not in only:
            continue
        write(k, f())
    if not only:
        expected()


if __name__ == "__main__":
    main(sys.argv[1:] or None)
