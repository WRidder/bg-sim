# /// script
# requires-python = ">=3.11"
# dependencies = ["numpy>=2.0", "scipy>=1.13", "trimesh>=4.0"]
# ///
"""Writes `models/sequence-contact.bgmodel.json`, `scenes/tetra-3d.sdf` and `meshes/tetra.glb`.

The diagram uses the wiring and the layout of `examples/cube-pyramid-3d/models/sequence-contact.bgmodel.json`
(floating body on a `PoseIntegrator3D`, a `ContactPoint` per vertex, four driven wheels with their own
pose integrators for the 3D scene, `TipSequencer` -> `Allocator`), and replaces what is specific to the
cube: the geometry (`design.py`), the vertex positions, the wheel mounts (spin axis along the face
normal, wheel centre `DW` inside the face), the sensors and the scene bindings.

Run it with ``uv run examples/tetra-3d/design/build_model.py`` (needs the cube example next to it).
"""

from __future__ import annotations

import copy
import json
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
import design as d  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
TEMPLATE = ROOT.parent / "cube-pyramid-3d" / "models" / "sequence-contact.bgmodel.json"

# ------------------------------------------------------------------ parameters of this example
FIRMWARE = dict(t1=d.FW["t1"], t2=d.FW["t2"], Tf=d.FW["Tf"], Tr1=d.FW["Tr1"], Tr2=d.FW["Tr2"])
T_END = 3.8
K_CONTACT, XREF = 2.0e4, 1.0e-3


def num(x: float) -> str:
    return repr(float(x))


def vec(values) -> str:
    return "[" + ", ".join(num(v) for v in values) + "]"


def rest_penetration(load: float) -> float:
    """delta with k delta sqrt(delta / xref) = load (the ContactPoint law)."""
    return (load / K_CONTACT * np.sqrt(XREF)) ** (2.0 / 3.0)


def rpy(q: np.ndarray) -> tuple[float, float, float]:
    """SDF roll, pitch, yaw (R = Rz Ry Rx) of the quaternion (w x y z)."""
    rot = d.quat_rot(q)
    pitch = -np.arcsin(np.clip(rot[2, 0], -1, 1))
    if abs(rot[2, 0]) < 1 - 1e-9:
        return float(np.arctan2(rot[2, 1], rot[2, 2])), float(pitch), float(np.arctan2(rot[1, 0], rot[0, 0]))
    return float(np.arctan2(-rot[1, 2], rot[1, 1])), float(pitch), 0.0


