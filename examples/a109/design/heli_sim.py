"""The flyable A109 (model a109-sim): rigging, SCAS and the demonstration pilot, as the library
blocks `Rigging`, `Scas` and `DemoPilot` compute them, on the SI model of heli_si.py.

Everything here is ours: the report has no control system. Units: sticks are -1 .. 1 (collective
0 .. 1), angles in deg inside the laws, rates in deg/s, speeds in m/s.

* Rigging: the percent-of-travel mapping fitted to the report's control-position charts
  (design.py, a109_trims): percent = a + b * angle per axis. Collective 0..1 is 0..100 % "from
  full down", longitudinal +1 is full forward (100 % "from full rearward"), lateral +1 full right
  (100 % "from full left"), pedals +1 full right (0 % "left pedal from full rearward").
* SCAS (scas = 1): attitude command / attitude hold in pitch and roll, yaw-rate command / heading
  hold, with turn coordination above 10 m/s; trim feedforward over the forward airspeed from the
  trim sweep (Lookup1D tables), PI on the attitude and yaw-rate errors, rate damping. With
  scas = 0 the sticks drive the swashplate and the tail rotor through the rigging alone.
* Switches: the flyable model runs the airframe with smooth = 1 (heli_si.SM_*): the report's
  hard switches (fin stall in particular, near |va| = 0.3 u at 40 .. 55 kt) make the closed loop
  slide along them (chatter, the integrator stalls); the blend removes that.
* DemoPilot: the outer loops that fly the demonstration (hover, transition, coordinated turn,
  deceleration, hover) by stick, from a schedule of speed, height and bank over time; with
  demo = 0 it holds the hover sticks. In the FMU the host replaces it (export markers).
"""

from __future__ import annotations

import math

import numpy as np

import heli_si as HS

G0 = HS.G0
D = math.degrees
R2D = 180.0 / math.pi

# SCAS (ours)
K_THETA_STICK = 15.0     # deg of pitch per full stick
K_PHI_STICK = 30.0       # deg of bank per full stick
K_R_STICK = 30.0         # deg/s of yaw rate per full pedal
GAINS = {"Kth": 0.6, "Kq": 0.25, "Kith": 0.3, "Kph": 0.35, "Kp": 0.12, "Kiph": 0.15, "Kr": 0.8, "Kir": 0.6}
V_TC = (10.0, 20.0)      # m/s: turn coordination fades in over this airspeed band

# The demonstration (ours): (t s, forward speed m/s, height m, bank deg)
DEMO = [(0.0, 0.0, 15.0, 0.0), (5.0, 0.0, 15.0, 0.0), (25.0, 36.0, 45.0, 0.0), (35.0, 36.0, 45.0, 0.0),
        (38.0, 36.0, 45.0, 20.0), (64.0, 36.0, 45.0, 20.0), (67.0, 36.0, 45.0, 0.0), (75.0, 36.0, 45.0, 0.0),
        (100.0, 0.0, 15.0, 0.0), (120.0, 0.0, 15.0, 0.0)]
DEMO_T_END = 120.0
PILOT = {"Ku": 0.6, "Kv": 1.2, "Kh": 0.012, "Khd": 0.03}    # deg per m/s; collective fraction per m and per m/s


def schedule(t):
    ts, us, hs, phis = zip(*DEMO)
    return float(np.interp(t, ts, us)), float(np.interp(t, ts, hs)), float(np.interp(t, ts, phis))


