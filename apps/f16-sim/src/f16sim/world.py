"""The world: sky, terrain, the airfield, landmarks, clouds and the ring gates. All procedural.

Panda3D coordinates: x east, y north, z up (metres); the simulation's NED maps to (east, north, -down).
"""

from __future__ import annotations

import math

import numpy as np
from panda3d.core import (
    AmbientLight, BillboardEffect, CompassEffect, DirectionalLight, Fog, Geom, GeomNode,
    GeomTriangles, GeomVertexArrayFormat, GeomVertexData, GeomVertexFormat, NodePath, SamplerState,
    Texture, TransparencyAttrib, Vec4,
)

from . import terrain

_FMT = None


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


def cylinder(name, r0, r1, h, color, seg=16) -> NodePath:
    a = np.linspace(0, 2 * math.pi, seg + 1)
    v, n, c, t = [], [], [], []
    for k in range(seg):
        for (aa, z, r) in ((a[k], 0, r0), (a[k + 1], 0, r0), (a[k + 1], h, r1), (a[k], h, r1)):
            v.append((r * math.cos(aa), r * math.sin(aa), z))
            n.append((math.cos(aa), math.sin(aa), 0.0))
            c.append(color)
        b = 4 * k
        t += [(b, b + 1, b + 2), (b, b + 2, b + 3)]
    return mesh(name, np.array(v, float), np.array(n, float), np.array(c, float), np.array(t))


def torus(name, R, r, color, seg=48, side=10) -> NodePath:
    u = np.linspace(0, 2 * math.pi, seg)
    w = np.linspace(0, 2 * math.pi, side)
    U, W = np.meshgrid(u, w, indexing="ij")
    # ring in the x-z plane (its axis along y: the aircraft flies through it along +y)
    cx, cz = R * np.cos(U), R * np.sin(U)
    nx, ny, nz = np.cos(W) * np.cos(U), np.sin(W), np.cos(W) * np.sin(U)
    v = np.stack([cx + r * nx, r * ny, cz + r * nz], -1).reshape(-1, 3)
    nrm = np.stack([nx, ny, nz], -1).reshape(-1, 3)
    col = np.tile(color, (len(v), 1))
    return mesh(name, v, nrm, col, grid_tris(seg, side))


