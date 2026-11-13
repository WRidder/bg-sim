# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""The host-interface variant of the AIM-9X intercept model (`models/aim9x-fmu`).

    uv run examples/aim9x/design/build_fmu_model.py

`aim9x-intercept` is the closed-loop example: its target is a `TargetMotion` source and its
run stops at the proximity fuze. The F-16 host (`apps/f16-sim`) needs the same weapon as a
reusable FMU:

* the target is supplied by the host, so `Target` becomes `ExternalTarget` and the seven
  target values are `ExportInput` markers (`target_north_m`, `target_east_m`,
  `target_down_m`, `target_vn_mps`, `target_ve_mps`, `target_vd_mps`, `target_ir_w`), plus
  `seeker_on`;
* the fuze no longer stops the simulation (the host latches `fuze`/`hit` and retires the
  instance);
* the pose, attitude, air data, fin angles, thrust and fuze status are `ExportOutput`
  markers, so the FMU has the interface `examples/export_aim9x.jl` builds;
* the launch state stays in the globals `vt0`, `h0`, `alpha0`, `tvc_on`, `nav_N`, `a_max_g`.

The model is generated from `aim9x-intercept`, so run `build_model.py` first. The scene is
not part of the FMU model.
"""

from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
MODELS = ROOT / "models"
SOURCE = MODELS / "aim9x-intercept.bgmodel.json"
DEST = MODELS / "aim9x-fmu.bgmodel.json"
PROJECT = ROOT / "bgsim.project.json"

TARGET_GLOBALS = {"tgt_x", "tgt_y", "tgt_z", "tgt_v", "tgt_psi", "turn_rate", "turn_t"}

INPUTS = {
    "target_north_m": ("pn", 2000.0),
    "target_east_m": ("pe", 0.0),
    "target_down_m": ("pd", -6000.0),
    "target_vn_mps": ("vn", 150.0),
    "target_ve_mps": ("ve", 0.0),
    "target_vd_mps": ("vd", 0.0),
    "target_ir_w": ("I", 1.0e6),
}
OUTPUTS = (
    ("north_m", "Status", "x"),
    ("west_m", "Status", "y"),
    ("alt_m", "Status", "z"),
    ("q_w", "Status", "qw"),
    ("q_x", "Status", "qx"),
    ("q_y", "Status", "qy"),
    ("q_z", "Status", "qz"),
    ("phi_deg", "Status", "phi_deg"),
    ("theta_deg", "Status", "theta_deg"),
    ("psi_deg", "Status", "psi_deg"),
    ("gamma_deg", "Status", "gamma_deg"),
    ("vt_mps", "Status", "vt_out"),
    ("alpha_deg", "Status", "alpha_deg_out"),
    ("beta_deg", "Status", "beta_deg_out"),
    ("qbar_pa", "Status", "qbar_out"),
    ("mach", "Status", "mach_out"),
    ("n_z_g", "Status", "n_z_out"),
    ("n_y_g", "Status", "n_y_out"),
    ("mass_kg", "Status", "mass"),
    ("lock", "Status", "lock_out"),
    ("range_m", "Seeker", "range"),
    ("range_rate_mps", "Seeker", "range_rate"),
    ("min_range_m", "Status", "min_range"),
    ("t_go_s", "Status", "t_go"),
    ("fuze", "Status", "fuze"),
    ("hit", "Status", "hit"),
    ("thrust_n", "Motor", "T"),
    ("fin1_deg", "Fin1", "y"),
    ("fin2_deg", "Fin2", "y"),
    ("fin3_deg", "Fin3", "y"),
    ("fin4_deg", "Fin4", "y"),
    ("p_dps", "Air", "p_deg"),
    ("q_dps", "Air", "q_deg"),
    ("r_dps", "Air", "r_deg"),
)


def main() -> int:
    doc = json.loads(SOURCE.read_text(encoding="utf-8"))
    nodes = doc["diagram"]["nodes"]
    conns = doc["diagram"]["connections"]
    by_name = {n["name"]: n for n in nodes}
    ids = {n["id"]: n["name"] for n in nodes}
    nodes_by_id = {n["id"]: n for n in nodes}

    # The target is the host's now, and the fuze no longer stops the instance.
    target = by_name["Target"]
    target["block"] = {"ref": "project:ExternalTarget"}
    target["params"] = {}
    target["starts"] = {}
    for name in ("SeekerOn", "Stop", "View"):
        node = by_name.get(name)
        if node is not None:
            nodes.remove(node)
            conns[:] = [c for c in conns if node["id"] not in (c["from"]["node"], c["to"]["node"])]

    conns[:] = [c for c in conns
                if not (ids.get(c["from"]["node"]) == "Air" and ids.get(c["to"]["node"]) == "Target")]

    def add_node(name: str, ref: str, x: int, y: int, params: dict[str, str] | None = None) -> str:
        nid = f"h{len(nodes) + 1:03d}"
        nodes.append({"id": nid, "name": name, "block": {"ref": ref},
                      "position": {"x": x, "y": y}, "rotation": 0, "flipX": False,
                      "params": params or {}, "constants": {}, "starts": {},
                      "ui": {"showLabel": True, "color": None}})
        nodes_by_id[nid] = nodes[-1]
        return nid

    def sig(src: str, sport: str, dst: str, dport: str) -> None:
        conns.append({"id": f"hn{len(conns) + 1:04d}", "kind": "signal",
                      "from": {"node": src, "port": sport}, "to": {"node": dst, "port": dport},
                      "route": [], "label": None})

    for k, (name, (port, value)) in enumerate(INPUTS.items(), start=1):
        nid = add_node(name, "stdlib:converters/ExportInput", 900, 1500 + 70 * k,
                       {"value": str(value)})
        sig(nid, "y", target["id"], port)
    on = add_node("seeker_on", "stdlib:converters/ExportInput", 900, 2100, {"value": "1.0"})
    sig(on, "y", by_name["Seeker"]["id"], "seeker_on")

    for k, (name, src, port) in enumerate(OUTPUTS, start=1):
        nid = add_node(name, "stdlib:converters/ExportOutput", 2700, 60 * k)
        sig(by_name[src]["id"], port, nid, "u")

    doc["parameters"] = [g for g in doc["parameters"] if g["name"] not in TARGET_GLOBALS]
    doc["name"] = "aim9x-fmu"
    doc["$comment"] = (
        "Host-interface AIM-9X for apps/f16-sim: launch-relative target inputs, missile pose/status "
        "outputs, no fuze stop. Generated from aim9x-intercept by design/build_fmu_model.py; do not "
        "edit by hand.")
    doc.pop("scene", None)
    doc.pop("bindings", None)
    DEST.write_text(json.dumps(doc, indent=1) + "\n", encoding="utf-8", newline="\n")

    project = json.loads(PROJECT.read_text(encoding="utf-8"))
    if DEST.stem.split(".")[0] not in project["models"]:
        project["models"].append(DEST.stem.split(".")[0])
        PROJECT.write_text(json.dumps(project, indent=2) + "\n", encoding="utf-8", newline="\n")
    print(f"wrote {DEST} ({len(nodes)} nodes, {len(conns)} connections)")
    print(f"inputs: {', '.join([*INPUTS, 'seeker_on'])}")
    print(f"outputs: {', '.join(name for name, _, _ in OUTPUTS)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
