"""Scripted pilots for the headless runs and the video: closed-loop, deterministic functions of
the FMU's outputs (no randomness, so a run is reproducible to the bit).

``Pilot`` flies by phases, as a pilot flies a circuit: the take-off roll on the centre line, the
rotation, the climb at the best-rate speed, the turns and the legs of a left-hand circuit for
runway 36, the approach on a 3 deg glide path, the flare, the landing roll and the braking. A
script is a list of legs: each starts the FMU at one of the start conditions and lets the pilot
fly from the phase that fits it.

The inner loops are those of the model's demo pilot (examples/cessna/library/DemoPilot.jl):
pitch attitude with pitch-rate damping on the yoke, bank with roll-rate damping on the yoke, a
heading loop on the bank, a yaw damper (and on the ground the heading and centre-line hold) on
the pedals. The rates are differences of the attitude between steps (the FMU outputs angles).
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field

from .core import RUNWAY_X0, Simulation, wrap180

KT = 0.514444
FT = 0.3048
X_AIM = 120.0                   # m north: the aiming point (150 m past the threshold)
GLIDE = math.radians(3.0)


def clamp(v, lo, hi):
    return lo if v < lo else hi if v > hi else v


@dataclass
class Pilot:
    """A closed-loop pilot. ``phase`` is where it is in the circuit; ``circuit_ft`` the circuit
    height above the runway."""

    phase: str = "roll"
    circuit_ft: float = 700.0
    v_climb: float = 75.0          # KIAS
    v_circuit: float = 90.0
    v_approach: float = 65.0
    thr_cruise: float = 0.78       # about 90 KIAS level (the trim of the downwind start)
    thr_approach: float = 0.68     # flaps 30, 65 KIAS, 3 deg (the trim of the final start)
    use_autopilot: bool = True
    turn_after: float = 1e9        # s: from the roll, end the climb with a turn to `turn_hdg` at this time
    turn_hdg: float = 270.0
    t_phase: float = 0.0
    log: list = field(default_factory=list)
    _prev: tuple | None = None
    _rates: tuple = (0.0, 0.0, 0.0)
    _xi: float = 0.0
    _thc: float = 0.0

    def set_phase(self, sim: Simulation, phase: str) -> None:
        if phase != self.phase:
            self.log.append((round(sim.model.time, 2), phase))
            self.phase = phase
            self.t_phase = 0.0

    # ---- inner loops
    def _rates_of(self, sim: Simulation) -> tuple[float, float, float]:
        m = sim.model
        now = (m["phi_deg"], m["theta_deg"], m["psi_deg"])
        if self._prev is not None:
            dt = m.step_size
            raw = [(now[0] - self._prev[0]) / dt, (now[1] - self._prev[1]) / dt, wrap180(now[2] - self._prev[2]) / dt]
            a = 0.3     # a light filter (the differences of 5 ms steps)
            self._rates = tuple(r0 + a * (r1 - r0) for r0, r1 in zip(self._rates, raw))
        self._prev = now
        return self._rates

    def _att(self, target: float, dt: float, rate: float = 1.5) -> float:
        """The pitch attitude command, moved towards `target` at most `rate` deg/s."""
        self._thc += clamp(target - self._thc, -rate * dt, rate * dt)
        return self._thc

    def _climb_attitude(self, v: float, agl_ft: float) -> float:
        """The climb attitude: about 6.5 deg holds the best-rate speed; lower when slow, but not
        below 6 deg close to the ground (no sinking back after the lift-off)."""
        th = clamp(6.5 + 0.8 * (v - self.v_climb), 4.5, 10.0)
        return max(th, 6.0) if agl_ft < 60.0 else th

    def _pitch(self, theta_c_deg: float, theta: float, q: float) -> float:
        return 0.175 * (theta_c_deg - theta) - 0.035 * q

    def _roll(self, phi_c_deg: float, phi: float, p: float) -> float:
        return clamp(0.035 * (phi_c_deg - phi) - 0.005 * p, -0.6, 0.6)

    def _bank_for(self, hdg_c: float, psi: float, limit: float = 20.0) -> float:
        return clamp(1.2 * wrap180(hdg_c - psi), -limit, limit)

    # ---- the circuit
    def __call__(self, sim: Simulation) -> None:
        m = sim.model
        dt = m.step_size
        self.t_phase += dt
        p, q, r = self._rates_of(sim)
        phi, theta, psi = m["phi_deg"], m["theta_deg"], m["psi_deg"]
        v, agl_ft = m["kias"], m["agl_ft"]
        north, east = m["north_m"], m["east_m"]
        h_c = self.circuit_ft * FT
        ph = self.phase
        yoke = roll = ped = 0.0
        thr = sim.u[3]
        brake = 0.0
        if ph == "roll":                                   # full power, centre line, rotate at 50 KIAS
            thr = clamp(self.t_phase / 2.0, 0.0, 1.0)
            ped = clamp(-0.06 * wrap180(psi) - 0.04 * r - 0.03 * east, -1, 1)
            roll = self._roll(0.0, phi, p)
            yoke = -0.05
            if v > 50.0:
                self.set_phase(sim, "rotate")
        elif ph == "rotate":
            thr = 1.0
            if self.t_phase <= dt:
                self._thc = theta
            yoke = self._pitch(self._att(8.0, dt, 3.0), theta, q)
            ped = clamp(-0.06 * wrap180(psi) - 0.04 * r, -1, 1) if m["on_ground"] > 0.5 else -0.01 * r
            roll = self._roll(0.0, phi, p)
            if agl_ft > 15.0:
                self.set_phase(sim, "climb")
        elif ph == "climb":                                # best-rate climb, flaps up at 300 ft
            thr = 1.0
            th_c = self._climb_attitude(v, agl_ft)
            yoke = self._pitch(self._att(th_c, dt), theta, q)
            hdg_c = 0.0
            if agl_ft > 300.0:
                sim.u[5] = 0.0
            roll = self._roll(self._bank_for(hdg_c - 0.03 * east if abs(wrap180(psi)) < 30 else hdg_c, psi), phi, p)
            ped = -0.01 * r
            if m.time > self.turn_after:
                self.set_phase(sim, "turn_out")
            elif agl_ft > 0.75 * self.circuit_ft and north > RUNWAY_X0 + 1300.0:
                self.set_phase(sim, "crosswind")
        elif ph == "turn_out":                             # the demo: climb on, turn to turn_hdg
            thr = 1.0
            th_c = self._climb_attitude(v, agl_ft)
            yoke = self._pitch(self._att(th_c, dt), theta, q)
            roll = self._roll(self._bank_for(self.turn_hdg, psi), phi, p)
            ped = -0.01 * r
            if agl_ft > 300.0:
                sim.u[5] = 0.0
        elif ph == "crosswind":                            # climb to circuit height, turn left to 270
            hdg_c = 270.0
            thr = 1.0 if m["alt_m"] < h_c - 10.0 else self.thr_cruise
            th_c = self._climb_attitude(v, agl_ft) if m["alt_m"] < h_c - 10.0 else \
                clamp(2.0 + 0.04 * (h_c - m["alt_m"]) / FT, -3.0, 8.0)
            yoke = self._pitch(self._att(th_c, dt), theta, q)
            roll = self._roll(self._bank_for(hdg_c, psi), phi, p)
            ped = -0.01 * r
            if -east > 900.0:
                self.set_phase(sim, "downwind")
        elif ph == "downwind":                             # level at circuit height, heading 180, the autopilot
            thr = self.thr_cruise
            if self.use_autopilot:
                if self.t_phase < 2 * dt:
                    sim.ap(roll_mode=2, alt_mode=1, hdg=180.0, alt=h_c + 1.25)
                yoke, roll = 0.0, 0.0
            else:
                yoke = self._pitch(clamp(2.0 + 0.04 * (h_c - m["alt_m"]) / FT, -3.0, 8.0), theta, q)
                roll = self._roll(self._bank_for(180.0, psi), phi, p)
            ped = -0.01 * r
            if north < RUNWAY_X0 - 1700.0:
                sim.ap(roll_mode=0, alt_mode=0)
                sim.u[5] = 2.0
                self.set_phase(sim, "base")
        elif ph == "base":                                 # flaps 20, descend at 70 KIAS, turn left to 090
            thr = 0.18
            th_c = clamp(-2.0 + 1.5 * (v - 70.0), -8.0, 6.0)
            yoke = self._pitch(self._att(th_c, dt), theta, q)
            roll = self._roll(self._bank_for(90.0, psi), phi, p)
            ped = -0.01 * r
            if east > -420.0:
                sim.u[5] = 3.0
                self.set_phase(sim, "final")
        elif ph in ("final", "flare", "landed"):
            self._final(sim, v, agl_ft, north, east, phi, theta, psi, p, q, r)
            return
        sim.set_controls(yoke_pitch=yoke, yoke_roll=roll, pedals=ped, throttle=thr, brake_l=brake, brake_r=brake)

    def _final(self, sim, v, agl_ft, north, east, phi, theta, psi, p, q, r) -> None:
        m = sim.model
        ph = self.phase
        brake = 0.0
        if ph == "final":                                  # 3 deg to the aiming point, 65 KIAS, flaps 30
            hdg_c = clamp(-0.06 * east - 0.0, -25.0, 25.0)  # back to the centre line (east positive: turn left)
            roll = self._roll(self._bank_for(hdg_c, psi, 20.0), phi, p)
            h_gp = max(0.0, (X_AIM - north) * math.tan(GLIDE))
            agl = agl_ft * FT
            vs_gp = -v * KT * math.sin(GLIDE) / FT * 60.0
            th_c = clamp(-1.0 + 0.6 * (h_gp - agl) + 0.006 * (vs_gp - m["vs_fpm"]), -7.0, 7.0)
            yoke = self._pitch(th_c, theta, q)
            self._xi = clamp(self._xi + m.step_size * (self.v_approach - v), -40.0, 40.0)
            thr = clamp(self.thr_approach + 0.06 * (self.v_approach - v) + 0.01 * self._xi, 0.0, 1.0)
            ped = -0.01 * r
            if agl_ft < 22.0:
                self.set_phase(sim, "flare")
        elif ph == "flare":                                # idle, pitch up to hold a small sink rate
            thr = 0.0
            vs_c = -(60.0 + 5.0 * agl_ft)
            th_c = clamp(theta + 0.02 * (vs_c - m["vs_fpm"]), -2.0, 9.0)
            yoke = self._pitch(th_c, theta, q)
            roll = self._roll(0.0, phi, p)
            ped = clamp(-0.06 * wrap180(psi) - 0.02 * r, -1, 1)
            if m["on_ground"] > 0.5 and sim.ground_time > 0.3:
                self.set_phase(sim, "landed")
        else:                                              # landing roll: nose down, centre line, brakes
            thr = 0.0
            yoke = self._pitch(0.0, theta, q) if self.t_phase < 2.0 else 0.2
            roll = self._roll(0.0, phi, p)
            ped = clamp(-0.06 * wrap180(psi) - 0.04 * r - 0.03 * east, -1, 1)
            brake = clamp((self.t_phase - 2.0) / 3.0, 0.0, 0.7) if v > 3.0 else 0.4
            sim.u[5] = 0.0 if self.t_phase > 3.0 else sim.u[5]
        sim.set_controls(yoke_pitch=yoke, yoke_roll=roll, pedals=ped, throttle=thr, brake_l=brake, brake_r=brake)


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
    # 30 s of take-off roll, rotation and lift-off: the headless smoke test
    "smoke": Script("smoke", [Leg(0, 40.0, {"phase": "roll"}, views=[(0.0, "chase"), (20.0, "cockpit")])]),
    # the full left-hand circuit of runway 36 at 700 ft, the autopilot on downwind, the landing
    # (touchdown at about 415 s)
    "circuit": Script("circuit", [Leg(0, 440.0, {"phase": "roll"}, views=[(0.0, "chase")])]),
    # the approach from 2 nm and the landing (touchdown at about 106 s)
    "landing": Script("landing", [Leg(2, 125.0, {"phase": "final"})]),
    # the video: take-off, climb and a turn; then (a new start) the final approach and the landing
    "demo": Script("demo", [
        Leg(0, 115.0, {"phase": "roll", "turn_after": 80.0, "turn_hdg": 300.0},
            views=[(0.0, "chase"), (14.0, "tower"), (40.0, "chase"), (62.0, "cockpit"), (80.0, "chase")],
            captions=[(0.0, 5.0, "cessna-sim FMU: Cessna 172P on runway 36, full power, flaps 10"),
                      (14.0, 40.0, "tower view: the take-off roll, rotation at 50 KIAS"),
                      (40.0, 62.0, "lift-off at 55 KIAS, climb-out at full power"),
                      (62.0, 80.0, "cockpit view: the six-pack in the climb"),
                      (80.0, 115.0, "a climbing left turn to 300, flaps up at 300 ft")]),
        Leg(2, 125.0, {"phase": "final"},
            views=[(0.0, "chase"), (35.0, "cockpit"), (75.0, "chase"), (92.0, "tower"), (112.0, "chase")],
            captions=[(0.0, 6.0, "final approach, 2 nm: flaps 30, 65 KIAS, 3 deg glide path"),
                      (35.0, 75.0, "cockpit view: on the glide path to runway 36"),
                      (75.0, 92.0, "short final"),
                      (92.0, 112.0, "tower view: flare and touchdown"),
                      (112.0, 125.0, "landing roll, brakes")]),
    ]),
}
