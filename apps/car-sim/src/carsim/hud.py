"""The dashboard and the screen text, drawn in Panda3D's 2D layer (aspect2d).

Bottom left: the speed, the direction (D or R), the pedals and the steering. Bottom right: the
electric drive: motor speed, torque against its limit, power (negative while regenerating) and the
battery: state of charge, voltage and current. Top: the lap times on the track, the surfaces under
the wheels, the info line and the help.
"""

from __future__ import annotations

from direct.gui.OnscreenText import OnscreenText
from panda3d.core import LineSegs, NodePath, TextNode

WHITE = (0.96, 0.96, 0.96, 1.0)
GREY = (0.6, 0.62, 0.66, 1.0)
GREEN = (0.35, 0.95, 0.45, 1.0)
AMBER = (1.0, 0.75, 0.2, 1.0)
RED = (1.0, 0.3, 0.25, 1.0)
CYAN = (0.35, 0.8, 1.0, 1.0)


def fmt_lap(t: float | None) -> str:
    if t is None:
        return "--:--.---"
    m, s = divmod(t, 60.0)
    return f"{int(m):d}:{s:06.3f}"


class Hud:
    def __init__(self, aspect2d: NodePath, aspect: float, line_scale: float = 1.0):
        self.root = aspect2d.attach_new_node("hud")
        self.ar = aspect
        self.line_scale = line_scale
        self.lines_np: NodePath | None = None
        self.texts: dict[str, OnscreenText] = {}
        ar = aspect

        def txt(name, pos, scale=0.05, align=TextNode.A_left, fg=WHITE):
            self.texts[name] = OnscreenText(text="", pos=pos, scale=scale, align=align, fg=fg, parent=self.root,
                                            mayChange=True, shadow=(0, 0, 0, 0.7))

        txt("speed", (-ar + 0.42, -0.80), 0.14, TextNode.A_right)
        txt("speed_l", (-ar + 0.44, -0.80), 0.045)
        txt("dir", (-ar + 0.44, -0.72), 0.07, TextNode.A_left, GREEN)
        txt("pedals", (-ar + 0.08, -0.93), 0.035, TextNode.A_left, GREY)
        txt("drive", (ar - 0.06, -0.42), 0.045, TextNode.A_right)
        txt("soc", (ar - 0.06, -0.95), 0.05, TextNode.A_right, GREEN)
        txt("tq_l", (ar - 0.66, -0.605), 0.032, TextNode.A_left, GREY)
        txt("lap", (ar - 0.06, 0.90), 0.05, TextNode.A_right)
        txt("surface", (ar - 0.06, 0.62), 0.035, TextNode.A_right, GREY)
        txt("info", (-ar + 0.05, 0.92), 0.038, TextNode.A_left, WHITE)
        txt("help", (-ar + 0.05, 0.84), 0.038, TextNode.A_left, WHITE)
        txt("warn", (0.0, 0.45), 0.075, TextNode.A_center, AMBER)
        txt("big", (0.0, 0.15), 0.12, TextNode.A_center, RED)
        txt("caption", (0.0, -0.55), 0.055, TextNode.A_center, WHITE)
        self.show_help = False

    def _bar(self, ls, x0, y0, w, h, frac, color, signed=False):
        """A bar from x0 (or from its middle when signed) filled to frac (0..1, or -1..1)."""
        ls.set_color(*GREY)
        for a, b in (((x0, y0), (x0 + w, y0)), ((x0 + w, y0), (x0 + w, y0 + h)), ((x0 + w, y0 + h), (x0, y0 + h)),
                     ((x0, y0 + h), (x0, y0))):
            ls.move_to(a[0], 0, a[1])
            ls.draw_to(b[0], 0, b[1])
        ls.set_color(*color)
        frac = max(-1.0, min(1.0, frac))
        xa = x0 + w / 2 if signed else x0
        xb = xa + (w / 2 if signed else w) * frac
        n = 5
        for k in range(n + 1):
            yy = y0 + h * (0.15 + 0.7 * k / n)
            ls.move_to(xa, 0, yy)
            ls.draw_to(xb, 0, yy)

    def update(self, y: dict, *, motors: list[str], controls: dict, reverse: bool, info: str, lap: str, surface: str,
               caption: str, warning: str, crashed: str, paused: bool, help_text: str, t: float) -> None:
        ar = self.ar
        ls = LineSegs("hud")
        ls.set_thickness(2.0 * self.line_scale)
        # pedals and steering, bottom left
        x0 = -ar + 0.08
        self._bar(ls, x0, -0.90, 0.30, 0.05, controls["throttle"], GREEN)
        self._bar(ls, x0 + 0.34, -0.90, 0.30, 0.05, controls["brake"], RED)
        self._bar(ls, x0 + 0.68, -0.90, 0.36, 0.05, controls["steer"], CYAN, signed=True)
        # motor torque against its limit and the state of charge, bottom right
        tq = sum(y.get(f"motor_{a}_torque", 0.0) for a in motors)
        tl = max(1e-6, sum(y.get(f"motor_{a}_tlim", 0.0) for a in motors))
        self._bar(ls, ar - 0.66, -0.66, 0.60, 0.04, tq / tl, AMBER if tq >= 0 else CYAN, signed=True)
        soc = y.get("soc", 0.0)
        self._bar(ls, ar - 0.66, -0.86, 0.60, 0.05, soc, GREEN if soc > 0.2 else RED)
        if self.lines_np is not None:
            self.lines_np.remove_node()
        self.lines_np = self.root.attach_new_node(ls.create())

        T = self.texts
        T["speed"].setText(f"{abs(y.get('kmh', 0.0)):3.0f}")
        T["speed_l"].setText("km/h")
        T["dir"].setText("R" if reverse else "D")
        T["dir"].setFg(AMBER if reverse else GREEN)
        hb = "   HANDBRAKE" if controls.get("handbrake", 0.0) > 0.5 else ""
        T["pedals"].setText(f"throttle {controls['throttle'] * 100:3.0f}%     brake {controls['brake'] * 100:3.0f}%"
                            f"     steer {controls['steer']:+.2f}{hb}")
        rows = []
        for a in motors:
            rpm = y.get(f"motor_{a}_rpm", 0.0)
            tqa = y.get(f"motor_{a}_torque", 0.0)
            pw = y.get(f"motor_{a}_power", 0.0) / 1000.0
            name = {"f": "front", "r": "rear"}[a] if len(motors) > 1 else "motor"
            rows.append(f"{name} {rpm:6.0f} rpm  {tqa:+5.0f} N m  {pw:+6.1f} kW")
        p_bat = y.get("battery_w", 0.0) / 1000.0
        regen = p_bat < -0.5
        rows.append(("REGEN " if regen else "") + f"battery {y.get('battery_v', 0.0):5.1f} V  {y.get('battery_a', 0.0):+6.1f} A"
                    f"  {p_bat:+6.1f} kW")
        T["drive"].setText("\n".join(rows))
        T["drive"].setFg(CYAN if regen else WHITE)
        T["tq_l"].setText("motor torque / limit (regen: left)")
        T["soc"].setText(f"SOC {soc * 100:5.1f} %")
        T["soc"].setFg(GREEN if soc > 0.2 else RED)
        T["lap"].setText(lap)
        T["surface"].setText(surface)
        T["info"].setText(info)
        T["help"].setText(help_text if self.show_help else "F1: help")
        blink = ((t + 0.1) * 2.0) % 1.0 < 0.7
        T["warn"].setText(warning.upper() if (warning and blink) else "")
        T["big"].setText(f"{crashed}\nR to reset" if crashed else ("PAUSED" if paused else ""))
        T["big"].setFg(RED if crashed else WHITE)
        T["caption"].setText(caption)
