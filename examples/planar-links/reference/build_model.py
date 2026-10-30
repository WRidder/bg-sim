"""Generate the Planar Links model documents (``../models/*.bgmodel.json``).

``uv run reference/build_model.py`` writes

* ``planar-links``         inverse dynamics: every joint's speed is prescribed by the CSV
                           (flow source), the model outputs the torque the joint needs;
* ``planar-links-fwd``     forward dynamics: the CSV torque drives the joint (effort source),
                           the model integrates the motion;
* ``planar-links-payload`` the 3-link arm with the 1 kg payload (RTB 4-link comparison).

One arm = ground + (joint, link frame, body) per link, built from the planar multibond
elements. Joint ``j`` of an arm has the drive train of the reference script: a source on the
joint-side 1-junction, a gear ``TF`` (ratio G) to a motor-side 1-junction with the motor
inertia ``Jm`` and viscous friction ``B``.
"""
from __future__ import annotations

import json
import math
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
OUT = HERE.parent / "models"

# a, m, r (COM w.r.t. the link END), Izz, B, G, Jm   (planar_robot.py, main())
LINKS = [
    dict(a=0.675, m=3.815, r=-0.291, I=0.310, B=0.02, G=12.0, Jm=0.000492),
    dict(a=0.525, m=3.690, r=-0.182, I=0.146, B=0.02, G=9.33, Jm=0.0004845),
    dict(a=0.370, m=4.0, r=-0.360, I=0.016, B=0.01, G=9.25, Jm=0.0001859),
]
PAYLOAD = dict(m=1.0, I=0.0, r=0.1)  # point mass 0.1 m beyond the end of link 3
G0 = 9.81
ARMS_IN_MODEL = ()  # set by build(); the base offsets only exist when several arms share a scene
BASE_X = [0.0, 2.0, 4.2]  # arm base x in the scene (m), by arm position in the model


def num(x):
    return repr(float(x))


class Model:
    def __init__(self, name):
        self.name = name
        self.nodes = []
        self.conns = []
        self._n = 0
        self._c = 0

    def node(self, name, block, params=None, constants=None, starts=None, pos=(0, 0)):
        self._n += 1
        nid = f"n{self._n:03d}"
        if block in ("0", "1"):
            blk = {"junction": block}
        else:
            blk = {"ref": block}
        self.nodes.append({
            "id": nid, "name": name, "block": blk,
            "position": {"x": pos[0], "y": pos[1]}, "rotation": 0, "flipX": False,
            "params": {k: str(v) for k, v in (params or {}).items()},
            "constants": constants or {},
            "starts": starts or {},
        })
        return nid

    def conn(self, kind, a, ap, b, bp):
        self._c += 1
        fr = {"node": a} if ap is None else {"node": a, "port": ap}
        to = {"node": b} if bp is None else {"node": b, "port": bp}
        self.conns.append({"id": f"c{self._c:03d}", "kind": kind, "from": fr, "to": to})

    def bond(self, a, ap, b, bp=None):
        self.conn("bond", a, ap, b, bp)

    def sig(self, a, ap, b, bp):
        self.conn("signal", a, ap, b, bp)

    def doc(self, plots, bindings, scene, t_end=1.0, comment=""):
        return {
            "format": "bgsim.model", "language": "0.1.0", "name": self.name,
            "$comment": comment,
            "diagram": {"nodes": self.nodes, "connections": self.conns},
            "settings": {"t_start": 0.0, "t_end": t_end, "solver": "auto", "reltol": 1e-9,
                         "abstol": 1e-11, "max_step": None,
                         "output": {"mode": "points", "points": 1001}, "event_limit": 10000},
            "plots": plots, "scene": {"file": scene}, "bindings": bindings,
        }


