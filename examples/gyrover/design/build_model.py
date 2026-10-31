# /// script
# requires-python = ">=3.11"
# dependencies = ["numpy>=2.0", "scipy>=1.13", "sympy>=1.13"]
# ///
"""Writes the models of the `gyrover` example (``models/*.bgmodel.json``).

Bond-graph models (library blocks only, plus the project's sensor, controller and energy
blocks): the wheel is a ``RigidBody3D`` on a ``PoseIntegrator3D`` that rolls on the ground
through a ``RollingDisk``; the pendulum (drive unit) hangs on the axle ``Revolute3D``, the
gimbal on the tilt ``Revolute3D``, and the flywheel is a ``Rotor3D`` on the gimbal. The motors
are ``MSe`` sources on the two joint drives and on the rotor drive.

The reference model is the equation block ``GyroverRef`` (``gen_ref.py``) with the same
controller.

    uv run examples/gyrover/design/build_model.py

Every scenario starts from a state of the exact model (``eom.py`` coordinates); this script
converts it into the bond graph's body poses, body momenta, joint angles and rotor momentum, so
both models start from the same physical state.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
import design as d  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
MODELS = ROOT / "models"
P = d.PARAMS

# contact
K_C, XREF, C_C, MU, VS = 1.0e6, 1.0e-3, 2.0, 0.9, 1.0e-3
M_TOT = P["m_w"] + P["m_p"] + P["m_g"] + P["m_r"]
DELTA0 = (M_TOT * P["g0"] * np.sqrt(XREF) / K_C) ** (2.0 / 3.0)   # static penetration
# controller constants (docs page "Steady turn": small-angle turn of the whole robot)
H0 = P["Jra"] * d.W3
MGH = P["g0"] * (M_TOT * P["R"] - P["m_p"] * P["l_p"] - (P["m_g"] + P["m_r"]) * P["l_g"])
MH = M_TOT * P["R"] - P["m_p"] * P["l_p"] - (P["m_g"] + P["m_r"]) * P["l_g"] + P["Jwa"] / P["R"]


# ------------------------------------------------------------------ small helpers
def num(x) -> str:
    return repr(float(x))


def vec(v) -> str:
    return "[" + ", ".join(num(x) for x in v) + "]"


def Rx(a):
    c, s = np.cos(a), np.sin(a)
    return np.array([[1, 0, 0], [0, c, -s], [0, s, c]])


def Ry(a):
    c, s = np.cos(a), np.sin(a)
    return np.array([[c, 0, s], [0, 1, 0], [-s, 0, c]])


def Rz(a):
    c, s = np.cos(a), np.sin(a)
    return np.array([[c, -s, 0], [s, c, 0], [0, 0, 1]])


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


# bg body axes in terms of the eom frame of that body: x -> x, y -> -z, z -> y
C = np.array([[1.0, 0, 0], [0, 0, 1.0], [0, -1.0, 0]])
# tilt-joint frame in Pf: x_T = Pf.z, y_T = Pf.y, z_T = -Pf.x (so the joint angle is the paper's theta2)
CT = np.array([[0, 0, -1.0], [0, 1.0, 0], [1.0, 0, 0]])
# gimbal carrier (Rotor3D: z = spin axis G.y) in the tilt-joint child frame: x_c = G.z, y_c = G.x, z_c = G.y
CG = CT.T @ np.array([[0, 1.0, 0], [0, 0, 1.0], [1.0, 0, 0]])


def frames(x):
    """World rotations of the eom frames and the wheel centre for the state x (eom.py)."""
    psi, phi, gam, beta, th2 = x[:5]
    A = Rz(psi)
    B = A @ Rx(phi)
    W = B @ Ry(gam)
    Pf = B @ Ry(beta)
    G = Pf @ Rx(th2)
    O = np.array([x[11], x[12], P["R"] * np.cos(phi) - DELTA0])
    return A, B, W, Pf, G, O


def bg_state(x):
    """Bond-graph starts (poses, momenta, joint angles, rotor momentum) of the eom state x."""
    psi, phi, gam, beta, th2 = x[:5]
    u1, u2, u3, u4, u5, u6 = x[5:11]
    A, B, W, Pf, G, O = frames(x)
    ez = np.array([0, 0, 1.0])
    wW = u1 * ez + u2 * A[:, 0] + u3 * B[:, 1]
    wP = u1 * ez + u2 * A[:, 0] + u4 * B[:, 1]
    wG = wP + u5 * Pf[:, 0]
    vO = np.cross(wW, P["R"] * B[:, 2])
    # bodies: wheel (W C, at O), pendulum (Pf Ry(a_p) C, CoM at O - l_p Pf.z), gimbal (Pf CT CG..)
    Rw = W @ C
    Rp = Pf @ Ry(P["a_p"]) @ C
    Rt = Pf @ CT                       # tilt joint frame at q = 0
    Rg = G @ CT @ CG                   # gimbal carrier frame (tilt applied)
    pP = O - P["l_p"] * Pf[:, 2]
    pG = O - P["l_g"] * Pf[:, 2]
    vP = vO + np.cross(wP, pP - O)
    vG = vO + np.cross(wP, pG - O)
    Jw = np.array([P["Jwt"], P["Jwt"], P["Jwa"]])
    Jp = np.array([P["Jp1"], P["Jp3"], P["Jp2"]])
    Jg = np.array([P["Jg3"] + P["Jrt"], P["Jg1"] + P["Jrt"], P["Jg2"]])
    mg = P["m_g"] + P["m_r"]

    def mom(R, w, v, J, m):
        wb, vb = R.T @ w, R.T @ v
        return np.concatenate([J * wb, m * vb])

    h = P["Jra"] * (wG @ G[:, 1] + u6)
    return dict(
        wheel_q=quat(Rw), wheel_p=O, Pw=mom(Rw, wW, vO, Jw, P["m_w"]), Pp=mom(Rp, wP, vP, Jp, P["m_p"]),
        Pg=mom(Rg, wG, vG, Jg, mg), qa=beta - gam, qt=d.S2 * th2, h=h, Jw=Jw, Jp=Jp, Jg=Jg, mg=mg,
        Rw=Rw, Rp=Rp, Rt=Rt, Rg=Rg, pP=pP, pG=pG, O=O,
    )


def pose_params(R, p):
    q = quat(R)
    return {"qw": num(q[0]), "qx": num(q[1]), "qy": num(q[2]), "qz": num(q[3]),
            "x": num(p[0]), "y": num(p[1]), "z": num(p[2])}


def fixed_transforms():
    """Constant mounts (child pose in the parent frame) at the reference configuration."""
    x0 = np.zeros(17)
    s = bg_state(x0)
    Rc = s["Rw"]                                         # axle child frame at q = 0 = wheel frame
    link_p = (Rc.T @ s["Rp"], Rc.T @ (s["pP"] - s["O"]))               # pendulum body in axle child
    # tilt mount: pendulum body (b) in the tilt joint frame (a)
    mount_t = (s["Rt"].T @ s["Rp"], s["Rt"].T @ (s["pP"] - s["pG"]))
    local_t = (s["Rp"].T @ s["Rt"], s["Rp"].T @ (s["pG"] - s["pP"]))   # tilt frame in the pendulum body
    link_g = (s["Rt"].T @ s["Rg"], np.zeros(3))                       # gimbal carrier in the tilt child
    return link_p, mount_t, local_t, link_g


# ------------------------------------------------------------------ diagram builder
class Diagram:
    def __init__(self):
        self.nodes, self.conns = [], []
        self._ids = {}

    def node(self, name, ref, x, y, params=None, starts=None):
        nid = f"n{len(self.nodes) + 1:02d}"
        self._ids[name] = nid
        self.nodes.append({
            "id": nid, "name": name, "block": {"ref": ref}, "position": {"x": int(x), "y": int(y)},
            "rotation": 0, "flipX": False, "params": params or {}, "constants": {}, "starts": starts or {},
            "ui": {"showLabel": True, "color": None},
        })

    def _c(self, kind, a, pa, b, pb):
        self.conns.append({"id": f"c{len(self.conns) + 1:03d}", "kind": kind,
                           "from": {"node": self._ids[a], "port": pa}, "to": {"node": self._ids[b], "port": pb},
                           "label": None})

    def bond(self, a, pa, b, pb):
        self._c("bond", a, pa, b, pb)

    def sig(self, a, pa, b, pb):
        self._c("signal", a, pa, b, pb)


# The tilt servo (poles near -4000 rad/s), the joint springs and the contact are stiff.
SOLVER = "Rodas5P"


def settings(t_end, points, reltol=1e-7, abstol=1e-9):
    return {"t_start": 0.0, "t_end": float(t_end), "solver": SOLVER, "reltol": reltol, "abstol": abstol,
            "max_step": None, "output": {"mode": "points", "points": int(points)}, "event_limit": 10000}


CTRL_SIGNALS = ["lean", "heading", "th1", "w1", "wz", "th2", "w2", "wx", "wy"]


def joint_damping(c: dict) -> dict:
    """Damping of the stiff held directions of the two joints (kr = kt = 1e6). Without it the
    joint springs ring undamped at a few kHz; the energy run (`free`) keeps it at 0."""
    if c.get("joint_damping", True):
        return {"br": num(20.0), "bt": num(500.0)}
    return {}


def ctrl_params(c: dict) -> dict:
    base = {"R": num(P["R"]), "mgh": num(MGH), "Ls": num(H0), "mh": num(MH),
            "w3_ref": num(c.get("w3", d.W3)), "kp_t": num(4.0e4), "kd_t": num(c.get("kd_t", 20.0))}
    for k in ("bal", "servo", "spin", "head"):
        base[k] = num(c.get(k, 0.0))
    base["lat"] = num(c.get("lat", 1.0))
    if "lean0" in c:
        base["lean0"] = num(c["lean0"])
    if "K2" in c:
        base["K2"] = vec(c["K2"])
    return base


def add_plan(D, c, x, y):
    if c.get("plan"):
        D.node("Plan", "project:GyroPlan", x, y, params={k: num(v) for k, v in c["plan"].items()})
        return ("Plan", "v_ref"), ("Plan", "psi_ref")
    D.node("Vref", "stdlib:sources/Constant", x, y, params={"value": num(c.get("v_ref", 0.0))})
    D.node("PsiRef", "stdlib:sources/Constant", x, y + 80, params={"value": num(c.get("psi_ref", 0.0))})
    return ("Vref", "y"), ("PsiRef", "y")


def bond_graph(name, comment, x0, c, t_end, points, plots, scene="scenes/gyrover.sdf", extra=None):
    """The bond-graph Gyrover started at the eom state x0 with controller options c."""
    s = bg_state(x0)
    link_p, mount_t, local_t, link_g = fixed_transforms()
    D = Diagram()
    # wheel and contact
    D.node("Wheel", "stdlib:spatial/RigidBody3D", 600, 300,
           params={"m": num(P["m_w"]), "J": vec(s["Jw"]), "g0": num(P["g0"])},
           starts={"inertia/P": vec(s["Pw"])})
    q, p = s["wheel_q"], s["wheel_p"]
    D.node("Pose", "stdlib:multibond/PoseIntegrator3D", 600, 460,
           starts={"qw": num(q[0]), "qx": num(q[1]), "qy": num(q[2]), "qz": num(q[3]),
                   "px": num(p[0]), "py": num(p[1]), "pz": num(p[2])})
    D.node("Ground", "stdlib:contact/ContactSurface", 380, 300)
    D.node("Tyre", "stdlib:contact/RollingDisk", 420, 440,
           params={"radius": num(P["R"]), "k": num(K_C), "xref": num(XREF), "c": num(C_C), "mu": num(MU),
                   "vs": num(VS), "bsp": num(c.get("bsp", 0.0))})
    D.sig("Wheel", "V", "Pose", "tw")
    D.sig("Pose", "g", "Wheel", "g")
    D.bond("Wheel", "p", "Tyre", "p")
    D.sig("Pose", "g", "Tyre", "g")
    D.sig("Ground", "o", "Tyre", "o")
    D.sig("Ground", "fr", "Tyre", "fr")
    # axle joint and pendulum
    D.node("Axle", "stdlib:spatial/Revolute3D", 820, 300, params={"q0": num(s["qa"]), **joint_damping(c)})
    D.node("LinkP", "stdlib:multibond/FixedTransform3DNeutral", 1000, 300, params=pose_params(*link_p))
    D.node("Pendulum", "stdlib:spatial/RigidBody3D", 1180, 300,
           params={"m": num(P["m_p"]), "J": vec(s["Jp"]), "g0": num(P["g0"])}, starts={"inertia/P": vec(s["Pp"])})
    D.node("MountA", "stdlib:multibond/FixedTransform3DNeutral", 820, 140)
    D.bond("MountA", "b", "Wheel", "p")
    D.bond("MountA", "a", "Axle", "parent")
    D.bond("Axle", "child", "LinkP", "a")
    D.bond("LinkP", "b", "Pendulum", "p")
    D.node("PoseA", "stdlib:multibond/ComposePose3D", 820, 460)
    D.node("LocalP", "stdlib:spatial/LocalPose3D", 1000, 460, params=pose_params(*link_p))
    D.node("PoseP", "stdlib:multibond/ComposePose3D", 1180, 460)
    D.sig("Pose", "g", "PoseA", "gp")
    D.sig("Axle", "pose", "PoseA", "gl")
    D.sig("PoseA", "g", "PoseP", "gp")
    D.sig("LocalP", "g", "PoseP", "gl")
    D.sig("PoseP", "g", "Pendulum", "g")
    # tilt joint and gimbal + flywheel
    D.node("MountT", "stdlib:multibond/FixedTransform3DNeutral", 1180, 140, params=pose_params(*mount_t))
    D.node("Tilt", "stdlib:spatial/Revolute3D", 1380, 140, params={"q0": num(s["qt"]), **joint_damping(c)})
    D.node("LinkG", "stdlib:multibond/FixedTransform3DNeutral", 1560, 140, params=pose_params(*link_g))
    D.node("Gimbal", "stdlib:spatial/RigidBody3D", 1740, 140,
           params={"m": num(s["mg"]), "J": vec(s["Jg"]), "g0": num(P["g0"])}, starts={"inertia/P": vec(s["Pg"])})
    D.node("Flywheel", "stdlib:spatial/Rotor3D", 1920, 140, params={"Ja": num(P["Jra"])}, starts={"h": num(s["h"])})
    D.bond("MountT", "b", "Pendulum", "p")
    D.bond("MountT", "a", "Tilt", "parent")
    D.bond("Tilt", "child", "LinkG", "a")
    D.bond("LinkG", "b", "Gimbal", "p")
    D.bond("Gimbal", "p", "Flywheel", "p")
    D.node("LocalT", "stdlib:spatial/LocalPose3D", 1380, 460, params=pose_params(*local_t))
    D.node("PoseT", "stdlib:multibond/ComposePose3D", 1380, 600)
    D.node("PoseTc", "stdlib:multibond/ComposePose3D", 1560, 600)
    D.node("LocalG", "stdlib:spatial/LocalPose3D", 1560, 460, params=pose_params(*link_g))
    D.node("PoseG", "stdlib:multibond/ComposePose3D", 1740, 600)
    D.sig("PoseP", "g", "PoseT", "gp")
    D.sig("LocalT", "g", "PoseT", "gl")
    D.sig("PoseT", "g", "PoseTc", "gp")
    D.sig("Tilt", "pose", "PoseTc", "gl")
    D.sig("PoseTc", "g", "PoseG", "gp")
    D.sig("LocalG", "g", "PoseG", "gl")
    D.sig("PoseG", "g", "Gimbal", "g")
    # motors (MSe on the joint drives and the rotor drive)
    D.node("Drive", "stdlib:bondgraph/MSe", 820, 0)
    D.node("TiltMotor", "stdlib:bondgraph/MSe", 1380, 0)
    D.node("SpinMotor", "stdlib:bondgraph/MSe", 1920, 0)
    D.bond("Drive", "p", "Axle", "drive")
    D.bond("TiltMotor", "p", "Tilt", "drive")
    D.bond("SpinMotor", "p", "Flywheel", "drive")
    # sensing, control, energy
    D.node("Sense", "project:GyroSense", 820, 800, params={"R": num(P["R"])}, starts={"psi": num(x0[0])})
    D.sig("Pose", "g", "Sense", "g")
    D.sig("Wheel", "V", "Sense", "V")
    D.sig("Axle", "qout", "Sense", "qa")
    D.sig("Axle", "qdout", "Sense", "qda")
    D.sig("Tilt", "qout", "Sense", "qt")
    D.sig("Tilt", "qdout", "Sense", "qdt")
    D.sig("Flywheel", "w_rel", "Sense", "w3")
    vref, psiref = add_plan(D, c, 380, 960)
    D.node("Ctrl", "project:GyroCtrl", 600, 960, params=ctrl_params(c),
           starts={"r": num(s["qt"])})
    for k in CTRL_SIGNALS:
        D.sig("Sense", k, "Ctrl", k)
    D.sig("Flywheel", "w_rel", "Ctrl", "w3")
    D.sig(*vref, "Ctrl", "v_ref")
    D.sig(*psiref, "Ctrl", "psi_ref")
    D.sig("Ctrl", "tau1", "Drive", "u")
    D.sig("Ctrl", "tau2", "TiltMotor", "u")
    D.sig("Ctrl", "tau3", "SpinMotor", "u")
    D.node("Energy", "project:GyroEnergy", 1180, 800,
           params={"m_w": num(P["m_w"]), "m_p": num(P["m_p"]), "m_g": num(s["mg"]), "g0": num(P["g0"])})
    for b, k in (("Wheel", "w"), ("Pendulum", "p"), ("Gimbal", "g")):
        D.sig(b, "V", "Energy", "V" + k)
        D.sig(b, "P", "Energy", "P" + k)
    D.sig("Pose", "g", "Energy", "gw")
    D.sig("PoseP", "g", "Energy", "gp")
    D.sig("PoseG", "g", "Energy", "gg")
    D.sig("Flywheel", "Ek", "Energy", "Er")
    D.sig("Tyre", "Ec", "Energy", "Ec")
    D.sig("Tyre", "Pd", "Energy", "Pd")
    for a, pa, b in (("Ctrl", "tau1", "tau1"), ("Axle", "qdout", "qda"), ("Ctrl", "tau2", "tau2"),
                     ("Tilt", "qdout", "qdt"), ("Ctrl", "tau3", "tau3"), ("Flywheel", "w_rel", "w3")):
        D.sig(a, pa, "Energy", b)
    model = {
        "format": "bgsim.model", "language": "0.1.0", "name": name, "$comment": comment,
        "diagram": {"nodes": D.nodes, "connections": D.conns, "subsystemPorts": [], "annotations": []},
        "settings": settings(t_end, points),
        "plots": plots,
    }
    if scene:
        model["scene"] = {"file": scene}
        model["bindings"] = [
            {"target": "link:wheel", "property": "pose",
             "signal": ["Pose/qw", "Pose/qx", "Pose/qy", "Pose/qz", "Pose/px", "Pose/py", "Pose/pz"]},
            {"target": "link:pendulum", "property": "pose", "signal": [f"PoseP/g[{i}]" for i in range(1, 8)]},
            {"target": "link:gimbal", "property": "pose", "signal": [f"PoseG/g[{i}]" for i in range(1, 8)]},
            {"target": "joint:flywheel_spin", "property": "position", "signal": "Sense/spin_vis"},
        ]
    if extra:
        model.update(extra)
    return model


def reference(name, comment, x0, c, t_end, points, plots):
    D = Diagram()
    starts = {"psi": x0[0], "phi": x0[1], "gam": x0[2], "beta": x0[3], "tlt": d.S2 * x0[4],
              "u1": x0[5], "u2": x0[6], "u3": x0[7], "u4": x0[8], "u5": d.S2 * x0[9], "u6": x0[10],
              "x": x0[11], "y": x0[12]}
    D.node("Gyrover", "project:GyroverRef", 600, 300,
           params={"bsp": num(c.get("bsp", 0.0))}, starts={k: num(v) for k, v in starts.items()})
    vref, psiref = add_plan(D, c, 380, 600)
    D.node("Ctrl", "project:GyroCtrl", 600, 600, params=ctrl_params(c), starts={"r": num(d.S2 * x0[4])})
    for k in CTRL_SIGNALS:
        D.sig("Gyrover", k, "Ctrl", k)
    D.sig("Gyrover", "w3", "Ctrl", "w3")
    D.sig(*vref, "Ctrl", "v_ref")
    D.sig(*psiref, "Ctrl", "psi_ref")
    for k in ("tau1", "tau2", "tau3"):
        D.sig("Ctrl", k, "Gyrover", k)
    return {
        "format": "bgsim.model", "language": "0.1.0", "name": name, "$comment": comment,
        "diagram": {"nodes": D.nodes, "connections": D.conns, "subsystemPorts": [], "annotations": []},
        "settings": settings(t_end, points),
        "plots": plots,
    }


def x_init(v=0.0, phi=0.0, beta=0.0, th2=0.0, psid=0.0, w3=d.W3, x0=0.0, y0=0.0):
    x = np.zeros(17)
    x[1], x[3], x[4] = phi, beta, th2
    x[5] = psid
    x[7] = v / P["R"] - psid * np.sin(phi)
    x[10] = w3
    x[11], x[12] = x0, y0
    return x


def plots_bg(prefix="Sense"):
    return [
        {"id": "lean", "title": "Lean and tilt (paper theta0 - pi/2, theta2)", "signals": [f"{prefix}/lean", f"{prefix}/th2", "Ctrl/lean_ref"]},
        {"id": "heading", "title": "Heading", "signals": [f"{prefix}/heading"]},
        {"id": "speeds", "title": "Wheel rate and forward speed", "signals": [f"{prefix}/wz", f"{prefix}/v"]},
        {"id": "flywheel", "title": "Flywheel speed relative to the gimbal", "signals": ["Flywheel/w_rel"]},
        {"id": "path", "title": "Path of the wheel centre (y against x)", "signals": [f"{prefix}/yc", f"{prefix}/xc"]},
        {"id": "torques", "title": "Actuator torques", "signals": ["Ctrl/tau1", "Ctrl/tau2", "Ctrl/tau3"]},
        {"id": "energy", "title": "Energy", "signals": ["Energy/E", "Energy/loss", "Energy/Ebal"]},
    ]


def write(name, model):
    MODELS.mkdir(parents=True, exist_ok=True)
    path = MODELS / f"{name}.bgmodel.json"
    path.write_text(json.dumps(model, indent=2) + "\n", encoding="utf-8", newline="\n")
    print("wrote", path.relative_to(ROOT))


def plots_ref():
    return [
        {"id": "lean", "title": "Lean and tilt (paper theta0 - pi/2, theta2)", "signals": ["Gyrover/lean", "Gyrover/th2", "Ctrl/lean_ref"]},
        {"id": "heading", "title": "Heading", "signals": ["Gyrover/heading"]},
        {"id": "speeds", "title": "Wheel rate and forward speed", "signals": ["Gyrover/wz", "Gyrover/v"]},
        {"id": "path", "title": "Path of the wheel centre (y against x)", "signals": ["Gyrover/yc", "Gyrover/xc"]},
        {"id": "torques", "title": "Actuator torques", "signals": ["Ctrl/tau1", "Ctrl/tau2", "Ctrl/tau3"]},
        {"id": "energy", "title": "Energy", "signals": ["Gyrover/E", "Gyrover/Ek", "Gyrover/Ep"]},
    ]


def plots_paper(prefix):
    """The quantities of the paper's figure 3."""
    return [
        {"id": "fig3a", "title": "Pendulum and tilt angles (paper fig. 3, top)", "signals": [f"{prefix}/th1", f"{prefix}/th2"]},
        {"id": "fig3b", "title": "Roll and pitch rates (paper fig. 3, bottom)", "signals": [f"{prefix}/wx", f"{prefix}/w1"]},
        {"id": "lean", "title": "Lean and heading rate", "signals": [f"{prefix}/lean", f"{prefix}/yaw_rate"]},
        {"id": "torques", "title": "Actuator torques", "signals": ["Ctrl/tau1", "Ctrl/tau2"]},
    ]


