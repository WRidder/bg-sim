# /// script
# requires-python = ">=3.11"
# dependencies = ["numpy>=2.0"]
# ///
"""Write the fem-torsion example: model, scene, expected checks.

The two-disk torsion rig of `flex-torsion`, with the shaft as a FEM flexible body
(`ModalBody3D`) instead of the assumed-modes beam: two steel disks on a slender aluminium shaft
hang from a bearing; a motor torque pulse on the upper disk sets the pair spinning and twisting.

The shaft's reduced model comes from the part spec `design/shaft.fem.json` (quadratic
tetrahedra, Craig-Bampton with the two end faces as interfaces and 4 fixed-interface modes):

    julia --project=julia/BGSimFEM julia/BGSimFEM/bin/bgsim-fem.jl examples/fem-torsion/design/shaft.fem.json
    uv run examples/fem-torsion/design/build.py

The point: the assumed-modes beam with 3 clamped-free torsion modes is 3.5 % too stiff for this
rig (heavy end disks, the shaft twists almost linearly, a sine series converges slowly to that).
The Craig-Bampton basis has the static constraint modes of interface B, so the linear twist is
in the basis exactly and the first torsional frequency matches the exact transcendental root.
"""

from __future__ import annotations

import json
import math
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
NAME = "fem-torsion"
MODAL_FILE = "data/shaft.modal.json"

# shaft (aluminium) and disks (steel)
RHO, E, NU = 2700.0, 70.0e9, 0.33
D, L = 0.006, 1.0
ZETA = 0.002
R_DISK, T_DISK, RHO_DISK = 0.08, 0.02, 7850.0
# motor pulse
T0, T_ON, T_PULSE = 1.0, 0.05, 0.1
T_END = 5.0
# joints: compliant bearing/welds (stiff), weld torsion springs
KT, KR, KW = 1.0e8, 1.0e5, 1.0e5

S2 = math.sqrt(0.5)
M_DISK = RHO_DISK * math.pi * R_DISK**2 * T_DISK
J_AX = 0.5 * M_DISK * R_DISK**2
J_TR = 0.25 * M_DISK * R_DISK**2 + M_DISK * T_DISK**2 / 12
G = E / (2 * (1 + NU))
IP = math.pi * D**4 / 32
J_SHAFT = RHO * IP * L
K_SHAFT = G * IP / L
C_T = math.sqrt(G / RHO)
MU = J_AX / J_SHAFT

MODAL = json.loads((ROOT / MODAL_FILE).read_text())
NM = MODAL["nm"]
# the torsion coordinate: the mode that rotates interface B most about the shaft axis (x)
_PRB = MODAL["interfaces"][1]["rotation"]
K_TORSION = 1 + max(range(NM), key=lambda k: abs(_PRB[0][k]) / (1e-30 + math.sqrt(sum(_PRB[a][k] ** 2 for a in range(3)) + sum(r[k] ** 2 for r in MODAL["interfaces"][1]["translation"]))))
TWIST_PER_ETA = _PRB[0][K_TORSION - 1]


def torsion_psi(n: int, xi: float) -> float:
    return math.sqrt(2) * math.sin((2 * n - 1) * math.pi * xi / 2)


def ritz(nt: int) -> float:
    """First torsional frequency of the assumed-modes beam (rigid rotation + nt clamped-free
    torsion modes) with the disks at its ends: what FlexibleBeam3D gives (example flex-torsion)."""
    at = [math.sqrt(2) * 2 / ((2 * n - 1) * math.pi) for n in range(1, nt + 1)]
    m = np.zeros((nt + 1, nt + 1))
    k = np.zeros((nt + 1, nt + 1))
    m[0, 0] = 2 * MU + 1
    for i in range(nt):
        m[0, i + 1] = m[i + 1, 0] = at[i] + MU * torsion_psi(i + 1, 1.0)
        for j in range(nt):
            m[i + 1, j + 1] = (i == j) + MU * torsion_psi(i + 1, 1.0) * torsion_psi(j + 1, 1.0)
        k[i + 1, i + 1] = ((2 * i + 1) / 2 * math.pi) ** 2
    ev = np.linalg.eigvals(np.linalg.solve(m, k)).real
    return math.sqrt(min(e for e in ev if e > 1e-9)) * C_T / L


