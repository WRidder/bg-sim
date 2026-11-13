# /// script
# requires-python = ">=3.11"
# dependencies = ["numpy>=2.0", "trimesh>=4.4", "pymeshlab>=2023.12", "scipy>=1.13", "networkx>=3"]
# ///
"""Build the microduck's per-link visual meshes from Pollen Robotics' own CAD meshes.

    uv run examples/microduck/design/build_visuals.py [--source <dir>] [--cache <dir>]

Source (CC BY-NC-SA 4.0, Pollen Robotics; see `meshes/LICENSE` and `meshes/NOTICE`): the visual
meshes of the microduck_rl MJCF that design/robot_data.json was extracted from,

    https://github.com/pollen-robotics/microduck_rl at 0daab160d3fb1c2cbaba16a4a19052f36709dd9e
    src/mjlab_microduck/robot/microduck/robot_groundcontact.xml   (the `class="visual"` geoms)
    src/mjlab_microduck/robot/microduck/assets/<mesh>.stl          (38 meshes, metres)

`--source` is that folder of a local clone; without it the files are fetched from
raw.githubusercontent.com at the pinned commit into `--cache`. Every file is checked against
the SHA256 pinned below (the repository publishes no checksums; these are the files as fetched
on 2026-11-12), and the MJCF's body frames are checked against design/robot_data.json, so the
meshes sit in exactly the link frames the bg-sim model uses (z of each body is its joint axis).

For every body the script places each visual geom's STL by the geom's pos/quat in the body
frame, decimates it (quadric edge collapse, MeshLab via `pymeshlab`; budget per mesh in
`FACES`), splits the vertex normals at edges sharper than 35 deg (flat faces stay flat, curved
shells stay smooth), merges the parts of one MJCF material colour and writes

* `examples/microduck/meshes/<body>.glb`: one GLB per body, vertices in the body frame
  (MuJoCo/bg-sim: x forward, y left, z up, metres; the bg-sim viewer reads GLB coordinates
  in the SDF frame, so no axis change), one glTF material per colour;
* `apps/web/src/microduck/duck.glb`: the same meshes in one file for the browser game, one
  node per body named after it, and the lower beak (`jaw`, `jaw_soft`) in its own node `jaw`
  whose origin and z axis are the mouth servo's horn axis (found from the XL330 horn axis of
  the two hip-yaw servos, which drive known joints), so the game can open the beak.

It prints the face counts and the file sizes (README table). The scene and the bindings are
written by build_model.py (design/scene.py), not here.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import sys
import tempfile
import urllib.request
import xml.etree.ElementTree as ET
from pathlib import Path

import numpy as np
import pymeshlab
import trimesh

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
REPO = ROOT.parent.parent
OUT = ROOT / "meshes"
GAME_GLB = REPO / "apps" / "web" / "src" / "microduck" / "duck.glb"

COMMIT = "0daab160d3fb1c2cbaba16a4a19052f36709dd9e"
RAW = f"https://raw.githubusercontent.com/pollen-robotics/microduck_rl/{COMMIT}/src/mjlab_microduck/robot/microduck/"
MJCF = "robot_groundcontact.xml"
# SHA256 of the files as fetched (the XML with LF line endings).
SHA256 = {
    "robot_groundcontact.xml": "99d23867e46e9d4748ff1398016b850f09fb6cf02a558c0272743b39ce3acf15",
    "assets/ankle_left.stl": "2ec1bd89205b407efebaa9a8898ad9fea741389d87b80ecc5c96b21d1668119e",
    "assets/ankle_right.stl": "f83f388ae00787415e76b8ecaab769f08f25b8c4e90c1937ff0fc4d68d81722e",
    "assets/banana_pcb_locker.stl": "42ddde9d01bf5d91f88b99847017f14d97d2537ee27383c6d41dd8bf30a51134",
    "assets/bearing_roll.stl": "b5603a64b2d965ad75ea847767b5798130852e12a658fde7b5068fc457e2adcc",
    "assets/bottom_head_shell.stl": "1820f7cf96646b0fc0c431f07da87b91b13111bfa9857ab1bf2b1fc3388f8da2",
    "assets/elec_rpi_robot_hat_pcb.stl": "1a61582759d82b5b4df9b7d11099bf1bb3944fc77e6b74d3237adf24dd5d03d7",
    "assets/face_part.stl": "d0e89a173e7bdc8038c4d413f458140d8f42f1a2f098f67a887c2388eff31718",
    "assets/foot_left.stl": "a1f5d43456d0f522bd60870153795f1e8112c1adf9b8b4373b59608d9545c044",
    "assets/foot_right.stl": "54f97fa1f0e0e611d31329df9f3c3b17ffcca2d695c579d1d32cbe99e8a6c7ef",
    "assets/hip_l.stl": "e175896932d76dc7648cf939aa39cb7b1d188b783d91745adb9a4cec65e9052c",
    "assets/jaw.stl": "45cdbd319a4583095d8daa0db07dee726522a743d59acb82d27d82ded500a1cf",
    "assets/jaw_soft.stl": "2d2ade4e86df4b37ce313bb9b96023109dd04bab39dba08b154e76d332fbce2e",
    "assets/left_shell.stl": "2abde8e2b79c9b011cdb11957c67ab4287b45d7301affd4235ab81141118e331",
    "assets/leg.stl": "9a91cc1ae31ecd9e0c1ba93f3bb2ad8a12e29bff24ec27d1ac66c0c3037d9fcf",
    "assets/lens.stl": "b1c717432ff7666398de58adec6a1b7e03a7e45aa155dbfe27a6152ef19663e5",
    "assets/m12_lens_holder.stl": "031d5ffaf6247328cf6d020f6b6695ffb3f8d3f22cf923b85811351d89ecfd7c",
    "assets/motor_support.stl": "ce0aa5bef82c7474512d302568c341b9769b3005e0bdb91a19c2eaaba6dad480",
    "assets/neck.stl": "b6e86b886153be8a8a776c1cb219c074ee9e89c8bd431117662a2d9e504d7cb5",
    "assets/neck_pitch.stl": "a685ce65348ae4d0d49417c69a7a8871f8bbd54a6e3419362be9c334abd5d2ae",
    "assets/noenoeil.stl": "e1167b3d5ad7fbbe6e63296bcd0c6b61556611e6bc1367b15ecfd27e3abb72f5",
    "assets/np_f970.stl": "0e55a48281331b3b7b1a363d2e93b6012f37c52045b6dc922a149ca7c1b38388",
    "assets/pcb__raspberry_pi_zero_2_w.stl": "802cc66fc5447c67fc642d1339e55160df10f2ad04a65efd130e35fb7b2d3c90",
    "assets/power_support.stl": "ee45e397d3f3422f34940a4b61156c3c11c7e8c2b240451ce5f9ddd1622a130e",
    "assets/right_shell.stl": "3efba3e193cc6aa49d49a9c92cdded0504917397c9e2c5b8fe002a958e2f2d2b",
    "assets/seeed_bearing__configuration__22x16x4.stl": "295ee68ed9766c91fe06d3a2a49d39f7c2f56cc943395d293afdeb013123435e",
    "assets/seeed_bearing__configuration_default.stl": "e815f3483a2e7b80844f3c0938a47e53db38b12faed9b2d364414c19e4322da4",
    "assets/soft_mouth_top.stl": "3c2b52b0b6e2ce944a1e1b5a0838e1216be1ad3a34c8cdf91be186e634aec57b",
    "assets/sole_left.stl": "e028c8b09fecd4cb354d042bf7fd95a1a1bc2d524d760d62137fa8d74093fc23",
    "assets/sole_right.stl": "3f5068872f3add10eb967327651445bdfca635f5a8a01befa0ef05e462b72b4c",
    "assets/speaker.stl": "75a35f9bcf94cd8e52f99b3fd6ae667b48f52503f9075ee2f699eebe8e7b3ddf",
    "assets/top_head_shell.stl": "6d01f396f514c9d2185cf6b8250b1d8382ac3fa0702eb525bcb284f706196291",
    "assets/trunk_base.stl": "aa4f853ae555a8b765e585ce4519c0bbff325ce298ec15a1437792c52a0beac1",
    "assets/upper_leg_left.stl": "8cb1c12dfa6d366a318bb1ec16f585427b9a185afeb7738d0a6f41f5db46a07d",
    "assets/upper_leg_right.stl": "5caf996cc3e151b01f393cdc6a6a6a940c1d86179d8b7c7f5f85cf1f1ac2fb63",
    "assets/upper_leg_rigidity_plate.stl": "231b3e5f1e24d146d735dc158cbcfec0c95a0d0ca8c500f61f04d15d0b665652",
    "assets/xl330.stl": "96238ed0d020ce0009cf1a5aa4b6926176c800840318ee65e4375be2298d2744",
    "assets/yaw2roll.stl": "6c8f193ec7cb40be0f48eeb5fba81bce2c87f12e1aab3f77f1bc4981386e1495",
    "assets/yaw_roll_motion.stl": "b0c9902dee19f06cdb7fa930292e0e1c91e2dc59baa971211495b58ff76c3c60",
}

# Face budget per source mesh (after decimation; meshes at or under it are kept). The bearings
# sit inside the parts and are mostly hidden; the servos and the shells carry the look.
FACES_DEFAULT = 2000
FACES = {
    "seeed_bearing__configuration__22x16x4": 64,
    "seeed_bearing__configuration_default": 64,
    "xl330": 500,
    "np_f970": 200,  # the battery, inside the shells
    "pcb__raspberry_pi_zero_2_w": 200,  # inside the head
    "elec_rpi_robot_hat_pcb": 200,
    "power_support": 400,
    "banana_pcb_locker": 200,
    "speaker": 12,
    "lens": 200,
    "m12_lens_holder": 300,
    "motor_support": 400,
    "neck": 600,
    "left_shell": 3600, "right_shell": 3600, "top_head_shell": 3600, "bottom_head_shell": 3600,
}
CREASE = math.radians(35.0)
JAW_MESHES = ("jaw", "jaw_soft")  # the lower beak, moved by the mouth servo in the game
MOUTH_SERVO_POS = (0.003, 0.0255, -0.018)  # the xl330 geom of the head that is not on the roll axis


def quat_rot(q) -> np.ndarray:
    w, x, y, z = np.asarray(q, float) / np.linalg.norm(q)
    return np.array([
        [1 - 2 * (y * y + z * z), 2 * (x * y - w * z), 2 * (x * z + w * y)],
        [2 * (x * y + w * z), 1 - 2 * (x * x + z * z), 2 * (y * z - w * x)],
        [2 * (x * z - w * y), 2 * (y * z + w * x), 1 - 2 * (x * x + y * y)],
    ])


def hom(r, p) -> np.ndarray:
    t = np.eye(4)
    t[:3, :3] = r
    t[:3, 3] = p
    return t


def floats(s: str | None, default: str) -> list[float]:
    return [float(v) for v in (s or default).split()]


# ------------------------------------------------------------------ sources

def fetch(rel: str, source: Path | None, cache: Path) -> bytes:
    """The file `rel` (relative to the MJCF folder), from a clone or downloaded, SHA256-checked."""
    if source is not None:
        data = (source / rel).read_bytes()
    else:
        path = cache / rel
        if not path.exists():
            path.parent.mkdir(parents=True, exist_ok=True)
            req = urllib.request.Request(RAW + rel, headers={"User-Agent": "bgsim-example-build"})
            with urllib.request.urlopen(req, timeout=60) as r:  # noqa: S310 - fixed https URL
                path.write_bytes(r.read())
        data = path.read_bytes()
    if rel.endswith(".xml"):
        data = data.replace(b"\r\n", b"\n")
    digest = hashlib.sha256(data).hexdigest()
    if SHA256.get(rel) != digest:
        raise SystemExit(f"{rel}: SHA256 {digest} is not the pinned {SHA256.get(rel)}")
    return data


def read_stl(data: bytes) -> trimesh.Trimesh:
    n = int(np.frombuffer(data[80:84], "<u4")[0])
    rec = np.dtype([("n", "<f4", 3), ("v", "<f4", (3, 3)), ("a", "<u2")])
    tri = np.frombuffer(data[84:84 + n * rec.itemsize], rec)
    v = tri["v"].reshape(-1, 3).astype(float)
    return trimesh.Trimesh(vertices=v, faces=np.arange(len(v)).reshape(-1, 3), process=True)


def parse_mjcf(xml: bytes) -> tuple[list[dict], dict]:
    root = ET.fromstring(xml)
    materials = {m.get("name"): floats(m.get("rgba"), "0.7 0.7 0.7 1") for m in root.iter("material")}
    bodies: list[dict] = []

    def walk(elem, parent):
        for body in elem.findall("body"):
            rec = {"name": body.get("name"), "parent": parent,
                   "pos": floats(body.get("pos"), "0 0 0"), "quat": floats(body.get("quat"), "1 0 0 0"), "geoms": []}
            for g in body.findall("geom"):
                if g.get("class") != "visual":
                    continue
                rec["geoms"].append({"mesh": g.get("mesh"), "pos": floats(g.get("pos"), "0 0 0"),
                                     "quat": floats(g.get("quat"), "1 0 0 0"),
                                     "rgba": materials.get(g.get("material"), [0.7, 0.7, 0.7, 1.0])})
            bodies.append(rec)
            walk(body, rec["name"])

    walk(root.find("worldbody"), None)
    return bodies, materials


def check_frames(bodies: list[dict]) -> None:
    """The MJCF's body frames are the ones robot_data.json (and so every model) uses."""
    data = json.loads((HERE / "robot_data.json").read_text(encoding="utf-8"))["bodies"]
    ours = {b["name"]: b for b in data}
    if [b["name"] for b in bodies] != [b["name"] for b in data]:
        raise SystemExit("body tree of the MJCF differs from robot_data.json")
    for b in bodies:
        o = ours[b["name"]]
        if b["parent"] is not None and (not np.allclose(b["pos"], o["pos"], atol=1e-9) or not np.allclose(b["quat"], o["quat"], atol=1e-9)):
            raise SystemExit(f"{b['name']}: frame differs from robot_data.json")


