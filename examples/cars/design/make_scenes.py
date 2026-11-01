# /// script
# requires-python = ">=3.11"
# dependencies = ["numpy>=2.0", "scipy>=1.13", "trimesh>=4.4", "networkx>=3", "shapely>=2.0", "mapbox-earcut>=1.0", "rtree>=1.3"]
# ///
"""Meshes (`meshes/*.glb`) and 3D scenes (`scenes/*.sdf`) of the `cars` example.

    uv run examples/cars/design/make_scenes.py

Meshes (built from simple solids; frames as in the bond graph):

* `racecar_body.glb`, `buggy_body.glb`: the chassis in the chassis frame (x forward, y left,
  z up, origin at the sprung centre of gravity; the ground is at z = -h_s at rest).
* `racecar_wheel.glb`, `buggy_wheel.glb`: wheel and tyre in the carrier frame (axle = z), a
  coloured sidewall mark and spokes so the spin is visible; `*_hub.glb` the upright and the brake
  (no spin).
* `racecar_suspension.json`, `buggy_suspension.json`: the suspension rods (arms, push rods or
  dampers, tie rods, drive shafts), each between a point fixed in the chassis frame and a point
  fixed in its corner's carrier frame, for car-sim to draw from both ends every frame;
  `*_suspension.glb` the same rods at rest in the chassis frame (the scenes). The script checks
  that every rod end lies on the body or on the hub.
* `flat.glb`: the test pad of the race car runs (600 m x 600 m with a 10 m grid) and a 2 km
  straight with lane dashes; `grade.glb`: the 25 % ramp; `hills.glb`: the buggy's height field
  (design/hills.json) with its dirt track; `track.glb`: the race track (design/track.json:
  asphalt, kerbs, run-off, grass, the start/finish line).

Scenes: one per vehicle and world (`racecar-flat`, `racecar-track`, `buggy-flat`, `buggy-grade`,
`buggy-hills`). Links `chassis`, `wheel_fl` .. `wheel_rr`, `hub_fl` .. `hub_rr` and `world`;
the models bind them to the CarView outputs (the car stays near the origin and the world moves
under it). The link poses are the static rest poses, so the car is visible before a run.
"""

from __future__ import annotations

import json
import math
import sys
from pathlib import Path

import numpy as np
import trimesh

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(HERE))

import track as TR  # noqa: E402
from bg import Q_CARRIER  # noqa: E402
from vehicles import CORNERS, vehicles  # noqa: E402

MESHES = ROOT / "meshes"
SCENES = ROOT / "scenes"


# ---------------------------------------------------------------------------------------
# Mesh helpers
# ---------------------------------------------------------------------------------------

def coloured(mesh: trimesh.Trimesh, rgb) -> trimesh.Trimesh:
    mesh.visual = trimesh.visual.ColorVisuals(mesh, face_colors=np.tile([*rgb, 255], (len(mesh.faces), 1)))
    return mesh


def box(lo, hi, rgb) -> trimesh.Trimesh:
    lo, hi = np.asarray(lo, float), np.asarray(hi, float)
    m = trimesh.creation.box(extents=hi - lo)
    m.apply_translation((lo + hi) / 2)
    return coloured(m, rgb)


def tube(p, q, r, rgb, sections=10) -> trimesh.Trimesh:
    p, q = np.asarray(p, float), np.asarray(q, float)
    m = trimesh.creation.cylinder(radius=r, segment=[p, q], sections=sections)
    return coloured(m, rgb)


def sphere(c, r, rgb) -> trimesh.Trimesh:
    m = trimesh.creation.icosphere(subdivisions=2, radius=r)
    m.apply_translation(c)
    return coloured(m, rgb)


def loft(stations, rgb, segments=28, yc=0.0) -> trimesh.Trimesh:
    """Body of elliptic sections: stations (x, half-width, half-height, z-centre), front first."""
    rings = []
    ang = np.linspace(0, 2 * math.pi, segments, endpoint=False)
    for x, a, b, zc in stations:
        rings.append(np.column_stack([np.full(segments, x), yc + a * np.cos(ang), zc + b * np.sin(ang)]))
    verts = np.vstack(rings + [[[stations[0][0], yc, stations[0][3]]], [[stations[-1][0], yc, stations[-1][3]]]])
    front, back = len(verts) - 2, len(verts) - 1
    faces = []
    for r in range(len(rings) - 1):
        for k in range(segments):
            a = r * segments + k
            b = r * segments + (k + 1) % segments
            faces += [[a, a + segments, b + segments], [a, b + segments, b]]
    last = (len(rings) - 1) * segments
    for k in range(segments):
        faces.append([front, (k + 1) % segments, k])
        faces.append([back, last + k, last + (k + 1) % segments])
    m = trimesh.Trimesh(verts, np.array(faces), process=True)
    m.fix_normals()
    return coloured(m, rgb)


def plate_xz(points, y0, thickness, rgb) -> trimesh.Trimesh:
    """A flat plate in the x-z plane at y = y0 (the polygon extruded along y)."""
    poly = np.asarray(points, float)
    from shapely.geometry import Polygon

    m = trimesh.creation.extrude_polygon(Polygon(poly), thickness)
    # extrude_polygon builds in x-y and extrudes along z: map (x, y, z) -> (x, z, y)
    m.apply_transform(np.array([[1, 0, 0, 0], [0, 0, 1, 0], [0, 1, 0, 0], [0, 0, 0, 1]], float))
    m.invert()
    m.apply_translation([0, y0 - thickness / 2, 0])
    m.fix_normals()
    return coloured(m, rgb)


