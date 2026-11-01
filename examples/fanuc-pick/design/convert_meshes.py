# /// script
# requires-python = ">=3.11"
# dependencies = ["numpy>=2.0", "trimesh>=4.4"]
# ///
"""Convert the ROS-Industrial LR Mate 200iD/7L visual meshes (STL) to GLB for the 3D scene.

    uv run examples/fanuc-pick/design/convert_meshes.py <dir with base_link.stl, link_1.stl .. link_6.stl>

Source: `fanuc_lrmate200id_support/meshes/{lrmate200id,lrmate200id7l}/visual/*.stl` of
github.com/ros-industrial/fanuc, `noetic-devel` at d8f42bd73584b255df87098395512538882caea1
(BSD-3-Clause, `meshes/LICENSE`). The 7L variant uses its own `link_2.stl` and `link_4.stl`
(the longer upper arm and forearm) and the 200iD files for the other links, as the xacro does.

For every link the script loads the STL (metres, link frame of the URDF, Z-up) with trimesh and
writes `meshes/<link>.glb` with one PBR material in the URDF colour (`common_colours.xacro`:
FANUC yellow RAL 1021 for the arm, grey 28 for the base, black 0.15 for the flange), no rotation
(the bgsim viewer reads GLB content in the SDF frame, which is the link frame). The arm is
kinematic in the models, so no mass properties are needed.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import trimesh

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "meshes"
LINKS = ["base_link", "link_1", "link_2", "link_3", "link_4", "link_5", "link_6"]
YELLOW = [0.96, 0.76, 0.13, 1.0]
COLOURS = {"base_link": [71 / 255, 71 / 255, 71 / 255, 1.0], "link_6": [0.15, 0.15, 0.15, 1.0]}


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("stl_dir", type=Path)
    args = parser.parse_args(argv)
    OUT.mkdir(parents=True, exist_ok=True)
    print("| link | faces | GLB bytes |")
    print("| --- | --- | --- |")
    for n in LINKS:
        m = trimesh.load(args.stl_dir / f"{n}.stl", force="mesh")
        rgba = COLOURS.get(n, YELLOW)
        m.visual = trimesh.visual.TextureVisuals(material=trimesh.visual.material.PBRMaterial(
            name=f"{n}_mat", baseColorFactor=[int(round(255 * c)) for c in rgba],
            metallicFactor=0.0, roughnessFactor=0.55, doubleSided=True))
        data = trimesh.Scene(m).export(file_type="glb")
        (OUT / f"{n}.glb").write_bytes(data)
        print(f"| {n} | {len(m.faces)} | {len(data)} |")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