def build_model() -> dict:
    model = json.loads(TEMPLATE.read_text(encoding="utf-8"))
    diagram = model["diagram"]
    nodes = {n["name"]: n for n in diagram["nodes"]}

    pz0 = d.RIN - rest_penetration(d.M_TOT * d.G0 / 3.0)

    model["name"] = "sequence-contact"
    model["$comment"] = (
        "Face -> edge -> vertex on four vertex contacts: the regular tetrahedron with a reaction wheel on each face "
        "starts on its base face, the scripted torque profile (TipSequencer + Allocator, 1 ms) tips it onto the edge "
        "v2-v3, holds it, then onto the vertex v3 and holds it."
    )
    model["settings"].update({
        "t_end": T_END,
        "output": {"mode": "points", "points": int(T_END * 200) + 1},
    })

    # body and pose
    body = nodes["Cube"]
    body["name"] = "Tetra"
    body["params"] = {"m": num(d.M_BODY), "J": vec([d.J_BODY] * 3), "g0": "9.81"}
    nodes["Pose"]["starts"]["pz"] = num(pz0)

    # sensors
    sense = nodes["Sense"]
    sense["block"] = {"ref": "project:TetraSense"}
    sense["params"] = {"m": num(d.M_TOT), "g0": "9.81"}
    nodes["EnCube"]["name"] = "EnBody"
    nodes["EnBody"] = nodes.pop("EnCube")
    nodes["EnBody"]["params"] = {"m": num(d.M_BODY), "g0": "9.81"}

    # contacts at the four vertices
    for k in range(4):
        v = d.VERT[k]
        nodes[f"Mount{k + 1}"]["params"] = {"x": num(-v[0]), "y": num(-v[1]), "z": num(-v[2])}
        nodes[f"Local{k + 1}"]["params"] = {"x": num(v[0]), "y": num(v[1]), "z": num(v[2])}

    # the cube had eight vertex inputs on the sensors; the tetrahedron has four
    zero_id = nodes["Zero"]["id"]
    diagram["nodes"] = [n for n in diagram["nodes"] if n["id"] != zero_id]
    diagram["connections"] = [c for c in diagram["connections"]
                              if c["from"]["node"] != zero_id and c["to"]["node"] != zero_id]

    # firmware
    seq = nodes["Seq"]
    seq["params"] = {"m": num(d.M_TOT), "g0": "9.81", "L": num(d.L), "Jw": num(d.JA),
                     **{k: num(v) for k, v in FIRMWARE.items()}}
    nodes["Alloc"]["params"] = {"k_t": "0.1", "tau_max": num(d.TAU_MAX)}
    nodes["Tap"]["params"] = {}
    nodes["Ledger"]["params"].update({"k_t": "0.1", "R_m": num(d.RM)})

    # wheels on the face normals
    quats = d.wheel_quats()
    for k in range(4):
        q, a = quats[k], d.AXES[k]
        qc = np.array([q[0], -q[1], -q[2], -q[3]])
        nodes[f"WMount{k + 1}"]["params"] = {
            "qw": num(qc[0]), "qx": num(qc[1]), "qy": num(qc[2]), "qz": num(qc[3]),
            "x": "0.0", "y": "0.0", "z": num(-d.DW),
        }
        nodes[f"WLocal{k + 1}"]["params"] = {
            "qw": num(q[0]), "qx": num(q[1]), "qy": num(q[2]), "qz": num(q[3]),
            "x": num(d.DW * a[0]), "y": num(d.DW * a[1]), "z": num(d.DW * a[2]),
        }
        nodes[f"Wheel{k + 1}"]["params"]["m"] = num(d.M_WHEEL)
        nodes[f"Wheel{k + 1}"]["params"]["J"] = vec([d.JT, d.JT, d.JA])
        nodes[f"Drv{k + 1}"]["params"]["k_t"] = "0.1"
        nodes[f"EnW{k + 1}"]["params"]["m"] = num(d.M_WHEEL)

    model["plots"] = [
        {"id": "p1", "title": "Attitude error to the edge and vertex balance", "signals": ["Sense/ang_edge", "Sense/ang_vert", "Seq/ph"]},
        {"id": "p2", "title": "Vertex loads", "signals": ["C1/f_n", "C2/f_n", "C3/f_n", "C4/f_n"]},
        {"id": "p3", "title": "Wheel speeds (relative to the body)", "signals": [f"WJoint{k}/qdout" for k in range(1, 5)]},
        {"id": "p4", "title": "Motor torques", "signals": [f"Tap/t{k}" for k in range(1, 5)]},
        {"id": "p5", "title": "Motor terminal voltage", "signals": [f"Ledger/v{k}" for k in range(1, 5)]},
        {"id": "p6", "title": "Height of the centre of mass", "signals": ["Sense/zc"]},
        {"id": "p7", "title": "Realised body torque", "signals": ["Tap/Tbx", "Tap/Tby", "Tap/Tbz"]},
    ]
    model["scene"] = {"file": "scenes/tetra-3d.sdf"}
    # The body follows its world pose (PoseIntegrator3D exposes the seven components with units: the
    # viewer wants m on the position of a pose binding); each wheel hangs on a revolute joint of the SDF
    # tree whose position is the model's joint angle `WJointk/q` (rad, relative to the body).
    model["bindings"] = [{"target": "link:tetra", "property": "pose", "signal": [f"Pose/{c}" for c in ("qw", "qx", "qy", "qz", "px", "py", "pz")]}] + [
        {"target": f"joint:wheel_{k}", "property": "position", "signal": f"WJoint{k}/q"} for k in range(1, 5)
    ]
    return copy.deepcopy(model), pz0


WHEEL_COLORS = ["0.9 0.55 0.1 1", "0.35 0.7 0.45 1", "0.9 0.3 0.3 1", "0.6 0.45 0.85 1"]