def _noise_texture(size: int, seed: int, base, var, scale: float = 1.0) -> Texture:
    """A tileable patchwork of fields with soft noise (an original procedural texture)."""
    rng = np.random.default_rng(seed)
    img = np.zeros((size, size, 3))
    img[:] = base
    # fields: rectangles of slightly different greens and browns
    for _ in range(90):
        x0, y0 = rng.integers(0, size, 2)
        w, h = rng.integers(size // 16, size // 4, 2)
        col = np.array(base) + rng.uniform(-1, 1, 3) * var
        xs = (np.arange(x0, x0 + w) % size)
        ys = (np.arange(y0, y0 + h) % size)
        img[np.ix_(ys, xs)] = col
    # low-frequency noise (sum of periodic sines keeps it tileable)
    yy, xx = np.mgrid[0:size, 0:size] / size * 2 * math.pi
    nse = np.zeros((size, size))
    for k in range(1, 6):
        fx, fy, ph = rng.integers(1, 6 * k), rng.integers(1, 6 * k), rng.uniform(0, 6.28)
        nse += np.sin(fx * xx + fy * yy + ph) / k
    img *= (1.0 + 0.06 * scale * nse)[..., None]
    img += rng.normal(0, 0.012, img.shape)
    img = np.clip(img, 0, 1)
    tex = Texture("ground")
    tex.setup_2d_texture(size, size, Texture.T_unsigned_byte, Texture.F_rgb)
    # Panda wants BGR rows bottom-up
    tex.set_ram_image(np.ascontiguousarray((img[::-1, :, ::-1] * 255).astype(np.uint8)).tobytes())
    tex.set_minfilter(SamplerState.FT_linear_mipmap_linear)
    tex.set_magfilter(SamplerState.FT_linear)
    tex.set_anisotropic_degree(8)
    tex.set_wrap_u(SamplerState.WM_repeat)
    tex.set_wrap_v(SamplerState.WM_repeat)
    return tex


def _cloud_texture(size=128, seed=3) -> Texture:
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


HORIZON = (0.72, 0.80, 0.90)
ZENITH = (0.20, 0.38, 0.72)


class World:
    def __init__(self, render: NodePath, camera: NodePath):
        self.root = render.attach_new_node("world")
        self.camera = camera
        self._lights(render)
        self._sky(render)
        self._terrain()
        self._airfield()
        self._landmarks()
        self._clouds()
        self.rings_np = self.root.attach_new_node("rings")
        self.ring_nodes: list[NodePath] = []
        self.turbines: list[NodePath] = []
        self._turbines()
        fog = Fog("haze")
        fog.set_color(*HORIZON)
        fog.set_exp_density(1.0 / 30000.0)
        self.root.set_fog(fog)

    # ---- environment
    def _lights(self, render):
        sun = DirectionalLight("sun")
        sun.set_color(Vec4(1.0, 0.97, 0.9, 1))
        self.sun = render.attach_new_node(sun)
        self.sun.set_hpr(-40, -50, 0)
        amb = AmbientLight("amb")
        amb.set_color(Vec4(0.45, 0.48, 0.55, 1))
        self.amb = render.attach_new_node(amb)
        render.set_light(self.sun)
        render.set_light(self.amb)

    def _sky(self, render):
        seg, rings = 48, 24
        th = np.linspace(-0.15, math.pi / 2, rings)       # elevation, a little below the horizon
        ph = np.linspace(0, 2 * math.pi, seg)
        T, P = np.meshgrid(th, ph, indexing="ij")
        R = 50000.0
        v = np.stack([R * np.cos(T) * np.cos(P), R * np.cos(T) * np.sin(P), R * np.sin(T)], -1).reshape(-1, 3)
        s = np.clip(np.sin(T), 0, 1).reshape(-1, 1) ** 0.6
        col = np.hstack([(1 - s) * np.array(HORIZON) + s * np.array(ZENITH), np.ones((len(v), 1))])
        tris = grid_tris(rings, seg)[:, ::-1]               # seen from inside
        sky = mesh("sky", v, -v / R, col, tris)
        sky.reparent_to(render)
        sky.set_bin("background", 0)
        sky.set_depth_write(False)
        sky.set_depth_test(False)
        sky.set_light_off()
        sky.set_fog_off()
        sky.set_effect(CompassEffect.make(self.camera, CompassEffect.P_pos))
        self.sky = sky

    def _terrain(self):
        half, res = 42000.0, 300.0
        xs = np.arange(-half, half + 1, res)
        E, N = np.meshgrid(xs, xs, indexing="ij")
        H = terrain.height(N, E)
        nx, ny = len(xs), len(xs)
        v = np.stack([E, N, H], -1).reshape(-1, 3)
        gx, gy = np.gradient(H, res)
        nrm = np.stack([-gx, -gy, np.ones_like(H)], -1)
        nrm /= np.linalg.norm(nrm, axis=-1, keepdims=True)
        slope = 1 - nrm[..., 2]
        g = np.array([0.36, 0.52, 0.25])
        rock = np.array([0.50, 0.47, 0.42])
        snow = np.array([0.95, 0.95, 0.97])
        hn = np.clip(H / 700.0, 0, 1)[..., None]
        col = (1 - hn) * g + hn * (0.6 * g + 0.4 * rock)
        col = np.where((slope[..., None] > 0.08), 0.5 * col + 0.5 * rock, col)
        col = np.where((H[..., None] > 780.0), snow, col)
        col = np.concatenate([col, np.ones(H.shape + (1,))], -1).reshape(-1, 4)
        uv = np.stack([E / 1600.0, N / 1600.0], -1).reshape(-1, 2)
        ground = mesh("terrain", v, nrm.reshape(-1, 3), col, grid_tris(nx, ny), uv)
        tex = _noise_texture(512, 11, (0.80, 0.85, 0.70), 0.12)
        ground.set_texture(tex)
        ground.reparent_to(self.root)
        # the plain beyond the heightfield: a frame of four quads around it (no overlap, no z-fighting)
        big = 400000.0
        v, t = [], []
        for x0, y0, x1, y1 in ((-big, -big, big, -half), (-big, half, big, big), (-big, -half, -half, half),
                               (half, -half, big, half)):
            b = len(v)
            v += [(x0, y0, 0.0), (x1, y0, 0.0), (x1, y1, 0.0), (x0, y1, 0.0)]
            t += [(b, b + 1, b + 2), (b, b + 2, b + 3)]
        v = np.array(v)
        far = mesh("plain", v, np.tile([0, 0, 1.0], (len(v), 1)), np.tile([0.36, 0.52, 0.25, 1.0], (len(v), 1)),
                   np.array(t), v[:, :2] / 1600.0)
        far.set_texture(tex)
        far.reparent_to(self.root)

    def _airfield(self):
        n0, e0 = terrain.AIRFIELD
        af = self.root.attach_new_node("airfield")
        af.set_pos(e0, n0, 0.0)
        L, W = terrain.RUNWAY_LENGTH, terrain.RUNWAY_WIDTH
        # the pavement lies on the flat ground (terrain.height is 0 here); depth offsets keep it, and the
        # markings on it, drawn over the terrain far away, where the depth buffer cannot separate 0.3 m
        rw = box("runway", W, L, 0.3, (0.22, 0.22, 0.24, 1))
        rw.set_depth_offset(1)
        rw.reparent_to(af)
        mark = af.attach_new_node("markings")
        for y in np.arange(-L / 2 + 120, L / 2 - 120, 60.0):            # centre line
            box("cl", 0.9, 30.0, 0.05, (0.95, 0.95, 0.95, 1)).copy_to(mark).set_pos(0, y, 0.3)
        for end in (-1, 1):                                           # threshold bars
            for k in range(8):
                x = -W / 2 + 4 + k * (W - 8) / 7.0
                box("thr", 1.8, 40.0, 0.05, (0.95, 0.95, 0.95, 1)).copy_to(mark).set_pos(x, end * (L / 2 - 30), 0.3)
        mark.set_depth_offset(2)
        mark.flatten_strong()
        for name, sx, sy, colour, pos in (("taxiway", 23, L * 0.8, (0.28, 0.28, 0.30, 1), (-180, 0, 0)),
                                          ("apron", 260, 220, (0.30, 0.30, 0.32, 1), (-330, 200, 0))):
            pave = box(name, sx, sy, 0.25, colour).copy_to(af)
            pave.set_pos(*pos)
            pave.set_depth_offset(1)
        for k in range(4):
            box("hangar", 60, 45, 18, (0.62, 0.64, 0.66, 1), (0.45, 0.47, 0.50, 1)).copy_to(af).set_pos(-500, 80 + 60 * k, 0)
        tower = af.attach_new_node("tower")
        tower.set_pos(-300, -60, 0)
        box("shaft", 7, 7, 32, (0.85, 0.83, 0.78, 1)).copy_to(tower)
        box("cab", 12, 12, 5, (0.25, 0.45, 0.55, 1), (0.3, 0.3, 0.3, 1)).copy_to(tower).set_z(32)
        af.flatten_medium()

    def _mast(self, parent, e, n, h):
        mast = parent.attach_new_node("mast")
        mast.set_pos(e, n, terrain.height(n, e))
        seg = h / 8
        for k in range(8):
            col = (0.85, 0.15, 0.1, 1) if k % 2 == 0 else (0.95, 0.95, 0.95, 1)
            cylinder("seg", 2.2 - 0.15 * k, 2.05 - 0.15 * k, seg, col, 8).copy_to(mast).set_z(k * seg)
        return mast

    def _landmarks(self):
        lm = self.root.attach_new_node("landmarks")
        # radio masts along the approach and on two hilltops
        for e, n, h in ((-1800, 6200, 180), (-2600, -900, 140), (2500, 2500, 220), (-9000, 9000, 260), (6000, -8000, 200)):
            self._mast(lm, e, n, h)
        # the town: blocks of houses and a few towers
        rng = np.random.default_rng(5)
        tn, te = terrain.TOWN
        town = lm.attach_new_node("town")
        for i in range(-9, 10):
            for j in range(-9, 10):
                if rng.uniform() < 0.25:
                    continue
                hgt = rng.uniform(6, 16) if math.hypot(i, j) > 3 else rng.uniform(20, 90)
                c = rng.uniform(0.6, 0.9)
                box("house", rng.uniform(15, 35), rng.uniform(15, 35), hgt, (c, c * 0.95, c * 0.88, 1),
                    (0.55, 0.30, 0.25, 1) if hgt < 20 else (0.4, 0.42, 0.45, 1)).copy_to(town).set_pos(
                    te + i * 70 + rng.uniform(-10, 10), tn + j * 70 + rng.uniform(-10, 10), 0)
        town.flatten_strong()
        # the lake
        ln, le, lr = terrain.LAKE
        a = np.linspace(0, 2 * math.pi, 64, endpoint=False)
        rr = lr * (1 + 0.12 * np.sin(3 * a) + 0.07 * np.cos(5 * a))
        v = np.vstack([[le, ln, 0.4], np.stack([le + rr * np.cos(a), ln + rr * np.sin(a), np.full(64, 0.4)], -1)])
        tris = np.array([[0, 1 + k, 1 + (k + 1) % 64] for k in range(64)])
        mesh("lake", v, np.tile([0, 0, 1.0], (65, 1)), np.tile([0.18, 0.32, 0.48, 1], (65, 1)), tris).reparent_to(lm)
        # a tall tower by the lake: a landmark visible from far
        tw = lm.attach_new_node("lake_tower")
        tw.set_pos(le + lr + 300, ln, 0)
        cylinder("tw", 9, 5, 240, (0.9, 0.9, 0.88, 1), 16).copy_to(tw)
        cylinder("pod", 16, 16, 14, (0.3, 0.35, 0.45, 1), 16).copy_to(tw).set_z(200)
        self.landmarks = lm

    def _turbines(self):
        for k in range(7):
            e, n = 9000.0 + 400 * k, -3000.0 + 250 * k
            base = self.root.attach_new_node("turbine")
            base.set_pos(e, n, terrain.height(n, e))
            cylinder("pole", 2.2, 1.4, 80, (0.93, 0.93, 0.93, 1), 10).copy_to(base)
            hub = base.attach_new_node("hub")
            hub.set_pos(0, -2.5, 80)
            for b in range(3):
                blade = box("blade", 2.0, 0.5, 38, (0.95, 0.95, 0.95, 1)).copy_to(hub)
                blade.set_r(b * 120)
            self.turbines.append(hub)

    def _clouds(self):
        tex = _cloud_texture()
        rng = np.random.default_rng(9)
        clouds = self.root.attach_new_node("clouds")
        card = mesh("cloud", np.array([[-1, 0, -0.5], [1, 0, -0.5], [1, 0, 0.5], [-1, 0, 0.5]], float),
                    np.tile([0, -1, 0.0], (4, 1)), np.ones((4, 4)), np.array([[0, 1, 2], [0, 2, 3]]),
                    np.array([[0, 0], [1, 0], [1, 1], [0, 1]], float))
        for _ in range(140):
            c = card.copy_to(clouds)
            s = rng.uniform(500, 1400)
            c.set_scale(s, 1, s * 0.45)
            c.set_pos(rng.uniform(-30000, 30000), rng.uniform(-30000, 30000), rng.uniform(2300, 3600))
            c.set_effect(BillboardEffect.make_point_eye())
        clouds.set_texture(tex)
        clouds.set_transparency(TransparencyAttrib.M_alpha)
        clouds.set_depth_write(False)
        clouds.set_bin("transparent", 10)
        clouds.set_light_off()
        clouds.set_two_sided(True)

    # ---- per frame
    def set_rings(self, rings) -> None:
        for np_ in self.ring_nodes:
            np_.remove_node()
        self.ring_nodes = []
        for r in rings:
            t = torus("ring", r.radius, 2.5, (1.0, 0.55, 0.1, 1.0))
            t.reparent_to(self.rings_np)
            t.set_pos(r.east, r.north, r.alt)
            t.set_h(-r.heading_deg)
            t.set_light_off()
            self.ring_nodes.append(t)

    def update(self, t: float, rings) -> None:
        for k, hub in enumerate(self.turbines):
            hub.set_r(t * 40.0 + 17 * k)
        nxt = next((i for i, r in enumerate(rings) if not r.passed), None)
        for i, (r, np_) in enumerate(zip(rings, self.ring_nodes)):
            if r.passed:
                if r.hit:
                    np_.set_color_scale(0.3, 1.0, 0.4, 0.5)
                else:
                    np_.set_color_scale(1.0, 0.2, 0.2, 0.4)
                np_.set_transparency(TransparencyAttrib.M_alpha)
            elif i == nxt:
                pulse = 0.75 + 0.25 * math.sin(6.0 * t)
                np_.set_color_scale(1.0, 1.0, 0.3 * pulse, 1)
            else:
                np_.set_color_scale(1, 1, 1, 1)