class FF:
    """Trim feedforward tables over the forward airspeed (body u, m/s): theta, phi, coll (deg), B1, A1,
    thtr (deg); the breakpoints straddle the switch of the dihedral magnification at VTRANS."""

    def __init__(self, h: HS.Heli, alt=15.0):
        s = h.s
        vt = s["VTRANS"]
        self.u = [0.0, 3.0, 6.0, 9.0, 12.0, vt - 0.05, vt + 0.05, 18.0, 22.0, 26.0, 30.0, 36.0, 42.0, 48.0, 55.0]
        rows = []
        g = None
        for u in self.u:
            x, c, o = HS.trim(h, vn=u, alt=alt, guess=g)
            g = np.r_[c, x[HS.ITH], x[HS.IPHI], x[HS.IA1], x[HS.IB1]]
            rows.append([D(x[HS.ITH]), D(x[HS.IPHI]), D(c[0]), D(c[1]), D(c[2]), D(c[3])])
        rows = np.array(rows)
        self.tab = {k: list(rows[:, i]) for i, k in enumerate(("theta", "phi", "coll", "B1", "A1", "thtr"))}

    def __call__(self, key, u):
        return float(np.interp(u, self.u, self.tab[key]))


class Rig:
    def __init__(self, rig: dict):
        self.r = rig

    def deg(self, ax, pct):
        return (pct - self.r[ax]["a"]) / self.r[ax]["b"]

    def pct(self, ax, deg):
        return self.r[ax]["a"] + self.r[ax]["b"] * deg

    def direct(self, coll, lon, lat, ped):
        return (self.deg("coll", 100 * coll), self.deg("lon", 50 + 50 * lon), self.deg("lat", 50 + 50 * lat),
                self.deg("ped", 50 - 50 * ped))

    def sticks(self, th0, B1, A1, thtr):
        return (self.pct("coll", th0) / 100, (self.pct("lon", B1) - 50) / 50, (self.pct("lat", A1) - 50) / 50,
                (50 - self.pct("ped", thtr)) / 50)


def blend(u):
    return min(max((u - V_TC[0]) / (V_TC[1] - V_TC[0]), 0.0), 1.0)


def scas_law(ff: FF, sticks, st, xi, scas=1.0, gains=GAINS):
    """sticks (coll, lon, lat, ped); st: dict of u, theta, phi (deg), p, q, r (deg/s, FRD);
    xi = (xth, xph, xr) the integrators (deg). Returns the control angles (deg) and xi'."""
    k = gains
    coll, lon, lat, ped = sticks
    u = st["u"]
    th_cmd = ff("theta", u) - K_THETA_STICK * lon
    ph_cmd = ff("phi", u) + K_PHI_STICK * lat
    sig = blend(u)
    r_tc = sig * G0 * math.tan(math.radians(st["phi"])) / max(u, 5.0) * R2D
    r_cmd = K_R_STICK * ped + r_tc
    e_th = st["theta"] - th_cmd
    e_ph = ph_cmd - st["phi"]
    e_r = st["r"] - r_cmd
    B1 = ff("B1", u) + k["Kth"] * e_th + k["Kq"] * st["q"] + xi[0]
    A1 = ff("A1", u) + k["Kph"] * e_ph - k["Kp"] * st["p"] + xi[1]
    thtr = ff("thtr", u) + k["Kr"] * e_r + xi[2]
    dxi = (scas * k["Kith"] * e_th, scas * k["Kiph"] * e_ph, scas * k["Kir"] * e_r)
    return (B1, A1, thtr), dxi


def pilot_law(ff: FF, rig: Rig, t, st, demo=1.0, scas=1.0, hover_sticks=(0.5, 0.0, 0.0, 0.0), p=PILOT):
    """The demonstration pilot: sticks from the schedule. st: u, v (m/s), h, hdot (m), theta, phi
    (deg). With demo = 0: the hover sticks (SCAS on: zero cyclic and pedal)."""
    u_cmd, h_cmd, ph_turn = schedule(t)
    u = st["u"]
    sig = blend(u)
    lon = -p["Ku"] * (u - u_cmd) / K_THETA_STICK
    ph_des = sig * ph_turn - (1 - sig) * p["Kv"] * st["v"]
    lat = ph_des / K_PHI_STICK
    coll = rig.pct("coll", ff("coll", u)) / 100 + p["Kh"] * (h_cmd - st["h"]) - p["Khd"] * st["hdot"]
    lon = min(max(lon, -1.0), 1.0)
    lat = min(max(lat, -1.0), 1.0)
    hs = hover_sticks if scas < 0.5 else (hover_sticks[0], 0.0, 0.0, 0.0)
    return (demo * coll + (1 - demo) * hs[0], demo * lon + (1 - demo) * hs[1], demo * lat + (1 - demo) * hs[2],
            (1 - demo) * hs[3])