def exact() -> float:
    def f(z):
        return 2 * MU * z * math.cos(z) + (1 - MU * MU * z * z) * math.sin(z)

    zs = np.linspace(1e-9, math.pi - 1e-9, 400001)
    vals = [f(z) for z in zs]
    i = next(i for i in range(len(zs) - 1) if (vals[i] > 0) != (vals[i + 1] > 0))
    a, b = zs[i], zs[i + 1]
    for _ in range(200):
        c = (a + b) / 2
        if (f(c) > 0) == (f(a) > 0):
            a = c
        else:
            b = c
    return (a + b) / 2 * C_T / L


W_RITZ3 = ritz(3)
W_EXACT = exact()
W_MASSLESS = math.sqrt(K_SHAFT * 2 / J_AX)
# the FEM shaft's own torsional stiffness: the torsion coordinate's static stiffness seen at B
K_FEM = MODAL["modal_stiffness"][K_TORSION - 1] / TWIST_PER_ETA**2
W_FEM_MASSLESS = math.sqrt(K_FEM * 2 / J_AX)


def fmt(x: float) -> str:
    return repr(float(x))


def node(nid, name, ref, x, y, params=None, constants=None):
    return {
        "id": nid,
        "name": name,
        "block": {"ref": f"stdlib:{ref}"},
        "position": {"x": x, "y": y},
        "rotation": 0,
        "flipX": False,
        "params": params or {},
        "constants": constants or {},
        "starts": {},
        "ui": {"showLabel": True, "color": None},
    }


def end(nid, port):
    return {"node": nid, "port": port}


def conn(cid, kind, a, ap, b, bp):
    return {"id": cid, "kind": kind, "from": end(a, ap), "to": end(b, bp), "route": [], "label": None}


def joint_params():
    return {
        "kt": fmt(KT), "kr": fmt(KR),
        "bt": fmt(2 * 0.05 * math.sqrt(KT * M_DISK)), "br": fmt(2 * 0.05 * math.sqrt(KR * J_TR)),
    }


