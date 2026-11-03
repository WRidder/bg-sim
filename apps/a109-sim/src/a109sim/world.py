"""The world: sky, the heliport, the countryside, a village, woods, a lake and clouds. All procedural.

Panda3D coordinates: x east, y north, z up (metres). The model's world is x north, y west, z up:
a point (north, west, up) is drawn at (-west, north, up). The ground is flat at z = 0, as the
FMU's (its gear meets a flat ground): the countryside's relief is in the colours and the
objects on it, not in its height, except for the hills beyond 6 km that the circuit never reaches.

The heliport is at the origin: the helipad "H" (a 30 m concrete FATO, the 24 m TLOF circle, the
"H", its edge lights), a second pad, the apron with the hangar, the terminal and the tower, and a
windsock. The grass around it has a fine texture and rows of marker posts, so that a drift of a
few decimetres in the hover shows.

This module started as a copy of apps/cessna-sim's world (the helpers, the sky and the countryside).
"""

from __future__ import annotations

import math

import numpy as np
from panda3d.core import (
    AmbientLight, BillboardEffect, CompassEffect, DirectionalLight, Fog, Geom, GeomNode,
    GeomTriangles, GeomVertexArrayFormat, GeomVertexData, GeomVertexFormat, NodePath, SamplerState,
    Texture, TransparencyAttrib, Vec4,
)

from .core import PAD_RADIUS

_FMT = None
HORIZON = (0.74, 0.82, 0.92)
ZENITH = (0.22, 0.42, 0.76)
GROUND_CAM = (42.0, -38.0, 1.7)               # an observer at the apron's corner (east, north, up): the ground camera
TOWER = (95.0, -55.0, 0.0)                    # the control tower's foot (east, north)
PAD2 = (70.0, 45.0)                           # the second helipad (east, north)
FLAT = 6000.0                                 # m: the flat country around the heliport


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


def mesh(name: str, v: np.ndarray, n: np.ndarray, c: np.ndarray, tris: np.ndarray, uv: np.ndarray | None = None) -> NodePath:
    """A GeomNode from numpy arrays (vertices, normals, RGBA colours, triangle indices, UVs)."""
    count = len(v)
    if uv is None:
        uv = np.zeros((count, 2))
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


def box(name, sx, sy, sz, color, top=None) -> NodePath:
    """A box with its base on z = 0, centred in x and y."""
    hx, hy = sx / 2, sy / 2
    faces = [((0, 0, 1), [(-hx, -hy, sz), (hx, -hy, sz), (hx, hy, sz), (-hx, hy, sz)]),
             ((0, -1, 0), [(-hx, -hy, 0), (hx, -hy, 0), (hx, -hy, sz), (-hx, -hy, sz)]),
             ((1, 0, 0), [(hx, -hy, 0), (hx, hy, 0), (hx, hy, sz), (hx, -hy, sz)]),
             ((0, 1, 0), [(hx, hy, 0), (-hx, hy, 0), (-hx, hy, sz), (hx, hy, sz)]),
             ((-1, 0, 0), [(-hx, hy, 0), (-hx, -hy, 0), (-hx, -hy, sz), (-hx, hy, sz)])]
    v, n, c, t = [], [], [], []
    for k, (nrm, quad) in enumerate(faces):
        base = len(v)
        v += quad
        n += [nrm] * 4
        c += [top if (top is not None and k == 0) else color] * 4
        t += [(base, base + 1, base + 2), (base, base + 2, base + 3)]
    return mesh(name, np.array(v, float), np.array(n, float), np.array(c, float), np.array(t))


def roof(name, sx, sy, h, color) -> NodePath:
    """A gable roof over a box of sx (along the ridge) by sy, its eaves on z = 0."""
    hx, hy = sx / 2, sy / 2
    v = [(-hx, -hy, 0), (hx, -hy, 0), (hx, 0, h), (-hx, 0, h), (hx, hy, 0), (-hx, hy, 0), (-hx, 0, h), (hx, 0, h),
         (-hx, -hy, 0), (-hx, 0, h), (-hx, hy, 0), (hx, -hy, 0), (hx, hy, 0), (hx, 0, h)]
    s = math.hypot(hy, h)
    n = [(0, -h / s, hy / s)] * 4 + [(0, h / s, hy / s)] * 4 + [(-1, 0, 0)] * 3 + [(1, 0, 0)] * 3
    t = [(0, 1, 2), (0, 2, 3), (4, 5, 6), (4, 6, 7), (8, 10, 9), (11, 13, 12)]
    return mesh(name, np.array(v, float), np.array(n, float), np.tile(color, (len(v), 1)), np.array(t))


