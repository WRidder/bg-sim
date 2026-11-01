"""Driver inputs: wheels, pedals and gamepads through SDL (pygame-ce), with a keyboard fallback.

pygame is used for its joystick API only: the window is Panda3D's. SDL is started with the dummy
video driver and allowed to read joysticks while another window has the focus.
"""

from __future__ import annotations

import os
import tomllib
from dataclasses import dataclass
from pathlib import Path

CONTROLS = ("steer", "throttle", "brake")


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
        return shape(min(1.0, max(0.0, 0.5 * (v + 1.0))), m.deadzone, m.expo)
    return shape(v, m.deadzone, m.expo)


def load_config(path: Path) -> tuple[dict[str, AxisMap], dict[str, ButtonMap], dict]:
    data = tomllib.loads(Path(path).read_text(encoding="utf-8")) if Path(path).exists() else {}
    maps = {c: AxisMap(**data.get(c, {})) for c in CONTROLS if c in data}
    buttons = {b: ButtonMap(**data[b]) for b in ("handbrake", "reverse") if b in data}
    kb = {"steer_rate": 2.2, "steer_return": 3.0, "pedal_rate": 3.0, "pedal_release": 5.0, **data.get("keyboard", {})}
    return maps, buttons, kb


class Joysticks:
    """The SDL joysticks and which control reads which one."""

    def __init__(self, maps: dict[str, AxisMap], buttons: dict[str, ButtonMap] | None = None, enabled: bool = True):
        self.maps = maps
        self.button_maps = buttons or {}
        self.sticks = []
        self.bound: dict[str, object] = {}
        self.bound_buttons: dict[str, object] = {}
        self.pg = None
        self._prev_buttons: dict[str, bool] = {}
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
        for control, m in maps.items():
            js = self._find(m.device)
            if js is not None and m.axis < js.get_numaxes():
                self.bound[control] = js
        for name, b in self.button_maps.items():
            js = self._find(b.device)
            if js is not None and b.button < js.get_numbuttons():
                self.bound_buttons[name] = js

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
            out.append(f"[{i}] {js.get_name()}: {js.get_numaxes()} axes, {js.get_numbuttons()} buttons")
        for c in CONTROLS:
            js = self.bound.get(c)
            out.append(f"  {c:9s} <- " + (f"{js.get_name()} axis {self.maps[c].axis}" if js else "keyboard"))
        return out

    def poll(self) -> dict[str, float]:
        """The controls that have a device: control -> value (steer -1..1, pedals 0..1)."""
        if self.pg is None:
            return {}
        self.pg.event.pump()
        return {c: map_axis(js.get_axis(self.maps[c].axis), self.maps[c]) for c, js in self.bound.items()}

    def buttons(self) -> dict[str, bool]:
        """Held state of the bound buttons (handbrake, reverse)."""
        if self.pg is None:
            return {}
        return {n: bool(js.get_button(self.button_maps[n].button)) for n, js in self.bound_buttons.items()}


class Keyboard:
    """Keyboard driving: the steering moves at a rate while a key is held and returns to the
    centre when released; the pedals press in at a rate and come back faster."""

    def __init__(self, cfg: dict):
        self.cfg = cfg
        self.steer = 0.0
        self.throttle = 0.0
        self.brake = 0.0

    def update(self, keys: dict[str, bool], dt: float) -> None:
        rate, back = self.cfg["steer_rate"], self.cfg["steer_return"]
        left, right = keys.get("left", False), keys.get("right", False)
        if right and not left:
            self.steer = min(1.0, self.steer + rate * dt)
        elif left and not right:
            self.steer = max(-1.0, self.steer - rate * dt)
        else:
            step = back * dt
            self.steer = 0.0 if abs(self.steer) <= step else self.steer - step * (1 if self.steer > 0 else -1)
        for name, key in (("throttle", "accel"), ("brake", "brake")):
            v = getattr(self, name)
            if keys.get(key, False):
                v = min(1.0, v + self.cfg["pedal_rate"] * dt)
            else:
                v = max(0.0, v - self.cfg["pedal_release"] * dt)
            setattr(self, name, v)


def list_devices() -> int:
    js = Joysticks({c: AxisMap() for c in CONTROLS})
    if not js.sticks:
        print("no joysticks found (the keyboard drives)")
    for i, s in enumerate(js.sticks):
        print(f"[{i}] {s.get_name()}: {s.get_numaxes()} axes, {s.get_numbuttons()} buttons, {s.get_numhats()} hats")
    return 0


class Mixer:
    """Keyboard and devices together: per control, the input touched last wins.

    A bound device must not lock the keyboard out (a wheel or gamepad that SDL lists first would
    otherwise sit centred and swallow the arrow keys). The keyboard takes a control while its keys
    are held and while the keyboard value returns to rest; the device takes it back when its axis
    moves by more than ``MOVE`` from where it was when the keyboard took over.
    """

    MOVE = 0.05
    KEYS = {"steer": ("left", "right"), "throttle": ("accel",), "brake": ("brake",)}

    def __init__(self) -> None:
        self.source: dict[str, str] = {}
        self._anchor: dict[str, float] = {}

    def mix(self, joy: dict[str, float], kb: Keyboard, held: dict[str, bool]) -> tuple[float, float, float]:
        out = []
        for c in CONTROLS:
            kb_value = getattr(kb, c)
            if c not in joy:
                out.append(kb_value)
                continue
            dev = joy[c]
            pressed = any(held.get(k, False) for k in self.KEYS[c])
            src = self.source.get(c, "device")
            if pressed and src != "keyboard":
                src = "keyboard"
                self._anchor[c] = dev
            elif src == "keyboard" and not pressed and abs(dev - self._anchor.get(c, dev)) > self.MOVE:
                src = "device"
            self.source[c] = src
            out.append(kb_value if src == "keyboard" else dev)
        return out[0], out[1], out[2]
