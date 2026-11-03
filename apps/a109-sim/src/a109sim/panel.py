"""The instrument panel, drawn in Panda3D's 2D layer (aspect2d): airspeed, attitude, altimeter and
torque in the top row; rotor speed (NR), heading, vertical speed and the hover display (the ground
velocity over the nose) in the bottom row; the collective, cyclic and pedal positions, the SCAS
annunciator and the screen text on the right.

The faces (bezels, ticks, numbers) are built once; the needles, the attitude ball and the texts
change per frame. All instruments read the FMU's outputs: the airspeed indicator is the
airspeed over the air mass, the altimeter the height above the ground (the field at sea level),
NR the rotor speed in % of 385 rpm and the torque the engine power over the 740 hp take-off rating
at 100 % NR.
"""

from __future__ import annotations

import math

import numpy as np
from direct.gui.OnscreenText import OnscreenText
from panda3d.core import LineSegs, NodePath, TextNode, TransparencyAttrib

from .world import mesh

WHITE = (0.95, 0.95, 0.95, 1.0)
GREY = (0.55, 0.55, 0.57, 1.0)
DARK = (0.08, 0.08, 0.09, 1.0)
PANEL = (0.20, 0.21, 0.23, 1.0)
SKY = (0.25, 0.55, 0.90, 1.0)
EARTH = (0.55, 0.36, 0.18, 1.0)
GREEN = (0.20, 0.80, 0.30, 1.0)
YELLOW = (0.95, 0.80, 0.15, 1.0)
RED = (0.95, 0.25, 0.20, 1.0)
AMBER = (1.0, 0.75, 0.2, 1.0)
CYAN = (0.45, 0.85, 1.0, 1.0)
# airspeed markings (kt): green 20-150, yellow 150-168, red line 168 (VNE)
ASI_ARCS = ((20.0, 150.0, GREEN, 0.86), (150.0, 168.0, YELLOW, 0.86))
VNE = 168.0
HOVER_COLL = 0.60                  # the collective (lever fraction) of the hover out of ground effect
P_RATED = 740.0                    # hp, the take-off power
FT = 0.3048
KT = 0.514444


def torque_pct(y: dict) -> float:
    """The engine torque in % of the take-off rating: the power over 740 hp at the rotor speed."""
    return 100.0 * y["power_hp"] / P_RATED / max(y["rotor_pct"] / 100.0, 0.05)


def disk(name, r, color, seg=48) -> NodePath:
    a = np.linspace(0, 2 * math.pi, seg, endpoint=False)
    v = np.vstack([[0, 0, 0], np.stack([r * np.cos(a), np.zeros(seg), r * np.sin(a)], -1)])
    t = np.array([[0, 1 + (k + 1) % seg, 1 + k] for k in range(seg)])
    return mesh(name, v, np.tile([0, -1, 0.0], (seg + 1, 1)), np.tile(color, (seg + 1, 1)), t)


def rect(name, x0, z0, x1, z1, color) -> NodePath:
    v = np.array([[x0, 0, z0], [x1, 0, z0], [x1, 0, z1], [x0, 0, z1]], float)
    return mesh(name, v, np.tile([0, -1, 0.0], (4, 1)), np.tile(color, (4, 1)), np.array([[0, 2, 1], [0, 3, 2]]))


def polygon(name, pts, color) -> NodePath:
    """A convex polygon (x, z) as a triangle fan."""
    n = len(pts)
    v = np.array([[x, 0, z] for x, z in pts], float)
    t = np.array([[0, k + 1, k] for k in range(1, n - 1)])
    return mesh(name, v, np.tile([0, -1, 0.0], (n, 1)), np.tile(color, (n, 1)), t)