# start of the showcase: the loop is centred on the viewer's 10 m ground grid
START = (-3.55, -4.42)
PLAN = dict(v_cruise=1.2, dpsi=float(np.pi / 2), t_go=1.0, tau_v=0.8, t_turn=5.5, t_leg=6.0, tau_psi=0.6)
DRIVE_C = dict(bal=1.0, servo=1.0, spin=1.0, head=1.0, plan=PLAN)
FREE_C = dict(servo=1.0, kd_t=0.0, joint_damping=False)
TURN_C = dict(bal=1.0, servo=1.0, spin=1.0, v_ref=1.5, lean0=0.12)
HOLD_C = dict(servo=1.0, spin=1.0)
# the close-up scene of the models that stay near the origin
CLOSE = "scenes/gyrover-close.sdf"
FIG3_C = dict(bal=1.0, servo=1.0, spin=1.0)


def dashboard():
    return {
        "autoRerun": False,
        "cards": [
            {"id": "speed", "kind": "slider", "size": "2x1", "title": "Cruise speed",
             "parameter": "Plan/v_cruise", "options": {"min": 0.5, "max": 2.5, "step": 0.1, "decimals": 1, "unit": "m/s"}},
            {"id": "turn", "kind": "slider", "size": "2x1", "title": "Heading change per turn",
             "parameter": "Plan/dpsi", "options": {"min": -3.0, "max": 3.0, "step": 0.05, "decimals": 2, "unit": "rad"}},
            {"id": "lean", "kind": "gauge", "size": "1x1", "title": "Lean", "signals": ["Sense/lean"],
             "options": {"min": -0.4, "max": 0.4, "decimals": 3, "unit": "rad",
                         "zones": [{"from": -0.4, "to": -0.3, "tone": "bad"}, {"from": -0.3, "to": -0.2, "tone": "warn"},
                                   {"from": -0.2, "to": 0.2, "tone": "good"}, {"from": 0.2, "to": 0.3, "tone": "warn"},
                                   {"from": 0.3, "to": 0.4, "tone": "bad"}]}},
            {"id": "v", "kind": "value", "size": "1x1", "title": "Speed", "signals": ["Sense/v"],
             "options": {"decimals": 2, "unit": "m/s", "sparkline": True}},
            {"id": "flywheel", "kind": "value", "size": "1x1", "title": "Flywheel", "signals": ["Flywheel/w_rel"],
             "options": {"decimals": 0, "unit": "rad/s", "sparkline": True}},
            {"id": "tilt", "kind": "gauge", "size": "1x1", "title": "Tilt", "signals": ["Sense/th2"],
             "options": {"min": -0.8, "max": 0.8, "decimals": 3, "unit": "rad"}},
            {"id": "heading", "kind": "plot", "size": "2x1", "title": "Heading and set-point",
             "signals": ["Sense/heading", "Plan/psi_ref"]},
            {"id": "torques", "kind": "plot", "size": "2x1", "title": "Drive and tilt torque",
             "signals": ["Ctrl/tau1", "Ctrl/tau2"]},
        ],
    }