def link_params(k, payload):
    """Mass, COM offset c from the joint and inertia about the COM of link k (1-based)."""
    p = LINKS[k - 1]
    m, c, J = p["m"], p["a"] + p["r"], p["I"]
    if payload and k == 3:
        # lump the point payload into link 3: parallel axis theorem about the new COM
        xp = p["a"] + PAYLOAD["r"]
        mt = m + PAYLOAD["m"]
        cn = (m * c + PAYLOAD["m"] * xp) / mt
        J = J + m * (c - cn) ** 2 + PAYLOAD["I"] + PAYLOAD["m"] * (xp - cn) ** 2
        m, c = mt, cn
    return m, c, J


def build_arm(M, n, mode, variant, payload, col, csvfile):
    """Add the n-link arm to the model."""
    tag = f"A{n}"
    x0 = col * 2200
    y0 = 0
    if BASE_X[col] != 0.0 and len(ARMS_IN_MODEL) > 1:
        # the arm's x position in the 3D scene, so the scene_bindings check can sum it
        M.node(f"{tag}_BaseX", "stdlib:sources/Constant", params={"value": num(BASE_X[col])},
               pos=(x0, y0 - 200))
    ground = M.node(f"{tag}_Ground", "stdlib:multibond/GroundPlanar", pos=(x0, y0))
    csv_cols = ([f"qd{j}" for j in range(1, n + 1)] + [f"tau_rtb{j}" for j in range(1, n + 1)]
                + [f"tau_analytical{j}" for j in range(1, n + 1)]
                + [f"q{j}" for j in range(1, n + 1)])
    csv = M.node(f"{tag}_Csv", "stdlib:sources/CsvSource",
                 constants={"file": csvfile, "columns": ",".join(csv_cols),
                            "method": 2, "extrapolation": 0},
                 pos=(x0, y0 + 900))
    N = len(csv_cols)

    def pick(name, idx, pos):
        s = M.node(name, "stdlib:continuous/Select", constants={"N": N, "index": idx}, pos=pos)
        M.sig(csv, "y", s, "u")
        return s

    prev_node = ground          # the power node the next joint's parent port bonds to
    prev_port = "p"
    prev_pose = None
    for j in range(1, n + 1):
        m, c, J = link_params(j, payload)
        r_prev = LINKS[j - 2]["r"] if j > 1 else 0.0
        px = 0.0 if j == 1 else -r_prev      # pivot x in the parent body's COM frame
        q0 = -math.pi / 2 if j == 1 else 0.0
        bx = x0 + 150 + (j - 1) * 520
        joint_ref = ("stdlib:planar/Revolute2DRigid" if variant == "rigid"
                     else "stdlib:planar/Revolute2DCompliant")
        jp = {"rx": num(px), "ry": "0.0", "q0": num(q0)}
        if variant == "compliant":
            jp.update({"kt": "1e8", "bt": "1e5", "k": "0.0", "b": "0.0", "qrest": "0.0"})
        starts = {}
        if variant == "compliant" and n > 1:
            # static pivot deflection of the hanging arm (child +x points down): the link-j
            # pivot carries the weight of links j..n, so the model starts in equilibrium
            carried = sum(link_params(k, payload)[0] for k in range(j, n + 1))
            starts = {"d": f"[{carried * G0 / 1e8!r}, 0.0]"}
        jn = M.node(f"{tag}_Joint{j}", joint_ref, params=jp, starts=starts, pos=(bx, y0 + 200))
        ln = M.node(f"{tag}_Link{j}", "stdlib:planar/FixedJoint2D",
                    params={"x": num(c), "y": "0.0", "theta": "0.0"}, pos=(bx + 160, y0 + 200))
        bn = M.node(f"{tag}_Body{j}", "stdlib:planar/RigidBody2D",
                    params={"m": num(m), "J": num(J), "g0": num(G0 if n > 1 else 0.0)}, pos=(bx + 320, y0 + 330))
        # power chain
        if j == 1:
            M.bond(prev_node, prev_port, jn, "parent")       # ground -> shoulder
        else:
            M.bond(jn, "parent", prev_node, None)            # elbow -> body 1-junction
        M.bond(jn, "child", ln, "parent")
        if j < n:
            node1 = M.node(f"{tag}_N{j}", "1", pos=(bx + 320, y0 + 200))
            M.bond(ln, "child", node1, None)
            M.bond(bn, "p", node1, None)
            prev_node, prev_port = node1, None
        else:
            M.bond(ln, "child", bn, "p")
        # poses
        cm = M.node(f"{tag}_CoM{j}", "stdlib:planar/LocalPose2D", params={"x": num(c)},
                    pos=(bx + 160, y0 + 420))
        if j == 1:
            pj, pjport = jn, "pose"
        else:
            pjn = M.node(f"{tag}_PoseJ{j}", "stdlib:multibond/ComposePose2D", pos=(bx, y0 + 420))
            M.sig(prev_pose, "g", pjn, "gp")
            M.sig(jn, "pose", pjn, "gl")
            pj, pjport = pjn, "g"
        pb = M.node(f"{tag}_PoseB{j}", "stdlib:multibond/ComposePose2D", pos=(bx + 320, y0 + 480))
        M.sig(pj, pjport, pb, "gp")
        M.sig(cm, "g", pb, "gl")
        M.sig(pb, "g", bn, "g")
        prev_pose = pb
        if j == n:
            tipx = LINKS[n - 1]["a"] + (PAYLOAD["r"] if payload else 0.0)
            tip = M.node(f"{tag}_TipOffset", "stdlib:planar/LocalPose2D",
                         params={"x": num(tipx)}, pos=(bx + 480, y0 + 420))
            tp = M.node(f"{tag}_PoseTip", "stdlib:multibond/ComposePose2D", pos=(bx + 480, y0 + 480))
            M.sig(pj, pjport, tp, "gp")
            M.sig(tip, "g", tp, "gl")
        # drive train
        L = LINKS[j - 1]
        dy = y0 + 640
        J1 = M.node(f"{tag}_Drive{j}", "1", pos=(bx, dy))
        M.bond(J1, None, jn, "drive")
        tf = M.node(f"{tag}_Gear{j}", "stdlib:rotation/IdealGear", params={"n": num(L["G"])},
                    pos=(bx + 130, dy))
        M1 = M.node(f"{tag}_Motor{j}", "1", pos=(bx + 260, dy))
        jm = M.node(f"{tag}_Jm{j}", "stdlib:bondgraph/I", params={"i": num(L["Jm"])},
                    pos=(bx + 360, dy - 40))
        bm = M.node(f"{tag}_Bm{j}", "stdlib:bondgraph/R", params={"r": num(L["B"])},
                    pos=(bx + 360, dy + 40))
        M.bond(J1, None, tf, "b")       # joint side
        M.bond(tf, "a", M1, None)       # motor side, a.f = G b.f
        M.bond(M1, None, jm, "p")
        M.bond(M1, None, bm, "p")
        # source (+ torque sensor in inverse mode); CSV column order: qd, tau_rtb, tau_an, q
        if mode == "inverse":
            src = M.node(f"{tag}_Speed{j}", "stdlib:bondgraph/MSf", params={"gain": "1.0"},
                         pos=(bx - 260, dy))
            ts = M.node(f"{tag}_Torque{j}", "stdlib:converters/TorqueSensor", pos=(bx - 130, dy))
            M.bond(src, "p", ts, "b")
            M.bond(ts, "a", J1, None)
            qd = pick(f"{tag}_qd{j}", j, (bx - 260, dy + 120))
            M.sig(qd, "y", src, "u")
            rt = pick(f"{tag}_tau_rtb{j}", n + j, (bx - 130, dy + 120))
            an = pick(f"{tag}_tau_an{j}", 2 * n + j, (bx, dy + 120))
            er = M.node(f"{tag}_TauErr{j}", "project:TorqueError", pos=(bx + 130, dy + 120))
            M.sig(ts, "y", er, "tau")
            M.sig(rt, "y", er, "ref_rtb")
            M.sig(an, "y", er, "ref_an")
        else:
            src = M.node(f"{tag}_Torque{j}", "stdlib:bondgraph/MSe", params={"gain": "1.0"},
                         pos=(bx - 130, dy))
            M.bond(src, "p", J1, None)
            an = pick(f"{tag}_tau_an{j}", 2 * n + j, (bx - 130, dy + 120))
            M.sig(an, "y", src, "u")
            qref = pick(f"{tag}_q{j}", 3 * n + j, (bx, dy + 120))
            er = M.node(f"{tag}_QErr{j}", "project:AngleError",
                        params={"offset": num(q0 if variant == "rigid" else 0.0)},
                        pos=(bx + 130, dy + 120))
            M.sig(jn, "qout", er, "q")
            M.sig(qref, "y", er, "ref")


