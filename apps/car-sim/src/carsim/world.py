"""The worlds: sky and light, and the race track or the rolling hills. All procedural.

Panda3D coordinates are those of the FMU: x, y horizontal, z up, metres.

Race track: the circuit lies on z = 0, the race car's physics ground. Grass, run-off, kerbs,
asphalt and the paint are all drawn *at* z = 0, so a tyre touches the drawn surface where the
FMU's contact sits; Panda's depth offsets (grass 0, run-off/kerb/asphalt 1, paint 2) decide which
coplanar layer wins instead of a few millimetres of height, which would z-fight at a distance.

Hills: the heightfield is a grid of 2 m over the drivable square |x|, |y| <= 400 m whose vertices
lie exactly on terrain.Hills.height, the function the FMU's TerrainSurface elements evaluate.
Between the vertices the drawn triangles are within 2 cm of the analytic surface (the shortest
wavelength is 25 m). Beyond the square a coarser ring (10 m) continues the same function to the
horizon.
"""

from __future__ import annotations

import math

import numpy as np
from panda3d.core import (
    AmbientLight, CompassEffect, DirectionalLight, Fog, Geom, GeomNode, GeomTriangles,
    GeomVertexArrayFormat, GeomVertexData, GeomVertexFormat, NodePath, SamplerState, Texture, Vec4,
)

from .terrain import EXTENT, Hills
from .track import Track

_FMT = None
HORIZON = (0.74, 0.82, 0.92)
ZENITH = (0.22, 0.42, 0.76)


def _format():
    global _FMT
    if _FMT is None:
        a = GeomVertexArrayFormat()
        a.add_column("vertex", 3, Geom.NT_float32, Geom.C_point)
        a.add_column("normal", 3, Geom.NT_float32, Geom.C_normal)
        a.add_column("color", 4, Geom.NT_float32, Geom.C_color)
        a.add_column("texcoord", 2, Geom.NT_float32, Geom.C_texcoord)
        _FMT = GeomVertexFormat.register_format(GeomVertexFormat(a))
    return _FMT


def mesh(name: str, v, n, c, tris, uv=None) -> NodePath:
    """A GeomNode from numpy arrays (vertices, normals, RGBA colours, triangle indices, UVs)."""
    v = np.asarray(v, float)
    count = len(v)
    n = np.broadcast_to(np.asarray(n, float), (count, 3))
    c = np.broadcast_to(np.asarray(c, float), (count, 4))
    uv = np.zeros((count, 2)) if uv is None else np.asarray(uv, float)
    data = np.hstack([v, n, c, uv]).astype(np.float32)
    vdata = GeomVertexData(name, _format(), Geom.UH_static)
    vdata.unclean_set_num_rows(count)
    vdata.modify_array(0).modify_handle().copy_data_from(data.tobytes())
    prim = GeomTriangles(Geom.UH_static)
    prim.set_index_type(Geom.NT_uint32)
    prim.modify_vertices().modify_handle().copy_data_from(np.ascontiguousarray(tris, dtype=np.uint32).tobytes())
    geom = Geom(vdata)
    geom.add_primitive(prim)
    node = GeomNode(name)
    node.add_geom(geom)
    return NodePath(node)


def grid_tris(nx: int, ny: int) -> np.ndarray:
    i, j = np.meshgrid(np.arange(nx - 1), np.arange(ny - 1), indexing="ij")
    a = (i * ny + j).ravel()
    b, c, d = a + ny, a + 1, a + ny + 1
    return np.stack([a, b, d, a, d, c], axis=1).reshape(-1, 3)


