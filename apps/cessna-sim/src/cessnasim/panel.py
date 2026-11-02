"""The instrument panel, drawn in Panda3D's 2D layer (aspect2d): the six-pack (airspeed, attitude,
altimeter, turn coordinator, heading, vertical speed), the tachometer, the flap and trim
indicators, the throttle and mixture levers, the autopilot annunciator and the screen text.

The faces (bezels, ticks, numbers) are built once; the needles, the attitude ball and the texts
change per frame. All instruments read the FMU's outputs: the airspeed indicator is the
calibrated airspeed (no position error), the altimeter the ISA altitude, the turn coordinator the
heading rate and the ball the aerodynamic side force over the weight.
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
# POH airspeed markings (KIAS): white arc 33-85 (flaps), green 44-127, yellow 127-158, red line 158
ASI_ARCS = ((33.0, 85.0, WHITE, 0.92), (44.0, 127.0, GREEN, 0.86), (127.0, 158.0, YELLOW, 0.86))
VNE = 158.0


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
        self.ball_np: NodePath | None = None
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
        txt("ap", (0.62, -0.53), 0.04, TextNode.A_left, GREEN, self.root)
        txt("levers", (0.62, -0.62), 0.036, TextNode.A_left, WHITE, self.root)
        txt("engine", (0.62, -0.86), 0.034, TextNode.A_left, WHITE, self.root)
        for t in ("asi", "alt", "vsi", "hdg", "tach"):
            txt(t, (0, 0), 0.03, TextNode.A_center, WHITE, self.root)

    # ---- static faces
    def _build(self, aspect: float):
        r = 0.105
        top, bot = -0.43, -1.0
        rect("panel_bg", -1.0, bot, 1.30, top, PANEL).reparent_to(self.root)
        self.root.set_transparency(TransparencyAttrib.M_alpha)
        xs = (-0.80, -0.55, -0.30)
        z1, z2 = -0.575, -0.84
        self.asi = Gauge(self.root, xs[0], z1, r, "asi")
        self.ai = Gauge(self.root, xs[1], z1, r, "ai")
        self.alt = Gauge(self.root, xs[2], z1, r, "alt")
        self.tc = Gauge(self.root, xs[0], z2, r, "tc")
        self.hi = Gauge(self.root, xs[1], z2, r, "hi")
        self.vsi = Gauge(self.root, xs[2], z2, r, "vsi")
        self.tach = Gauge(self.root, -0.03, z1, r * 0.85, "tach")
        g = self.asi
        for a0, a1, col, rr in ASI_ARCS:
            g.arc(self._asi_ang(a0), self._asi_ang(a1), rr, col)
        g.tick(self._asi_ang(VNE), 0.78, 0.98, RED)
        for v in range(40, 161, 10):
            g.tick(self._asi_ang(v), 0.80 if v % 20 else 0.74, 0.98)
            if v % 20 == 0:
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
        g = self.tc
        for a in (-15.0, 15.0):   # standard-rate marks (3 deg/s)
            g.tick(-90.0 + a * 1.0 if a < 0 else 90.0 + a, 0.80, 0.98)
        g.tick(-90.0 - 15.0, 0.8, 0.98)
        g.tick(90.0 - 15.0, 0.8, 0.98)
        g.label("L", -104.0, 0.65, g.r * 0.15)
        g.label("R", 104.0, 0.65, g.r * 0.15)
        g.caption("TURN COORDINATOR", 0.35, g.r * 0.1)
        g.finish()
        rect("tube", -0.42 * r, -0.62 * r, 0.42 * r, -0.44 * r, (0.18, 0.18, 0.16, 1)).reparent_to(self.tc.node)
        g = self.tach
        for v in range(0, 3501, 100):
            g.tick(self._tach_ang(v), 0.86 if v % 500 else 0.76, 0.98)
        g.arc(self._tach_ang(2100), self._tach_ang(2700), 0.9, GREEN)
        g.tick(self._tach_ang(2700), 0.7, 0.98, RED)
        for v in range(0, 36, 5):
            g.label(str(v), self._tach_ang(v * 100), 0.6, g.r * 0.17)
        g.caption("RPM x100", -0.3)
        g.finish()
        self.ai.caption("", 0.0)
        self.hi.finish()
        self.ai.finish()
        # flap and trim scales
        ls = LineSegs("scales")
        ls.set_thickness(1.5)
        ls.set_color(*WHITE)
        self.flap_x, self.flap_z0, self.flap_z1 = 0.17, -0.50, -0.95
        for k, d in enumerate((0, 10, 20, 30)):
            z = self.flap_z0 + (self.flap_z1 - self.flap_z0) * d / 30.0
            ls.move_to(self.flap_x, 0, z)
            ls.draw_to(self.flap_x + 0.03, 0, z)
            OnscreenText(text=str(d), pos=(self.flap_x + 0.065, z - 0.01), scale=0.028, fg=WHITE, parent=self.root)
        OnscreenText(text="FLAPS", pos=(self.flap_x + 0.03, -0.995), scale=0.026, fg=GREY, parent=self.root)
        self.trim_x, self.trim_z0, self.trim_z1 = 0.36, -0.50, -0.95
        for k in range(9):
            z = self.trim_z0 + (self.trim_z1 - self.trim_z0) * k / 8.0
            ls.move_to(self.trim_x, 0, z)
            ls.draw_to(self.trim_x + (0.03 if k % 4 == 0 else 0.015), 0, z)
        OnscreenText(text="DN", pos=(self.trim_x + 0.06, self.trim_z0 - 0.01), scale=0.026, fg=WHITE, parent=self.root)
        OnscreenText(text="UP", pos=(self.trim_x + 0.06, self.trim_z1 - 0.01), scale=0.026, fg=WHITE, parent=self.root)
        OnscreenText(text="TRIM", pos=(self.trim_x + 0.03, -0.995), scale=0.026, fg=GREY, parent=self.root)
        # throttle and mixture slots
        self.lev_x = (0.47, 0.53)
        for x in self.lev_x:
            ls.set_color(*GREY)
            ls.move_to(x, 0, -0.50)
            ls.draw_to(x, 0, -0.95)
        OnscreenText(text="THR MIX", pos=(0.50, -0.995), scale=0.026, fg=GREY, parent=self.root)
        self.root.attach_new_node(ls.create())

    @staticmethod
    def _asi_ang(v):
        return 20.0 + (min(max(v, 20.0), 170.0) - 20.0) * 2.2

    @staticmethod
    def _vsi_ang(v):
        v = min(2000.0, max(-2000.0, v))
        return -90.0 + v / 2000.0 * 170.0

    @staticmethod
    def _tach_ang(rpm):
        return -135.0 + min(3500.0, max(0.0, rpm)) / 3500.0 * 270.0

    # ---- per frame
    def update(self, y: dict, *, info: str, caption: str, t: float, crashed: str, paused: bool, help_text: str,
               touch: str, warn: list[str], ap: str, levers: dict) -> None:
        T = self.texts
        T["info"].setText(info)
        T["help"].setText(help_text if self.show_help else "F1: help")
        T["big"].setText(f"CRASHED: {crashed}\nR to reset" if crashed else ("PAUSED" if paused else ""))
        T["big"].setFg(RED if crashed else WHITE)
        blink = ((t + 0.1) * 2.0) % 1.0 < 0.65
        T["warn"].setText("\n".join(warn[:2]) if (warn and blink) else "")
        T["warn"].setFg(RED if warn and warn[0].startswith(("STALL", "PULL")) else AMBER)
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
        self._needle(ls, self.asi, self._asi_ang(y["kias"]), 0.92)
        h_ft = y["alt_ft"]
        self._needle(ls, self.alt, (h_ft % 1000.0) * 0.36, 0.92)
        self._needle(ls, self.alt, (h_ft % 10000.0) * 0.036, 0.58, 4.0)
        self._needle(ls, self.vsi, self._vsi_ang(y["vs_fpm"]), 0.92)
        self._needle(ls, self.tach, self._tach_ang(y["rpm"]), 0.92)
        self._attitude(y["phi_deg"], y["theta_deg"])
        self._heading(ls, y["psi_deg"], levers.get("hdg_bug"))
        self._turn(ls, y["turn_dps"], y["slip"])
        # flaps (indicator pointer at the angle), trim, levers
        ls.set_color(*AMBER)
        z = self.flap_z0 + (self.flap_z1 - self.flap_z0) * y["flap_deg"] / 30.0
        ls.move_to(self.flap_x - 0.035, 0, z)
        ls.draw_to(self.flap_x, 0, z)
        zc = self.flap_z0 + (self.flap_z1 - self.flap_z0) * levers["flaps"] / 3.0
        ls.set_color(*WHITE)
        ls.move_to(self.flap_x - 0.03, 0, zc + 0.012)
        ls.draw_to(self.flap_x - 0.005, 0, zc)
        ls.draw_to(self.flap_x - 0.03, 0, zc - 0.012)
        ls.set_color(*AMBER)
        z = self.trim_z0 + (self.trim_z1 - self.trim_z0) * (levers["trim"] + 1.0) / 2.0
        ls.move_to(self.trim_x - 0.035, 0, z)
        ls.draw_to(self.trim_x, 0, z)
        for x, v, col in ((self.lev_x[0], levers["throttle"], (0.1, 0.1, 0.1, 1)), (self.lev_x[1], levers["mixture"], RED)):
            z = -0.95 + 0.45 * v
            rect("knob", x - 0.022, z - 0.018, x + 0.022, z + 0.018, col).reparent_to(self.dyn)
        node = self.dyn.attach_new_node(ls.create())
        node.set_bin("fixed", 10)
        T["asi"].setText(f"{y['kias']:3.0f}")
        T["asi"].setPos(self.asi.cx, self.asi.cz - 0.06)
        T["alt"].setText(f"{h_ft:5.0f}")
        T["alt"].setPos(self.alt.cx, self.alt.cz - 0.065)
        T["vsi"].setText(f"{y['vs_fpm']:+5.0f}")
        T["vsi"].setPos(self.vsi.cx + 0.03, self.vsi.cz - 0.035)
        T["hdg"].setText(f"{y['psi_deg'] % 360.0:03.0f}")
        T["hdg"].setPos(self.hi.cx, self.hi.cz - 0.125)
        T["tach"].setText(f"{y['rpm']:4.0f}")
        T["tach"].setPos(self.tach.cx, self.tach.cz - 0.06)
        T["ap"].setText(ap)
        T["levers"].setText(levers["text"])
        T["engine"].setText(f"MAP {y['map_inhg']:4.1f} inHg   {y['hp']:3.0f} hp\nFF {y['ff_gph']:4.1f} gph   "
                            f"thrust {y['thrust_n']:4.0f} N\nAOA {y['alpha_deg']:4.1f}   GS {y['gs_mps'] / 0.514444:3.0f} kt")

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
            t = OnscreenText(text=lab, pos=(g.cx + x, g.cz + z - 0.012), scale=g.r * (0.2 if lab in "NESW" else 0.15),
                             fg=WHITE if lab not in "NESW" else AMBER, parent=self.dyn, align=TextNode.A_center)
            t.set_r(k * 30.0 - psi)
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

    def _turn(self, ls, rate_dps, slip):
        """The turn coordinator: the small aircraft banks 15 deg at standard rate (3 deg/s); the
        ball moves right when the side force pushes it right (slip > 0)."""
        g = self.tc
        b = max(-30.0, min(30.0, rate_dps * 5.0))
        c, s = math.cos(math.radians(-b)), math.sin(math.radians(-b))
        ls.set_color(*WHITE)
        for (x0, z0), (x1, z1) in (((-0.62, 0), (0.62, 0)), ((0, 0), (0, 0.18)), ((-0.18, 0.02), (0.18, 0.02))):
            ls.move_to(g.cx + (x0 * c - z0 * s) * g.r, 0, g.cz + (x0 * s + z0 * c) * g.r)
            ls.draw_to(g.cx + (x1 * c - z1 * s) * g.r, 0, g.cz + (x1 * s + z1 * c) * g.r)
        bx = max(-0.36, min(0.36, slip * 4.0)) * g.r
        bz = -0.53 * g.r
        rb = 0.075 * g.r
        ls.set_color(0.05, 0.05, 0.05, 1)
        for k in range(13):
            a = 2 * math.pi * k / 12
            (ls.move_to if k == 0 else ls.draw_to)(g.cx + bx + rb * math.cos(a), 0, g.cz + bz + rb * math.sin(a))
        disk("ball", rb, (0.05, 0.05, 0.05, 1), 12).copy_to(self.dyn).set_pos(g.cx + bx, 0, g.cz + bz)
        ls.set_color(*GREY)
        for x in (-0.11, 0.11):
            ls.move_to(g.cx + x * g.r, 0, g.cz - 0.62 * g.r)
            ls.draw_to(g.cx + x * g.r, 0, g.cz - 0.44 * g.r)
