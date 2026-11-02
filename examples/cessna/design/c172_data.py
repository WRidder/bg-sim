"""Cessna 172P flight-model data, transcribed from JSBSim's c172p (JSBSim/FlightGear).

Source and attribution
----------------------
JSBSim Flight Dynamics Model, https://github.com/JSBSim-Team/jsbsim (branch master, read in
November 2026):

* ``aircraft/c172p/c172p.xml`` (fdm_config "c172", version 2.0, $Id: c172p.xml,v 1.29 2013/10/25
  jentron): metrics, mass balance, ground reactions, flight-control surface limits, the flap
  traverse and the complete aerodynamic build-up;
* ``engine/eng_io320.xml`` (Ron Jensen): the 160 hp Lycoming IO-320 piston engine;
* ``engine/prop_75in2f.xml``: the fixed-pitch 75-inch two-blade propeller;
* ``src/models/propulsion/FGPiston.cpp``, ``FGPropeller.cpp``, ``src/models/FGLGear.cpp``: the
  equations these numbers go into, and the defaults the engine file does not override (bore,
  stroke, compression ratio, friction mean effective pressures, the mixture efficiency table and
  the side-force magic-formula factors).

Licence: the JSBSim repository is distributed under the GNU Lesser General Public License,
version 2.1 (its ``COPYING``). ``c172p.xml`` carries no licence of its own; its header says the
model "was created using publicly available data, publicly available technical reports,
textbooks, and guesses", contains no proprietary or restricted data, is meant for educational and
entertainment purposes only, is not endorsed by the manufacturer and "is not to be sold". The
numbers below are transcribed (not the files) under the LGPL-2.1, with this attribution; this
file is a derivative of that data and is distributed under the same licence.

Most stability and control derivatives of the c172p are those of the Cessna 182 in J. Roskam,
*Airplane Flight Dynamics and Automatic Flight Controls* (Appendix B, Airplane A): S = 174 ft^2,
b = 35.8 ft, cbar = 4.9 ft, Ixx/Iyy/Izz = 948/1346/1967 slug ft^2, CLq 3.9, CLadot 1.7, Cmq -12.4,
Cmadot -7.27, Cmde -1.122, Clp -0.484, Clda 0.229, Cnr -0.0937, CYdr 0.187 ...

Units are JSBSim's (ft, in, lb, slug ft^2, deg or rad as named); ``c172_si.py`` converts.
Structural frame (JSBSim): x aft, y right, z up, in inches from the Cessna datum (the front face
of the firewall: the baggage arm 95 in and the MAC 58.8 in match the type certificate data).
"""

from __future__ import annotations

# --------------------------------------------------------------------------- metrics
WING_AREA_FT2 = 174.0
WING_SPAN_FT = 35.8
CHORD_FT = 4.9
HTAIL_AREA_FT2 = 21.9
HTAIL_ARM_FT = 15.7
VTAIL_AREA_FT2 = 16.5
AERORP_IN = (43.2, 0.0, 59.4)
EYEPOINT_IN = (37.0, 0.0, 48.0)
VRP_IN = (42.6, 0.0, 38.5)

# --------------------------------------------------------------------------- mass balance
IXX_SLUGFT2 = 948.0
IYY_SLUGFT2 = 1346.0
IZZ_SLUGFT2 = 1967.0
EMPTY_WEIGHT_LB = 1500.0
CG_EMPTY_IN = (41.0, 0.0, 36.5)
# JSBSim's point masses (name: weight lb in c172p.xml, location in)
POINT_MASS_STATIONS_IN = {
    "pilot": (36.0, -14.0, 24.0),
    "copilot": (36.0, 14.0, 24.0),
    "left_passenger": (70.0, -14.0, 24.0),
    "right_passenger": (70.0, 14.0, 24.0),
    "baggage": (95.0, 0.0, 24.0),
}
TANK_STATIONS_IN = {"left_tank": (56.0, -112.0, 59.4), "right_tank": (56.0, 112.0, 59.4)}
TANK_CAPACITY_LB = 185.0

