"""The head-up display and the screen text, drawn in Panda3D's 2D layer (aspect2d).

In the cockpit view the pitch ladder, the horizon and the flight-path marker are conformal: one
degree on the HUD is one degree of the view (the camera's vertical field of view sets the scale).
In the chase view the HUD keeps its numbers, the warnings and the heading tape.
"""

from __future__ import annotations

import math

from direct.gui.OnscreenText import OnscreenText
from panda3d.core import LineSegs, NodePath, TextNode

GREEN = (0.35, 1.0, 0.45, 1.0)
AMBER = (1.0, 0.75, 0.2, 1.0)
RED = (1.0, 0.25, 0.2, 1.0)
WHITE = (0.95, 0.95, 0.95, 1.0)
KT, FT = 1.0 / 0.514444, 1.0 / 0.3048


class Hud:
    def __init__(self, aspect2d: NodePath, fov_v_deg: float, line_scale: float = 1.0):
        self.line_scale = line_scale
        self.root = aspect2d.attach_new_node("hud")
        self.lines_np: NodePath | None = None
        self.k = 1.0 / math.tan(math.radians(fov_v_deg) / 2.0)
        self.texts = {}
        self._pool: list[OnscreenText] = []
        self._used = 0

        def txt(name, pos, scale=0.05, align=TextNode.A_left, fg=GREEN, mono=True):
            t = OnscreenText(text="", pos=pos, scale=scale, align=align, fg=fg, parent=self.root, mayChange=True,
                             shadow=(0, 0, 0, 0.6))
            self.texts[name] = t
            return t

        txt("speed", (-0.78, -0.015), 0.06, TextNode.A_right)
        txt("speed_l", (-0.78, 0.06), 0.035, TextNode.A_right)
        txt("alt", (0.78, -0.015), 0.06, TextNode.A_left)
        txt("alt_l", (0.78, 0.06), 0.035, TextNode.A_left)
        txt("vs", (0.78, -0.09), 0.04, TextNode.A_left)
        txt("left", (-0.95, -0.25), 0.045, TextNode.A_left)
        txt("right", (0.62, -0.25), 0.045, TextNode.A_left)
        txt("heading", (0.0, 0.70), 0.05, TextNode.A_center)
        txt("warn", (0.0, -0.52), 0.085, TextNode.A_center, AMBER)
        txt("big", (0.0, 0.25), 0.12, TextNode.A_center, RED)
        txt("info", (-1.30, 0.92), 0.04, TextNode.A_left, WHITE)
        txt("ring", (1.30, 0.92), 0.045, TextNode.A_right, AMBER)
        txt("help", (-1.30, 0.80), 0.04, TextNode.A_left, WHITE)
        txt("caption", (0.0, -0.88), 0.06, TextNode.A_center, WHITE)
        self.show_help = False

    # ---- helpers
    def _label(self, text, x, y, scale=0.035, align=TextNode.A_center, fg=GREEN):
        if self._used == len(self._pool):
            self._pool.append(OnscreenText(text="", scale=scale, parent=self.root, mayChange=True, fg=fg))
        t = self._pool[self._used]
        self._used += 1
        t.setText(text)
        t.setPos(x, y)
        t.setScale(scale)
        t.setFg(fg)
        t.setAlign(align) if hasattr(t, "setAlign") else None
        t.show()
        return t

    def _proj(self, az_deg: float, el_deg: float) -> tuple[float, float]:
        """Screen position of a direction az (right), el (up) from the boresight."""
        return (math.tan(math.radians(max(-80, min(80, az_deg)))) * self.k,
                math.tan(math.radians(max(-80, min(80, el_deg)))) * self.k)

    # ---- per frame
    def update(self, y: dict, *, cockpit: bool, info: str, ring: str, caption: str, t: float, crashed: bool,
               paused: bool, help_text: str, ring_cue: tuple[float, float] | None) -> None:
        self._used = 0
        ls = LineSegs("hud")
        ls.set_thickness(2.0 * self.line_scale)
        ls.set_color(*GREEN)
        phi, theta, psi = y["phi_deg"], y["theta_deg"], y["psi_deg"]
        if cockpit:
            self._ladder(ls, phi, theta)
            # waterline (the boresight)
            for a, b in (((-0.09, 0), (-0.04, 0)), ((-0.04, 0), (-0.02, -0.025)), ((-0.02, -0.025), (0, 0)),
                         ((0, 0), (0.02, -0.025)), ((0.02, -0.025), (0.04, 0)), ((0.04, 0), (0.09, 0))):
                ls.move_to(a[0], 0, a[1] - 0.0)
                ls.draw_to(b[0], 0, b[1])
            # flight-path marker: the velocity is beta right and alpha down of the nose
            fx, fz = self._proj(y["beta_deg"], -y["alpha_deg"])
            self._circle(ls, fx, fz, 0.025)
            for a, b in (((-0.06, 0), (-0.025, 0)), ((0.025, 0), (0.06, 0)), ((0, 0.025), (0, 0.05))):
                ls.move_to(fx + a[0], 0, fz + a[1])
                ls.draw_to(fx + b[0], 0, fz + b[1])
        self._tape(ls, psi)
        # speed and altitude boxes
        for x0, x1 in ((-1.02, -0.76), (0.76, 1.08)):
            ls.move_to(x0, 0, -0.04)
            for x, z in ((x1, -0.04), (x1, 0.035), (x0, 0.035), (x0, -0.04)):
                ls.draw_to(x, 0, z)
        if ring_cue is not None:
            cx, cz = ring_cue
            ls.set_color(*AMBER)
            self._circle(ls, cx, cz, 0.04, 12)
        if self.lines_np is not None:
            self.lines_np.remove_node()
        self.lines_np = self.root.attach_new_node(ls.create())

        T = self.texts
        T["speed"].setText(f"{y['cas_mps'] * KT:4.0f}")
        T["speed_l"].setText("CAS kt")
        T["alt"].setText(f"{y['alt_m'] * FT:6.0f}")
        T["alt_l"].setText("ALT ft")
        T["vs"].setText(f"{y['vs_mps'] * FT * 60:+6.0f} fpm")
        thr = y.get("throttle", 0.0)
        T["left"].setText(f"M {y['mach']:.2f}\nG {y['nz_g']:4.1f}\nAOA {y['alpha_deg']:4.1f}\nB {y['beta_deg']:+4.1f}")
        T["right"].setText(f"THR {thr * 100:3.0f}%{' AB' if thr > 0.77 else ''}\nPWR {y['power_pct']:3.0f}%\n"
                           f"TAS {y['tas_mps'] * KT:4.0f}\nROLL {phi:+4.0f}")
        # warnings, most important first; they blink at 2 Hz
        blink = ((t + 0.1) * 2.0) % 1.0 < 0.65
        warn = []
        if y["departed"] > 0.5:
            warn.append("DEPARTED")
        tti = y.get("agl", y["alt_m"]) / max(1e-3, -y["vs_mps"]) if y["vs_mps"] < -1.0 else 1e9
        if y.get("agl", y["alt_m"]) < 600.0 and tti < 8.0:
            warn.append("PULL UP")
        if y["alpha_deg"] > 22.0 or (y["cas_mps"] * KT < 130.0):
            warn.append("STALL")
        if y["limiter_active"] > 0.5:
            warn.append("ALPHA/G LIMIT" if y["alpha_deg"] > 20.0 else "G LIMIT")
        T["warn"].setText("\n".join(warn[:2]) if (warn and blink) else "")
        T["warn"].setFg(RED if warn and warn[0] in ("DEPARTED", "PULL UP", "STALL") else AMBER)
        T["big"].setText("CRASHED\nR to reset" if crashed else ("PAUSED" if paused else ""))
        T["big"].setFg(RED if crashed else WHITE)
        T["info"].setText(info)
        T["ring"].setText(ring)
        T["help"].setText(help_text if self.show_help else "F1: help")
        T["caption"].setText(caption)
        for t_ in self._pool[self._used:]:
            t_.hide()

    def _circle(self, ls, x, z, r, n=16):
        ls.move_to(x + r, 0, z)
        for k in range(1, n + 1):
            a = 2 * math.pi * k / n
            ls.draw_to(x + r * math.cos(a), 0, z + r * math.sin(a))

    def _ladder(self, ls, phi, theta):
        # a right bank turns the world (and the ladder) counter-clockwise on the screen
        c, s = math.cos(math.radians(phi)), math.sin(math.radians(phi))

        def rot(x, z):
            return x * c - z * s, x * s + z * c

        lo = int(math.floor((theta - 25) / 5.0)) * 5
        for p in range(lo, lo + 55, 5):
            if p < -90 or p > 90:
                continue
            d = math.tan(math.radians(max(-80, min(80, p - theta)))) * self.k
            if abs(d) > 0.9:
                continue
            if p == 0:   # the horizon line, long
                segs = [(-0.75, -0.08), (0.08, 0.75)]
            else:
                segs = [(-0.30, -0.10), (0.10, 0.30)]
            for x0, x1 in segs:
                if p < 0:     # dashed below the horizon
                    n = 3
                    for k in range(n):
                        a = x0 + (x1 - x0) * k / n
                        b = a + (x1 - x0) / n * 0.6
                        ax, az = rot(a, d)
                        bx, bz = rot(b, d)
                        ls.move_to(ax, 0, az)
                        ls.draw_to(bx, 0, bz)
                else:
                    ax, az = rot(x0, d)
                    bx, bz = rot(x1, d)
                    ls.move_to(ax, 0, az)
                    ls.draw_to(bx, 0, bz)
            if p != 0:   # end ticks towards the horizon
                tick = -0.03 if p > 0 else 0.03
                for x in (-0.30, 0.30):
                    ax, az = rot(x, d)
                    bx, bz = rot(x, d + tick)
                    ls.move_to(ax, 0, az)
                    ls.draw_to(bx, 0, bz)
                lx, lz = rot(-0.38, d - 0.012)
                self._label(f"{abs(p)}", lx, lz, 0.035)
                lx, lz = rot(0.38, d - 0.012)
                self._label(f"{abs(p)}", lx, lz, 0.035)

    def _tape(self, ls, psi):
        y0, span, scale = 0.80, 30, 0.022
        psi = psi % 360.0
        start = int(math.floor((psi - span) / 5.0)) * 5
        for h in range(start, int(psi + span) + 1, 5):
            x = (h - psi) * scale
            tall = h % 10 == 0
            ls.move_to(x, 0, y0)
            ls.draw_to(x, 0, y0 + (0.035 if tall else 0.018))
            if h % 10 == 0:
                hh = h % 360
                name = {0: "N", 90: "E", 180: "S", 270: "W"}.get(hh, f"{hh // 10:02d}")
                self._label(name, x, y0 + 0.05, 0.035)
        ls.move_to(-0.012, 0, y0 - 0.03)
        ls.draw_to(0, 0, y0 - 0.005)
        ls.draw_to(0.012, 0, y0 - 0.03)
        self.texts["heading"].setText(f"{psi:03.0f}")
        self.texts["heading"].setPos(0.0, y0 - 0.09)