def build(name, mode, variant, arms, payload, scene):
    global ARMS_IN_MODEL
    ARMS_IN_MODEL = arms
    M = Model(name)
    for col, n in enumerate(arms):
        csvfile = "data/arm3p.csv" if (payload and n == 3) else f"data/arm{n}.csv"
        build_arm(M, n, mode, variant, payload, col, csvfile)
    plots, bindings = [], []
    for n in arms:
        tag = f"A{n}"
        if mode == "inverse":
            plots.append({"id": f"tau{n}", "title": f"{n}-link: joint torque error vs RTB",
                          "signals": [f"{tag}_TauErr{j}/e_rtb" for j in range(1, n + 1)]})
            plots.append({"id": f"tauan{n}", "title": f"{n}-link: joint torque error vs analytical",
                          "signals": [f"{tag}_TauErr{j}/e_an" for j in range(1, n + 1)]})
            plots.append({"id": f"torque{n}", "title": f"{n}-link: required joint torque",
                          "signals": [f"{tag}_Torque{j}/y" for j in range(1, n + 1)]})
        else:
            plots.append({"id": f"q{n}", "title": f"{n}-link: angle drift vs CSV",
                          "signals": [f"{tag}_QErr{j}/e" for j in range(1, n + 1)]})
        for j in range(1, n + 1):
            bindings.append({"target": f"joint:a{n}_joint{j}", "property": "position",
                             "signal": f"{tag}_Joint{j}/qout"})
    return M.doc(plots, bindings, scene)