def plate_xy(points, z0, thickness, rgb) -> trimesh.Trimesh:
    from shapely.geometry import Polygon

    m = trimesh.creation.extrude_polygon(Polygon(np.asarray(points, float)), thickness)
    m.apply_translation([0, 0, z0 - thickness / 2])
    return coloured(m, rgb)


def revolve(profile, rgb, segments=48) -> trimesh.Trimesh:
    """Surface of revolution about z of the closed profile [(r, z), ...]."""
    prof = np.asarray(profile, float)
    n = len(prof)
    ang = np.linspace(0, 2 * math.pi, segments, endpoint=False)
    verts = np.array([[r * math.cos(a), r * math.sin(a), z] for a in ang for r, z in prof])
    faces = []
    for i in range(segments):
        j = (i + 1) % segments
        for k in range(n):
            k2 = (k + 1) % n
            a, b = i * n + k, i * n + k2
            c, d = j * n + k, j * n + k2
            faces += [[a, c, d], [a, d, b]]
    m = trimesh.Trimesh(verts, np.array(faces), process=True)
    m.fix_normals()
    return coloured(m, rgb)


def mirror_y(mesh: trimesh.Trimesh) -> trimesh.Trimesh:
    m = mesh.copy()
    m.apply_transform(np.diag([1.0, -1.0, 1.0, 1.0]))
    m.invert()
    m.fix_normals()
    return m


def both_sides(mesh):
    return [mesh, mirror_y(mesh)]


def scene_of(parts) -> trimesh.Scene:
    s = trimesh.Scene()
    for i, p in enumerate(parts):
        s.add_geometry(p, node_name=f"part{i}")
    return s


def write(name: str, parts) -> None:
    MESHES.mkdir(exist_ok=True)
    data = scene_of(parts).export(file_type="glb")
    (MESHES / name).write_bytes(data)
    print(f"meshes/{name}: {len(data) / 1024:.0f} kB")


# ---------------------------------------------------------------------------------------
# Vehicles
# ---------------------------------------------------------------------------------------

RED = (200, 30, 35)
WHITE = (235, 235, 235)
CARBON = (38, 38, 42)
YELLOW = (240, 180, 20)
BLACK = (25, 25, 28)
GREY = (120, 124, 130)
RUBBER = (30, 30, 32)
RIM = (190, 192, 198)
BLUE = (30, 70, 160)


# ---------------------------------------------------------------------------------------
# Suspension: rods between a chassis point and a carrier point
# ---------------------------------------------------------------------------------------
#
# The wishbones, push rods, tie rods, dampers and drive shafts join the chassis (sprung) to the
# carriers (unsprung, steered at the front), so neither the body mesh nor the hub mesh can hold
# them: each is a rod between an inner point fixed in the chassis frame and an outer point fixed
# in the carrier frame of its corner (x forward, y down, z the axle; the hub mesh's frame). The
# outer points of the arms, push rods and dampers lie on the kingpin (the carrier y axis through
# the wheel centre, the steering axis of the model), so steering does not move them; the tie rods
# end on the steering arm behind it. car-sim draws every rod from both end points each frame
# (`<vehicle>_suspension.json`); the scenes draw them at rest (`<vehicle>_suspension.glb`, a
# second visual of the chassis link).

# per vehicle: the upright's half height (the ball joints at its top and bottom), the push rod or
# damper mount on it (carrier y), the steering arm end (carrier x, y)
UPRIGHT = {"racecar": {"h": 0.11, "mount": 0.08, "arm": (-0.10, 0.03)},
           "buggy": {"h": 0.15, "mount": -0.10, "arm": (-0.12, 0.05)}}


def racecar_tub(v) -> list:
    """Stations (x, half-width, half-height, z-centre) of the race car's tub and nose, front first."""
    a, b, zg = v["a"], v["b"], -v["h_s"]
    return [(a + 0.80, 0.04, 0.03, zg + 0.16), (a + 0.55, 0.11, 0.07, zg + 0.19), (a + 0.15, 0.17, 0.12, zg + 0.24),
            (a - 0.25, 0.23, 0.16, zg + 0.28), (a - 0.75, 0.33, 0.22, zg + 0.31), (a - 1.25, 0.37, 0.26, zg + 0.33),
            (a - 1.65, 0.37, 0.27, zg + 0.34), (a - 2.15, 0.30, 0.24, zg + 0.34), (-b + 0.25, 0.18, 0.15, zg + 0.31),
            (-b - 0.10, 0.08, 0.08, zg + 0.29)]


def on_tub(stations, x: float, z: float, side: float, inset: float = 0.012) -> tuple[float, float, float]:
    """A point just inside the loft's surface at (x, z) on the side `side` (+1 left), z clamped to
    the upper or lower 80 % of the section (the loft is linear between stations, so its section at x
    is the ellipse of the interpolated station values)."""
    xs = [st[0] for st in stations]
    i = next(k for k in range(len(xs) - 1) if xs[k] >= x >= xs[k + 1])
    t = (xs[i] - x) / (xs[i] - xs[i + 1])
    ha, hb, zc = (stations[i][j] + (stations[i + 1][j] - stations[i][j]) * t for j in (1, 2, 3))
    z = min(max(z, zc - 0.8 * hb), zc + 0.8 * hb)
    y = ha * math.sqrt(1.0 - ((z - zc) / hb) ** 2) - inset
    return (x, side * y, z)