# ------------------------------------------------------------------ meshes

def decimate(mesh: trimesh.Trimesh, faces: int) -> trimesh.Trimesh:
    """Quadric edge collapse to `faces` (MeshLab's filter; fast-simplification stalls at about a
    quarter of these CAD meshes, whose triangles are long and thin)."""
    if len(mesh.faces) <= faces:
        return mesh
    ms = pymeshlab.MeshSet()
    ms.add_mesh(pymeshlab.Mesh(vertex_matrix=mesh.vertices, face_matrix=mesh.faces))
    ms.meshing_decimation_quadric_edge_collapse(targetfacenum=faces, preservenormal=True, preservetopology=False,
                                                optimalplacement=True, planarquadric=True, qualitythr=0.3)
    out = ms.current_mesh()
    return trimesh.Trimesh(vertices=out.vertex_matrix(), faces=out.face_matrix(), process=True)


def shaded(mesh: trimesh.Trimesh) -> trimesh.Trimesh:
    """Vertices split at edges sharper than CREASE, so the vertex normals keep hard edges hard."""
    out = trimesh.graph.smooth_shade(mesh, angle=CREASE)
    _ = out.vertex_normals
    return out


def colour_key(rgba) -> tuple[int, int, int, int]:
    return tuple(int(round(255 * float(c))) for c in rgba)