def box(name, lo, hi, color) -> NodePath:
    """An axis-aligned box from the corner lo to the corner hi (five faces: no bottom)."""
    (x0, y0, z0), (x1, y1, z1) = lo, hi
    faces = [((0, 0, 1), [(x0, y0, z1), (x1, y0, z1), (x1, y1, z1), (x0, y1, z1)]),
             ((0, -1, 0), [(x0, y0, z0), (x1, y0, z0), (x1, y0, z1), (x0, y0, z1)]),
             ((1, 0, 0), [(x1, y0, z0), (x1, y1, z0), (x1, y1, z1), (x1, y0, z1)]),
             ((0, 1, 0), [(x1, y1, z0), (x0, y1, z0), (x0, y1, z1), (x1, y1, z1)]),
             ((-1, 0, 0), [(x0, y1, z0), (x0, y0, z0), (x0, y0, z1), (x0, y1, z1)])]
    v, n, t = [], [], []
    for nrm, quad in faces:
        b = len(v)
        v += quad
        n += [nrm] * 4
        t += [(b, b + 1, b + 2), (b, b + 2, b + 3)]
    return mesh(name, v, n, color, t)


def cylinder(name, r0, r1, h, color, seg=12) -> NodePath:
    a = np.linspace(0, 2 * math.pi, seg + 1)
    v, n, t = [], [], []
    for k in range(seg):
        for aa, z, r in ((a[k], 0, r0), (a[k + 1], 0, r0), (a[k + 1], h, r1), (a[k], h, r1)):
            v.append((r * math.cos(aa), r * math.sin(aa), z))
            n.append((math.cos(aa), math.sin(aa), 0.3))
        b = 4 * k
        t += [(b, b + 1, b + 2), (b, b + 2, b + 3)]
    return mesh(name, v, n, color, t)


def noise_texture(size: int, seed: int, base, var) -> Texture:
    """A tileable grain texture (sums of periodic sines plus pixel noise) to modulate a colour."""
    rng = np.random.default_rng(seed)
    yy, xx = np.mgrid[0:size, 0:size] / size * 2 * math.pi
    nse = np.zeros((size, size))
    for k in range(1, 7):
        fx, fy, ph = rng.integers(1, 5 * k), rng.integers(1, 5 * k), rng.uniform(0, 6.28)
        nse += np.sin(fx * xx + fy * yy + ph) / k
    img = np.empty((size, size, 3))
    img[:] = base
    img *= (1.0 + var * nse)[..., None]
    img += rng.normal(0, 0.025, img.shape)
    img = np.clip(img, 0, 1)
    tex = Texture("grain")
    tex.setup_2d_texture(size, size, Texture.T_unsigned_byte, Texture.F_rgb)
    tex.set_ram_image(np.ascontiguousarray((img[::-1, :, ::-1] * 255).astype(np.uint8)).tobytes())
    tex.set_minfilter(SamplerState.FT_linear_mipmap_linear)
    tex.set_magfilter(SamplerState.FT_linear)
    tex.set_anisotropic_degree(8)
    tex.set_wrap_u(SamplerState.WM_repeat)
    tex.set_wrap_v(SamplerState.WM_repeat)
    return tex


def ribbon(name, p, nrm, d0, d1, color, closed=True) -> NodePath:
    """A flat strip at z = 0 between the lateral offsets d0 and d1 of the polyline p."""
    N = len(p)
    a = p + nrm * d0
    b = p + nrm * d1
    v = np.vstack([np.column_stack([a, np.zeros(N)]), np.column_stack([b, np.zeros(N)])])
    t = []
    for i in range(N if closed else N - 1):
        j = (i + 1) % N
        t += [(i, j, N + j), (i, N + j, N + i)] if d1 > d0 else [(i, N + j, j), (i, N + i, N + j)]
    uv = v[:, :2] / 4.0
    return mesh(name, v, (0, 0, 1), color, t, uv)