def sdf_scene(arms, payload, title):
    """An SDF scene (x right, z up; the model's x-y plane is the SDF x-z plane)."""
    out = ['<?xml version="1.0"?>', "<!--",
           f"  {title}",
           "  The model is planar in its x-y plane with gravity along -y; the scene uses the SDF X-Z",
           "  plane (model x is SDF x, model y is SDF z). Counter-clockwise joint angles are rotations",
           "  about -Y. Each joint is bound to the relative angle of its joint (qout, rad); the scene",
           "  pose is the stretched arm (all angles 0), the model starts with joint 1 at -pi/2.",
           "-->", '<sdf version="1.9">', '  <model name="planar_links">']
    joints = []
    for col, n in enumerate(arms):
        x0 = BASE_X[col] if len(arms) > 1 else 0.0
        out += [f'    <link name="a{n}_base">', f"      <pose>{x0} 0 0 0 0 0</pose>",
                '      <visual name="a%d_pedestal">' % n,
                "        <pose>0 0 -0.12 0 0 0</pose>",
                "        <geometry><cylinder><radius>0.07</radius><length>0.24</length></cylinder></geometry>",
                "        <material><diffuse>0.45 0.47 0.5 1</diffuse></material>", "      </visual>",
                '      <visual name="a%d_floor">' % n, "        <pose>0 0 -0.25 0 0 0</pose>",
                "        <geometry><box><size>0.9 0.4 0.02</size></box></geometry>",
                "        <material><diffuse>0.3 0.3 0.33 1</diffuse></material>", "      </visual>",
                "    </link>"]
        reach = 0.0
        parent = f"a{n}_base"
        colors = ["0.25 0.5 0.85 1", "0.35 0.7 0.45 1", "0.85 0.45 0.25 1"]
        for j in range(1, n + 1):
            a = LINKS[j - 1]["a"]
            m, c, _ = link_params(j, payload)
            out += [f'    <link name="a{n}_link{j}">', f"      <pose>{x0 + reach!r} 0 0 0 0 0</pose>",
                    f'      <visual name="a{n}_bar{j}">', f"        <pose>{a / 2!r} 0 0 0 0 0</pose>",
                    f"        <geometry><box><size>{a!r} {0.05 - 0.008 * (j - 1)!r} {0.05 - 0.008 * (j - 1)!r}</size></box></geometry>",
                    f"        <material><diffuse>{colors[j - 1]}</diffuse></material>", "      </visual>",
                    f'      <visual name="a{n}_hub{j}">', "        <pose>0 0 0 1.5707963 0 0</pose>",
                    "        <geometry><cylinder><radius>0.04</radius><length>0.07</length></cylinder></geometry>",
                    "        <material><diffuse>0.2 0.2 0.22 1</diffuse></material>", "      </visual>",
                    f'      <visual name="a{n}_com{j}">', f"        <pose>{c!r} 0 0 0 0 0</pose>",
                    "        <geometry><sphere><radius>0.02</radius></sphere></geometry>",
                    "        <material><diffuse>0.95 0.9 0.2 1</diffuse></material>", "      </visual>"]
            if j == n and payload:
                out += [f'      <visual name="a{n}_payload">',
                        f"        <pose>{a + PAYLOAD['r']!r} 0 0 0 0 0</pose>",
                        "        <geometry><sphere><radius>0.04</radius></sphere></geometry>",
                        "        <material><diffuse>0.9 0.55 0.1 1</diffuse></material>", "      </visual>"]
            out.append("    </link>")
            joints.append((f"a{n}_joint{j}", parent, f"a{n}_link{j}"))
            parent = f"a{n}_link{j}"
            reach += a
    for name, par, ch in joints:
        out += [f'    <joint name="{name}" type="revolute">', f"      <parent>{par}</parent>",
                f"      <child>{ch}</child>", "      <axis>", "        <xyz>0 -1 0</xyz>",
                "      </axis>", "    </joint>"]
    out += ["  </model>", "</sdf>", ""]
    return "\n".join(out)