def material(rgba: tuple[int, int, int, int]) -> trimesh.visual.material.PBRMaterial:
    return trimesh.visual.material.PBRMaterial(
        name="mat_%02x%02x%02x" % rgba[:3], baseColorFactor=list(rgba),
        metallicFactor=0.0, roughnessFactor=0.65, doubleSided=False)


def horn_axis_local(bodies: list[dict]) -> tuple[np.ndarray, np.ndarray]:
    """The XL330 horn axis in the servo mesh's frame (point, unit direction), from the two
    hip-yaw servos: each sits in the trunk and drives the joint of yaw2roll / bearing_roll."""
    by = {b["name"]: b for b in bodies}
    trunk = by["trunk_base"]
    found = []
    for child in ("yaw2roll", "bearing_roll"):
        c = by[child]
        p, d = np.array(c["pos"]), quat_rot(c["quat"])[:, 2]
        servo = min((g for g in trunk["geoms"] if g["mesh"] == "xl330"),
                    key=lambda g: np.linalg.norm(np.cross(np.array(g["pos"]) - p, d)))
        r = quat_rot(servo["quat"])
        pl, dl = r.T @ (p - np.array(servo["pos"])), r.T @ d
        found.append((pl - (pl @ dl) * dl, dl))  # the point of the line closest to the servo origin
    (p1, d1), (p2, d2) = found
    if abs(d1 @ d2) < 1 - 1e-6 or np.linalg.norm(p1 - p2) > 1e-6:
        raise SystemExit(f"the two hip-yaw servos disagree on the horn axis: {p1} {d1} / {p2} {d2}")
    return p1, d1