def main(only=None):
    todo = {}
    # 0. the showcase: drive a rounded square (speed, steering and balance loops)
    x_rest = x_init(x0=START[0], y0=START[1])
    todo["gyrover"] = lambda: bond_graph(
        "gyrover", "The Gyrover drives a rounded square: it speeds up to 1.5 m/s and turns four times by 90 degrees. "
        "The paper's balance loops (K1 on the drive, K2 through the tilt servo) with our speed and heading loops.",
        x_rest, DRIVE_C, 30.0, 1501, plots_bg(), extra={"dashboard": dashboard()})
    todo["gyrover-ref"] = lambda: reference(
        "gyrover-ref", "The showcase mission on the reference model (GyroverRef, exact rolling).",
        x_rest, DRIVE_C, 30.0, 1501, plots_ref())
    # 1. free rolling: bond graph and reference, same start, tilt held by a lossless spring
    x_free = x_init(v=1.5, phi=0.05)
    todo["free"] = lambda: bond_graph(
        "free", "Free rolling at 1.5 m/s from a 0.05 rad lean, flywheel at 15 000 rpm, no drive; the tilt is held by "
        "the servo spring only (no damping), so the run is conservative except for the contact.",
        x_free, FREE_C, 6.0, 1201, plots_bg())
    todo["reference"] = lambda: reference(
        "reference", "Equation-based reference model (GyroverRef: exact rolling, Kane's equations) from the start of "
        "model `free`, with the same controller settings.", x_free, FREE_C, 6.0, 1201, plots_ref())
    # 2. steady turn (lateral loop holding a constant lean, speed loop at 1.5 m/s)
    st = d.steady_turn(0.1, 1.5)
    x_turn = x_init(v=1.5, phi=0.1, psid=st["psid"], beta=st["beta"])
    todo["steady-turn"] = lambda: bond_graph(
        "steady-turn", "Steady turn: speed loop at 1.5 m/s and the lateral loop holding a constant lean set-point; "
        "the run settles on a steady turn that is checked against the exact steady-turn solution.",
        x_turn, TURN_C, 10.0, 1001, plots_bg())
    todo["steady-turn-ref"] = lambda: reference(
        "steady-turn-ref", "Model `steady-turn` on the reference model.", x_turn, TURN_C, 10.0, 1001, plots_ref())
    # 3. gyroscopic stabilisation at rest: flywheel spinning vs stopped (tilt held, no drive)
    todo["spin"] = lambda: bond_graph(
        "spin", "Standing still, released at a 0.05 rad lean with the flywheel at 15 000 rpm and the tilt held: "
        "the gyroscope keeps it up (nutation and slow precession).", x_init(phi=0.05), HOLD_C, 5.0, 2001, plots_bg(), scene=CLOSE)
    todo["no-spin"] = lambda: bond_graph(
        "no-spin", "Model `spin` with the flywheel stopped: the Gyrover falls over.",
        x_init(phi=0.05, w3=0.0), dict(HOLD_C, spin=0.0, w3=0.0), 0.6, 601, plots_bg(), scene=CLOSE)
    # 4. the paper's figure 3: recovery from theta1 = 0.075, theta2 = -0.2 with K1, K2
    x_fig3 = x_init(beta=0.075 * d.SP, th2=-0.2 * d.S2)
    todo["fig3"] = lambda: bond_graph(
        "fig3", "The paper's figure 3 scenario: at rest, pendulum at 0.075 rad and tilt at -0.2 rad, recovered by the "
        "paper's gains K1 and K2 (true states instead of the paper's Kalman filter).",
        x_fig3, FIG3_C, 8.0, 1601, plots_paper("Sense"), scene=CLOSE)
    todo["fig3-ref"] = lambda: reference(
        "fig3-ref", "Model `fig3` on the reference model.", x_fig3, FIG3_C, 8.0, 1601, plots_paper("Gyrover"))
    todo["fig3-drill"] = lambda: reference(
        "fig3-drill", "Model `fig3-ref` with tyre drilling damping (0.3 N m s/rad): the damping destabilises the "
        "slow precession that the paper's K2 leaves at a zero pole.", x_fig3, dict(FIG3_C, bsp=0.3), 8.0, 1601,
        plots_paper("Gyrover"))
    for k in list(todo):
        if only and k not in only:
            del todo[k]
    for k, f in todo.items():
        write(k, f())


if __name__ == "__main__":
    main(sys.argv[1:] or None)