def main():
    OUT.mkdir(exist_ok=True)
    scenes = HERE.parent / "scenes"
    scenes.mkdir(exist_ok=True)
    for fname, arms, payload, title in (
        ("planar-links.sdf", (1, 2, 3), False, "Planar Links: the 1-, 2- and 3-link arms side by side."),
        ("planar-links-payload.sdf", (3,), True, "Planar Links: the 3-link arm with the 1 kg payload."),
    ):
        with open(scenes / fname, "w", newline="\n") as f:
            f.write(sdf_scene(arms, payload, title))
    scene = "scenes/planar-links.sdf"
    docs = {
        "planar-links": build("PlanarLinks", "inverse", "compliant", (1, 2, 3), False, scene),
        "planar-links-fwd": build("PlanarLinksForward", "forward", "compliant", (1, 2, 3), False, scene),
        "planar-links-payload": build("PlanarLinksPayload", "inverse", "compliant", (3,), True, "scenes/planar-links-payload.sdf"),
    }
    only = sys.argv[1:] or list(docs)
    for key in only:
        with open(OUT / f"{key}.bgmodel.json", "w", newline="\n") as f:
            json.dump(docs[key], f, indent=2)
            f.write("\n")
        print("wrote", key)


if __name__ == "__main__":
    main()