def RACECAR_GEARBOX(v):
    """The race car's gearbox and motor casing (lo, hi corners in the chassis frame)."""
    b, zg = v["b"], -v["h_s"]
    zw = v["corners"]["RL"]["z"]
    return (-b - 0.40, -0.14, zg + 0.08), (-b + 0.30, 0.14, zw + 0.12)


def buggy_frame(v) -> dict:
    """Nodes of the buggy's tube frame (left side; x, y, z in the chassis frame)."""
    a, b = v["a"], v["b"]
    zb = -v["h_s"] + 0.36                       # floor pan underside: 36 cm ground clearance at rest
    return {
        "fb": (a + 0.25, 0.42, zb + 0.05), "ft": (a - 0.05, 0.50, zb + 0.55), "rf": (a - 0.75, 0.62, zb + 1.30),
        "rr": (-b + 0.10, 0.62, zb + 1.30), "rt": (-b - 0.20, 0.55, zb + 0.70), "rb": (-b - 0.35, 0.48, zb + 0.08),
        "mb": (0.0, 0.58, zb + 0.04), "mt": (0.0, 0.62, zb + 0.62),
    }


def BUGGY_BRACKET(v, c):
    """The plate on the floor pan that carries a buggy corner's inner pickups (lo, hi corners)."""
    k = v["corners"][c]
    s = 1.0 if k["left"] else -1.0
    h = UPRIGHT["buggy"]["h"]
    y0, y1 = sorted((s * 0.42, s * 0.48))
    return (k["x"] - 0.32, y0, k["z"] - h - 0.04), (k["x"] + 0.32, y1, k["z"] + h + 0.04)


def carrier_to_chassis(k: dict, p) -> np.ndarray:
    """A carrier-frame point at rest (no travel, no steer) in the chassis frame: carrier x = x,
    carrier y = -z, carrier z = y (bg.Q_CARRIER), about the wheel centre."""
    return np.array([k["x"] + p[0], k["y"] + p[2], k["z"] - p[1]])


def suspension(v, veh: str) -> list[dict]:
    """The rods of the vehicle: per corner, {corner, name, inner (chassis frame), outer (carrier
    frame), r, rgb}."""
    up = UPRIGHT[veh]
    h, mount, (arm_x, arm_y) = up["h"], up["mount"], up["arm"]
    rods = []

    def rod(c, name, inner, outer, r, rgb):
        rods.append({"corner": c, "name": name, "inner": [round(float(q), 5) for q in inner],
                     "outer": [round(float(q), 5) for q in outer], "r": r, "rgb": list(rgb)})

    if veh == "racecar":
        tub = racecar_tub(v)
        lo, hi = RACECAR_GEARBOX(v)
        for c in CORNERS:
            k = v["corners"][c]
            s = 1.0 if k["left"] else -1.0
            x, zw = k["x"], k["z"]
            for arm, zo, zi in (("upper", -h, zw + 0.8 * h), ("lower", h, zw - 0.8 * h)):
                for leg, dx in (("front", 0.26), ("rear", -0.22)):
                    if k["front"]:
                        inner = on_tub(tub, x + dx, zi, s)
                    else:
                        inner = (x + dx, s * (hi[1] - 0.01), zi)
                    rod(c, f"{arm}-{leg}", inner, (0.0, zo, 0.0), 0.012, CARBON)
            # push rod: from the bottom of the upright to the rocker on top of the nose / gearbox
            if k["front"]:
                inner = on_tub(tub, x - 0.12, 1.0, s, inset=0.04)
            else:
                inner = (x + 0.10, s * 0.08, hi[2] - 0.01)
            rod(c, "push-rod", inner, (0.0, mount, 0.0), 0.012, GREY)
            if k["front"]:
                rod(c, "tie-rod", on_tub(tub, x + arm_x, zw - arm_y, s), (arm_x, arm_y, 0.0), 0.010, GREY)
            else:
                rod(c, "drive-shaft", (x, s * (hi[1] - 0.01), zw), (0.0, 0.0, 0.0), 0.022, GREY)
    else:
        N = buggy_frame(v)
        for c in CORNERS:
            k = v["corners"][c]
            s = 1.0 if k["left"] else -1.0
            x, zw = k["x"], k["z"]
            for arm, zo, zi in (("upper", -h, zw + 0.85 * h), ("lower", h, zw - 0.85 * h)):
                for leg, dx in (("front", 0.26), ("rear", -0.26)):
                    rod(c, f"{arm}-{leg}", (x + dx, s * 0.45, zi), (0.0, zo, 0.0), 0.02, BLACK)
            top = N["ft"] if k["front"] else N["rt"]
            rod(c, "damper", (top[0], s * top[1], top[2]), (0.0, mount, 0.0), 0.035, (220, 60, 30))
            if k["front"]:
                rod(c, "tie-rod", (x + arm_x, s * 0.45, zw - arm_y), (arm_x, arm_y, 0.0), 0.014, GREY)
            # drive shaft from the axle's motor (both axles are driven)
            rod(c, "drive-shaft", (x, s * 0.16, zw), (0.0, 0.0, 0.0), 0.025, GREY)
    return rods


