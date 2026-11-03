"""Scripted pilots for the headless runs and the video: closed-loop, deterministic functions of
the FMU's outputs (no randomness, so a run is reproducible to the bit).

``Pilot`` flies by phases, as a helicopter pilot flies a circuit from a helipad: parked with the
collective down, the lift-off into a hover, the hover check over the pad, the transition to
forward flight with a climb, a rectangular circuit, the approach to the pad on a steep glide
path while the speed bleeds off, the hover over the pad and the vertical descent onto the gear.
A script is a list of legs: each starts the FMU at one of the start conditions and lets the
pilot fly from the phase that fits it.

The pilot flies with the SCAS on (the FMU's ``scas`` input = 1): the cyclic then commands
attitude (``cyclic_lon`` 1 = 15 deg nose down, ``cyclic_lat`` 1 = 30 deg bank right, both about
the speed's trim attitude) and the pedals a yaw rate (1 = 30 deg/s). The outer loops are those of
a pilot: the ground speed over the nose on the cyclic (pitch), the bank for the heading (or, in a
hover, for the sideways drift), the heading on the pedals in a hover, the climb rate on the
collective (with the level-flight collective of the speed as its feed-forward).
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field

from .core import Simulation, wrap180
from .fmu import ground_velocity

KT = 0.514444
G = 9.80665
# the collective of level flight over the speed (kt -> lever fraction): the trims of build_fmu.py
COLL_LEVEL = ((0.0, 0.604), (20.0, 0.54), (40.0, 0.46), (60.0, 0.414), (80.0, 0.425), (100.0, 0.46), (140.0, 0.62))
H_HOVER = 5.0                   # m: the CG in the hover over the pad (the wheels at about 3.7 m)
H_GEAR = 1.28                   # m: the CG over the ground when the helicopter stands on its gear
GLIDE = math.radians(7.0)       # the approach angle to the hover point


def clamp(v, lo, hi):
    return lo if v < lo else hi if v > hi else v


def coll_level(kts: float) -> float:
    pts = COLL_LEVEL
    if kts <= pts[0][0]:
        return pts[0][1]
    for (x0, y0), (x1, y1) in zip(pts, pts[1:]):
        if kts <= x1:
            return y0 + (y1 - y0) * (kts - x0) / (x1 - x0)
    return pts[-1][1]


@dataclass
class Pilot:
    """A closed-loop pilot. ``phase``: where it starts (parked, hover, route, approach, ...);
    ``route``: the circuit's waypoints (north, east; m) after the hover; ``v_route`` (m/s) and
    ``h_route`` (m) its speed and height; ``t_parked`` and ``t_hover`` the time it waits on the
    pad and in the hover check; ``pad``: the pad to land on (north, east)."""

    phase: str = "parked"
    route: tuple = ((600.0, 0.0), (600.0, -700.0), (-900.0, -700.0), (-900.0, 0.0))
    v_route: float = 31.0
    h_route: float = 100.0
    t_parked: float = 2.0
    t_hover: float = 5.0
    pad: tuple = (0.0, 0.0)
    hover_heading: float | None = None
    decel: float = 0.45            # m/s^2: the deceleration of the approach
    t_check: float = 4.0           # s: the hover over the pad before the descent
    t_phase: float = 0.0
    log: list = field(default_factory=list)
    wp: int = 0
    _xi: float = 0.0               # the collective's integral
    _coll: float | None = None     # the collective last sent (rate limited)
    _u_cmd: float = 0.0            # the forward speed command (acceleration limited)
    _h_cmd: float | None = None
    _hdg: float | None = None      # the heading held in a hover
    _hold: tuple | None = None     # the point held in a hover

    def set_phase(self, sim: Simulation, phase: str) -> None:
        if phase != self.phase:
            self.log.append((round(sim.model.time, 2), phase))
            self.phase = phase
            self.t_phase = 0.0

    # ---- the loops
    def _collective(self, m, vs_c: float, dt: float, rate: float = 0.25) -> float:
        vs = m["vs_mps"]
        e = vs_c - vs
        airborne = m["wow"] < 0.5
        if airborne:
            self._xi = clamp(self._xi + 0.02 * e * dt, -0.15, 0.15)
        c = coll_level(m["kts"]) + 0.04 * e + self._xi
        prev = self._coll if self._coll is not None else c
        self._coll = prev + clamp(c - prev, -rate * dt, rate * dt)
        return clamp(self._coll, 0.0, 1.0)

    def _vs_for(self, m, h_c: float, vs_max: float = 3.0, vs_min: float = -2.5) -> float:
        return clamp(0.4 * (h_c - m["alt_m"]), vs_min, vs_max)

    def _hover_hold(self, sim: Simulation, target: tuple, heading: float) -> tuple[float, float, float]:
        """The cyclic and pedals that hold the helicopter over ``target`` (north, east) on ``heading``."""
        m = sim.model
        psi = math.radians(m["psi_deg"])
        gn, ge, _ = ground_velocity(m)
        c, s = math.cos(psi), math.sin(psi)
        fwd, right = gn * c + ge * s, -gn * s + ge * c
        dn, de = target[0] - m["north_m"], target[1] - m["east_m"]
        dx, dy = dn * c + de * s, -dn * s + de * c
        u_des = clamp(0.25 * dx, -3.0, 3.0)
        v_des = clamp(0.25 * dy, -3.0, 3.0)
        lon = clamp(2.0 * (u_des - fwd) / 15.0, -0.35, 0.35)
        lat = clamp(2.5 * (v_des - right) / 30.0, -0.25, 0.25)
        ped = clamp(0.03 * wrap180(heading - m["psi_deg"]), -0.4, 0.4)
        return lon, lat, ped

    def _fly_to(self, sim: Simulation, target: tuple, u_des: float, dt: float, bank: float = 20.0):
        """The cyclic towards ``target`` at the forward speed ``u_des``: the heading on the bank."""
        m = sim.model
        dn, de = target[0] - m["north_m"], target[1] - m["east_m"]
        brg = math.degrees(math.atan2(de, dn))
        psi = math.radians(m["psi_deg"])
        gn, ge, _ = ground_velocity(m)
        fwd = gn * math.cos(psi) + ge * math.sin(psi)
        self._u_cmd += clamp(u_des - self._u_cmd, -1.0 * dt, 1.0 * dt)
        lon = clamp(2.0 * (self._u_cmd - fwd) / 15.0, -0.45, 0.45)
        # the track (not the heading) to the target: the bank corrects the drift
        trk = math.degrees(math.atan2(ge, gn)) if math.hypot(gn, ge) > 5.0 else m["psi_deg"]
        phi_c = clamp(1.6 * wrap180(brg - trk), -bank, bank)
        lat = clamp(phi_c / 30.0, -0.8, 0.8)
        # the pedals against the sideslip (the SCAS coordinates the turns about its trim bank only)
        ped = clamp(0.03 * m["beta_deg"], -0.3, 0.3) if m["kts"] > 25.0 else 0.0
        return lon, lat, ped, math.hypot(dn, de), brg, fwd

    # ---- the phases
    def __call__(self, sim: Simulation) -> None:
        m = sim.model
        dt = m.step_size
        self.t_phase += dt
        if self._hdg is None:
            self._hdg = m["psi_deg"] if self.hover_heading is None else self.hover_heading
        if self._h_cmd is None:
            self._h_cmd = m["alt_m"]
            gn, ge, _ = ground_velocity(m)      # the speed command starts at the speed over the nose
            self._u_cmd = gn * math.cos(math.radians(m["psi_deg"])) + ge * math.sin(math.radians(m["psi_deg"]))
        lon = lat = ped = 0.0
        coll = 0.0
        ph = self.phase
        if ph == "parked":
            coll = 0.0
            self._coll = 0.0
            if self.t_phase >= self.t_parked:
                self._hold = (m["north_m"], m["east_m"])
                self.set_phase(sim, "liftoff")
        elif ph == "liftoff":
            # the collective up (rate limited) to a 1 m/s climb; the cyclic centred until light on the gear
            coll = self._collective(m, 1.0, dt, rate=0.2)
            if m["wow"] < 0.5:
                lon, lat, ped = self._hover_hold(sim, self._hold, self._hdg)
            if m["alt_m"] > H_HOVER - 0.4:
                self._h_cmd = H_HOVER
                self.set_phase(sim, "hover")
        elif ph == "hover":
            if self._hold is None:
                self._hold = (m["north_m"], m["east_m"])
            lon, lat, ped = self._hover_hold(sim, self._hold, self._hdg)
            coll = self._collective(m, self._vs_for(m, H_HOVER, 1.0, -1.0), dt)
            if self.t_phase >= self.t_hover:
                self._u_cmd = 0.0
                self._h_cmd = m["alt_m"]
                self.set_phase(sim, "route" if self.route else "approach")
        elif ph == "route":
            target = self.route[self.wp]
            lon, lat, ped, d, brg, fwd = self._fly_to(sim, target, self.v_route, dt)
            # the climb with the speed: the height command rises at 2.5 m/s once past 12 m/s
            if fwd > 12.0:
                self._h_cmd = min(self.h_route, self._h_cmd + 2.5 * dt)
            coll = self._collective(m, self._vs_for(m, self._h_cmd), dt)
            # the next waypoint a turn radius early (a 20 deg bank)
            r_turn = max(fwd, 10.0) ** 2 / (G * math.tan(math.radians(20.0)))
            nxt = self.route[self.wp + 1] if self.wp + 1 < len(self.route) else self.pad
            turn = abs(wrap180(math.degrees(math.atan2(nxt[1] - target[1], nxt[0] - target[0])) - brg))
            if d < max(40.0, r_turn * math.tan(math.radians(min(turn, 120.0)) / 2.0)):
                self.wp += 1
                if self.wp >= len(self.route):
                    self.set_phase(sim, "approach")
        elif ph == "approach":
            # to the hover point over the pad: the speed bleeds off as sqrt(2 a d) and the height
            # follows the glide path to the hover height
            d = math.hypot(self.pad[0] - m["north_m"], self.pad[1] - m["east_m"])
            u_des = min(self.v_route, math.sqrt(2.0 * self.decel * max(d - 8.0, 0.0)))
            lon, lat, ped, d, brg, fwd = self._fly_to(sim, self.pad, u_des, dt, bank=15.0)
            self._u_cmd = min(self._u_cmd, u_des)
            h_c = min(m["alt_m"] + 1.0, H_HOVER + d * math.tan(GLIDE))
            coll = self._collective(m, self._vs_for(m, h_c, 1.0, -3.0), dt)
            if fwd < 8.0:
                # slow: the heading on the pedals, the bank no longer turns the helicopter
                ped = clamp(0.03 * wrap180(brg - m["psi_deg"]), -0.3, 0.3) if d > 15.0 else 0.0
            if d < 12.0 and fwd < 3.0:
                self._hdg = m["psi_deg"]
                self._hold = self.pad
                self.set_phase(sim, "hover_pad")
        elif ph == "hover_pad":
            lon, lat, ped = self._hover_hold(sim, self.pad, self._hdg)
            coll = self._collective(m, self._vs_for(m, H_HOVER, 1.0, -1.0), dt)
            gn, ge, _ = ground_velocity(m)
            d = math.hypot(self.pad[0] - m["north_m"], self.pad[1] - m["east_m"])
            if self.t_phase > self.t_check and d < 2.0 and math.hypot(gn, ge) < 0.5:
                self.set_phase(sim, "descend")
        elif ph == "descend":
            lon, lat, ped = self._hover_hold(sim, self.pad, self._hdg)
            h = m["alt_m"] - H_GEAR
            vs_c = -0.8 if h > 0.8 else -0.35
            coll = self._collective(m, vs_c, dt)
            if m["wow"] > 0.5:
                self.set_phase(sim, "landed")
        elif ph == "landed":
            # the collective down (slowly: the SCAS fades out with the weight on the wheels)
            self._coll = max(0.0, (self._coll or 0.0) - 0.15 * dt)
            coll = self._coll
        sim.set_controls(collective=coll, cyclic_lon=lon, cyclic_lat=lat, pedals=ped)


@dataclass
class Leg:
    start: int                     # index into starts.json
    duration: float                # s of sim time
    pilot: dict                    # Pilot(**pilot)
    views: list[tuple[float, str]] = field(default_factory=lambda: [(0.0, "chase")])
    captions: list[tuple[float, float, str]] = field(default_factory=list)


@dataclass
class Script:
    name: str
    legs: list[Leg]

    @property
    def duration(self) -> float:
        return sum(leg.duration for leg in self.legs)


SCRIPTS = {
    # from the pad: the lift-off, the hover check and the transition (the headless smoke test)
    "smoke": Script("smoke", [Leg(0, 40.0, {"phase": "parked"}, views=[(0.0, "chase"), (20.0, "cockpit")])]),
    # the full circuit from the pad: take-off, hover, transition, a rectangular circuit at 100 m
    # and 60 kt, the approach, the hover over the pad and the landing
    "circuit": Script("circuit", [Leg(0, 300.0, {"phase": "parked"}, views=[(0.0, "chase")])]),
    # the approach from the short final and the landing on the pad
    "landing": Script("landing", [Leg(3, 70.0, {"phase": "approach", "route": ()})]),
    # the video: take-off, hover and transition from the pad; then (a new start) the approach
    # from the short final, the hover and the landing
    "demo": Script("demo", [
        Leg(0, 22.0, {"phase": "parked", "t_parked": 1.0, "t_hover": 3.0},
            views=[(0.0, "chase"), (11.0, "ground"), (16.0, "chase")],
            captions=[(0.0, 3.0, "a109-sim FMU: AgustaWestland A109 on helipad H, rotor at 100 %"),
                      (3.0, 7.5, "collective up: lift-off, the SCAS engages as the gear unloads"),
                      (7.5, 11.0, "hover check at 5 m over the pad"),
                      (11.0, 16.0, "ground view: the transition, nose down"),
                      (16.0, 22.0, "accelerating and climbing out through translational lift")]),
        Leg(7, 36.0, {"phase": "approach", "route": (), "v_route": 11.0, "decel": 0.6, "t_check": 2.5},
            views=[(0.0, "chase"), (9.0, "cockpit"), (17.0, "chase"), (23.0, "ground"), (31.0, "chase")],
            captions=[(0.0, 4.0, "short final: 20 kt, 15 m, 150 m south of the pad"),
                      (4.0, 9.0, "the approach on a 7 deg path, the speed bleeding off"),
                      (9.0, 17.0, "cockpit view: the hover display shows the drift over the ground"),
                      (17.0, 23.0, "hover over the pad, then the vertical descent"),
                      (23.0, 31.0, "ground view: the descent and the touchdown on the H"),
                      (31.0, 36.0, "on the gear: collective down, the SCAS fades out")]),
    ]),
}
