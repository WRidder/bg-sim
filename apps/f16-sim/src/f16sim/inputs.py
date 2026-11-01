"""Pilot inputs: joysticks and pedals through SDL (pygame-ce), with a keyboard fallback.

pygame is used for its joystick API only: the window is Panda3D's. SDL is started with the dummy
video driver and allowed to read joysticks while another window has the focus.
"""

from __future__ import annotations

import os
import tomllib
from dataclasses import dataclass
from pathlib import Path

CONTROLS = ("pitch", "roll", "yaw", "throttle")


@dataclass
class AxisMap:
    device: str | int = ""
    axis: int = 0
    invert: bool = False
    deadzone: float = 0.0
    expo: float = 0.0
    range: str = "bipolar"


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
        return min(1.0, max(0.0, 0.5 * (v + 1.0)))
    return shape(v, m.deadzone, m.expo)


def load_config(path: Path) -> tuple[dict[str, AxisMap], dict]:
    data = tomllib.loads(Path(path).read_text(encoding="utf-8")) if Path(path).exists() else {}
    maps = {c: AxisMap(**data.get(c, {})) for c in CONTROLS if c in data}
    kb = {"stick_rate": 2.5, "spring": 4.0, "throttle_rate": 0.4, **data.get("keyboard", {})}
    return maps, kb


class Joysticks:
    """The SDL joysticks and which control reads which one."""

    def __init__(self, maps: dict[str, AxisMap], enabled: bool = True):
        self.maps = maps
        self.sticks = []
        self.bound: dict[str, object] = {}
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
        for control, m in maps.items():
            js = self._find(m.device)
            if js is not None and m.axis < js.get_numaxes():
                self.bound[control] = js

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
        for c in CONTROLS:
            js = self.bound.get(c)
            out.append(f"  {c:8s} <- " + (f"{js.get_name()} axis {self.maps[c].axis}" if js else "keyboard"))
        return out

    def poll(self) -> dict[str, float]:
        """The controls that have a device: control -> value (sticks -1..1, throttle 0..1)."""
        if self.pg is None:
            return {}
        self.pg.event.pump()
        return {c: map_axis(js.get_axis(self.maps[c].axis), self.maps[c]) for c, js in self.bound.items()}


class Keyboard:
    """Keyboard controls with spring-back sticks. ``update`` takes which keys are held."""

    def __init__(self, cfg: dict):
        self.cfg = cfg
        self.pitch = self.roll = self.yaw = 0.0
        self.throttle = 0.0

    def _axis(self, value: float, minus: bool, plus: bool, dt: float) -> float:
        rate, spring = self.cfg["stick_rate"], self.cfg["spring"]
        if plus and not minus:
            value = min(1.0, value + rate * dt)
        elif minus and not plus:
            value = max(-1.0, value - rate * dt)
        else:
            step = spring * dt
            value = 0.0 if abs(value) <= step else value - step * (1 if value > 0 else -1)
        return value

    def update(self, keys: dict[str, bool], dt: float) -> None:
        # pitch +1 = aft stick (pull): the down arrow, like a stick drawn towards the pilot
        self.pitch = self._axis(self.pitch, keys.get("push", False), keys.get("pull", False), dt)
        self.roll = self._axis(self.roll, keys.get("left", False), keys.get("right", False), dt)
        self.yaw = self._axis(self.yaw, keys.get("yaw_left", False), keys.get("yaw_right", False), dt)
        r = self.cfg["throttle_rate"] * dt
        if keys.get("throttle_up"):
            self.throttle = min(1.0, self.throttle + r)
        if keys.get("throttle_down"):
            self.throttle = max(0.0, self.throttle - r)


def list_devices() -> int:
    js = Joysticks({c: AxisMap() for c in CONTROLS})
    if not js.sticks:
        print("no joysticks found (the keyboard flies)")
    for i, s in enumerate(js.sticks):
        print(f"[{i}] {s.get_name()}: {s.get_numaxes()} axes, {s.get_numbuttons()} buttons, {s.get_numhats()} hats")
    return 0


class Mixer:
    """Keyboard and devices together: per control, the input touched last wins.

    A bound device must not lock the keyboard out: a gamepad or virtual controller that SDL lists
    first would otherwise take the stick, sit centred and swallow the arrow keys. The keyboard takes
    a control while its keys are held (and while a released stick springs back); the device takes it
    back when its axis moves by more than ``MOVE``. Taking the throttle over from a device starts the
    keyboard at the device's setting, so there is no jump.
    """

    MOVE = 0.05

    def __init__(self) -> None:
        self.source: dict[str, str] = {}
        self._anchor: dict[str, float] = {}

    def mix(self, joy: dict[str, float], kb: Keyboard, held: dict[str, bool]) -> tuple[float, float, float, float]:
        keys = {
            "pitch": held.get("pull", False) or held.get("push", False),
            "roll": held.get("left", False) or held.get("right", False),
            "yaw": held.get("yaw_left", False) or held.get("yaw_right", False),
            "throttle": held.get("throttle_up", False) or held.get("throttle_down", False),
        }
        out = []
        for c in CONTROLS:
            kb_value = getattr(kb, c)
            if c not in joy:
                out.append(kb_value)
                continue
            dev = joy[c]
            src = self.source.get(c, "device")
            if keys[c] and src != "keyboard":
                if c == "throttle":
                    kb.throttle = dev   # continue from the lever's setting
                src = "keyboard"
                self._anchor[c] = dev
            elif src == "keyboard" and not keys[c] and abs(dev - self._anchor.get(c, dev)) > self.MOVE:
                src = "device"
            self.source[c] = src
            out.append(getattr(kb, c) if src == "keyboard" else dev)
        return out[0], out[1], out[2], out[3]