# --------------------------------------------------------------------------- ground reactions
# name: location (in), static, dynamic, rolling friction, spring (lb/ft), damping (lb/ft/s),
# max steer (deg), brake group
GEAR = {
    "nose": {"loc": (-6.8, 0.0, -19.5), "mu_s": 0.8, "mu_d": 0.5, "mu_r": 0.02,
             "k": 1800.0, "b": 600.0, "steer": 10.0, "brake": None},
    "left": {"loc": (58.2, -43.0, -15.5), "mu_s": 0.8, "mu_d": 0.5, "mu_r": 0.02,
             "k": 5400.0, "b": 1600.0, "steer": 0.0, "brake": "left"},
    "right": {"loc": (58.2, 43.0, -15.5), "mu_s": 0.8, "mu_d": 0.5, "mu_r": 0.02,
              "k": 5400.0, "b": 1600.0, "steer": 0.0, "brake": "right"},
}
# STRUCTURE contacts (used here only as crash points)
STRUCTURE_IN = {
    "nose_skid": (-37.7, 0.0, 26.6),
    "tail_skid": (188.0, 0.0, 8.0),
    "left_tip": (43.2, -214.8, 59.4),
    "right_tip": (43.2, 214.8, 59.4),
}
# FGLGear defaults of the side-force magic formula (slip in deg): B, C, D = static friction, E
SIDE_B_PER_DEG = 0.06
SIDE_C = 2.8
SIDE_E = 1.03

# --------------------------------------------------------------------------- propulsion
THRUSTER_IN = (-37.7, 0.0, 26.6)
PROP_SENSE = 1            # clockwise seen from the cockpit
PROP_P_FACTOR = 5.0       # not modelled here (see the README)
TANK_CONTENTS_LB = 100.0  # c172p.xml default per tank

ENGINE = {                 # eng_io320.xml
    "minmp_inhg": 10.0, "maxmp_inhg": 28.5, "displacement_in3": 320.0, "maxhp": 160.0,
    "bsfc": 0.32, "cycles": 4.0, "idlerpm": 550.0, "maxrpm": 2700.0,
    "maxthrottle": 1.0, "minthrottle": 0.1, "sparkfaildrop": 0.1,
}
ENGINE_DEFAULTS = {        # FGPiston constructor defaults not overridden by eng_io320.xml
    "bore_in": 5.125, "stroke_in": 4.375, "cylinders": 4.0, "compression_ratio": 8.5,
    "volumetric_efficiency": 0.85, "peak_piston_speed_fps": 100.0, "fmep_dynamic_pa": 18400.0,
    "fmep_static_pa": 46500.0, "static_friction_hp": 1.5, "man_press_lag_s": 1.0,
    "ram_air_factor": 1.0, "R_air": 287.3, "standard_pressure_pa": 101320.73,
}
# FGPiston default Mixture_Efficiency_Correlation: fuel/air ratio -> efficiency
MIXTURE_EFFICIENCY = (
    (0.05000, 0.00000), (0.05137, 0.00862), (0.05179, 0.21552), (0.05430, 0.48276),
    (0.05842, 0.70690), (0.06312, 0.83621), (0.06942, 0.93103), (0.07786, 1.00000),
    (0.08845, 1.00000), (0.09270, 0.98276), (0.10120, 0.93103), (0.11455, 0.72414),
    (0.12158, 0.45690), (0.12435, 0.23276), (0.12500, 0.00000),
)