class Gauge:
    """A round instrument: centre, radius, a static face node."""

    def __init__(self, parent: NodePath, cx: float, cz: float, r: float, title: str):
        self.cx, self.cz, self.r = cx, cz, r
        self.node = parent.attach_new_node(title)
        disk("bezel", r * 1.08, (0.03, 0.03, 0.03, 1)).reparent_to(self.node)
        disk("face", r, DARK).reparent_to(self.node)
        self.node.set_pos(cx, 0, cz)
        self.face = LineSegs(title)
        self.face.set_thickness(1.5)

    def pt(self, ang_deg: float, rr: float) -> tuple[float, float]:
        """A point on the face: angle clockwise from 12 o'clock, radius fraction rr."""
        a = math.radians(ang_deg)
        return rr * self.r * math.sin(a), rr * self.r * math.cos(a)

    def tick(self, ang, r0, r1, color=WHITE):
        self.face.set_color(*color)
        x0, z0 = self.pt(ang, r0)
        x1, z1 = self.pt(ang, r1)
        self.face.move_to(x0, 0, z0)
        self.face.draw_to(x1, 0, z1)

    def arc(self, a0, a1, rr, color, n=24):
        self.face.set_color(*color)
        for k in range(n + 1):
            x, z = self.pt(a0 + (a1 - a0) * k / n, rr)
            (self.face.move_to if k == 0 else self.face.draw_to)(x, 0, z)

    def label(self, text, ang, rr, scale=None, fg=WHITE):
        x, z = self.pt(ang, rr)
        OnscreenText(text=text, pos=(x, z - 0.012), scale=scale or self.r * 0.16, fg=fg, parent=self.node,
                     align=TextNode.A_center)

    def caption(self, text, dz=-0.42, scale=None):
        OnscreenText(text=text, pos=(0, dz * self.r), scale=scale or self.r * 0.12, fg=GREY, parent=self.node,
                     align=TextNode.A_center)

    def finish(self):
        self.node.attach_new_node(self.face.create())