def mouth_hinge(bodies: list[dict]) -> np.ndarray:
    """Pose of the mouth hinge in the head body (jaw_soft): origin on the horn axis of the mouth
    servo, z along that axis, x pointing from the hinge towards the lower beak's centre."""
    p_l, d_l = horn_axis_local(bodies)
    head = next(b for b in bodies if b["name"] == "jaw_soft")
    servo = min((g for g in head["geoms"] if g["mesh"] == "xl330"),
                key=lambda g: np.linalg.norm(np.array(g["pos"]) - np.array(MOUTH_SERVO_POS)))
    r = quat_rot(servo["quat"])
    origin = np.array(servo["pos"]) + r @ p_l
    z = r @ d_l
    return origin, z


def servo_fit(bodies: list[dict]) -> list[tuple[str, float, float]]:
    """For each joint: how far the horn axis of the nearest XL330 mesh (in the parent or the child
    body, the child placed at q = 0) lies from the joint axis of the model, (joint, distance in m
    of the horn centre from the axis, angle in rad between the axes)."""
    p_l, d_l = horn_axis_local(bodies)
    by = {b["name"]: b for b in bodies}
    out = []
    data = {b["name"]: b for b in json.loads((HERE / "robot_data.json").read_text(encoding="utf-8"))["bodies"]}
    for b in bodies:
        if b["parent"] is None:
            continue
        t_pb = hom(quat_rot(b["quat"]), b["pos"])
        o, d = t_pb[:3, 3], t_pb[:3, 2]
        best = None
        for frame, geoms in ((np.eye(4), by[b["parent"]]["geoms"]), (t_pb, b["geoms"])):
            for g in geoms:
                if g["mesh"] != "xl330":
                    continue
                t = frame @ hom(quat_rot(g["quat"]), g["pos"])
                c, a = t[:3, :3] @ p_l + t[:3, 3], t[:3, :3] @ d_l
                v = c - o
                dist = float(np.linalg.norm(v - (v @ d) * d))
                ang = float(math.acos(min(1.0, abs(float(a @ d)))))
                if best is None or dist + ang * 0.01 < best[0] + best[1] * 0.01:
                    best = (dist, ang)
        out.append((data[b["name"]]["joint"], *best))
    return out