PROP = {                   # prop_75in2f.xml
    "ixx_slugft2": 1.67, "diameter_in": 75.0, "numblades": 2, "pitch_deg": 22.0,
}
# Advance ratio J -> thrust and power coefficients (the active tables of prop_75in2f.xml)
C_THRUST = (
    (0.0, 0.073), (0.1, 0.073), (0.2, 0.072), (0.3, 0.071), (0.4, 0.069), (0.5, 0.066),
    (0.6, 0.062), (0.7, 0.055), (0.8, 0.045), (0.9, 0.034), (1.0, 0.024), (1.1, 0.013),
    (1.2, -0.006), (1.3, -0.013), (1.4, -0.024), (1.5, -0.034), (1.6, -0.045), (1.7, -0.055),
    (1.8, -0.062), (1.9, -0.066), (2.0, -0.069), (2.1, -0.071), (2.2, -0.072), (2.3, -0.073),
    (5.0, -0.073),
)
C_POWER = (
    (0.0, 0.0660), (0.1, 0.0700), (0.2, 0.0700), (0.3, 0.0660), (0.4, 0.0600), (0.5, 0.0530),
    (0.6, 0.0501), (0.7, 0.0469), (0.8, 0.0426), (0.9, 0.0360), (1.0, 0.0282), (1.1, 0.0191),
    (1.2, 0.0155), (1.3, 0.0191), (1.4, 0.0282), (1.5, 0.0360), (1.6, 0.0426), (1.7, 0.0469),
    (1.8, 0.0501), (1.9, 0.0516), (2.0, 0.0525), (2.1, 0.0525), (2.2, 0.0522), (2.3, 0.0511),
    (2.4, 0.0504), (5.0, 0.0493),
)
CT_MACH = ((0.85, 1.0), (1.05, 0.8))           # helical tip Mach -> thrust factor
CP_MACH = ((0.85, 1.0), (1.05, 1.8), (2.00, 1.4))  # helical tip Mach -> power factor

# --------------------------------------------------------------------------- flight controls
ELEVATOR_DEG = (-28.0, 23.0)       # range of the elevator (cmd -1 .. +1, zero-centred scale)
AILERON_DEG = (-20.0, 15.0)        # left aileron (cmd -1 .. +1); the right one is its negative
RUDDER_DEG = (-16.0, 16.0)
FLAP_DETENTS_DEG = (0.0, 10.0, 20.0, 30.0)
FLAP_TRAVERSE_S = (2.0, 1.0, 1.0)  # time from one detent to the next

# --------------------------------------------------------------------------- aerodynamics
ALPHA_LIMITS_RAD = (-0.087, 0.28)
HYSTERESIS_LIMITS_RAD = (0.09, 0.36)   # stall flag on above 0.36, off below 0.09

KCDGE = ((0.0, 0.4800), (0.1, 0.5150), (0.15, 0.6290), (0.2, 0.7090), (0.3, 0.8150),
         (0.4, 0.8820), (0.5, 0.9280), (0.6, 0.9620), (0.7, 0.9880), (0.8, 1.0000),
         (0.9, 1.0000), (1.0, 1.0000), (1.1, 1.0000))      # h_b-mac -> drag factor
KCLGE = ((0.0, 1.2030), (0.1, 1.1270), (0.15, 1.0900), (0.2, 1.0730), (0.3, 1.0460),
         (0.4, 1.0550), (0.5, 1.0190), (0.6, 1.0130), (0.7, 1.0080), (0.8, 1.0060),
         (0.9, 1.0030), (1.0, 1.0020), (1.1, 1.0000))      # h_b-mac -> lift factor