def model() -> dict:
    nodes = [
        node("n1", "World", "multibond/GroundSpatial", 40, 300),
        node("n2", "Bearing", "spatial/Revolute3D", 220, 300, joint_params()),
        node("n3", "Disk1", "spatial/RigidBody3D", 400, 300,
             {"m": fmt(M_DISK), "J": f"[{fmt(J_TR)}, {fmt(J_TR)}, {fmt(J_AX)}]"}),
        node("n4", "Weld1", "spatial/Revolute3D", 580, 300, joint_params()),
        node("n5", "Mount", "multibond/FixedTransform3DNeutral", 760, 300, {"qw": fmt(S2), "qy": fmt(S2)}),
        node("n6", "Shaft", "spatial/ModalBody3D", 940, 300, {"zeta": fmt(ZETA)}, {"file": MODAL_FILE}),
        node("n7", "Weld2", "spatial/Revolute3D", 1120, 300, joint_params()),
        node("n8", "Disk2", "spatial/RigidBody3D", 1300, 300,
             {"m": fmt(M_DISK), "J": f"[{fmt(J_AX)}, {fmt(J_TR)}, {fmt(J_TR)}]"}),
        node("n9", "Ground", "rotation/FixedShaft", 40, 120),
        node("n10", "Motor", "rotation/TorqueSource", 220, 120, {"T": fmt(T0)}),
        node("n11", "Pulse", "sources/Pulse", 220, 20,
             {"amplitude": "1.0", "period": "1000.0", "duty": fmt(T_PULSE / 1000.0), "t_start": fmt(T_ON)}),
        node("n12", "WeldGround1", "rotation/FixedShaft", 580, 120),
        node("n13", "WeldSpring1", "rotation/TorsionSpring", 580, 200, {"k": fmt(KW)}),
        node("n14", "WeldGround2", "rotation/FixedShaft", 1120, 120),
        node("n15", "WeldSpring2", "rotation/TorsionSpring", 1120, 200, {"k": fmt(KW)}),
        node("n16", "Twist", "continuous/Gain", 1120, 560, {"k": fmt(TWIST_PER_ETA)}),
        node("n20", "Origin", "spatial/LocalPose3D", 220, 480),
        node("n21", "PDisk1", "multibond/ComposePose3D", 400, 480),
        node("n22", "PWeld1", "multibond/ComposePose3D", 580, 480),
        node("n23", "MountPose", "spatial/LocalPose3D", 760, 560, {"qw": fmt(S2), "qy": fmt(S2)}),
        node("n24", "PShaftA", "multibond/ComposePose3D", 760, 480),
        node("n25", "PDisk2", "multibond/ComposePose3D", 1300, 480),
        node("n26", "EtaT", "continuous/Select", 940, 560, {}, {"N": str(NM), "index": str(K_TORSION)}),
    ]
    conns = [
        conn("c1", "bond", "n1", "p", "n2", "parent"),
        conn("c2", "bond", "n2", "child", "n3", "p"),
        conn("c3", "bond", "n3", "p", "n4", "parent"),
        conn("c4", "bond", "n4", "child", "n5", "a"),
        conn("c5", "bond", "n5", "b", "n6", "A"),
        conn("c6", "bond", "n6", "B", "n7", "parent"),
        conn("c7", "bond", "n7", "child", "n8", "p"),
        conn("c8", "wire", "n9", "a", "n10", "a"),
        conn("c9", "wire", "n10", "b", "n2", "drive"),
        conn("c10", "signal", "n11", "y", "n10", "u"),
        conn("c11", "wire", "n12", "a", "n13", "a"),
        conn("c12", "wire", "n13", "b", "n4", "drive"),
        conn("c13", "wire", "n14", "a", "n15", "a"),
        conn("c14", "wire", "n15", "b", "n7", "drive"),
        conn("c20", "signal", "n20", "g", "n21", "gp"),
        conn("c21", "signal", "n2", "pose", "n21", "gl"),
        conn("c22", "signal", "n21", "g", "n3", "g"),
        conn("c23", "signal", "n21", "g", "n22", "gp"),
        conn("c24", "signal", "n4", "pose", "n22", "gl"),
        conn("c25", "signal", "n22", "g", "n24", "gp"),
        conn("c26", "signal", "n23", "g", "n24", "gl"),
        conn("c27", "signal", "n24", "g", "n6", "gA"),
        conn("c28", "signal", "n6", "poseB", "n25", "gp"),
        conn("c29", "signal", "n7", "pose", "n25", "gl"),
        conn("c30", "signal", "n25", "g", "n8", "g"),
        conn("c31", "signal", "n6", "eta", "n26", "u"),
        conn("c32", "signal", "n26", "y", "n16", "u"),
    ]

    def pose(link, sig):
        return {"target": f"link:{link}", "property": "pose", "signal": [f"{sig}[{i}]" for i in range(1, 8)]}

    bindings = [
        pose("disk1", "PDisk1/g"),
        pose("shaft", "Shaft/pose"),
        pose("disk2", "PDisk2/g"),
        {
            "target": "visual:shaft_mesh",
            "property": "mode-shapes",
            "signal": [f"Shaft/eta[{i}]" for i in range(1, NM + 1)],
        },
    ]
    return {
        "format": "bgsim.model",
        "language": "0.1.0",
        "name": NAME,
        "diagram": {"nodes": nodes, "connections": conns, "subsystemPorts": [], "annotations": []},
        "settings": {
            "t_start": 0.0,
            "t_end": T_END,
            "solver": "Rodas5P",
            "reltol": 1e-08,
            "abstol": 1e-11,
            "max_step": None,
            "output": {"mode": "points", "points": 10001},
            "event_limit": 10000,
        },
        "plots": [
            {"id": "p1", "title": "Upper disk angle (rad) and shaft twist (rad)", "signals": ["Bearing/qout", "Twist/y"]},
            {"id": "p2", "title": "Modal coordinates (m)", "signals": [f"Shaft/eta[{i}]" for i in range(1, NM + 1)]},
            {"id": "p3", "title": "Upper disk speed (rad/s) and motor torque (N m)", "signals": ["Bearing/qdout", "Motor/a.e"]},
        ],
        "scene": {"file": f"scenes/{NAME}.sdf"},
        "bindings": bindings,
    }


