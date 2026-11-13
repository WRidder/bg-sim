"""Scripted inputs for the headless smoke test and the video: deterministic functions of sim time.

A segment either moves the controls open loop (``pitch``, ``roll``, ``yaw``) or, with ``bank``,
flies the roll stick like a pilot holding a bank angle (proportional on the bank error, at most
``roll`` of stick). Segment edges are ramped over ``edge`` seconds: no step inputs.
"""

from __future__ import annotations

from dataclasses import dataclass, field


def wrap180(a: float) -> float:
    return (a + 180.0) % 360.0 - 180.0


@dataclass
class Segment:
    t0: float
    t1: float
    pitch: float = 0.0
    roll: float = 0.0
    yaw: float = 0.0
    throttle: float | None = None   # from t0 on (None: keep the last throttle)
    bank: float | None = None       # deg: hold this bank with at most |roll| of stick
    gain: float = 0.008             # stick per deg of bank error


@dataclass
class Script:
    name: str
    start: int                       # index into starts.json
    duration: float                  # s of sim time
    segments: list[Segment]
    views: list[tuple[float, str]] = field(default_factory=lambda: [(0.0, "chase")])
    edge: float = 0.15               # s, ramp of each segment's edges
    captions: list[tuple[float, float, str]] = field(default_factory=list)
    fires: list[float] = field(default_factory=list)   # s, fire the next AIM-9X

    def controls(self, t: float, throttle0: float, phi_deg: float = 0.0) -> tuple[float, float, float, float]:
        p = r = y = 0.0
        thr = throttle0
        for s in self.segments:
            if s.throttle is not None and t >= s.t0:
                thr = s.throttle
            if s.t0 - self.edge <= t <= s.t1 + self.edge:
                w = min(1.0, max(0.0, (t - s.t0 + self.edge) / self.edge), max(0.0, (s.t1 + self.edge - t) / self.edge))
                roll = s.roll
                if s.bank is not None:
                    lim = abs(s.roll) or 1.0
                    roll = max(-lim, min(lim, s.gain * wrap180(s.bank - phi_deg)))
                p, r, y = p + w * s.pitch, r + w * roll, y + w * s.yaw
        return p, r, y, thr

    def view(self, t: float) -> str:
        v = self.views[0][1]
        for t0, name in self.views:
            if t >= t0:
                v = name
        return v

    def caption(self, t: float) -> str:
        return next((c for t0, t1, c in self.captions if t0 <= t < t1), "")


SCRIPTS = {
    # 10 s: a bit of everything, for the headless smoke test
    "smoke": Script("smoke", 0, 10.0, [
        Segment(1.0, 2.0, roll=0.5), Segment(2.5, 4.0, bank=0.0, roll=0.5),
        Segment(5.0, 6.0, pitch=0.3), Segment(7.0, 7.5, yaw=0.5), Segment(8.0, 10.0, bank=0.0, roll=0.5),
    ], views=[(0.0, "chase"), (5.0, "cockpit")]),
    # a short weapons demo: hold the target in the seeker and fire both wingtip missiles
    "missile": Script("missile", 2, 14.0, [], views=[(0.0, "chase"), (5.0, "cockpit"), (9.0, "chase")],
                      fires=[1.8, 2.8],
                      captions=[(0.0, 1.8, "AIM-9X seeker: keep a drone inside the 45 deg cue"),
                                (1.8, 2.8, "FOX 2: lock and launch"),
                                (2.8, 8.0, "second AIM-9X away"),
                                (8.0, 14.0, "target destroyed; a new drone enters the play area")]),
    # the video: a roll, a coordinated turn, a hard pull into the limiter, chase and cockpit views
    "demo": Script("demo", 2, 46.0, [
        Segment(3.0, 4.3, roll=1.0),                                   # a full-stick roll ...
        Segment(4.45, 7.5, bank=0.0, roll=0.6),                        # ... back to wings level
        Segment(8.5, 19.0, bank=60.0, roll=0.4),                       # a coordinated 60 deg turn, stick centred in pitch
        Segment(19.0, 21.0, bank=0.0, roll=0.4),
        Segment(21.5, 28.0, bank=80.0, roll=0.8, throttle=1.0),        # 80 deg bank, afterburner ...
        Segment(23.0, 27.5, pitch=1.0),                                # ... and full aft stick: the limiter
        Segment(28.2, 31.0, bank=0.0, roll=0.8),
        Segment(31.0, 33.0, throttle=0.6),
        Segment(34.0, 41.0, bank=-45.0, roll=0.4),                     # a turn the other way
        Segment(41.0, 46.0, bank=0.0, roll=0.4),
    ], views=[(0.0, "chase"), (12.5, "cockpit"), (31.0, "chase"), (37.0, "cockpit"), (42.0, "chase")],
        captions=[(0.0, 3.0, "f16-sim FMU: 700 ft/s at 5000 ft, chase view"),
                  (3.0, 8.0, "full-stick roll about the velocity vector"),
                  (8.5, 12.5, "coordinated 60 deg turn: the law holds the 2 g, beta near zero"),
                  (12.5, 19.0, "cockpit view: HUD in the turn"),
                  (19.0, 21.5, "cockpit view: rolling out"),
                  (21.5, 28.5, "full aft stick in an 80 deg bank: alpha/g limiter"),
                  (31.0, 37.0, "chase view"),
                  (37.0, 42.0, "cockpit view")]),
}