CD0 = 0.027
CDDF = ((0.0, 0.0), (10.0, 0.0070), (20.0, 0.0120), (30.0, 0.0180))   # flap deg -> dCD
CDWBH_FLAPS = (0.0, 10.0, 20.0, 30.0)
CDWBH = (   # alpha rad, then dCD at flaps 0, 10, 20, 30 deg
    (-0.0873, 0.0041, 0.0000, 0.0005, 0.0014),
    (-0.0698, 0.0013, 0.0004, 0.0025, 0.0041),
    (-0.0524, 0.0001, 0.0023, 0.0059, 0.0084),
    (-0.0349, 0.0003, 0.0057, 0.0108, 0.0141),
    (-0.0175, 0.0020, 0.0105, 0.0172, 0.0212),
    (0.0000, 0.0052, 0.0168, 0.0251, 0.0299),
    (0.0175, 0.0099, 0.0248, 0.0346, 0.0402),
    (0.0349, 0.0162, 0.0342, 0.0457, 0.0521),
    (0.0524, 0.0240, 0.0452, 0.0583, 0.0655),
    (0.0698, 0.0334, 0.0577, 0.0724, 0.0804),
    (0.0873, 0.0442, 0.0718, 0.0881, 0.0968),
    (0.1047, 0.0566, 0.0874, 0.1053, 0.1148),
    (0.1222, 0.0706, 0.1045, 0.1240, 0.1343),
    (0.1396, 0.0860, 0.1232, 0.1442, 0.1554),
    (0.1571, 0.0962, 0.1353, 0.1573, 0.1690),
    (0.1745, 0.1069, 0.1479, 0.1708, 0.1830),
    (0.1920, 0.1180, 0.1610, 0.1849, 0.1975),
    (0.2094, 0.1298, 0.1746, 0.1995, 0.2126),
    (0.2269, 0.1424, 0.1892, 0.2151, 0.2286),
    (0.2443, 0.1565, 0.2054, 0.2323, 0.2464),
    (0.2618, 0.1727, 0.2240, 0.2521, 0.2667),
    (0.2793, 0.1782, 0.2302, 0.2587, 0.2735),
    (0.2967, 0.1716, 0.2227, 0.2507, 0.2653),
    (0.3142, 0.1618, 0.2115, 0.2388, 0.2531),
    (0.3316, 0.1475, 0.1951, 0.2214, 0.2351),
    (0.3491, 0.1097, 0.1512, 0.1744, 0.1866),
)
CDDE = 0.06          # per rad of |elevator|
CDBETA = 0.17        # per rad of |beta|

CYB_FLAPS = (0.0, 30.0)
CYB = ((-0.3490, 0.1370, 0.1060), (0.0, 0.0, 0.0), (0.3490, -0.1370, -0.1060))   # beta rad
CYDA = 0.0
CYDR = 0.187
CYP = ((0.0, -0.0750, -0.1610), (0.094, -0.1450, -0.2310))   # alpha rad; flaps 0, 30
CYR = ((0.0, 0.2140, 0.1620), (0.094, 0.2670, 0.2150))

CLWBH_HYST = (0.0, 1.0)
CLWBH = (   # alpha rad, CL unstalled, CL stalled (hysteresis flag)
    (-0.09, -0.22, -0.22), (0.00, 0.25, 0.25), (0.09, 0.73, 0.73), (0.10, 0.83, 0.78),
    (0.12, 0.92, 0.79), (0.14, 1.02, 0.81), (0.16, 1.08, 0.82), (0.17, 1.13, 0.83),
    (0.19, 1.19, 0.85), (0.21, 1.25, 0.86), (0.24, 1.35, 0.88), (0.26, 1.44, 0.90),
    (0.28, 1.47, 0.92), (0.30, 1.43, 0.95), (0.32, 1.38, 0.99), (0.34, 1.30, 1.05),
    (0.36, 1.15, 1.15),
)
CLDF = ((0.0, 0.0), (10.0, 0.2000), (20.0, 0.3000), (30.0, 0.3500))
CLDE = 0.43
CLADOT = 1.7
CLQ = 3.9

CLB = ((-0.3490, 0.0322), (0.0, 0.0), (0.3490, -0.0322))     # roll, beta rad
CLP = -0.4840
CLR = ((0.0, 0.0798, 0.1246), (0.094, 0.1869, 0.2317))      # alpha rad; flaps 0, 30
CLDA = 0.2290
CLDR = 0.0147

CMO = 0.1000
CMALPHA = -1.8000
CMQ = -12.4000
CMADOT = -7.2700
CMDE = -1.1220        # on the propwash dynamic pressure
CMDF = ((0.0, 0.0), (10.0, -0.0654), (20.0, -0.0981), (30.0, -0.1140))

CNB = ((-0.3490, -0.0205), (0.0, 0.0), (0.3490, 0.0205))
CNP = -0.0278
CNR = -0.0937
CNDA = -0.0053
CNDR = -0.0430        # on the propwash dynamic pressure
