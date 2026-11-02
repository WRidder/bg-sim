"""SI version of the c172p data for the bg-sim model and the scipy reference.

Body frame (as in the bg-sim model): origin at the centre of gravity, x forward, y left, z up
(FLU). The JSBSim structural frame is x aft, y right, z up in inches, so a station s maps to
b = ((x_cg - s_x), (y_cg - s_y), (s_z - z_cg)) * 0.0254.

Loading (the "POH gross" case every check uses): JSBSim's empty aircraft (1500 lb at its CG, with
its inertia tensor) plus point masses at JSBSim's stations, adding up to the 2400 lb maximum
weight: pilot and front passenger 170 lb each, two rear passengers 155 lb each, 125 lb of fuel in
each wing tank, no baggage. JSBSim adds point masses the same way (parallel-axis terms only).
"""

from __future__ import annotations

import math

import numpy as np

import c172_data as D

IN = 0.0254
FT = 0.3048
LB = 0.45359237                  # lbm -> kg
LBF = 4.4482216152605            # lbf -> N
SLUG = 14.593902937206364
SLUGFT2 = SLUG * FT * FT
HP = 745.69987158227022          # mechanical horsepower, W
INHG = 3386.38                   # Pa per inHg (FGJSBBase inhgtopa)
G0 = 9.80665
DEG = math.pi / 180.0

S = D.WING_AREA_FT2 * FT * FT    # 16.165 m^2
B = D.WING_SPAN_FT * FT          # 10.912 m
CBAR = D.CHORD_FT * FT           # 1.4935 m

LOADING_LB = {  # station: weight (lb)
    "pilot": 170.0, "copilot": 170.0, "left_passenger": 155.0, "right_passenger": 155.0,
    "baggage": 0.0, "left_tank": 125.0, "right_tank": 125.0,
}


def loading(load: dict | None = None):
    """Mass (kg), CG (structural, in) and the inertia tensor about the CG in FLU (kg m^2)."""
    load = LOADING_LB if load is None else load
    stations = {**D.POINT_MASS_STATIONS_IN, **D.TANK_STATIONS_IN}
    items = [(D.EMPTY_WEIGHT_LB, np.array(D.CG_EMPTY_IN))]
    items += [(w, np.array(stations[k])) for k, w in load.items() if w > 0.0]
    w_tot = sum(w for w, _ in items)
    cg = sum(w * p for w, p in items) / w_tot
    m = w_tot * LB

    def to_body(p):
        return np.array([cg[0] - p[0], cg[1] - p[1], p[2] - cg[2]]) * IN

    J = np.diag([D.IXX_SLUGFT2, D.IYY_SLUGFT2, D.IZZ_SLUGFT2]) * SLUGFT2   # the empty tensor
    for w, p in items:
        r = to_body(p)
        J += w * LB * (np.dot(r, r) * np.eye(3) - np.outer(r, r))
    return m, cg, J


MASS, CG_IN, J_FULL = loading()
# The point masses add a small Ixz (the tanks sit above the CG, the rear seats behind it). The
# bg-sim RigidBody3D takes principal moments; the principal x axis is tilted by EPS about y.
EPS = 0.5 * math.atan2(2.0 * J_FULL[0, 2], J_FULL[2, 2] - J_FULL[0, 0])


def body(p_in) -> np.ndarray:
    """A structural station (in) in the body frame (FLU about the CG, m)."""
    return np.array([CG_IN[0] - p_in[0], CG_IN[1] - p_in[1], p_in[2] - CG_IN[2]]) * IN


R_AERO = body(D.AERORP_IN)       # aerodynamic reference point
R_PROP = body(D.THRUSTER_IN)     # propeller hub
R_EYE = body(D.EYEPOINT_IN)
GEAR = {k: {**v, "r": body(v["loc"]), "k_si": v["k"] * LBF / FT, "b_si": v["b"] * LBF / FT}
        for k, v in D.GEAR.items()}
STRUCT = {k: body(v) for k, v in D.STRUCTURE_IN.items()}

# ---- propulsion
PROP_D = D.PROP["diameter_in"] * IN
PROP_J = D.PROP["ixx_slugft2"] * SLUGFT2      # crank + propeller about the shaft
E = D.ENGINE
ED = D.ENGINE_DEFAULTS
DISPLACEMENT = E["displacement_in3"] * IN ** 3                       # m^3
STROKE_FT = ED["stroke_in"] / 12.0
RATED_MPS_FPS = E["maxrpm"] * ED["stroke_in"] / 360.0              # mean piston speed at max rpm
MAXMAP = E["maxmp_inhg"] * INHG
MINMAP = E["minmp_inhg"] * INHG
Z_AIRBOX = (ED["standard_pressure_pa"] * (ED["peak_piston_speed_fps"] / RATED_MPS_FPS) / MAXMAP
            - ED["peak_piston_speed_fps"] / RATED_MPS_FPS)
Z_THROTTLE = ((ED["peak_piston_speed_fps"] / (E["idlerpm"] * ED["stroke_in"] / 360.0))
              * (ED["standard_pressure_pa"] / MINMAP - 1.0) - Z_AIRBOX)

# ---- the ISA troposphere (JSBSim's standard atmosphere below 11 km)
T0 = 288.15
P0 = 101325.0
LAPSE = 0.0065
R_GAS = 287.0531             # J/(kg K): JSBSim's Reng 1716.56 ft lbf/(slug R)
GAMMA = 1.4


def atmosphere(h):
    T = T0 - LAPSE * h
    p = P0 * (T / T0) ** (G0 / (LAPSE * R_GAS))
    return T, p, p / (R_GAS * T), math.sqrt(GAMMA * R_GAS * T)


RHO0 = P0 / (R_GAS * T0)
A0 = math.sqrt(GAMMA * R_GAS * T0)