class World:
    """Lights, the sky dome and the ground of one vehicle's world."""

    def __init__(self, render: NodePath, camera: NodePath, vehicle: str):
        self.root = render.attach_new_node("world")
        self.camera = camera
        self.vehicle = vehicle
        self._lights(render)
        self._sky(render)
        self.tv_points: list[tuple[float, float, float]] = []
        if vehicle == "racecar":
            self.track = Track()
            self._track()
        else:
            self.hills = Hills()
            self._hills()
        fog = Fog("haze")
        fog.set_color(*HORIZON)
        fog.set_exp_density(1.0 / 2500.0)
        self.root.set_fog(fog)

    # ---- environment
    def _lights(self, render):
        sun = DirectionalLight("sun")
        sun.set_color(Vec4(1.0, 0.96, 0.88, 1))
        self.sun = render.attach_new_node(sun)
        self.sun.set_hpr(-35, -55, 0)
        amb = AmbientLight("amb")
        amb.set_color(Vec4(0.42, 0.45, 0.52, 1))
        self.amb = render.attach_new_node(amb)
        render.set_light(self.sun)
        render.set_light(self.amb)

    def _sky(self, render):
        seg, rings = 48, 24
        th = np.linspace(-0.2, math.pi / 2, rings)
        ph = np.linspace(0, 2 * math.pi, seg)
        T, P = np.meshgrid(th, ph, indexing="ij")
        R = 9000.0
        v = np.stack([R * np.cos(T) * np.cos(P), R * np.cos(T) * np.sin(P), R * np.sin(T)], -1).reshape(-1, 3)
        s = np.clip(np.sin(T), 0, 1).reshape(-1, 1) ** 0.6
        col = np.hstack([(1 - s) * np.array(HORIZON) + s * np.array(ZENITH), np.ones((len(v), 1))])
        sky = mesh("sky", v, -v / R, col, grid_tris(rings, seg)[:, ::-1])
        sky.reparent_to(render)
        sky.set_bin("background", 0)
        sky.set_depth_write(False)
        sky.set_depth_test(False)
        sky.set_light_off()
        sky.set_fog_off()
        sky.set_effect(CompassEffect.make(self.camera, CompassEffect.P_pos))

    # ---- the race track
    def _track(self):
        tr = self.track
        p, nrm, curv = tr.p, tr.n, tr.curv
        hw, kb, ro = tr.half_width, tr.kerb, tr.runoff
        grain = noise_texture(256, 3, (1.0, 1.0, 1.0), 0.05)
        # grass: one big quad at z = 0
        cx, cy = p.mean(axis=0)
        big = 3000.0
        v = [(cx - big, cy - big, 0), (cx + big, cy - big, 0), (cx + big, cy + big, 0), (cx - big, cy + big, 0)]
        grass = mesh("grass", v, (0, 0, 1), (0.30, 0.52, 0.24, 1), [(0, 1, 2), (0, 2, 3)], np.array(v)[:, :2] / 6.0)
        grass.set_texture(noise_texture(256, 7, (1.0, 1.0, 1.0), 0.12))
        grass.reparent_to(self.root)
        layer1 = self.root.attach_new_node("pavement")
        corner = np.abs(curv) > tr.kerb_curv
        idx = np.flatnonzero(corner)
        runs = np.split(idx, np.flatnonzero(np.diff(idx) > 1) + 1) if len(idx) else []
        n = len(p)
        for r in runs:
            if len(r) < 3:
                continue
            side = -1.0 if curv[r].mean() > 0 else 1.0       # the outside of the corner
            rr = r % n
            # run-off on the outside: exactly the surface rule of track.surface (no extension)
            ribbon("runoff", p[rr], nrm[rr], side * (hw + kb), side * (hw + kb + ro), (0.40, 0.41, 0.43, 1),
                   closed=False).reparent_to(layer1)
            for s in (-1.0, 1.0):
                for k0 in range(0, len(rr) - 1, 3):
                    seg = rr[k0:k0 + 4]
                    if len(seg) < 2:
                        continue
                    col = (0.82, 0.16, 0.16, 1) if (k0 // 3) % 2 else (0.93, 0.93, 0.93, 1)
                    ribbon("kerb", p[seg], nrm[seg], s * hw, s * (hw + kb), col, closed=False).reparent_to(layer1)
        ribbon("asphalt", p, nrm, -hw, hw, (0.30, 0.31, 0.33, 1)).reparent_to(layer1)
        layer1.set_texture(grain)
        layer1.set_depth_offset(1)
        layer1.flatten_strong()
        paint = self.root.attach_new_node("paint")
        for s in (-1.0, 1.0):
            ribbon("edge", p, nrm, s * (hw - 0.35), s * (hw - 0.2), (0.92, 0.92, 0.92, 1)).reparent_to(paint)
        # the start/finish line (s = 0): a chequered strip across the track
        t0, n0, p0 = tr.t[0], tr.n[0], tr.p[0]
        for i in range(12):
            for j in range(2):
                d0 = -hw + i * hw / 6
                q = [p0 + t0 * (-1.0 + j) + n0 * d0, p0 + t0 * j + n0 * d0,
                     p0 + t0 * j + n0 * (d0 + hw / 6), p0 + t0 * (-1.0 + j) + n0 * (d0 + hw / 6)]
                v = [(x, y, 0.0) for x, y in q]
                col = (0.08, 0.08, 0.09, 1) if (i + j) % 2 else (0.95, 0.95, 0.95, 1)
                mesh("chequer", v, (0, 0, 1), col, [(0, 1, 2), (0, 2, 3)]).reparent_to(paint)
        paint.set_depth_offset(2)
        paint.flatten_strong()
        # the gantry over the line, grandstands, marker boards, trees
        props = self.root.attach_new_node("props")
        heading = math.degrees(math.atan2(t0[1], t0[0]))
        gantry = props.attach_new_node("gantry")
        gantry.set_pos(p0[0], p0[1], 0)
        gantry.set_h(heading)
        for s in (-1, 1):
            box("post", (-0.3, s * (hw + 3.0) - 0.3, 0), (0.3, s * (hw + 3.0) + 0.3, 6.5), (0.55, 0.57, 0.6, 1)).reparent_to(gantry)
        box("beam", (-0.4, -hw - 3.3, 6.0), (0.4, hw + 3.3, 7.0), (0.12, 0.14, 0.45, 1)).reparent_to(gantry)
        stand = props.attach_new_node("stands")
        for k in range(6):
            x, y, h = tr.pose_at(40 + 30 * k, -(hw + 20.0))
            st = box("stand", (-12, -5, 0), (12, 5, 4.0 + (k % 2)), (0.62, 0.62, 0.68, 1))
            st.reparent_to(stand)
            st.set_pos(x, y, 0)
            st.set_h(math.degrees(h))
        rng = np.random.default_rng(4)
        trees = props.attach_new_node("trees")
        lo, hi = p.min(axis=0) - 150, p.max(axis=0) + 150
        placed = 0
        while placed < 260:
            x, y = rng.uniform(lo[0], hi[0]), rng.uniform(lo[1], hi[1])
            _, _, d = tr.locate(x, y)
            if abs(d) < hw + kb + ro + 12:
                continue
            h = rng.uniform(6, 14)
            tree = trees.attach_new_node("tree")
            cylinder("trunk", 0.25, 0.2, h * 0.35, (0.36, 0.26, 0.16, 1), 6).reparent_to(tree)
            crown = cylinder("crown", h * 0.28, 0.05, h * 0.75, (0.16, 0.36, 0.17, 1), 8)
            crown.reparent_to(tree)
            crown.set_z(h * 0.25)
            tree.set_pos(x, y, 0)
            placed += 1
        props.flatten_strong()
        # track-side cameras: every 150 m, 18 m to the outside, 4 m up
        for s in np.arange(60.0, tr.length, 150.0):
            k = int(np.searchsorted(tr.s, s) % len(p))
            side = -1.0 if curv[k] > 0 else 1.0
            x, y, _ = tr.pose_at(s, side * (hw + kb + 4.0))
            self.tv_points.append((x, y, 4.0))

    # ---- the hills
    def _hills(self):
        H = self.hills
        tex = noise_texture(256, 11, (1.0, 1.0, 1.0), 0.10)
        step = 2.0
        xs = np.arange(-EXTENT, EXTENT + 1e-9, step)
        X, Y = np.meshgrid(xs, xs, indexing="ij")
        Z = H.height(X, Y)
        gx, gy = H.gradient(X, Y)
        node = self._terrain_mesh("hills", X, Y, Z, gx, gy)
        node.set_texture(tex)
        node.reparent_to(self.root)
        # the ring beyond the square: 10 m cells, only those outside it (a vertex on the boundary is shared)
        far_step, far = 10.0, 2400.0
        xs = np.arange(-far, far + 1e-9, far_step)
        X, Y = np.meshgrid(xs, xs, indexing="ij")
        Z = H.height(X, Y)
        gx, gy = H.gradient(X, Y)
        ring = self._terrain_mesh("far", X, Y, Z, gx, gy, hole=EXTENT)
        ring.set_texture(tex)
        ring.reparent_to(self.root)
        # trees and rocks on the hills, the start pad's flags; the camera posts on hilltops
        rng = np.random.default_rng(8)
        props = self.root.attach_new_node("props")
        for _ in range(420):
            x, y = rng.uniform(-EXTENT, EXTENT, 2)
            if abs(math.hypot(x / 170.0, y / 120.0) - 1.0) < 0.12 or math.hypot(x, y) < 25:
                continue           # keep the demo loop and the centre clear
            z = float(H.height(x, y))
            tree = props.attach_new_node("tree")
            h = rng.uniform(5, 11)
            cylinder("trunk", 0.22, 0.18, h * 0.35, (0.36, 0.26, 0.16, 1), 6).reparent_to(tree)
            crown = cylinder("crown", h * 0.3, 0.05, h * 0.75, (0.20, 0.38, 0.16, 1), 8)
            crown.reparent_to(tree)
            crown.set_z(h * 0.25)
            tree.set_pos(x, y, z - 0.3)
        for k in range(36):
            th = 2 * math.pi * k / 36
            for r in (0.88, 1.12):
                x, y = 170.0 * r * math.cos(th), 120.0 * r * math.sin(th)
                z = float(H.height(x, y))
                col = (0.95, 0.45, 0.10, 1) if k % 2 else (0.95, 0.95, 0.95, 1)
                cylinder("pole", 0.06, 0.06, 1.4, col, 6).copy_to(props).set_pos(x, y, z - 0.1)
        props.flatten_strong()
        for k in range(8):
            th = 2 * math.pi * k / 8 + 0.3
            x, y = 205.0 * math.cos(th), 150.0 * math.sin(th)
            self.tv_points.append((x, y, float(H.height(x, y)) + 6.0))

    def _terrain_mesh(self, name, X, Y, Z, gx, gy, hole: float | None = None) -> NodePath:
        nx, ny = X.shape
        v = np.stack([X, Y, Z], -1).reshape(-1, 3)
        nrm = np.stack([-gx, -gy, np.ones_like(Z)], -1)
        nrm /= np.linalg.norm(nrm, axis=-1, keepdims=True)
        slope = (1.0 - nrm[..., 2]).reshape(-1, 1)
        hn = np.clip((Z.reshape(-1, 1) + 4.0) / 9.0, 0, 1)
        low, high, rock = np.array([0.30, 0.50, 0.22]), np.array([0.52, 0.58, 0.32]), np.array([0.50, 0.44, 0.36])
        col = (1 - hn) * low + hn * high
        w = np.clip(slope * 12.0, 0, 0.7)
        col = (1 - w) * col + w * rock
        col = np.hstack([col, np.ones((len(v), 1))])
        tris = grid_tris(nx, ny)
        if hole is not None:
            c = v[tris].mean(axis=1)
            tris = tris[(np.abs(c[:, 0]) > hole) | (np.abs(c[:, 1]) > hole)]
        uv = v[:, :2] / 8.0
        return mesh(name, v, nrm.reshape(-1, 3), col, tris, uv)