def build_scene(pz0: float) -> str:
    quats = d.wheel_quats()
    lines = [
        '<?xml version="1.0"?>',
        "<!--",
        "  tetra-3d (X5.6): a regular tetrahedron (edge 0.25 m) with a reaction wheel on each of its four faces,",
        "  on the ground plane z = 0.",
        "",
        "  Z-up, metres, the world frame of the model. The body is bound by its world pose",
        "  (qw, qx, qy, qz, x, y, z): link \"tetra\" follows Pose/qw .. Pose/pz. Each wheel link wheel_k_link hangs on a revolute",
        "  joint \"wheel_k\" of the tetra link (axis z of the wheel frame = the face normal) whose position is the",
        "  wheel angle WJoint<k>/q relative to the body.",
        "  The body is the GLB mesh meshes/tetra.glb (translucent, apex up, base face down; vertices 1..4 are",
        "  the base vertices at azimuth 90, 210, 330 deg and the apex). The wheel frame has its z axis along the",
        "  spin axis (the outward face normal), so the disc (a cylinder, whose axis is z) spins in place; a marker",
        "  on its rim shows the rotation. The red sphere marks vertex 3 (+L/2, -rho/2, -r), the vertex the body",
        "  ends up balanced on; the dark sphere marks vertex 2, the other end of the balance edge. The link poses",
        "  below are those of sequence-contact at the start (the body lies on its base face, sunk a fraction of a",
        "  millimetre into the compliant ground).",
        "  The wheel discs are drawn with a 0.04 m radius so that they fit inside the body; the real 0.25 kg",
        "  wheel with J = 0.002 kg m^2 would be 0.126 m wide.",
        "-->",
        '<sdf version="1.9">',
        '  <model name="tetra_3d">',
        '    <link name="ground">',
        "      <pose>0 0 0 0 0 0</pose>",
        '      <visual name="ground_slab">',
        "        <pose>0 0 -0.01 0 0 0</pose>",
        "        <geometry><box><size>0.5 0.5 0.02</size></box></geometry>",
        "        <material><diffuse>0.55 0.57 0.6 1</diffuse></material>",
        "      </visual>",
        "    </link>",
        "",
        '    <link name="tetra">',
        f"      <pose>0 0 {pz0:.6f} 0 0 0</pose>",
        '      <visual name="tetra_body">',
        "        <geometry><mesh><uri>meshes/tetra.glb</uri></mesh></geometry>",
        "      </visual>",
        '      <visual name="vertex3_marker">',
        f"        <pose>{d.VERT[2][0]:.6f} {d.VERT[2][1]:.6f} {d.VERT[2][2]:.6f} 0 0 0</pose>",
        "        <geometry><sphere><radius>0.01</radius></sphere></geometry>",
        "        <material><diffuse>0.9 0.2 0.2 1</diffuse></material>",
        "      </visual>",
        '      <visual name="vertex2_marker">',
        f"        <pose>{d.VERT[1][0]:.6f} {d.VERT[1][1]:.6f} {d.VERT[1][2]:.6f} 0 0 0</pose>",
        "        <geometry><sphere><radius>0.01</radius></sphere></geometry>",
        "        <material><diffuse>0.15 0.15 0.15 1</diffuse></material>",
        "      </visual>",
        "    </link>",
    ]
    for k in range(4):
        p = d.DW * d.AXES[k]
        r, pi, y = rpy(quats[k])
        lines += [
            "",
            f'    <link name="wheel_{k + 1}_link">',
            f"      <pose>{p[0]:.6f} {p[1]:.6f} {p[2] + pz0:.6f} {r:.6f} {pi:.6f} {y:.6f}</pose>",
            f'      <visual name="wheel_{k + 1}_disc">',
            "        <geometry><cylinder><radius>0.04</radius><length>0.012</length></cylinder></geometry>",
            f"        <material><diffuse>{WHEEL_COLORS[k]}</diffuse></material>",
            "      </visual>",
            f'      <visual name="wheel_{k + 1}_marker">',
            "        <pose>0.025 0 0.008 0 0 0</pose>",
            "        <geometry><box><size>0.025 0.008 0.005</size></box></geometry>",
            "        <material><diffuse>0.15 0.15 0.15 1</diffuse></material>",
            "      </visual>",
            "    </link>",
        ]
    for k in range(4):
        lines += [
            "",
            f'    <joint name="wheel_{k + 1}" type="revolute">',
            "      <parent>tetra</parent>",
            f"      <child>wheel_{k + 1}_link</child>",
            "      <axis><xyz>0 0 1</xyz></axis>",
            "    </joint>",
        ]
    lines += ["  </model>", "</sdf>", ""]
    return "\n".join(lines)


def build_mesh(path: Path) -> None:
    import trimesh

    faces = []
    for j in range(4):  # face opposite vertex j, wound counter-clockwise seen from outside
        idx = [i for i in range(4) if i != j]
        a, b, c = (d.VERT[i] for i in idx)
        outward = -d.VERT[j]
        if np.dot(np.cross(b - a, c - a), outward) < 0:
            idx = [idx[0], idx[2], idx[1]]
        faces.append(idx)
    material = trimesh.visual.material.PBRMaterial(
        baseColorFactor=[64, 128, 217, 120], alphaMode="BLEND", doubleSided=True, metallicFactor=0.0, roughnessFactor=0.8
    )
    mesh = trimesh.Trimesh(vertices=d.VERT, faces=faces, process=False)
    mesh.visual = trimesh.visual.TextureVisuals(material=material)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(mesh.export(file_type="glb"))


if __name__ == "__main__":
    model, pz0 = build_model()
    out = ROOT / "models" / "sequence-contact.bgmodel.json"
    out.parent.mkdir(exist_ok=True)
    out.write_text(json.dumps(model, indent=2) + "\n", encoding="utf-8", newline="\n")
    (ROOT / "scenes").mkdir(exist_ok=True)
    (ROOT / "scenes" / "tetra-3d.sdf").write_text(build_scene(pz0), encoding="utf-8", newline="\n")
    build_mesh(ROOT / "meshes" / "tetra.glb")
    print(f"pz0 = {pz0:.9f} (rest penetration {d.RIN - pz0:.3e} m)")
    print("wrote", out)