class Panel:
    def __init__(self, aspect2d: NodePath, aspect: float, line_scale: float = 1.0):
        self.root = aspect2d.attach_new_node("panel")
        self.line_scale = line_scale
        self.aspect = aspect
        self.dyn: NodePath | None = None
        self.show_panel = True
        self.show_help = False
        self._build(aspect)
        self.texts = {}

        def txt(name, pos, scale=0.045, align=TextNode.A_left, fg=WHITE, parent=None):
            t = OnscreenText(text="", pos=pos, scale=scale, align=align, fg=fg, parent=parent or aspect2d,
                             mayChange=True, shadow=(0, 0, 0, 0.7))
            self.texts[name] = t
            return t

        txt("info", (-aspect + 0.04, 0.93), 0.04)
        txt("help", (-aspect + 0.04, 0.84), 0.038)
        txt("big", (0.0, 0.30), 0.10, TextNode.A_center, RED)
        txt("warn", (0.0, 0.12), 0.07, TextNode.A_center, AMBER)
        txt("touch", (aspect - 0.04, 0.93), 0.042, TextNode.A_right, CYAN)
        txt("caption", (0.0, 0.72), 0.055, TextNode.A_center)
        txt("scas", (0.58, -0.50), 0.042, TextNode.A_left, GREEN, self.root)
        txt("data", (0.58, -0.57), 0.034, TextNode.A_left, WHITE, self.root)
        for t in ("asi", "alt", "vsi", "hdg", "nr", "tq", "hov", "coll"):
            txt(t, (0, 0), 0.03, TextNode.A_center, WHITE, self.root)

    # ---- static faces
    def _build(self, aspect: float):
        r = 0.105
        top, bot = -0.43, -1.0
        rect("panel_bg", -1.0, bot, 1.40, top, PANEL).reparent_to(self.root)
        self.root.set_transparency(TransparencyAttrib.M_alpha)
        xs = (-0.80, -0.55, -0.30, -0.05)
        z1, z2 = -0.575, -0.84
        self.asi = Gauge(self.root, xs[0], z1, r, "asi")
        self.ai = Gauge(self.root, xs[1], z1, r, "ai")
        self.alt = Gauge(self.root, xs[2], z1, r, "alt")
        self.tq = Gauge(self.root, xs[3], z1, r * 0.9, "tq")
        self.nr = Gauge(self.root, xs[0], z2, r * 0.95, "nr")
        self.hi = Gauge(self.root, xs[1], z2, r, "hi")
        self.vsi = Gauge(self.root, xs[2], z2, r, "vsi")
        self.hov = Gauge(self.root, xs[3], z2, r * 0.9, "hov")
        g = self.asi
        for a0, a1, col, rr in ASI_ARCS:
            g.arc(self._asi_ang(a0), self._asi_ang(a1), rr, col)
        g.tick(self._asi_ang(VNE), 0.78, 0.98, RED)
        for v in range(0, 181, 10):
            g.tick(self._asi_ang(v), 0.80 if v % 20 else 0.74, 0.98)
            if v % 40 == 0:
                g.label(str(v), self._asi_ang(v), 0.56, g.r * 0.15)
        g.caption("KNOTS", -0.25)
        g.finish()
        g = self.alt
        for k in range(50):
            g.tick(k * 7.2, 0.88 if k % 5 else 0.78, 0.98)
        for k in range(10):
            g.label(str(k), k * 36.0, 0.64)
        g.caption("ALT", 0.3)
        g.finish()
        g = self.vsi
        for v in range(-2000, 2001, 100):
            g.tick(self._vsi_ang(v), 0.86 if v % 500 else 0.76, 0.98)
        for v in (-2000, -1000, -500, 0, 500, 1000, 2000):
            g.label(f"{abs(v) // 100}", self._vsi_ang(v), 0.6)
        g.caption("VERT SPEED", -0.1)
        g.finish()
        g = self.nr                       # rotor speed: the green arc of the power-on limits
        g.arc(self._nr_ang(95.0), self._nr_ang(100.0), 0.9, GREEN)
        g.arc(self._nr_ang(90.0), self._nr_ang(95.0), 0.9, YELLOW)
        g.arc(self._nr_ang(100.0), self._nr_ang(110.0), 0.9, YELLOW)
        for v in (90.0, 110.0):
            g.tick(self._nr_ang(v), 0.7, 0.98, RED)
        for v in range(70, 121, 5):
            g.tick(self._nr_ang(v), 0.86 if v % 10 else 0.76, 0.98)
            if v % 10 == 0:
                g.label(str(v), self._nr_ang(v), 0.58, g.r * 0.16)
        g.caption("NR %", 0.3)
        g.finish()
        g = self.tq                       # torque: 100 % = the 740 hp take-off power at 100 % NR
        g.arc(self._tq_ang(0.0), self._tq_ang(100.0), 0.9, GREEN)
        g.tick(self._tq_ang(100.0), 0.7, 0.98, RED)
        for v in range(0, 121, 10):
            g.tick(self._tq_ang(v), 0.86 if v % 20 else 0.76, 0.98)
            if v % 20 == 0:
                g.label(str(v), self._tq_ang(v), 0.58, g.r * 0.16)
        g.caption("TQ %", 0.3)
        g.finish()
        g = self.hov                      # the hover display: the ground velocity over the nose
        g.face.set_color(*GREY)
        for rr in (0.5, 1.0):
            g.arc(0.0, 360.0, 0.92 * rr, GREY, 48)
        for a in (0.0, 90.0):
            x0, z0 = g.pt(a, 0.92)
            g.face.set_color(*GREY)
            g.face.move_to(-x0, 0, -z0)
            g.face.draw_to(x0, 0, z0)
        g.label("10", 0.0, 1.13, g.r * 0.14, GREY)
        g.caption("HOVER kt", -1.22, g.r * 0.12)
        g.finish()
        self.ai.caption("", 0.0)
        self.hi.finish()
        self.ai.finish()
        # the collective lever (with the hover mark), the cyclic and pedal positions
        ls = LineSegs("scales")
        ls.set_thickness(1.5)
        self.coll_x, self.coll_z0, self.coll_z1 = 0.17, -0.95, -0.50
        ls.set_color(*GREY)
        ls.move_to(self.coll_x, 0, self.coll_z0)
        ls.draw_to(self.coll_x, 0, self.coll_z1)
        for k in range(11):
            z = self.coll_z0 + (self.coll_z1 - self.coll_z0) * k / 10.0
            ls.set_color(*WHITE)
            ls.move_to(self.coll_x + 0.012, 0, z)
            ls.draw_to(self.coll_x + (0.035 if k % 5 == 0 else 0.022), 0, z)
        z = self.coll_z0 + (self.coll_z1 - self.coll_z0) * HOVER_COLL
        ls.set_color(*CYAN)
        ls.move_to(self.coll_x - 0.035, 0, z)
        ls.draw_to(self.coll_x - 0.012, 0, z)
        OnscreenText(text="HOV", pos=(self.coll_x - 0.075, z - 0.01), scale=0.022, fg=CYAN, parent=self.root)
        OnscreenText(text="COLL", pos=(self.coll_x, -0.995), scale=0.026, fg=GREY, parent=self.root)
        self.cyc = (0.38, -0.66, 0.085)      # centre x, z, half size of the cyclic box
        cx, cz, hs = self.cyc
        ls.set_color(*GREY)
        for (x0, z0), (x1, z1) in (((cx - hs, cz - hs), (cx + hs, cz - hs)), ((cx + hs, cz - hs), (cx + hs, cz + hs)),
                                   ((cx + hs, cz + hs), (cx - hs, cz + hs)), ((cx - hs, cz + hs), (cx - hs, cz - hs)),
                                   ((cx - hs, cz), (cx + hs, cz)), ((cx, cz - hs), (cx, cz + hs))):
            ls.move_to(x0, 0, z0)
            ls.draw_to(x1, 0, z1)
        OnscreenText(text="CYCLIC", pos=(cx, cz - hs - 0.04), scale=0.026, fg=GREY, parent=self.root)
        self.ped = (0.38, -0.88, 0.085)
        px, pz, ph = self.ped
        ls.move_to(px - ph, 0, pz)
        ls.draw_to(px + ph, 0, pz)
        for x in (px - ph, px, px + ph):
            ls.move_to(x, 0, pz - 0.015)
            ls.draw_to(x, 0, pz + 0.015)
        OnscreenText(text="PEDALS", pos=(px, -0.945), scale=0.026, fg=GREY, parent=self.root)
        self.root.attach_new_node(ls.create())

    @staticmethod
    def _asi_ang(v):
        return 15.0 + min(max(v, 0.0), 180.0) * 1.85

    @staticmethod
    def _vsi_ang(v):
        v = min(2000.0, max(-2000.0, v))
        return -90.0 + v / 2000.0 * 170.0

    @staticmethod
    def _nr_ang(nr):
        return -135.0 + (min(120.0, max(70.0, nr)) - 70.0) / 50.0 * 270.0

    @staticmethod
    def _tq_ang(tq):
        return -135.0 + min(120.0, max(0.0, tq)) / 120.0 * 270.0

    # ---- per frame
    def update(self, y: dict, *, info: str, caption: str, t: float, crashed: str, paused: bool, help_text: str,
               touch: str, warn: list[str], scas: str, data: str, sticks: dict, ground: tuple[float, float]) -> None:
        """``y``: the FMU's outputs (drawn); ``sticks``: collective, cyclic_lon, cyclic_lat, pedals and the
        cyclic trim (trim_lon, trim_lat); ``ground``: the ground velocity forward and right (m/s)."""
        T = self.texts
        T["info"].setText(info)
        T["help"].setText(help_text if self.show_help else "F1: help")
        T["big"].setText(f"CRASHED: {crashed}\nR to reset" if crashed else ("PAUSED" if paused else ""))
        T["big"].setFg(RED if crashed else WHITE)
        blink = ((t + 0.1) * 2.0) % 1.0 < 0.65
        T["warn"].setText("\n".join(warn[:2]) if (warn and blink) else "")
        T["warn"].setFg(RED if warn and warn[0].startswith(("LOW ROTOR", "PULL UP", "VRS")) else AMBER)
        T["touch"].setText(touch)
        T["caption"].setText(caption)
        if self.dyn is not None:
            self.dyn.remove_node()
            self.dyn = None
        if not self.show_panel:
            self.root.hide()
            return
        self.root.show()
        self.dyn = self.root.attach_new_node("dynamic")
        ls = LineSegs("needles")
        ls.set_thickness(2.5 * self.line_scale)
        kts = y["kts"]
        self._needle(ls, self.asi, self._asi_ang(kts), 0.92)
        h_ft = y["alt_m"] / FT
        self._needle(ls, self.alt, (h_ft % 1000.0) * 0.36, 0.92)
        self._needle(ls, self.alt, (h_ft % 10000.0) * 0.036, 0.58, 4.0)
        vs_fpm = y["vs_mps"] / FT * 60.0
        self._needle(ls, self.vsi, self._vsi_ang(vs_fpm), 0.92)
        nr = y["rotor_pct"]
        self._needle(ls, self.nr, self._nr_ang(nr), 0.92)
        tq = torque_pct(y)
        self._needle(ls, self.tq, self._tq_ang(tq), 0.92)
        self._attitude(y["phi_deg"], y["theta_deg"])
        self._heading(ls, y["psi_deg"], None)
        # the hover display: the ground velocity (forward up, right right), 10 kt at the rim
        g = self.hov
        fwd, right = ground[0] / KT, ground[1] / KT
        sp = math.hypot(fwd, right)
        k = min(1.0, 10.0 / max(sp, 1e-9)) if sp > 10.0 else 1.0
        hx, hz = g.cx + right * k / 10.0 * 0.92 * g.r, g.cz + fwd * k / 10.0 * 0.92 * g.r
        ls.set_color(*(GREEN if sp < 1.0 else CYAN if sp < 10.0 else AMBER))
        ls.move_to(g.cx, 0, g.cz)
        ls.draw_to(hx, 0, hz)
        disk("hover_dot", 0.010, GREEN if sp < 1.0 else CYAN, 12).copy_to(self.dyn).set_pos(hx, 0, hz)
        # the collective knob, the cyclic and its trim, the pedals
        z = self.coll_z0 + (self.coll_z1 - self.coll_z0) * sticks["collective"]
        rect("coll_knob", self.coll_x - 0.022, z - 0.014, self.coll_x + 0.022, z + 0.014, AMBER).reparent_to(self.dyn)
        cx, cz, hs = self.cyc
        tx, tz = cx + sticks["trim_lat"] * hs, cz + sticks["trim_lon"] * hs
        ls.set_color(*GREY)
        for kk in range(9):
            a = 2 * math.pi * kk / 8
            (ls.move_to if kk == 0 else ls.draw_to)(tx + 0.012 * math.cos(a), 0, tz + 0.012 * math.sin(a))
        sx, sz = cx + sticks["cyclic_lat"] * hs, cz + sticks["cyclic_lon"] * hs
        disk("cyc_dot", 0.012, AMBER, 12).copy_to(self.dyn).set_pos(sx, 0, sz)
        px, pz, ph = self.ped
        rect("ped_knob", px + sticks["pedals"] * ph - 0.008, pz - 0.022, px + sticks["pedals"] * ph + 0.008, pz + 0.022,
             AMBER).reparent_to(self.dyn)
        node = self.dyn.attach_new_node(ls.create())
        T["asi"].setText(f"{kts:3.0f}")
        T["asi"].setPos(self.asi.cx, self.asi.cz + 0.02)
        T["alt"].setText(f"{h_ft:5.0f}")
        T["alt"].setPos(self.alt.cx, self.alt.cz - 0.035)
        T["vsi"].setText(f"{vs_fpm:+5.0f}")
        T["vsi"].setPos(self.vsi.cx + 0.03, self.vsi.cz - 0.035)
        T["hdg"].setText(f"{y['psi_deg'] % 360.0:03.0f}")
        T["hdg"].setPos(self.hi.cx, self.hi.cz - 0.125)
        T["nr"].setText(f"{nr:5.1f}")
        T["nr"].setPos(self.nr.cx, self.nr.cz - 0.03)
        T["tq"].setText(f"{tq:3.0f}")
        T["tq"].setPos(self.tq.cx, self.tq.cz - 0.028)
        T["hov"].setText(f"{sp:4.1f}")
        T["hov"].setPos(self.hov.cx + 0.05, self.hov.cz - 0.075)
        T["coll"].setText(f"{sticks['collective'] * 100:3.0f}")
        T["coll"].setPos(self.coll_x, -0.47)
        T["scas"].setText(scas)
        T["scas"].setFg(GREEN if scas.startswith("SCAS ON") else AMBER)
        T["data"].setText(data)

    def _needle(self, ls, g: Gauge, ang, length, width=2.0):
        ls.set_color(*WHITE)
        x, z = g.pt(ang, length)
        bx, bz = g.pt(ang + 180.0, 0.12)
        ls.move_to(g.cx + bx, 0, g.cz + bz)
        ls.draw_to(g.cx + x, 0, g.cz + z)

    def _attitude(self, phi, theta):
        """The attitude ball: sky and earth split by the horizon line, turned by the bank and
        moved by the pitch (4 deg of pitch per tenth of the radius), clipped to the face."""
        g = self.ai
        r = g.r * 0.96
        # a right bank turns the world (the horizon) counter-clockwise in the instrument
        c, s = math.cos(math.radians(phi)), math.sin(math.radians(phi))
        d = -theta / 40.0 * r * 1.0      # the horizon's offset from the centre along its normal
        nx, nz = -s, c                   # the normal of the horizon line (up in the instrument)
        a = np.linspace(0, 2 * math.pi, 64, endpoint=False)
        pts = np.stack([r * np.cos(a), r * np.sin(a)], -1)
        above = pts @ np.array([nx, nz]) > d
        for name, mask, col in (("sky", above, SKY), ("earth", ~above, EARTH)):
            poly = self._clip(pts, mask, nx, nz, d)
            if len(poly) >= 3:
                p = polygon(name, [(g.cx + x, g.cz + z) for x, z in poly], col)
                p.reparent_to(self.dyn)
        ls = LineSegs("ai")
        ls.set_thickness(2.0 * self.line_scale)
        ls.set_color(*WHITE)
        tx, tz = c, s                     # along the horizon
        for p in range(-20, 21, 10):      # pitch lines
            off = d + p / 40.0 * r
            half = r * (0.5 if p == 0 else 0.22)
            if abs(off) > r * 0.8:
                continue
            cx0, cz0 = g.cx + nx * off, g.cz + nz * off
            ls.move_to(cx0 - tx * half, 0, cz0 - tz * half)
            ls.draw_to(cx0 + tx * half, 0, cz0 + tz * half)
        ls.set_color(*YELLOW)              # the aircraft symbol
        for (x0, z0), (x1, z1) in (((-0.55, 0), (-0.18, 0)), ((-0.18, 0), (-0.09, -0.08)), ((-0.09, -0.08), (0, 0)),
                                   ((0, 0), (0.09, -0.08)), ((0.09, -0.08), (0.18, 0)), ((0.18, 0), (0.55, 0))):
            ls.move_to(g.cx + x0 * r, 0, g.cz + z0 * r)
            ls.draw_to(g.cx + x1 * r, 0, g.cz + z1 * r)
        ls.set_color(*WHITE)               # the bank scale (fixed) and its pointer (turns with the bank)
        for b in (-60, -45, -30, -20, -10, 0, 10, 20, 30, 45, 60):
            x0, z0 = g.pt(b, 0.98)
            x1, z1 = g.pt(b, 0.88 if b % 30 else 0.80)
            ls.move_to(g.cx + x0, 0, g.cz + z0)
            ls.draw_to(g.cx + x1, 0, g.cz + z1)
        px, pz = g.pt(-phi, 0.78)
        lx, lz = g.pt(-phi - 6, 0.68)
        rx, rz = g.pt(-phi + 6, 0.68)
        ls.set_color(*AMBER)
        ls.move_to(g.cx + lx, 0, g.cz + lz)
        ls.draw_to(g.cx + px, 0, g.cz + pz)
        ls.draw_to(g.cx + rx, 0, g.cz + rz)
        self.dyn.attach_new_node(ls.create())

    @staticmethod
    def _clip(pts, mask, nx, nz, d):
        """The part of the circle polygon on one side of the line n . p = d."""
        out = []
        n = len(pts)
        for k in range(n):
            p, q = pts[k], pts[(k + 1) % n]
            if mask[k]:
                out.append(tuple(p))
            if mask[k] != mask[(k + 1) % n]:
                fp, fq = p @ (nx, nz) - d, q @ (nx, nz) - d
                u = fp / (fp - fq)
                out.append(tuple(p + (q - p) * u))
        return out

    def _heading(self, ls, psi, bug):
        g = self.hi
        ls.set_color(*WHITE)
        for k in range(72):               # the card turns: the heading at the top
            a = k * 5.0 - psi
            ls_r0 = 0.86 if k % 2 else 0.76
            x0, z0 = g.pt(a, 0.98)
            x1, z1 = g.pt(a, ls_r0)
            ls.move_to(g.cx + x0, 0, g.cz + z0)
            ls.draw_to(g.cx + x1, 0, g.cz + z1)
        for k, lab in enumerate(("N", "3", "6", "E", "12", "15", "S", "21", "24", "W", "30", "33")):
            x, z = g.pt(k * 30.0 - psi, 0.56)
            OnscreenText(text=lab, pos=(g.cx + x, g.cz + z), roll=k * 30.0 - psi, scale=g.r * (0.2 if lab in "NESW" else 0.15),
                             fg=WHITE if lab not in "NESW" else AMBER, parent=self.dyn, align=TextNode.A_center)   # roll: about its own position
        if bug is not None:
            ls.set_color(*CYAN)
            x0, z0 = g.pt(bug - psi - 5, 0.99)
            x1, z1 = g.pt(bug - psi, 0.86)
            x2, z2 = g.pt(bug - psi + 5, 0.99)
            ls.move_to(g.cx + x0, 0, g.cz + z0)
            ls.draw_to(g.cx + x1, 0, g.cz + z1)
            ls.draw_to(g.cx + x2, 0, g.cz + z2)
        ls.set_color(*AMBER)             # the lubber line and the aircraft
        ls.move_to(g.cx, 0, g.cz + g.r * 0.99)
        ls.draw_to(g.cx, 0, g.cz + g.r * 0.80)
        ls.move_to(g.cx - 0.3 * g.r, 0, g.cz)
        ls.draw_to(g.cx + 0.3 * g.r, 0, g.cz)
        ls.move_to(g.cx, 0, g.cz + 0.3 * g.r)
        ls.draw_to(g.cx, 0, g.cz - 0.35 * g.r)