def cylinder(name, r0, r1, h, color, seg=16) -> NodePath:
    a = np.linspace(0, 2 * math.pi, seg + 1)
    v, n, c, t = [], [], [], []
    for k in range(seg):
        for (aa, z, r) in ((a[k], 0, r0), (a[k + 1], 0, r0), (a[k + 1], h, r1), (a[k], h, r1)):
            v.append((r * math.cos(aa), r * math.sin(aa), z))
            n.append((math.cos(aa), math.sin(aa), 0.3 * (r0 - r1) / max(h, 1e-6)))
            c.append(color)
        b = 4 * k
        t += [(b, b + 1, b + 2), (b, b + 2, b + 3)]
    return mesh(name, np.array(v, float), np.array(n, float), np.array(c, float), np.array(t))


def _texture(img: np.ndarray, name: str) -> Texture:
    size = img.shape[0]
    tex = Texture(name)
    tex.setup_2d_texture(size, size, Texture.T_unsigned_byte, Texture.F_rgb)
    tex.set_ram_image(np.ascontiguousarray((np.clip(img, 0, 1)[::-1, :, ::-1] * 255).astype(np.uint8)).tobytes())
    tex.set_minfilter(SamplerState.FT_linear_mipmap_linear)
    tex.set_magfilter(SamplerState.FT_linear)
    tex.set_anisotropic_degree(8)
    tex.set_wrap_u(SamplerState.WM_repeat)
    tex.set_wrap_v(SamplerState.WM_repeat)
    return tex


def fields_texture(size: int = 512, seed: int = 11) -> Texture:
    """A tileable patchwork of fields (greens, wheat, ploughed brown) with hedgerows and soft noise."""
    rng = np.random.default_rng(seed)
    palette = np.array([[0.40, 0.56, 0.28], [0.47, 0.60, 0.30], [0.62, 0.62, 0.36], [0.55, 0.47, 0.33],
                        [0.35, 0.50, 0.26], [0.70, 0.66, 0.42]])
    img = np.zeros((size, size, 3))
    img[:] = palette[0]
    cells = 8
    step = size // cells
    for i in range(cells):
        for j in range(cells):
            col = palette[rng.integers(len(palette))] * rng.uniform(0.92, 1.06)
            img[i * step:(i + 1) * step, j * step:(j + 1) * step] = col
            if rng.uniform() < 0.5:   # furrows
                yy = np.arange(step)[:, None]
                img[i * step:(i + 1) * step, j * step:(j + 1) * step] *= (1.0 + 0.05 * np.sin(yy * 1.3))
    hedge = np.array([0.22, 0.33, 0.16])
    for k in range(cells):
        img[k * step:k * step + 2, :] = hedge
        img[:, k * step:k * step + 2] = hedge
    yy, xx = np.mgrid[0:size, 0:size] / size * 2 * math.pi
    nse = np.zeros((size, size))
    for k in range(1, 6):
        fx, fy, ph = rng.integers(1, 5 * k), rng.integers(1, 5 * k), rng.uniform(0, 6.28)
        nse += np.sin(fx * xx + fy * yy + ph) / k
    img *= (1.0 + 0.05 * nse)[..., None]
    img += rng.normal(0, 0.015, img.shape)
    return _texture(img, "fields")


def grass_texture(size: int = 256, seed: int = 4, fine: bool = False) -> Texture:
    """Tileable grass. ``fine``: tufts and clover patches with strong contrast (a texture that
    repeats every few metres, for judging the drift in a hover)."""
    rng = np.random.default_rng(seed)
    img = np.zeros((size, size, 3))
    img[:] = (0.38, 0.54, 0.27)
    yy, xx = np.mgrid[0:size, 0:size] / size * 2 * math.pi
    nse = sum(np.sin(rng.integers(1, 8) * xx + rng.integers(1, 8) * yy + rng.uniform(0, 6.3)) / k for k in range(1, 5))
    img *= (1.0 + 0.06 * nse)[..., None]
    img += rng.normal(0, 0.03, img.shape)
    if fine:
        for _ in range(140):               # darker tufts and lighter patches, wrapped (tileable)
            cx, cy = rng.integers(0, size, 2)
            r = rng.uniform(2.0, 9.0)
            dx = (np.arange(size)[None, :] - cx + size / 2) % size - size / 2
            dy = (np.arange(size)[:, None] - cy + size / 2) % size - size / 2
            m = (dx * dx + dy * dy) < r * r
            img[m] *= rng.choice([0.72, 0.8, 1.18, 1.25])
        img += rng.normal(0, 0.05, img.shape)
    return _texture(img, "grass")