def suspension_meshes(v, veh: str) -> list:
    """The rods at rest in the chassis frame (the scenes' static picture of them)."""
    return [tube(r["inner"], carrier_to_chassis(v["corners"][r["corner"]], r["outer"]), r["r"], r["rgb"], 8)
            for r in suspension(v, veh)]


def _attached(parts: list, p) -> float:
    """0 when p is inside a closed part, else its distance to the nearest part (m)."""
    best = math.inf
    for m in parts:
        if m.is_watertight and m.contains([p])[0]:
            return 0.0
        best = min(best, float(trimesh.proximity.closest_point(m, [p])[1][0]))
    return best


def check_suspension(v, veh: str, body: list, hub_parts: list) -> None:
    """Every rod end on its part: the inner end inside the body or within the rod's radius of its
    surface, the outer end likewise on the hub (upright, steering arm, axle)."""
    bad = []
    for r in suspension(v, veh):
        d_in, d_out = _attached(body, r["inner"]), _attached(hub_parts, r["outer"])
        if max(d_in, d_out) > max(r["r"], 0.012):
            bad.append(f"{veh} {r['corner']} {r['name']}: inner {d_in * 100:.1f} cm, outer {d_out * 100:.1f} cm off")
    if bad:
        raise SystemExit("suspension rods not attached:\n  " + "\n  ".join(bad))


def write_suspension(v, veh: str) -> None:
    data = {"comment": "Generated by design/make_scenes.py. Rods between a point fixed in the chassis frame "
                       "(inner; x forward, y left, z up, origin at the sprung CG) and a point fixed in the carrier "
                       "frame of the corner (outer; x forward, y down, z the axle, origin at the wheel centre). "
                       "Radius r in m, colour rgb 0..255.",
            "vehicle": veh, "rods": suspension(v, veh)}
    path = MESHES / f"{veh}_suspension.json"
    path.write_text(json.dumps(data, indent=1) + "\n", encoding="utf-8", newline="\n")
    print(f"meshes/{path.name}: {len(data['rods'])} rods")


def racecar_body(v) -> list:
    hs = v["h_s"]
    a, b = v["a"], v["b"]
    zg = -hs                                     # ground
    P = []
    P.append(box((-b + 0.1, -0.5, zg + 0.035), (a - 0.25, 0.5, zg + 0.055), CARBON))       # floor / plank
    P.append(loft(racecar_tub(v), RED))
    # white stripe on the nose
    P.append(loft([(a + 0.70, 0.03, 0.025, zg + 0.19), (a + 0.2, 0.06, 0.04, zg + 0.34), (a - 0.3, 0.07, 0.04, zg + 0.42)], WHITE, 16))
    # sidepods
    pod = loft([(a - 0.80, 0.05, 0.05, zg + 0.20), (a - 1.0, 0.13, 0.13, zg + 0.24), (a - 1.6, 0.15, 0.14, zg + 0.24),
                (-b + 0.6, 0.10, 0.09, zg + 0.20), (-b + 0.25, 0.04, 0.04, zg + 0.17)], RED, 20, yc=0.42)
    P += both_sides(pod)
    # motor and battery cover with the cooling intake above the driver's head
    P.append(loft([(a - 1.55, 0.10, 0.08, zg + 0.62), (a - 1.75, 0.13, 0.12, zg + 0.58), (a - 2.2, 0.12, 0.14, zg + 0.50),
                   (-b + 0.2, 0.08, 0.10, zg + 0.42), (-b - 0.2, 0.04, 0.05, zg + 0.36)], RED, 20))
    P.append(box((a - 2.0, -0.01, zg + 0.45), (-b - 0.15, 0.01, zg + 0.68), WHITE))          # shark fin
    # cockpit: helmet, roll hoop
    P.append(sphere((a - 1.30, 0.0, zg + 0.62), 0.125, (245, 210, 30)))
    P.append(box((a - 1.20, -0.09, zg + 0.60), (a - 1.12, 0.09, zg + 0.645), BLACK))           # visor
    P.append(tube((a - 1.0, -0.2, zg + 0.52), (a - 1.0, 0.2, zg + 0.52), 0.02, CARBON))
    # front wing: main plane, flap, end plates
    P.append(box((a + 0.45, -0.85, zg + 0.07), (a + 0.85, 0.85, zg + 0.09), CARBON))
    P.append(box((a + 0.35, -0.85, zg + 0.12), (a + 0.55, 0.85, zg + 0.135), RED))
    for s in (-1, 1):
        P.append(box((a + 0.30, s * 0.86 - 0.01, zg + 0.04), (a + 0.88, s * 0.86 + 0.01, zg + 0.22), WHITE))
        P.append(box((a + 0.45, s * 0.15 - 0.01, zg + 0.09), (a + 0.60, s * 0.15 + 0.01, zg + 0.20), CARBON))
    # rear wing: two elements on end plates and a pylon
    P.append(box((-b - 0.65, -0.48, zg + 0.82), (-b - 0.30, 0.48, zg + 0.85), CARBON))
    P.append(box((-b - 0.35, -0.48, zg + 0.88), (-b - 0.15, 0.48, zg + 0.90), RED))
    for s in (-1, 1):
        P.append(box((-b - 0.70, s * 0.49 - 0.01, zg + 0.35), (-b - 0.10, s * 0.49 + 0.01, zg + 0.95), RED))
    P.append(box((-b - 0.45, -0.015, zg + 0.40), (-b - 0.30, 0.015, zg + 0.83), CARBON))
    # diffuser, and the gearbox between the rear wheels: it carries the rear suspension pickups,
    # the drive shafts and the rear wing pylon (the suspension rods are not part of the body,
    # see `suspension`)
    P.append(box((-b - 0.25, -0.45, zg + 0.04), (-b + 0.2, 0.45, zg + 0.10), CARBON))
    P.append(box(*RACECAR_GEARBOX(v), CARBON))
    # numbers on the cover
    P += both_sides(box((-0.30, 0.125, zg + 0.46), (0.05, 0.13, zg + 0.56), WHITE))
    return P