NOTICE = """microduck visual meshes (examples/microduck/meshes/*.glb, apps/web/src/microduck/duck.glb)

Source
  Pollen Robotics, microduck_rl, https://github.com/pollen-robotics/microduck_rl
  commit 0daab160d3fb1c2cbaba16a4a19052f36709dd9e,
  src/mjlab_microduck/robot/microduck/assets/*.stl (38 meshes) placed by the visual geoms of
  src/mjlab_microduck/robot/microduck/robot_groundcontact.xml.
  Copyright Pollen Robotics. The STL files are licensed under the Creative Commons
  Attribution-NonCommercial-ShareAlike 4.0 International License (CC BY-NC-SA 4.0),
  https://creativecommons.org/licenses/by-nc-sa/4.0/ (microduck_rl LICENSE-MODELS.md).
  The MJCF itself is Apache-2.0 (microduck_rl LICENSE).

Changes (examples/microduck/design/build_visuals.py)
  - every STL placed into the frame of the body it belongs to, by the geom's pos and quat;
  - decimated with quadric edge collapse (MeshLab, pymeshlab) to a face budget per mesh
    ({src_faces:,} source faces of the placed parts to {out_faces:,} in total);
  - vertex normals split at edges sharper than 35 degrees;
  - the parts of one body merged per material colour, the colour taken from the MJCF material;
  - written as glTF 2.0 binary: one file per body (meshes/), and one file with a node per body
    and the lower beak in its own node on the mouth servo's axis (duck.glb, for the web game).

Licence of these files
  The GLB files are an adaptation of the Pollen Robotics STL files and are licensed under
  CC BY-NC-SA 4.0 (https://creativecommons.org/licenses/by-nc-sa/4.0/). NON-COMMERCIAL USE ONLY.
  This licence covers these mesh files only; it does not change the licence of the rest of
  bg-sim, and the rest of bg-sim does not relicense them. Share them, or anything made from them,
  only under the same licence, with this notice.
"""
LICENSE = """The mesh files in this folder (*.glb) are licensed under the Creative Commons
Attribution-NonCommercial-ShareAlike 4.0 International License (CC BY-NC-SA 4.0).

  Licensor of the original work: Pollen Robotics (microduck_rl, assets/*.stl)
  Summary:    https://creativecommons.org/licenses/by-nc-sa/4.0/
  Legal code: https://creativecommons.org/licenses/by-nc-sa/4.0/legalcode

They are an adaptation (converted, re-posed into link frames, decimated, recoloured per
material); see NOTICE for the source, the changes and the attribution. Non-commercial use
only. This licence applies to these files alone, not to the rest of the repository.
"""