def scene() -> str:
    return f"""<?xml version="1.0"?>
<!--
  fem-torsion: two steel disks on a slender aluminium shaft (a FEM flexible body), hanging
  from a bearing.

  Z-up, metres, the world frame of the model. The bearing (Revolute3D, axis world z) is the
  origin; the shaft hangs down to z = -{L:g}. The links follow the model's poses:

    disk1   PDisk1/g    the bearing's child frame (z = shaft axis)
    shaft   Shaft/pose  the shaft's reference frame: interface A, x along the shaft (down)
    disk2   PDisk2/g    the lower weld's child frame (x along the shaft)

  The shaft visual `shaft_mesh` is the GLB the reduction wrote (meshes/shaft.glb, in the
  reference frame, one morph target per mode); a mode-shapes binding deforms it with
  Shaft/eta[1..{NM}].
-->
<sdf version="1.9">
  <model name="fem_torsion">
    <link name="frame">
      <pose>0 0 0 0 0 0</pose>
      <visual name="bearing_housing">
        <pose>0 0 0.04 0 0 0</pose>
        <geometry><cylinder><radius>0.03</radius><length>0.04</length></cylinder></geometry>
        <material><diffuse>0.2 0.2 0.22 1</diffuse></material>
      </visual>
      <visual name="top_beam">
        <pose>0 0 0.08 0 0 0</pose>
        <geometry><box><size>0.5 0.06 0.04</size></box></geometry>
        <material><diffuse>0.45 0.47 0.5 1</diffuse></material>
      </visual>
      <visual name="post_left">
        <pose>-0.23 0 -0.6 0 0 0</pose>
        <geometry><box><size>0.04 0.06 1.32</size></box></geometry>
        <material><diffuse>0.45 0.47 0.5 1</diffuse></material>
      </visual>
      <visual name="post_right">
        <pose>0.23 0 -0.6 0 0 0</pose>
        <geometry><box><size>0.04 0.06 1.32</size></box></geometry>
        <material><diffuse>0.45 0.47 0.5 1</diffuse></material>
      </visual>
      <visual name="floor">
        <pose>0 0 -1.27 0 0 0</pose>
        <geometry><box><size>0.8 0.5 0.02</size></box></geometry>
        <material><diffuse>0.55 0.57 0.6 1</diffuse></material>
      </visual>
    </link>

    <link name="disk1">
      <pose>0 0 0 0 0 0</pose>
      <visual name="disk1_body">
        <geometry><cylinder><radius>{R_DISK}</radius><length>{T_DISK}</length></cylinder></geometry>
        <material><diffuse>0.25 0.5 0.85 1</diffuse></material>
      </visual>
      <visual name="disk1_mark">
        <pose>{R_DISK - 0.015} 0 0.012 0 0 0</pose>
        <geometry><box><size>0.03 0.012 0.006</size></box></geometry>
        <material><diffuse>0.95 0.95 0.95 1</diffuse></material>
      </visual>
    </link>

    <link name="shaft">
      <pose>0 0 0 0 1.570796 0</pose>
      <visual name="shaft_mesh">
        <geometry><mesh><uri>meshes/shaft.glb</uri></mesh></geometry>
      </visual>
    </link>

    <link name="disk2">
      <pose>0 0 -{L} 0 1.570796 0</pose>
      <visual name="disk2_body">
        <pose>0 0 0 0 1.570796 0</pose>
        <geometry><cylinder><radius>{R_DISK}</radius><length>{T_DISK}</length></cylinder></geometry>
        <material><diffuse>0.9 0.55 0.1 1</diffuse></material>
      </visual>
      <visual name="disk2_mark">
        <pose>-0.012 0 {R_DISK - 0.015} 0 0 0</pose>
        <geometry><box><size>0.006 0.012 0.03</size></box></geometry>
        <material><diffuse>0.95 0.95 0.95 1</diffuse></material>
      </visual>
    </link>
  </model>
</sdf>
"""


