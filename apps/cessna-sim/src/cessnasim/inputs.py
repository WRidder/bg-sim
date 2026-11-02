"""Pilot inputs: yoke, pedals, throttle quadrant and toe brakes through SDL (pygame-ce), with a
keyboard fallback.

pygame is used for its joystick API only: the window is Panda3D's. SDL is started with the dummy
video driver and allowed to read joysticks while another window has the focus.

Axes: pitch, roll, yaw (the pedals) are bipolar -1..1; throttle, mixture and the two toe brakes
are unipolar 0..1. The flaps (detents), the trim and the autopilot are keys or buttons.
"""

from __future__ import annotations

import os
import tomllib
from dataclasses import dataclass, field
from pathlib import Path

AXES = ("pitch", "roll", "yaw", "throttle", "mixture", "brake_l", "brake_r")
BIPOLAR = ("pitch", "roll", "yaw")
BUTTONS = ("flaps_down", "flaps_up", "trim_up", "trim_down", "brakes", "ap_roll", "ap_alt")


@dataclass
class AxisMap:
    device: str | int = ""
    axis: int = 0
    invert: bool = False
    deadzone: float = 0.0
    expo: float = 0.0
    range: str = "bipolar"


@dataclass
class ButtonMap:
    device: str | int = ""
    button: int = 0


def shape(v: float, deadzone: float, expo: float) -> float:
    """Dead zone (rescaled, so full deflection stays full) and expo (blend of linear and cubic)."""
    v = max(-1.0, min(1.0, v))
    a = abs(v)
    if a <= deadzone:
        return 0.0
    a = (a - deadzone) / (1.0 - deadzone) if deadzone < 1.0 else 0.0
    a = (1.0 - expo) * a + expo * a**3
    return a if v > 0 else -a


def map_axis(raw: float, m: AxisMap) -> float:
    v = -raw if m.invert else raw
    if m.range == "unipolar":
        u = min(1.0, max(0.0, 0.5 * (v + 1.0)))
        return 0.0 if u <= m.deadzone else (u - m.deadzone) / (1.0 - m.deadzone)
    return shape(v, m.deadzone, m.expo)


KEYBOARD = {"stick_rate": 2.0, "spring": 3.0, "pedal_rate": 2.0, "throttle_rate": 0.4, "mixture_rate": 0.3,
            "trim_rate": 0.25}


def load_config(path: Path) -> tuple[dict[str, AxisMap], dict[str, ButtonMap], dict]:
    data = tomllib.loads(Path(path).read_text(encoding="utf-8")) if Path(path).exists() else {}
    axes = {c: AxisMap(**data[c]) for c in AXES if c in data}
    buttons = {b: ButtonMap(**v) for b, v in data.get("buttons", {}).items() if b in BUTTONS}
    kb = {**KEYBOARD, **data.get("keyboard", {})}
    return axes, buttons, kb


class Joysticks:
    """The SDL devices and which control reads which one."""

    def __init__(self, axes: dict[str, AxisMap], buttons: dict[str, ButtonMap] | None = None, enabled: bool = True):
        self.maps = axes
        self.bmaps = buttons or {}
        self.sticks = []
        self.bound: dict[str, object] = {}
        self.bbound: dict[str, object] = {}
        self._prev: dict[str, bool] = {}
        self.pg = None
        if not enabled:
            return
        os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
        os.environ.setdefault("SDL_JOYSTICK_ALLOW_BACKGROUND_EVENTS", "1")
        os.environ.setdefault("PYGAME_HIDE_SUPPORT_PROMPT", "1")
        try:
            import pygame
        except ImportError:
            return
        self.pg = pygame
        pygame.display.init()
        pygame.joystick.init()
        self.sticks = [pygame.joystick.Joystick(i) for i in range(pygame.joystick.get_count())]
        for js in self.sticks:
            js.init()
        for control, m in axes.items():
            js = self._find(m.device)
            if js is not None and m.axis < js.get_numaxes():
                self.bound[control] = js
        for name, b in self.bmaps.items():
            js = self._find(b.device)
            if js is not None and b.button < js.get_numbuttons():
                self.bbound[name] = js

    def _find(self, device):
        if isinstance(device, int):
            return self.sticks[device] if 0 <= device < len(self.sticks) else None
        frag = str(device).lower()
        for js in self.sticks:
            if frag in js.get_name().lower():
                return js
        return None

    def describe(self) -> list[str]:
        out = []
        for i, js in enumerate(self.sticks):
            out.append(f"[{i}] {js.get_name()}: {js.get_numaxes()} axes, {js.get_numbuttons()} buttons, "
                       f"{js.get_numhats()} hats")
        for c in AXES:
            js = self.bound.get(c)
            out.append(f"  {c:9s} <- " + (f"{js.get_name()} axis {self.maps[c].axis}" if js else "keyboard"))
        return out

    def poll(self) -> tuple[dict[str, float], set[str]]:
        """The axes that have a device (control -> value) and the buttons pressed since the last
        poll (rising edges)."""
        if self.pg is None:
            return {}, set()
        self.pg.event.pump()
        axes = {c: map_axis(js.get_axis(self.maps[c].axis), self.maps[c]) for c, js in self.bound.items()}
        pressed = set()
        for name, js in self.bbound.items():
            down = bool(js.get_button(self.bmaps[name].button))
            if down and not self._prev.get(name, False):
                pressed.add(name)
            self._prev[name] = down
        return axes, pressed

    def held(self, name: str) -> bool:
        return self._prev.get(name, False)