def write_notices(src_faces: int, out_faces: int) -> None:
    notice = NOTICE.format(src_faces=src_faces, out_faces=out_faces)
    (OUT / "NOTICE").write_text(notice, encoding="utf-8", newline="\n")
    (OUT / "LICENSE").write_text(LICENSE, encoding="utf-8", newline="\n")
    (GAME_GLB.parent / "duck.glb.NOTICE").write_text(
        notice + "\nThe full notice and licence statement: examples/microduck/meshes/NOTICE and LICENSE.\n",
        encoding="utf-8", newline="\n")


def build_body(body: dict, stl: dict, cache: dict, stats: dict) -> dict[str, dict]:
    """{part key: {colour: [meshes in the body frame]}}; key 'jaw' for the lower beak, else 'body'."""
    parts: dict[str, dict] = {}
    for g in body["geoms"]:
        name = g["mesh"]
        if name not in cache:
            src = read_stl(stl[name])
            dec = decimate(src, FACES.get(name, FACES_DEFAULT))
            cache[name] = shaded(dec)
            stats[name] = (len(src.faces), len(dec.faces))
        mesh = cache[name].copy()
        mesh.apply_transform(hom(quat_rot(g["quat"]), g["pos"]))
        key = "jaw" if body["name"] == "jaw_soft" and name in JAW_MESHES else "body"
        parts.setdefault(key, {}).setdefault(colour_key(g["rgba"]), []).append(mesh)
    return parts


def merged(colours: dict) -> list[tuple[tuple, trimesh.Trimesh]]:
    out = []
    for rgba, meshes in sorted(colours.items()):
        m = trimesh.util.concatenate(meshes)
        normals = np.concatenate([x.vertex_normals for x in meshes])
        m = trimesh.Trimesh(vertices=m.vertices, faces=m.faces, vertex_normals=normals, process=False)
        m.visual = trimesh.visual.TextureVisuals(material=material(rgba))
        out.append((rgba, m))
    return out