def expected() -> dict:
    f_exact = W_EXACT / (2 * math.pi)
    f_ritz = W_RITZ3 / (2 * math.pi)
    return {
        "project": NAME,
        "description": "Two disks on a torsion shaft, the shaft a FEM flexible body (ModalBody3D, Craig-Bampton: 4 fixed-interface + 6 constraint modes): the first torsional frequency matches the exact transcendental root to 0.2 %, where the assumed-modes beam with 3 torsion modes (flex-torsion) is 3.5 % too high.",
        "models": {
            NAME: {
                "checks": [
                    {"kind": "no_diagnostics", "codes": ["E101", "E102", "E108", "W201", "W202"]},
                    {"kind": "scene_bindings"},
                    {
                        "kind": "fft_peak", "signal": "Twist/y", "from_t": 0.3, "to_t": T_END,
                        "min_hz": 1.0, "max_hz": 20.0, "value": f_exact, "rtol": 0.004,
                        "note": f"exact root of 2 mu z cos z + (1 - mu^2 z^2) sin z = 0 (mu = {MU:.1f}): {W_EXACT:.5f} rad/s = {f_exact:.5f} Hz. The assumed-modes beam with 3 torsion modes gives {f_ritz:.5f} Hz (+{(W_RITZ3 / W_EXACT - 1) * 100:.2f} %), outside this tolerance",
                    },
                    {
                        "kind": "max_abs", "signal": "Twist/y", "from_t": 0.0, "to_t": T_END,
                        "value": 0.27, "rtol": 0.05, "note": "the largest twist, about 15 degrees (as flex-torsion)",
                    },
                ]
            }
        },
    }


def main() -> None:
    (ROOT / "models").mkdir(parents=True, exist_ok=True)
    (ROOT / "scenes").mkdir(parents=True, exist_ok=True)
    with open(ROOT / "models" / f"{NAME}.bgmodel.json", "w", newline="\n") as f:
        json.dump(model(), f, indent=2)
        f.write("\n")
    with open(ROOT / "scenes" / f"{NAME}.sdf", "w", newline="\n") as f:
        f.write(scene())
    with open(ROOT / "expected.json", "w", newline="\n") as f:
        json.dump(expected(), f, indent=2)
        f.write("\n")
    with open(ROOT / "bgsim.project.json", "w", newline="\n") as f:
        json.dump({"format": "bgsim.project", "language": "0.1.0", "name": NAME, "models": [NAME],
                   "libraryDir": "library", "scenesDir": "scenes"}, f, indent=2)
        f.write("\n")
    print(f"disk m {M_DISK:.4f} kg, J {J_AX:.6f} kg m^2; shaft k {K_SHAFT:.4f} N m/rad, J {J_SHAFT:.3e}, mu {MU:.1f}")
    print(f"FEM shaft: nm {NM}, torsion coordinate eta[{K_TORSION}] ({MODAL['frequency_hz'][K_TORSION - 1]:.2f} Hz clamped), "
          f"twist per eta {TWIST_PER_ETA:.3f} rad/m, k_FEM {K_FEM:.4f} N m/rad ({K_FEM / K_SHAFT - 1:+.3%} vs G Ip / L)")
    print(f"exact {W_EXACT:.6f} rad/s ({W_EXACT / 2 / math.pi:.5f} Hz), massless {W_MASSLESS:.6f}, "
          f"FEM massless {W_FEM_MASSLESS:.6f} ({W_FEM_MASSLESS / W_EXACT - 1:+.3%}), "
          f"assumed modes nt=3 {W_RITZ3:.6f} ({W_RITZ3 / W_EXACT - 1:+.3%})")


if __name__ == "__main__":
    main()