class Keyboard:
    """Keyboard controls: a spring-back yoke and pedals, levers that stay where they are put."""

    def __init__(self, cfg: dict):
        self.cfg = {**KEYBOARD, **cfg}
        self.pitch = self.roll = self.yaw = 0.0
        self.throttle = 0.0
        self.mixture = 1.0
        self.brake_l = self.brake_r = 0.0

    def _axis(self, value: float, minus: bool, plus: bool, dt: float, rate: float) -> float:
        spring = self.cfg["spring"]
        if plus and not minus:
            value = min(1.0, value + rate * dt)
        elif minus and not plus:
            value = max(-1.0, value - rate * dt)
        else:
            step = spring * dt
            value = 0.0 if abs(value) <= step else value - step * (1 if value > 0 else -1)
        return value

    def update(self, keys: dict[str, bool], dt: float) -> None:
        c = self.cfg
        # pitch +1 = yoke aft (pull): the down arrow, like a yoke drawn towards the pilot
        self.pitch = self._axis(self.pitch, keys.get("push", False), keys.get("pull", False), dt, c["stick_rate"])
        self.roll = self._axis(self.roll, keys.get("left", False), keys.get("right", False), dt, c["stick_rate"])
        self.yaw = self._axis(self.yaw, keys.get("yaw_left", False), keys.get("yaw_right", False), dt, c["pedal_rate"])
        r = c["throttle_rate"] * dt
        if keys.get("throttle_up"):
            self.throttle = min(1.0, self.throttle + r)
        if keys.get("throttle_down"):
            self.throttle = max(0.0, self.throttle - r)
        r = c["mixture_rate"] * dt
        if keys.get("mixture_rich"):
            self.mixture = min(1.0, self.mixture + r)
        if keys.get("mixture_lean"):
            self.mixture = max(0.0, self.mixture - r)
        both = keys.get("brakes", False)
        self.brake_l = 1.0 if (both or keys.get("brake_l", False)) else 0.0
        self.brake_r = 1.0 if (both or keys.get("brake_r", False)) else 0.0


KEY_OF = {"pitch": ("pull", "push"), "roll": ("left", "right"), "yaw": ("yaw_left", "yaw_right"),
          "throttle": ("throttle_up", "throttle_down"), "mixture": ("mixture_rich", "mixture_lean"),
          "brake_l": ("brake_l", "brakes"), "brake_r": ("brake_r", "brakes")}


class Mixer:
    """Keyboard and devices together: per control, the input touched last wins.

    A bound device must not lock the keyboard out (a gamepad SDL lists first would sit centred
    and swallow the arrow keys). The keyboard takes a control while its keys are held (and while a
    released yoke springs back); the device takes it back when its axis moves by more than
    ``MOVE``. Taking a lever over from a device starts the keyboard at the device's setting.
    """

    MOVE = 0.05

    def __init__(self) -> None:
        self.source: dict[str, str] = {}
        self._anchor: dict[str, float] = {}

    def mix(self, joy: dict[str, float], kb: Keyboard, held: dict[str, bool]) -> dict[str, float]:
        out = {}
        for c in AXES:
            kb_value = getattr(kb, c)
            if c not in joy:
                out[c] = kb_value
                continue
            dev = joy[c]
            keys = any(held.get(k, False) for k in KEY_OF[c])
            src = self.source.get(c, "device")
            if keys and src != "keyboard":
                if c in ("throttle", "mixture"):
                    setattr(kb, c, dev)   # continue from the lever's setting
                src = "keyboard"
                self._anchor[c] = dev
            elif src == "keyboard" and not keys and abs(dev - self._anchor.get(c, dev)) > self.MOVE:
                src = "device"
            self.source[c] = src
            out[c] = getattr(kb, c) if src == "keyboard" else dev
        return out


def list_devices() -> int:
    js = Joysticks({c: AxisMap() for c in AXES})
    if not js.sticks:
        print("no joysticks found (the keyboard flies)")
    for i, s in enumerate(js.sticks):
        print(f"[{i}] {s.get_name()}: {s.get_numaxes()} axes, {s.get_numbuttons()} buttons, {s.get_numhats()} hats")
    return 0