def buggy_body(v) -> list:
    hs = v["h_s"]
    a, b = v["a"], v["b"]
    zg = -hs
    P = []
    zb = zg + 0.36                               # floor pan underside: 36 cm ground clearance at rest
    P.append(box((-b - 0.1, -0.55, zb), (a + 0.05, 0.55, zb + 0.04), GREY))
    r = 0.028
    # tube frame: nodes (x, y, z) for the left side, mirrored
    N = buggy_frame(v)
    edges = [("fb", "ft"), ("ft", "rf"), ("rf", "rr"), ("rr", "rt"), ("rt", "rb"), ("rb", "mb"), ("mb", "fb"),
             ("ft", "mt"), ("mt", "rt"), ("mb", "mt"), ("rf", "mt"), ("mt", "rr")]
    for s in (1, -1):
        def n(k):
            x, y, z = N[k]
            return (x, s * y, z)
        for e in edges:
            P.append(tube(n(e[0]), n(e[1]), r, BLACK))
    for k in ("fb", "ft", "rf", "rr", "rt", "rb"):
        x, y, z = N[k]
        P.append(tube((x, -y, z), (x, y, z), r, BLACK))
    # body panels: hood, side panels, rear deck, seats
    P.append(plate_xy([(a + 0.30, -0.45), (a + 0.30, 0.45), (a - 0.30, 0.52), (a - 0.30, -0.52)], zb + 0.48, 0.03, YELLOW))
    for s in (1, -1):
        P.append(plate_xz([(a + 0.25, zb + 0.08), (a - 0.05, zb + 0.52), (-b - 0.20, zb + 0.66), (-b - 0.32, zb + 0.10)],
                          s * 0.60, 0.02, YELLOW))
        P.append(box((-0.45, s * 0.30 - 0.20, zb + 0.04), (0.05, s * 0.30 + 0.20, zb + 0.22), BLUE))     # seats
        P.append(box((-0.50, s * 0.30 - 0.20, zb + 0.20), (-0.38, s * 0.30 + 0.20, zb + 0.75), BLUE))
    P.append(plate_xy([(-b + 0.05, -0.55), (-b + 0.05, 0.55), (-b - 0.30, 0.50), (-b - 0.30, -0.50)], zb + 0.68, 0.03, YELLOW))
    P.append(plate_xy([(a - 0.75, -0.62), (a - 0.75, 0.62), (-b + 0.10, 0.62), (-b + 0.10, -0.62)], zb + 1.33, 0.02, BLACK))
    # battery pack low in the middle, a motor on each axle (between the drive shafts), lights
    P.append(box((-b + 0.55, -0.45, zb + 0.06), (a - 0.75, 0.45, zb + 0.30), (40, 70, 140)))
    for c in ("FL", "RL"):
        xm, zm = v["corners"][c]["x"], v["corners"][c]["z"]
        P.append(tube((xm, -0.16, zm), (xm, 0.16, zm), 0.13, GREY, 16))
    for s in (1, -1):
        P.append(tube((a - 0.65, s * 0.35, zb + 1.38), (a - 0.55, s * 0.35, zb + 1.38), 0.08, (250, 245, 200)))
    # suspension brackets on the floor pan: they carry the inner pickups of the arms and the
    # steering rack ends (the arms, dampers and shafts are not part of the body, see `suspension`)
    for c in CORNERS:
        P.append(box(*BUGGY_BRACKET(v, c), BLACK))
    return P