def disk_mesh(name, r, color, seg=48) -> NodePath:
    """A flat disc on z = 0, facing up."""
    a = np.linspace(0, 2 * math.pi, seg, endpoint=False)
    v = np.vstack([[0, 0, 0], np.stack([r * np.cos(a), r * np.sin(a), np.zeros(seg)], -1)])
    t = np.array([[0, 1 + k, 1 + (k + 1) % seg] for k in range(seg)])
    return mesh(name, v, np.tile([0, 0, 1.0], (seg + 1, 1)), np.tile(color, (seg + 1, 1)), t)


def ring_mesh(name, r0, r1, color, seg=64) -> NodePath:
    """A flat ring between the radii r0 and r1 on z = 0, facing up."""
    a = np.linspace(0, 2 * math.pi, seg, endpoint=False)
    v = np.vstack([np.stack([r0 * np.cos(a), r0 * np.sin(a), np.zeros(seg)], -1),
                   np.stack([r1 * np.cos(a), r1 * np.sin(a), np.zeros(seg)], -1)])
    t = []
    for k in range(seg):
        j = (k + 1) % seg
        t += [(k, seg + k, seg + j), (k, seg + j, j)]
    return mesh(name, v, np.tile([0, 0, 1.0], (2 * seg, 1)), np.tile(color, (2 * seg, 1)), np.array(t))


def cloud_texture(size=128, seed=3) -> Texture:
    rng = np.random.default_rng(seed)
    yy, xx = (np.mgrid[0:size, 0:size] - size / 2) / (size / 2)
    a = np.zeros((size, size))
    for _ in range(14):
        cx, cy = rng.uniform(-0.45, 0.45, 2)
        r = rng.uniform(0.25, 0.5)
        a = np.maximum(a, np.clip(1 - ((xx - cx) ** 2 + (yy - cy) ** 2) / r**2, 0, 1))
    a = a**1.5
    img = np.zeros((size, size, 4))
    img[..., :3] = 0.97 - 0.1 * (yy[..., None] > 0.2)
    img[..., 3] = a * 0.85
    tex = Texture("cloud")
    tex.setup_2d_texture(size, size, Texture.T_unsigned_byte, Texture.F_rgba)
    tex.set_ram_image(np.ascontiguousarray((img[::-1, :, [2, 1, 0, 3]] * 255).astype(np.uint8)).tobytes())
    tex.set_minfilter(SamplerState.FT_linear_mipmap_linear)
    return tex


def hills(e: np.ndarray, n: np.ndarray) -> np.ndarray:
    """The far hills: zero inside FLAT, rising to a few hundred metres beyond."""
    r = np.hypot(e, n)
    ramp = np.clip((r - FLAT) / 4000.0, 0.0, 1.0)
    h = (180.0 * np.sin(e / 2300.0 + 0.7) * np.cos(n / 3100.0 - 0.4) + 120.0 * np.sin((e + n) / 1700.0) + 260.0)
    return ramp ** 2 * np.maximum(h, 0.0)


