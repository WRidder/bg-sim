# /// script
# requires-python = ">=3.11"
# dependencies = ["numpy>=2.0", "scipy>=1.13", "casadi>=3.6"]
# ///
"""Write the model documents, the controller block, the scene and the project file of
`pendulum-double-rotary` from `design/design.json` (run `design.py` first).

    uv run examples/pendulum-double-rotary/design/build_model.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import rotary_build as rb  # noqa: E402
import rotary_lib as rl  # noqa: E402

ROOT = HERE.parent
N_LINKS = 2


def main() -> None:
    dz = json.loads((HERE / "design.json").read_text(encoding="utf-8"))
    for key in ("tab_x", "tab_k"):
        dz[key] = rb.np.array(dz[key])
    plant = rl.Plant(N_LINKS, *rl.LINKS[N_LINKS])
    name = dz["example"]
    (ROOT / "models").mkdir(exist_ok=True)
    (ROOT / "library").mkdir(exist_ok=True)
    (ROOT / "scenes").mkdir(exist_ok=True)
    (ROOT / "library" / "RotaryCtrl.jl").write_text(
        rb.controller_source(plant, dz), encoding="utf-8", newline="\n"
    )
    (ROOT / "library" / "LinkAngles.jl").write_text(rb.angles_source(plant), encoding="utf-8", newline="\n")
    (ROOT / "scenes" / f"{name}.sdf").write_text(rb.scene_sdf(plant, name), encoding="utf-8", newline="\n")
    rb.write_json(ROOT / "models" / f"{name}.bgmodel.json", rb.build_model(plant, dz, name, False))
    rb.write_json(ROOT / "models" / f"{name}-free.bgmodel.json", rb.build_model(plant, dz, f"{name}-free", True))
    rb.write_json(
        ROOT / "bgsim.project.json",
        {
            "format": "bgsim.project",
            "language": "0.1.0",
            "name": name,
            "models": [name, f"{name}-free"],
            "libraryDir": "library",
            "scenesDir": "scenes",
        },
    )
    print(f"wrote models, library, scene and project of {name}")


if __name__ == "__main__":
    main()