def wheel(v, knobby: bool) -> list:
    ty = v["tyre"]
    R = ty["R0"]
    w = 0.32
    rr = R * (0.62 if not knobby else 0.55)
    prof = [(rr, -w / 2), (R - 0.03, -w / 2), (R - 0.005, -w / 2 + 0.03), (R, -w / 2 + 0.06), (R, w / 2 - 0.06),
            (R - 0.005, w / 2 - 0.03), (R - 0.03, w / 2), (rr, w / 2), (rr, w / 2 - 0.02), (rr, -w / 2 + 0.02)]
    P = [revolve(prof, RUBBER, 64)]
    if knobby:
        for i in range(28):
            ang = 2 * math.pi * i / 28
            for zz in (-0.08, 0.08):
                blk = box((-0.035, -0.04, -0.045), (0.035, 0.04, 0.045), (45, 45, 48))
                blk.apply_translation([R + 0.012, 0, zz + (0.03 if i % 2 else -0.03)])
                blk.apply_transform(trimesh.transformations.rotation_matrix(ang, [0, 0, 1]))
                P.append(blk)
    # rim: barrel and dish with spokes on both faces (symmetric, the same mesh on both sides)
    P.append(revolve([(rr - 0.012, -w / 2 + 0.01), (rr, -w / 2 + 0.01), (rr, w / 2 - 0.01), (rr - 0.012, w / 2 - 0.01)], RIM, 48))
    for face in (-1, 1):
        zf = face * (w / 2 - 0.05)
        P.append(revolve([(0.0, zf - 0.015), (0.07, zf - 0.015), (0.07, zf + 0.015), (0.0, zf + 0.015)], RIM, 24))
        for i in range(5):
            ang = 2 * math.pi * i / 5
            sp = box((0.05, -0.022, zf - 0.012), (rr - 0.01, 0.022, zf + 0.012), RIM if i else (230, 60, 40))
            sp.apply_transform(trimesh.transformations.rotation_matrix(ang, [0, 0, 1]))
            P.append(sp)
    # a sidewall mark so the spin is visible on the tyre too
    for face in (-1, 1):
        mk = box((R - 0.07, -0.03, face * w / 2 - 0.004), (R - 0.03, 0.03, face * w / 2 + 0.004), (240, 200, 30))
        P.append(mk)
    return P


def hub(v, buggy: bool) -> list:
    """Upright and brake caliper in the carrier frame (x forward, y down, z = axle), symmetric."""
    P = [revolve([(0.0, -0.06), (0.06, -0.06), (0.06, 0.06), (0.0, 0.06)], GREY, 20)]
    for face in (-1, 1):
        cal = box((-0.06, -0.20, face * 0.05 - 0.03), (0.06, -0.12, face * 0.05 + 0.03), (200, 40, 40) if not buggy else (60, 60, 200))
        P.append(cal)
    # the upright along the kingpin (its ends carry the arms' ball joints) and the steering arm
    up = UPRIGHT["buggy" if buggy else "racecar"]
    h, (ax, ay) = up["h"], up["arm"]
    P.append(box((-0.04, -h - 0.015, -0.035), (0.04, h + 0.015, 0.035), CARBON))
    P.append(box((ax - 0.015, ay - 0.015, -0.015), (-0.03, ay + 0.015, 0.015), CARBON))
    return P


# ---------------------------------------------------------------------------------------
# Worlds
# ---------------------------------------------------------------------------------------

ASPHALT = (78, 80, 84)
ASPHALT2 = (92, 94, 98)
LINE = (225, 225, 225)
GRASS = (70, 128, 60)
GRASS2 = (82, 140, 68)
KERB_R = (205, 40, 40)
DIRT = (150, 118, 80)


def flat_world() -> list:
    P = [box((-300, -300, -0.02), (300, 300, 0.0), ASPHALT)]
    for k in range(-30, 31):
        P.append(box((k * 10 - 0.06, -300, 0.0), (k * 10 + 0.06, 300, 0.004), ASPHALT2))
        P.append(box((-300, k * 10 - 0.06, 0.0), (300, k * 10 + 0.06, 0.004), ASPHALT2))
    # the straight of the top-speed run: 2 km along +x with lane dashes
    P.append(box((300, -8, -0.02), (2300, 8, 0.0), ASPHALT))
    for x in range(300, 2300, 20):
        P.append(box((x, -0.08, 0.0), (x + 8, 0.08, 0.005), LINE))
    for s in (-1, 1):
        P.append(box((300, s * 7.5 - 0.1, 0.0), (2300, s * 7.5 + 0.1, 0.005), LINE))
        P.append(box((300, s * 8, -0.02), (2300, s * 40, -0.005), GRASS))
    return P


def grade_world(slope: float) -> list:
    gam = math.atan(slope)
    ramp = box((-30, -10, -0.15), (130, 10, 0.0), DIRT)
    stripes = [box((x, -10, 0.0), (x + 0.4, 10, 0.004), (120, 95, 65)) for x in range(-30, 130, 5)]
    parts = [ramp] + stripes
    rot = trimesh.transformations.rotation_matrix(-gam, [0, 1, 0])
    out = []
    for p in parts:
        q = p.copy()
        # the ramp's local x runs along the slope: x_world = s cos(gam), z = s sin(gam)
        q.apply_transform(rot)
        out.append(q)
    return out


def height(t: dict, x, y):
    h = t["h0"] + t["sx"] * x + t["sy"] * y
    for a, kx, ky, ph in zip(t["a"], t["kx"], t["ky"], t["ph"]):
        h = h + a * np.cos(kx * x + ky * y + ph)
    return h