def glb(scene: trimesh.Scene) -> bytes:
    return scene.export(file_type="glb", include_normals=True)


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--source", type=Path, help="microduck_rl/src/mjlab_microduck/robot/microduck of a clone at the pinned commit")
    parser.add_argument("--cache", type=Path, default=Path(tempfile.gettempdir()) / "bgsim-microduck-visuals" / COMMIT[:12])
    args = parser.parse_args(argv)
    xml = fetch(MJCF, args.source, args.cache)
    bodies, _ = parse_mjcf(xml)
    check_frames(bodies)
    names = sorted({g["mesh"] for b in bodies for g in b["geoms"]})
    stl = {n: fetch(f"assets/{n}.stl", args.source, args.cache) for n in names}
    origin, axis = mouth_hinge(bodies)

    OUT.mkdir(parents=True, exist_ok=True)
    cache: dict = {}
    stats: dict = {}
    game = trimesh.Scene()
    rows = []
    total = 0
    for body in bodies:
        parts = build_body(body, stl, cache, stats)
        scene = trimesh.Scene()
        game.graph.update(frame_from=game.graph.base_frame, frame_to=body["name"], matrix=np.eye(4))
        faces_src = sum(stats[g["mesh"]][0] for g in body["geoms"])
        faces_out = 0
        for key, colours in parts.items():
            for k, (rgba, m) in enumerate(merged(colours)):
                gname = f"{body['name']}_{key}_{k}"
                faces_out += len(m.faces)
                scene.add_geometry(m, node_name=gname, geom_name=gname)
                if key == "jaw":
                    # the game's copy: in the hinge frame, under a node `jaw` at the hinge
                    x = np.cross(axis, [0.0, 0.0, 1.0])
                    x = x / np.linalg.norm(x) if np.linalg.norm(x) > 1e-9 else np.array([1.0, 0, 0])
                    hinge = hom(np.column_stack([x, np.cross(axis, x), axis]), origin)
                    if "jaw" not in game.graph.nodes:
                        game.graph.update(frame_from=body["name"], frame_to="jaw", matrix=hinge)
                    local = m.copy()
                    local.apply_transform(np.linalg.inv(hinge))
                    game.add_geometry(local, node_name=f"game_{gname}", geom_name=f"game_{gname}", parent_node_name="jaw")
                else:
                    game.add_geometry(m, node_name=f"game_{gname}", geom_name=f"game_{gname}", parent_node_name=body["name"])
        data = glb(scene)
        (OUT / f"{body['name']}.glb").write_bytes(data)
        total += len(data)
        rows.append((body["name"], len(body["geoms"]), faces_src, faces_out, len(data)))
    game_bytes = glb(game)
    GAME_GLB.write_bytes(game_bytes)

    print("| link | parts | faces (source) | faces (GLB) | GLB bytes |")
    print("| --- | --- | --- | --- | --- |")
    for r in rows:
        print(f"| {r[0]} | {r[1]} | {r[2]} | {r[3]} | {r[4]} |")
    print(f"| total | {sum(r[1] for r in rows)} | {sum(r[2] for r in rows)} | {sum(r[3] for r in rows)} | {total} |")
    src_bytes = sum(len(stl[g['mesh']]) for b in bodies for g in b["geoms"])
    print(f"source STL bytes (per placed part) {src_bytes} ({src_bytes / 2**20:.2f} MiB); meshes/ {total / 2**20:.2f} MiB; "
          f"{GAME_GLB.relative_to(REPO).as_posix()} {len(game_bytes)} bytes ({len(game_bytes) / 2**20:.2f} MiB)")
    print(f"mouth hinge in jaw_soft: origin {np.round(origin, 6).tolist()} axis {np.round(axis, 6).tolist()}")
    print("| joint | horn centre from the joint axis (mm) | angle between the axes (deg) |")
    print("| --- | --- | --- |")
    for joint, dist, ang in servo_fit(bodies):
        print(f"| {joint} | {dist * 1000:.3f} | {math.degrees(ang):.3f} |")
    write_notices(sum(r[2] for r in rows), sum(r[3] for r in rows))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