class World:
    def __init__(self, render: NodePath, camera: NodePath):
        self.root = render.attach_new_node("world")
        self.camera = camera
        self._lights(render)
        self._sky(render)
        self._ground()
        self._heliport()
        self._countryside()
        self._clouds()
        fog = Fog("haze")
        fog.set_color(*HORIZON)
        fog.set_exp_density(1.0 / 22000.0)
        self.root.set_fog(fog)

    # ---- environment
    def _lights(self, render):
        sun = DirectionalLight("sun")
        sun.set_color(Vec4(1.0, 0.96, 0.88, 1))
        self.sun = render.attach_new_node(sun)
        self.sun.set_hpr(-35, -48, 0)
        amb = AmbientLight("amb")
        amb.set_color(Vec4(0.47, 0.50, 0.57, 1))
        self.amb = render.attach_new_node(amb)
        render.set_light(self.sun)
        render.set_light(self.amb)

    def _sky(self, render):
        seg, rings = 48, 24
        th = np.linspace(-0.15, math.pi / 2, rings)
        ph = np.linspace(0, 2 * math.pi, seg)
        T, P = np.meshgrid(th, ph, indexing="ij")
        R = 40000.0
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
        self.sky = sky

    def _ground(self):
        # the countryside: a grid of fields, flat to FLAT, then the hills
        half, res = 16000.0, 250.0
        xs = np.arange(-half, half + 1, res)
        E, N = np.meshgrid(xs, xs, indexing="ij")
        H = hills(E, N) - 0.25         # just below the heliport's grass
        v = np.stack([E, N, H], -1).reshape(-1, 3)
        gx, gy = np.gradient(H, res)
        nrm = np.stack([-gx, -gy, np.ones_like(H)], -1)
        nrm /= np.linalg.norm(nrm, axis=-1, keepdims=True)
        hn = np.clip(H / 400.0, 0, 1)[..., None]
        col = (1 - hn) * np.array([1.0, 1.0, 1.0]) + hn * np.array([0.72, 0.78, 0.66])
        col = np.concatenate([col, np.ones(H.shape + (1,))], -1).reshape(-1, 4)
        uv = np.stack([E / 1200.0, N / 1200.0], -1).reshape(-1, 2)
        g = mesh("countryside", v, nrm.reshape(-1, 3), col, grid_tris(len(xs), len(xs)), uv)
        g.set_texture(fields_texture())
        g.reparent_to(self.root)
        # beyond: a plain to the horizon
        big = 200000.0
        n0 = 0.0
        v, t = [], []
        for x0, y0, x1, y1 in ((-big, -big, big, n0 - half), (-big, n0 + half, big, big), (-big, n0 - half, -half, n0 + half),
                               (half, n0 - half, big, n0 + half)):
            b = len(v)
            v += [(x0, y0, -0.3), (x1, y0, -0.3), (x1, y1, -0.3), (x0, y1, -0.3)]
            t += [(b, b + 1, b + 2), (b, b + 2, b + 3)]
        v = np.array(v)
        far = mesh("plain", v, np.tile([0, 0, 1.0], (len(v), 1)), np.tile([0.62, 0.70, 0.55, 1.0], (len(v), 1)),
                   np.array(t), v[:, :2] / 1200.0)
        far.set_texture(fields_texture())
        far.reparent_to(self.root)

    def _heliport(self):
        """The helipad "H" at the origin (as the model's world: the ground at z = 0), a second pad,
        the apron with a hangar, the terminal, the tower, a fuel truck, a windsock, and the fine
        grass and marker posts around them."""
        hp = self.root.attach_new_node("heliport")
        # fine grass around the heliport: the texture repeats every 6 m (a few cm per texel), so the
        # ground moves visibly under a drifting hover
        half = 400.0
        q = np.array([[-half, -half, 0], [half, -half, 0], [half, half, 0], [-half, half, 0]], float)
        grass = mesh("heliport_grass", q, np.tile([0, 0, 1.0], (4, 1)), np.ones((4, 4)), np.array([[0, 1, 2], [0, 2, 3]]),
                     q[:, :2] / 6.0)
        grass.set_texture(grass_texture(512, 4, fine=True))
        grass.set_z(-0.03)
        grass.reparent_to(hp)
        concrete, asphalt, white, yellow = (0.62, 0.62, 0.60, 1), (0.30, 0.31, 0.33, 1), (0.95, 0.95, 0.95, 1), (0.95, 0.80, 0.15, 1)
        for (pe, pn), name in (((0.0, 0.0), "H"), (PAD2, "H2")):
            pad = hp.attach_new_node(f"pad_{name}")
            pad.set_pos(pe, pn, 0)
            fato = 30.0 if name == "H" else 22.0
            r = PAD_RADIUS if name == "H" else 8.0
            box("fato", fato, fato, 0.06, concrete).copy_to(pad).set_z(-0.05)
            disk_mesh("tlof", r, asphalt, 48).copy_to(pad).set_z(0.015)
            ring_mesh("tlof_ring", r - 0.9, r - 0.4, white, 64).copy_to(pad).set_z(0.02)
            s = r / 12.0
            for x, y, sx, sy in ((-2.4, 0, 0.9, 9.0), (2.4, 0, 0.9, 9.0), (0, 0, 4.8, 0.9)):   # the "H", 9 m tall
                box("h", sx * s, sy * s, 0.02, white).copy_to(pad).set_pos(x * s, y * s, 0.02)
            for k in range(8):                          # the FATO's corner and side markers
                a = k * math.pi / 4
                x, y = (fato / 2 - 0.8) * np.sign(round(math.cos(a), 6)), (fato / 2 - 0.8) * np.sign(round(math.sin(a), 6))
                box("fato_mark", 1.2, 1.2, 0.02, white).copy_to(pad).set_pos(x, y, 0.01)
            for k in range(16):                         # the edge lights of the TLOF
                a = 2 * math.pi * k / 16
                cylinder("light", 0.12, 0.10, 0.25, yellow, 6).copy_to(pad).set_pos((r + 0.6) * math.cos(a),
                                                                                   (r + 0.6) * math.sin(a), 0)
        # the apron to the east, the taxi lane to the pads
        box("apron", 60.0, 110.0, 0.06, (0.38, 0.38, 0.39, 1)).copy_to(hp).set_pos(95.0, 0.0, -0.045)
        box("taxi", 50.0, 10.0, 0.06, asphalt).copy_to(hp).set_pos(40.0, 0.0, -0.045)
        box("taxi2", 10.0, 45.0, 0.06, asphalt).copy_to(hp).set_pos(70.0, 22.0, -0.045)
        for k in range(12):                             # the yellow taxi line
            box("taxi_line", 2.5, 0.25, 0.02, yellow).copy_to(hp).set_pos(17.0 + 4.0 * k, 0.0, 0.0)
        h = box("hangar", 36.0, 30.0, 11.0, (0.70, 0.72, 0.74, 1)).copy_to(hp)
        h.set_pos(140.0, 15.0, 0)
        r = roof("hangar_roof", 30.0, 37.0, 3.5, (0.55, 0.25, 0.20, 1)).copy_to(hp)
        r.set_pos(140.0, 15.0, 11.0)
        box("hangar_door", 0.3, 24.0, 9.0, (0.42, 0.44, 0.47, 1)).copy_to(hp).set_pos(121.9, 15.0, 0)
        box("terminal", 26.0, 14.0, 6.0, (0.86, 0.84, 0.78, 1), (0.30, 0.30, 0.32, 1)).copy_to(hp).set_pos(135.0, -32.0, 0)
        for k in range(5):
            box("window", 0.2, 3.0, 1.6, (0.30, 0.45, 0.55, 1)).copy_to(hp).set_pos(121.9, -38.0 + 3.5 * k, 2.6)
        tw = hp.attach_new_node("tower")
        tw.set_pos(TOWER[0], TOWER[1], 0)
        box("shaft", 5.0, 5.0, 14.0, (0.85, 0.85, 0.82, 1)).copy_to(tw)
        box("cab", 7.0, 7.0, 3.0, (0.30, 0.45, 0.55, 1), (0.25, 0.25, 0.25, 1)).copy_to(tw).set_z(14.0)
        box("fuel_truck", 2.4, 7.0, 2.8, (0.85, 0.75, 0.15, 1)).copy_to(hp).set_pos(105.0, -12.0, 0)
        box("fuel_tank", 3.0, 8.0, 3.0, (0.9, 0.9, 0.9, 1)).copy_to(hp).set_pos(160.0, -45.0, 0)
        # a parked helicopter on the apron (body, boom, skid-like gear, a two-blade rotor)
        p = hp.attach_new_node("parked_heli")
        p.set_pos(100.0, 30.0, 0)
        p.set_h(-90)
        box("cabin", 1.8, 4.0, 1.8, (0.20, 0.35, 0.65, 1)).copy_to(p).set_z(0.5)
        box("boom", 0.4, 5.0, 0.4, (0.20, 0.35, 0.65, 1)).copy_to(p).set_pos(0, -4.4, 1.6)
        box("fin", 0.1, 1.0, 1.4, (0.20, 0.35, 0.65, 1)).copy_to(p).set_pos(0, -6.8, 1.6)
        box("rotor", 0.3, 10.0, 0.05, (0.12, 0.12, 0.13, 1)).copy_to(p).set_pos(0, 0, 2.6)
        cylinder("mast", 0.12, 0.1, 0.4, (0.15, 0.15, 0.17, 1), 8).copy_to(p).set_z(2.3)
        # the windsock, west of the pad
        mast = cylinder("windsock_mast", 0.1, 0.08, 6.0, (0.85, 0.85, 0.85, 1), 8)
        mast.reparent_to(hp)
        mast.set_pos(-32.0, 18.0, 0)
        sock = cylinder("windsock", 0.35, 0.18, 2.4, (0.95, 0.45, 0.10, 1), 10)
        sock.reparent_to(hp)
        sock.set_pos(-32.0, 18.0, 5.6)
        sock.set_p(-80)
        self.sock = sock
        # marker posts: rows at 10 m spacing west and south of the pad, the hover-drift references
        post_w, post_r = (0.95, 0.95, 0.95, 1), (0.90, 0.20, 0.15, 1)
        for k in range(-6, 7):
            for e, n in ((-25.0, 10.0 * k), (10.0 * k, -25.0), (10.0 * k, 25.0)):
                if math.hypot(e - PAD2[0], n - PAD2[1]) < 16.0 or e > 15.0 and abs(n) < 8.0:
                    continue
                cylinder("post", 0.08, 0.08, 0.8, post_r if k % 2 else post_w, 6).copy_to(hp).set_pos(e, n, 0)
        # trees along the boundary road to the north-east
        crown = cylinder("crown", 2.4, 0.2, 7.0, (0.17, 0.32, 0.14, 1), 7)
        trunk = cylinder("trunk", 0.3, 0.25, 2.0, (0.35, 0.25, 0.15, 1), 5)
        for k in range(14):
            t = hp.attach_new_node("tree")
            t.set_pos(60.0 + 11.0 * k, 110.0 + 3.0 * math.sin(k), 0)
            trunk.copy_to(t)
            crown.copy_to(t).set_z(1.6)
        box("road", 7.0, 2000.0, 0.05, (0.36, 0.36, 0.37, 1)).copy_to(hp).set_pos(200.0, 0.0, -0.06)
        hp.flatten_medium()

    def _countryside(self):
        rng = np.random.default_rng(7)
        cs = self.root.attach_new_node("countryside_objects")
        n_mid = 0.0
        # woods: clusters of cone trees, kept off the heliport and its approach from the south
        trees = cs.attach_new_node("trees")
        crown = cylinder("crown", 3.2, 0.2, 9.0, (0.17, 0.32, 0.14, 1), 7)
        trunk = cylinder("trunk", 0.35, 0.3, 2.5, (0.35, 0.25, 0.15, 1), 5)
        for _ in range(26):
            ce, cn = rng.uniform(-4500, 4500), rng.uniform(-4000, 5500)
            if abs(ce) < 600 and -3500 < cn < 600:
                continue
            if math.hypot(ce, cn) < 1200:
                continue
            for _ in range(int(rng.integers(25, 70))):
                e, n = ce + rng.normal(0, 120), cn + rng.normal(0, 120)
                s = rng.uniform(0.7, 1.4)
                t = trees.attach_new_node("tree")
                t.set_pos(e, n, 0)
                t.set_scale(s)
                trunk.copy_to(t)
                crown.copy_to(t).set_z(2.0)
        trees.flatten_strong()
        # the village 2.5 km north-west of the field, a church spire
        town = cs.attach_new_node("village")
        te, tn = -2300.0, n_mid + 2400.0
        for i in range(-6, 7):
            for j in range(-6, 7):
                if rng.uniform() < 0.35 or math.hypot(i, j) > 6.5:
                    continue
                e, n = te + i * 45 + rng.uniform(-8, 8), tn + j * 45 + rng.uniform(-8, 8)
                c = rng.uniform(0.75, 0.92)
                sx, sy, sz = rng.uniform(9, 16), rng.uniform(8, 12), rng.uniform(5, 8)
                b = box("house", sx, sy, sz, (c, c * 0.95, c * 0.86, 1)).copy_to(town)
                b.set_pos(e, n, 0)
                r = roof("roof", sx, sy + 1.0, 3.5, (0.62, 0.28, 0.20, 1)).copy_to(town)
                r.set_pos(e, n, sz)
        box("church", 12, 24, 12, (0.85, 0.83, 0.78, 1)).copy_to(town).set_pos(te, tn, 0)
        cylinder("spire", 3.0, 0.2, 38, (0.30, 0.32, 0.36, 1), 8).copy_to(town).set_pos(te, tn - 14, 12)
        box("tower_base", 6, 6, 14, (0.85, 0.83, 0.78, 1)).copy_to(town).set_pos(te, tn - 14, 0)
        town.flatten_strong()
        # roads: one east of the heliport to the village
        roads = cs.attach_new_node("roads")
        for (e0, n0), (e1, n1) in (((400.0, -4000.0), (400.0, 2600.0)), ((400.0, 2600.0), (te, tn)),
                                   ((te, tn), (-6000.0, tn + 800.0)), ((400.0, n_mid), (200.0, n_mid))):
            ln = math.hypot(e1 - e0, n1 - n0)
            r = box("road", 7.0, ln, 0.05, (0.36, 0.36, 0.37, 1)).copy_to(roads)
            r.set_pos((e0 + e1) / 2, (n0 + n1) / 2, -0.06)
            r.set_h(-math.degrees(math.atan2(e1 - e0, n1 - n0)))
        roads.flatten_strong()
        # the lake 3 km south-east
        le, ln_, lr = 2600.0, -2200.0, 600.0
        a = np.linspace(0, 2 * math.pi, 64, endpoint=False)
        rr = lr * (1 + 0.15 * np.sin(3 * a) + 0.08 * np.cos(5 * a))
        v = np.vstack([[le, ln_, 0.05], np.stack([le + rr * np.cos(a), ln_ + rr * np.sin(a), np.full(64, 0.05)], -1)])
        tris = np.array([[0, 1 + k, 1 + (k + 1) % 64] for k in range(64)])
        mesh("lake", v, np.tile([0, 0, 1.0], (65, 1)), np.tile([0.20, 0.34, 0.50, 1], (65, 1)), tris).reparent_to(cs)
        # a radio mast as a landmark on the downwind side, a wind farm to the east
        mast = cs.attach_new_node("mast")
        mast.set_pos(-1600.0, n_mid - 1500.0, 0)
        for k in range(6):
            col = (0.85, 0.15, 0.1, 1) if k % 2 == 0 else (0.95, 0.95, 0.95, 1)
            cylinder("seg", 1.6 - 0.15 * k, 1.45 - 0.15 * k, 20.0, col, 8).copy_to(mast).set_z(k * 20.0)
        self.turbines = []
        for k in range(5):
            base = cs.attach_new_node("turbine")
            base.set_pos(4200.0 + 350.0 * k, n_mid + 1500.0 - 300.0 * k, 0)
            cylinder("pole", 1.8, 1.2, 70, (0.93, 0.93, 0.93, 1), 10).copy_to(base)
            hub = base.attach_new_node("hub")
            hub.set_pos(0, -2.0, 70)
            for b in range(3):
                box("blade", 1.6, 0.4, 32, (0.95, 0.95, 0.95, 1)).copy_to(hub).set_r(b * 120)
            self.turbines.append(hub)

    def _clouds(self):
        tex = cloud_texture()
        rng = np.random.default_rng(9)
        clouds = self.root.attach_new_node("clouds")
        card = mesh("cloud", np.array([[-1, 0, -0.5], [1, 0, -0.5], [1, 0, 0.5], [-1, 0, 0.5]], float),
                    np.tile([0, -1, 0.0], (4, 1)), np.ones((4, 4)), np.array([[0, 1, 2], [0, 2, 3]]),
                    np.array([[0, 0], [1, 0], [1, 1], [0, 1]], float))
        for _ in range(110):
            c = card.copy_to(clouds)
            s = rng.uniform(300, 900)
            c.set_scale(s, 1, s * 0.45)
            c.set_pos(rng.uniform(-20000, 20000), rng.uniform(-20000, 20000), rng.uniform(1300, 2200))
            c.set_effect(BillboardEffect.make_point_eye())
        clouds.set_texture(tex)
        clouds.set_transparency(TransparencyAttrib.M_alpha)
        clouds.set_depth_write(False)
        clouds.set_bin("transparent", 10)
        clouds.set_light_off()
        clouds.set_two_sided(True)

    # ---- per frame
    def update(self, t: float, wind_ne: tuple[float, float]) -> None:
        for k, hub in enumerate(self.turbines):
            hub.set_r(t * 35.0 + 23 * k)
        wn, we = wind_ne
        spd = math.hypot(wn, we)
        # the windsock points where the air goes, hangs down in calm air
        self.sock.set_h(-math.degrees(math.atan2(we, wn)) if spd > 0.1 else 0.0)
        self.sock.set_p(-90.0 + min(80.0, spd * 12.0))