def hills_world(t: dict, xr=(-260.0, 140.0), yr=(-160.0, 160.0), step=2.0, path=None) -> list:
    xs = np.arange(xr[0], xr[1] + 1e-9, step)
    ys = np.arange(yr[0], yr[1] + 1e-9, step)
    X, Y = np.meshgrid(xs, ys, indexing="ij")
    Z = height(t, X, Y)
    verts = np.column_stack([X.ravel(), Y.ravel(), Z.ravel()])
    nx, ny = X.shape
    faces = []
    for i in range(nx - 1):
        for j in range(ny - 1):
            a = i * ny + j
            faces += [[a, a + ny, a + ny + 1], [a, a + ny + 1, a + 1]]
    m = trimesh.Trimesh(verts, np.array(faces), process=False)
    # colours: grass shaded by height and slope, the dirt track along the recorded path
    hx = np.gradient(Z, step, axis=0)
    hy = np.gradient(Z, step, axis=1)
    sl = np.sqrt(hx ** 2 + hy ** 2).ravel()
    hn = ((Z.ravel() - Z.min()) / max(Z.max() - Z.min(), 1e-6))
    col = np.zeros((len(verts), 4), dtype=np.uint8)
    base = np.array(GRASS, float)
    hi = np.array((120, 150, 80), float)
    rock = np.array((120, 112, 100), float)
    c = base[None, :] * (1 - hn[:, None]) + hi[None, :] * hn[:, None]
    c = c * (1 - np.clip(sl[:, None] * 1.5, 0, 0.6)) + rock[None, :] * np.clip(sl[:, None] * 1.5, 0, 0.6)
    if path is not None:
        P = np.asarray(path)
        d = np.full(len(verts), 1e9)
        for k in range(0, len(P), 2):
            d = np.minimum(d, (verts[:, 0] - P[k, 0]) ** 2 + (verts[:, 1] - P[k, 1]) ** 2)
        w = np.clip(1.0 - (np.sqrt(d) - 1.2) / 1.5, 0, 1)
        c = c * (1 - w[:, None]) + np.array(DIRT, float)[None, :] * w[:, None]
    col[:, :3] = np.clip(c, 0, 255).astype(np.uint8)
    col[:, 3] = 255
    m.visual = trimesh.visual.ColorVisuals(m, vertex_colors=col)
    return [m]


def ribbon(px, py, d0, d1, z, rgb, closed=True) -> trimesh.Trimesh:
    """A strip between the lateral offsets d0 and d1 of the polyline (px, py) with normals."""
    p = np.column_stack([px, py])
    t = np.roll(p, -1, axis=0) - np.roll(p, 1, axis=0)
    t /= np.linalg.norm(t, axis=1)[:, None]
    n = np.column_stack([-t[:, 1], t[:, 0]])
    a = p + n * d0
    b = p + n * d1
    N = len(p)
    verts = np.vstack([np.column_stack([a, np.full(N, z)]), np.column_stack([b, np.full(N, z)])])
    faces = []
    for i in range(N if closed else N - 1):
        j = (i + 1) % N
        faces += [[i, j, N + j], [i, N + j, N + i]]
    m = trimesh.Trimesh(verts, np.array(faces), process=False)
    m.fix_normals()
    if m.face_normals[:, 2].mean() < 0:
        m.invert()
    return coloured(m, rgb)