class Sim:
    """The closed loop: state = heli_si state + (xth, xph, xr)."""

    def __init__(self, h: HS.Heli, rig: dict, scas=1.0, demo=1.0, alt=15.0, offsets=None):
        self.h = h
        self.ff = FF(h, alt)
        self.rig = Rig(rig)
        self.scas = scas
        self.demo = demo
        self.offsets = offsets or {}
        x0, c0, _ = HS.trim(h, alt=alt)
        self.x0 = np.r_[x0, 0.0, 0.0, 0.0]
        self.hover_sticks = self.rig.sticks(*np.degrees(c0))

    def state(self, x):
        o_u = x[HS.IU:HS.IW + 1]
        return {"u": o_u[0], "v": o_u[1], "h": -x[HS.IZD], "hdot": HS.climb_rate(x), "theta": D(x[HS.ITH]),
                "phi": D(x[HS.IPHI]), "p": D(x[HS.IP]), "q": D(x[HS.IQ]), "r": D(x[HS.IR])}

    def controls(self, t, x):
        st = self.state(x)
        sticks = list(pilot_law(self.ff, self.rig, t, st, self.demo, self.scas, self.hover_sticks))
        for i, key in enumerate(("coll", "lon", "lat", "ped")):
            if key in self.offsets and t >= self.offsets.get("t", 1.0):
                sticks[i] += self.offsets[key]
        direct = self.rig.direct(*sticks)
        (B1, A1, thtr), dxi = scas_law(self.ff, sticks, st, x[HS.NX:HS.NX + 3], self.scas)
        ang = (direct[0], self.scas * B1 + (1 - self.scas) * direct[1], self.scas * A1 + (1 - self.scas) * direct[2],
               self.scas * thtr + (1 - self.scas) * direct[3])
        return np.radians(ang), dxi, sticks

    def deriv(self, t, x):
        c, dxi, _ = self.controls(t, x)
        xd, _ = self.h.deriv(x[:HS.NX], c)
        return np.r_[xd, dxi]

    def run(self, t_end, dt=0.01, rtol=1e-9, atol=1e-9, max_step=0.02):
        """LSODA on the grid 0, dt, .. t_end, restarted at the step of the stick offsets (inputs
        clamped to each segment, so the step is not smeared over a solver step)."""
        from scipy.integrate import solve_ivp
        ts = np.linspace(0.0, t_end, int(round(t_end / dt)) + 1)
        t_off = self.offsets.get("t", 1.0) if self.offsets else None
        edges = [0.0] + ([t_off] if t_off is not None and 0.0 < t_off < t_end else []) + [t_end]
        x = self.x0
        T, X = [], []
        for k, (a, b) in enumerate(zip(edges, edges[1:])):
            grid = ts[(ts > a + 1e-12) & (ts <= b + 1e-12)]
            if k == 0:
                grid = np.r_[0.0, grid]
            if grid[-1] < b - 1e-12:
                grid = np.r_[grid, b]

            def f(t, y, a=a, b=b):
                return self.deriv(min(max(t, a + 1e-9), b - 1e-9), y)
            sol = solve_ivp(f, (a, b), x, method="LSODA", t_eval=grid, rtol=rtol, atol=atol, max_step=max_step)
            if not sol.success:
                raise RuntimeError(sol.message)
            x = sol.y[:, -1]
            keep = np.isin(sol.t, ts)
            T.append(sol.t[keep])
            X.append(sol.y.T[keep])
        return np.concatenate(T), np.concatenate(X)
