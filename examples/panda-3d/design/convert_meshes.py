# /// script
# requires-python = ">=3.11"
# dependencies = ["numpy>=2.0", "trimesh>=4.4", "pycollada>=0.9", "fast-simplification>=0.1.9", "scipy>=1.13", "networkx>=3"]
# ///
"""Convert the official Franka Panda visual meshes (COLLADA) to the GLB files of `meshes/`.

    uv run examples/panda-3d/design/convert_meshes.py <franka_description>/meshes/visual [--ratio 0.25]

Source: `franka_description/meshes/visual/link{0..7}.dae` of github.com/frankaemika/franka_ros
(Apache-2.0, see `meshes/LICENSE` and `meshes/NOTICE`). For every link the script

* loads the COLLADA scene with trimesh (pycollada), applying the node transforms, so the
  vertices are in the URDF link frame (Z-up, metres: the files say `Z_UP`, `meter = 1`);
* keeps one sub-mesh per COLLADA material and carries its diffuse colour over as a glTF
  PBR base colour (metallic 0, roughness 0.6: the DAE has Phong materials only);
* decimates each sub-mesh with quadric edge collapse to `ratio` of its faces (meshes under
  `MIN_FACES` faces are kept as they are; default 0.5: 2.2 MiB at full resolution, about half);
* writes `meshes/link<i>.glb`. The coordinates are not rotated: the bgsim viewer reads the
  GLB content in the SDF frame (`web/src/scene/build.ts`), which is the URDF link frame here.

It prints the face counts and the file sizes (the README table).
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import numpy as np
import trimesh

OUT = Path(__file__).resolve().parent.parent / "meshes"
MIN_FACES = 400


def colour_of(geom: trimesh.Trimesh) -> np.ndarray:
    """RGBA 0..255 of a COLLADA sub-mesh (material diffuse, else the vertex/face colour)."""
    vis = geom.visual
    material = getattr(vis, "material", None)
    if material is not None:
        for name in ("main_color", "diffuse", "baseColorFactor"):
            c = getattr(material, name, None)
            if c is not None:
                c = np.asarray(c, dtype=float).ravel()
                if c.size >= 3:
                    c = c if c.max() > 1.0 else c * 255.0
                    return np.r_[c[:3], c[3] if c.size > 3 else 255.0]
    try:
        return np.asarray(vis.to_color().main_color, dtype=float)
    except Exception:  # noqa: BLE001 - untextured, uncoloured geometry
        return np.array([200.0, 200.0, 200.0, 255.0])


def convert(src: Path, dst: Path, ratio: float) -> tuple[int, int, int]:
    scene = trimesh.load(src, file_type="dae", force="scene")
    out = trimesh.Scene()
    faces_in = faces_out = 0
    # bake the node transforms: one mesh per (geometry, node) in the link frame
    for node in scene.graph.nodes_geometry:
        transform, geom_name = scene.graph[node]
        geom = scene.geometry[geom_name]
        if not isinstance(geom, trimesh.Trimesh) or len(geom.faces) == 0:
            continue
        rgba = colour_of(geom)
        mesh = trimesh.Trimesh(vertices=geom.vertices.copy(), faces=geom.faces.copy(), process=True)
        mesh.apply_transform(transform)
        faces_in += len(mesh.faces)
        if len(mesh.faces) > MIN_FACES and ratio < 1.0:
            target = max(MIN_FACES, int(len(mesh.faces) * ratio))
            mesh = mesh.simplify_quadric_decimation(face_count=target)
        faces_out += len(mesh.faces)
        material = trimesh.visual.material.PBRMaterial(
            name=f"{geom_name}_mat",
            baseColorFactor=[int(round(v)) for v in rgba],
            metallicFactor=0.0,
            roughnessFactor=0.6,
            doubleSided=False,
        )
        mesh.visual = trimesh.visual.TextureVisuals(material=material)
        out.add_geometry(mesh, node_name=str(node), geom_name=str(geom_name))
    data = out.export(file_type="glb")
    dst.write_bytes(data)
    return faces_in, faces_out, len(data)


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("visual_dir", type=Path, help="franka_description/meshes/visual")
    parser.add_argument("--ratio", type=float, default=0.5, help="kept fraction of the faces")
    args = parser.parse_args(argv)
    OUT.mkdir(parents=True, exist_ok=True)
    total = 0
    print("| mesh | faces (source) | faces (GLB) | GLB bytes |")
    print("| --- | --- | --- | --- |")
    for i in range(8):
        src = args.visual_dir / f"link{i}.dae"
        dst = OUT / f"link{i}.glb"
        fin, fout, size = convert(src, dst, args.ratio)
        total += size
        print(f"| link{i}.glb | {fin} | {fout} | {size} |")
    print(f"total {total} bytes ({total / 2**20:.2f} MiB)")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