def track_world() -> list:
    c = TR.centreline(1.0)
    px, py = c["p"][:, 0], c["p"][:, 1]
    curv = c["curv"]
    lo, hi = px.min() - 120, px.max() + 120
    blo, bhi = py.min() - 120, py.max() + 120
    P = [box((lo, blo, -0.03), (hi, bhi, -0.006), GRASS)]
    hw, kb, ro = TR.HALF_WIDTH, TR.KERB, TR.RUNOFF
    # run-off on the outside of corners (drawn below the asphalt and the kerbs)
    corner = np.abs(curv) > TR.KERB_CURV
    idx = np.flatnonzero(corner)
    runs = np.split(idx, np.flatnonzero(np.diff(idx) > 1) + 1) if len(idx) else []
    for r in runs:
        if len(r) < 3:
            continue
        side = -1.0 if curv[r].mean() > 0 else 1.0
        rr = np.concatenate([r[:1] - np.arange(8, 0, -1), r, r[-1:] + np.arange(1, 9)]) % len(px)
        P.append(ribbon(px[rr], py[rr], side * (hw + kb), side * (hw + kb + ro), -0.003, ASPHALT2, closed=False))
        # kerbs: alternating red and white blocks of 3 m on both edges of the corner
        for s in (-1.0, 1.0):
            for k0 in range(0, len(rr) - 3, 3):
                seg = rr[k0:k0 + 4]
                P.append(ribbon(px[seg], py[seg], s * hw, s * (hw + kb), -0.001, KERB_R if (k0 // 3) % 2 else WHITE, closed=False))
    P.append(ribbon(px, py, -hw, hw, -0.002, ASPHALT))
    # white edge lines and the start/finish line with a chequered strip
    for s in (-1.0, 1.0):
        P.append(ribbon(px, py, s * (hw - 0.35), s * (hw - 0.2), -0.0005, LINE))
    for i in range(12):
        for j in range(2):
            y0 = -hw + i * hw / 6
            P.append(box((-1.0 + j * 1.0, y0, -0.001), (0.0 + j * 1.0, y0 + hw / 6, 0.0),
                         BLACK if (i + j) % 2 else WHITE))
    # a gantry over the start/finish line and grandstand blocks
    for s in (-1, 1):
        P.append(box((-0.3, s * (hw + 3.0) - 0.3, 0.0), (0.3, s * (hw + 3.0) + 0.3, 6.5), GREY))
    P.append(box((-0.4, -hw - 3.3, 6.0), (0.4, hw + 3.3, 7.0), (30, 30, 120)))
    for k in range(6):
        P.append(box((40 + 30 * k, -hw - 25, 0.0), (65 + 30 * k, -hw - 15, 3 + 0.0), (150, 150, 160)))
    return P


# ---------------------------------------------------------------------------------------
# SDF
# ---------------------------------------------------------------------------------------

def quat_to_rpy(q) -> tuple[float, float, float]:
    w, x, y, z = q
    roll = math.atan2(2 * (w * x + y * z), 1 - 2 * (x * x + y * y))
    pitch = math.asin(max(-1.0, min(1.0, 2 * (w * y - z * x))))
    yaw = math.atan2(2 * (w * z + x * y), 1 - 2 * (y * y + z * z))
    return roll, pitch, yaw


def sdf(name: str, comment: str, veh: str, v: dict, world_mesh: str, chassis_pose=None) -> str:
    hs = v["h_s"]
    cz = chassis_pose[2] if chassis_pose else hs
    rr, pp, yy = quat_to_rpy(Q_CARRIER)
    lines = ['<?xml version="1.0"?>', "<!--", comment, "-->", '<sdf version="1.9">', f'  <model name="{name}">',
             '    <link name="world">', "      <pose>0 0 0 0 0 0</pose>",
             '      <visual name="ground">', "        <pose>0 0 0 0 0 0</pose>",
             f"        <geometry><mesh><uri>meshes/{world_mesh}</uri></mesh></geometry>", "      </visual>", "    </link>",
             '    <link name="chassis">', f"      <pose>0 0 {cz:.4f} 0 0 0</pose>", '      <visual name="body">',
             "        <pose>0 0 0 0 0 0</pose>",
             f"        <geometry><mesh><uri>meshes/{veh}_body.glb</uri></mesh></geometry>", "      </visual>",
             '      <visual name="suspension">', "        <pose>0 0 0 0 0 0</pose>",
             f"        <geometry><mesh><uri>meshes/{veh}_suspension.glb</uri></mesh></geometry>", "      </visual>",
             "    </link>"]
    for c in CORNERS:
        k = v["corners"][c]
        x, y, z = k["x"], k["y"], cz + k["z"]
        for link, mesh in ((f"wheel_{c.lower()}", f"{veh}_wheel.glb"), (f"hub_{c.lower()}", f"{veh}_hub.glb")):
            lines += [f'    <link name="{link}">', f"      <pose>{x:.4f} {y:.4f} {z:.4f} {rr:.6f} {pp:.6f} {yy:.6f}</pose>",
                      f'      <visual name="{link}_v">', "        <pose>0 0 0 0 0 0</pose>",
                      f"        <geometry><mesh><uri>meshes/{mesh}</uri></mesh></geometry>", "      </visual>", "    </link>"]
    lines += ["  </model>", "</sdf>", ""]
    return "\n".join(lines)


def main() -> int:
    V = vehicles()
    rc, bg = V["racecar"], V["buggy"]
    write("racecar_body.glb", racecar_body(rc))
    write("buggy_body.glb", buggy_body(bg))
    write("racecar_wheel.glb", wheel(rc, knobby=False))
    write("buggy_wheel.glb", wheel(bg, knobby=True))
    write("racecar_hub.glb", hub(rc, False))
    write("buggy_hub.glb", hub(bg, True))
    check_suspension(rc, "racecar", racecar_body(rc), hub(rc, False))
    check_suspension(bg, "buggy", buggy_body(bg), hub(bg, True))
    write("racecar_suspension.glb", suspension_meshes(rc, "racecar"))
    write("buggy_suspension.glb", suspension_meshes(bg, "buggy"))
    write_suspension(rc, "racecar")
    write_suspension(bg, "buggy")
    write("flat.glb", flat_world())
    write("grade.glb", grade_world(0.25))
    hills = json.loads((HERE / "hills.json").read_text(encoding="utf-8"))
    pth = HERE / "hills_path.json"
    path = json.loads(pth.read_text(encoding="utf-8"))["xy"] if pth.exists() else None
    write("hills.glb", hills_world(hills, path=path))
    write("track.glb", track_world())
    SCENES.mkdir(exist_ok=True)
    common = ("  Generated by design/make_scenes.py. Z up, metres. The car stays near the origin: the\n"
              "  link \"world\" (the ground) moves under it by minus the chassis' horizontal position,\n"
              "  bound to View/ground; \"chassis\" to View/body, \"wheel_xx\" (spinning) to View/w1..w4,\n"
              "  \"hub_xx\" (upright and brake) to View/c1..c4. Link poses: the car at rest. The suspension\n"
              "  rods (visual \"suspension\" of the chassis) are drawn at rest: they join the chassis to the\n"
              "  carriers, so a moving wheel leaves them by its travel (car-sim draws them from both ends).")
    scenes = {
        "racecar-flat": ("racecar", rc, "flat.glb", "  Race car on the test pad (600 m grid, 2 km straight).\n" + common),
        "racecar-track": ("racecar", rc, "track.glb", "  Race car on the circuit of design/track.py.\n" + common),
        "buggy-flat": ("buggy", bg, "flat.glb", "  Buggy on the test pad.\n" + common),
        "buggy-grade": ("buggy", bg, "grade.glb", "  Buggy on the 25 % ramp.\n" + common),
        "buggy-hills": ("buggy", bg, "hills.glb", "  Buggy on the rolling hills of design/hills.json.\n" + common),
    }
    for nm, (veh, v, world, comment) in scenes.items():
        (SCENES / f"{nm}.sdf").write_text(sdf(nm, comment, veh, v, world), encoding="utf-8", newline="\n")
        print(f"scenes/{nm}.sdf")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
