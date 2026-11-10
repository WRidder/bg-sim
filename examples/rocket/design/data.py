"""Published data and estimates for the rocket example, each with its source.

Everything the models, the scipy reference and the checks use comes from here. Every number is
tagged in a comment as

    [pub]  a published value (the source is named next to it),
    [der]  derived from published values by the formula shown,
    [est]  an engineering estimate (no source found; see the README).

Sources:

    AS506   Saturn V Launch Vehicle Flight Evaluation Report AS-506 Apollo 11 Mission,
            MPR-SAT-FE-69-9, NASA Marshall Space Flight Center, 20 September 1969
            (https://ibiblio.org/apollo/Documents/lvfea-AS506-Apollo11.pdf). Tables 2-2 (event
            times), 4-1 (Mach 1, max Q, max acceleration), 4-2 (cutoff events), 4-5 (insertion),
            5-1 (F-1 engine performance), 6-1 and section 6.3 (S-II thrust and flow), 7-2 (S-IVB first
            burn), 20-1, 20-3, 20-5 (vehicle mass at the events).
    F1WIKI  Rocketdyne F-1, https://en.wikipedia.org/wiki/Rocketdyne_F-1: sea-level thrust 6,770 kN,
            vacuum thrust 7,770 kN.
    J2WIKI  Rocketdyne J-2, https://en.wikipedia.org/wiki/Rocketdyne_J-2: nozzle exit diameter 1.96 m.
    V2WIKI  V-2 rocket, https://en.wikipedia.org/wiki/V-2_rocket: launch mass 12,500 kg, diameter
            1.65 m, 3,810 kg ethanol/water + 4,910 kg LOX, thrust 25 t at sea level rising to 29 t
            as the ambient pressure falls, alcohol flow 55 kg/s and oxygen flow 68 kg/s, burn time
            up to 65 s, maximum vertical altitude 206 km (the highest wartime vertical shot reached
            174.6 km on 20 June 1944).
    V2SR    V-2 sounding rocket, https://en.wikipedia.org/wiki/V-2_sounding_rocket: burnout velocity
            "about 5,000 ft/s (1,500 m/s)", design profile "about 100 miles (160 km) high", fuel
            consumed in about the first minute.
    US76    U.S. Standard Atmosphere 1976, NOAA/NASA/USAF, NASA-TM-X-74335: the layer constants
            below 86 km and the tabulated values above it.
"""

from __future__ import annotations

import math

G0 = 9.80665                      # [pub] standard gravity (US76)
MU = 3.986004418e14               # [pub] Earth's gravitational parameter, m^3/s^2 (WGS 84)
RE = 6_378_165.0                  # [pub] spherical Earth radius used by AS506 (Table 4-5 note), m
P0 = 101_325.0                    # [pub] sea-level pressure (US76), Pa
TONF = 1000.0 * G0                # one tonne-force, N

# ------------------------------------------------------------------------------------------- V-2
V2 = {
    "m0": 12_500.0,               # [pub] V2WIKI launch mass, kg
    "m_prop_loaded": 3_810.0 + 4_910.0,   # [pub] V2WIKI ethanol/water + LOX, kg
    "mdot": 55.0 + 68.0,          # [pub] V2WIKI alcohol + oxygen flow at 25 t thrust, kg/s
    "t_burn": 65.0,               # [pub] V2WIKI "up to 65 s under its own power", s
    "T_sl": 25.0 * TONF,          # [pub] V2WIKI 25 t at sea level, N
    "T_vac": 29.0 * TONF,         # [pub] V2WIKI 29 t "as ambient pressure fell", N
    "d": 1.65,                    # [pub] V2WIKI body diameter, m
    "rg_pitch": 3.5,              # [est] pitch/yaw radius of gyration (14 m body: L/sqrt(12) = 4.0 m, less for the heavy tail), m
    "rg_roll": 0.5,               # [est] roll radius of gyration, m
    "l_gimbal": 6.0,              # [est] CoM to nozzle (not used: the V-2 model flies vertically, no TVC), m
}
V2["c_vac"] = V2["T_vac"] / V2["mdot"]                 # [der] vacuum effective exhaust velocity, m/s
V2["Ae"] = (V2["T_vac"] - V2["T_sl"]) / P0             # [der] nozzle exit area from T_vac - T_sl = p0 Ae, m^2
V2["S"] = math.pi * V2["d"] ** 2 / 4.0                 # [der] reference area, m^2

# Drag coefficient against Mach number, on the body cross-section. [est] No V-2 table was found
# online (the Peenemuende wind-tunnel reports are archived, e.g. UAH archives "table of drag
# coefficients cw for A4 at a = 0", 1941, but not digitised). The values follow the usual shape of
# a fin-stabilised ogive-cylinder missile: flat subsonic, a transonic rise to a peak just above
# Mach 1, and a slow supersonic decline.
V2_CD_MACH = [0.0, 0.6, 0.8, 0.9, 1.0, 1.1, 1.2, 1.5, 2.0, 3.0, 4.0, 5.0, 6.0]
V2_CD = [0.16, 0.16, 0.18, 0.25, 0.38, 0.42, 0.41, 0.36, 0.30, 0.24, 0.21, 0.19, 0.18]

# Published performance numbers the V-2 run is compared with (loose: different payloads and
# propellant loads flew; see the notes in expected.json).
V2_PUB = {
    "v_burnout": 1_500.0,         # [pub] V2SR "about 5,000 ft/s (1,500 m/s)"
    "apogee_design": 160e3,       # [pub] V2SR design profile "about 100 miles (160 km) high"
    "apogee_war_max": 174.6e3,    # [pub] V2WIKI highest wartime vertical shot (20 June 1944)
    "apogee_max": 206e3,          # [pub] V2WIKI infobox "max altitude, vertical launch"
}

# ------------------------------------------------------------------------------------ Saturn V
# Launch site and plane (AS506 section 1 and Table 3-3 of the report: launch azimuth 72.058 deg,
# pad 39A at 28.6084 deg N). The model flies in the vertical plane of the launch azimuth over a
# round, non-rotating Earth; the eastward speed of the pad (omega_E R cos(lat)) is resolved into
# that plane and given as the start velocity, and the air turns with the Earth at that rate.
OMEGA_E = 7.2921159e-5            # [pub] Earth's rotation rate, rad/s
LAT = 28.6084                     # [pub] AS506 pad 39A latitude, deg
AZ = 72.058                       # [pub] AS506 flight azimuth, deg
V_PAD = OMEGA_E * RE * math.cos(math.radians(LAT))      # [der] eastward speed of the pad, m/s
V0_PLANE = V_PAD * math.sin(math.radians(AZ))           # [der] its component along the azimuth, m/s
V0_CROSS = V_PAD * math.cos(math.radians(AZ))           # [der] the component the planar model drops, m/s

D_SV = 10.06                      # [pub] Saturn V diameter (S-IC/S-II), m
S_SV = math.pi * D_SV ** 2 / 4.0  # [der] reference area, m^2
# [est] Saturn V drag coefficient against Mach number on the 10.06 m cross-section. No flight-derived
# table was found (the Boeing D5-15796-1 aerothermodynamics summary is not online). The shape is that
# of a blunt launch vehicle with an escape tower: about 0.3 subsonic, a transonic peak near Mach 1.2
# and a supersonic decline.
SV_CD_MACH = [0.0, 0.5, 0.8, 0.9, 1.0, 1.1, 1.2, 1.4, 1.6, 2.0, 3.0, 4.0, 5.0, 8.0]
SV_CD = [0.30, 0.30, 0.34, 0.42, 0.56, 0.64, 0.66, 0.62, 0.57, 0.50, 0.40, 0.34, 0.30, 0.27]

# F-1: AS506 Table 5-1, reconstruction at standard sea-level conditions (35 to 38 s), the average
# of the five engines.
F1_ISP_SL = (2599 + 2598 + 2596 + 2595 + 2584) / 5.0       # [pub] AS506 Table 5-1, N*s/kg
F1_MDOT_SL = (2594 + 2569 + 2590 + 2613 + 2582) / 5.0      # [pub] AS506 Table 5-1, kg/s
F1_AE = (7_770e3 - 6_770e3) / P0                           # [der] F1WIKI: T_vac - T_sl = p0 Ae, m^2
F1_C_VAC = F1_ISP_SL + P0 * F1_AE / F1_MDOT_SL             # [der] vacuum effective exhaust velocity, m/s
J2_AE = math.pi * 1.96 ** 2 / 4.0                          # [der] J2WIKI exit diameter 1.96 m, m^2

# Vehicle mass at the events, AS506 Tables 20-1, 20-3, 20-5 (actual), kg.
M_HDA = 2_899_008.0               # [pub] holddown arm release (range time 0.30 s)
M_CECO = 1_110_189.0              # [pub] S-IC centre engine cutoff (135.20 s)
M_OECO = 827_292.0                # [pub] S-IC outboard engine cutoff (161.63 s)
M_SEP1 = 823_625.0                # [pub] S-IC/S-II separation (162.30 s)
M_SII_IGN = 658_363.0             # [pub] S-II ignition (164.00 s)
M_SII_OECO = 213_888.0            # [pub] S-II outboard engine cutoff (548.22 s)
M_SEP2 = 213_757.0                # [pub] S-II/S-IVB separation (549.00 s)
M_SIVB_IGN = 166_571.0            # [pub] S-IVB ignition (552.70 s)
M_SIVB_ECO = 135_182.0            # [pub] S-IVB first engine cutoff (699.34 s)
M_INTERSTAGE = 3_982.0            # [pub] S-II aft interstage (Table 20-3, S-IC/S-II IS at mainstage)
M_LET = 49_735.0 - 45_693.0       # [der] spacecraft mass before and after the escape tower jettison

# Event times, AS506 Table 2-2 (range time, actual), s.
T_PITCH = 13.2                    # [pub] begin pitch and roll manoeuvre
T_CECO = 135.20                   # [pub] S-IC centre engine cutoff
T_OECO = 161.63                   # [pub] S-IC outboard engine cutoff
T_SEP1 = 162.30                   # [pub] S-IC/S-II separation (Table 20-1)
T_SII_START = 165.2               # [der] S-II start: middle of the build-up, ESC+1 s solenoids (164.0) to mainstage (166.2)
T_IS = 192.3                      # [pub] S-II second plane (aft interstage) separation
T_LET = 197.9                     # [pub] launch escape tower jettison
T_SII_CECO = 460.62               # [pub] S-II centre engine cutoff
T_EMR = 498.0                     # [pub] S-II low engine mixture ratio shift, ESC + 335 s (section 6.3)
T_SII_OECO = 548.22               # [pub] S-II outboard engine cutoff
T_SEP2 = 549.00                   # [pub] S-II/S-IVB separation (Table 20-3)
T_SIVB_START = 552.70             # [pub] S-IVB ignition (Table 20-5)
T_SIVB_ECO = 699.34               # [pub] S-IVB first guidance cutoff
T_INSERT = 709.33                 # [pub] parking orbit insertion

# Flow, effective exhaust velocity and exit area per phase.
SIC_MDOT5 = (M_HDA - M_CECO) / (T_CECO - 0.30)             # [der] AS506 mass history, 5 engines, kg/s
SIC_MDOT4 = (M_CECO - M_OECO) / (T_OECO - T_CECO)          # [der] AS506 mass history, 4 engines, kg/s
SII_T5 = 5_141_516.0              # [pub] AS506 6.3: total thrust at ESC+61 s, N
SII_C_HIGH = (4169.8 + 4170.8 + 4165.9 + 4157.0 + 4162.9) / 5.0   # [pub] AS506 Table 6-1: J-2 specific impulse at
#                                   ESC+61 s, reconstruction, average of five, N*s/kg. The engine flow (thrust / Isp)
#                                   leaves the vehicle; the stage figure of 4150.2 N*s/kg in 6.3 also counts the
#                                   pressurisation gas, which stays in the tanks.
SII_T4 = 4_093_107.0              # [pub] AS506 6.3: thrust after S-II CECO, N
SII_T4_LOW = 3_082_769.0          # [pub] AS506 6.3: thrust at ESC+351 s (low EMR), N
SII_C_LOW = 4_205.0               # [est] low-EMR specific impulse (about 1 % above high EMR), N*s/kg
SIVB_T = 901_223.0                # [pub] AS506 Table 7-2: first burn thrust (reconstruction), N
SIVB_C = 4_204.0                  # [pub] AS506 Table 7-2: specific impulse, N*s/kg
TAU_ENGINE = 0.33                 # [der] thrust decay time constant: outboard cutoff impulse 10.6 MN*s (AS506 5.4) / 31.9 MN, s

# Gimbal arm (CoM to engine gimbal) and radii of gyration per configuration. [est] all: the AS506
# mass-characteristics table (20-10) is unreadable in the scan; the values give the right order of
# magnitude for a 110 m stack (L/sqrt(12) = 32 m) and its upper parts.
SV_CONFIGS = [
    # name,                       rg_pitch, rg_roll, l_gimbal
    ("full stack",                30.0,     4.5,     35.0),
    ("S-II + interstage + LET",   19.0,     4.0,     21.0),
    ("S-II + LET",                18.5,     4.0,     20.0),
    ("S-II",                      17.0,     4.0,     19.0),
    ("S-IVB + IU + spacecraft",   11.0,     3.0,     14.0),
]

# Pitch (attitude) controller: an ideal second-order loop through the gimbal. [est]
SV_WN = 1.5                       # rad/s
SV_ZETA = 0.8
SV_DELTA_MAX = 6.0                # [pub] F-1 gimbal range +/- 6 deg (F1WIKI), used for every stage, deg

# Published trajectory states (AS506 Tables 4-1, 4-2, 4-5, actual). Altitude and surface range in m,
# space-fixed velocity in m/s, space-fixed flight-path angle in deg.
SV_EVENTS = {
    "S-IC CECO":     {"t": 135.20, "h": 44.0e3,  "s": 46.4e3,    "v": 1_979.0, "fpa": 22.957},
    "S-IC OECO":     {"t": 161.63, "h": 66.1e3,  "s": 93.6e3,    "v": 2_764.1, "fpa": 19.114},
    "S-II CECO":     {"t": 460.62, "h": 180.2e3, "s": 1_114.3e3, "v": 5_707.5, "fpa": 0.897},
    "S-II OECO":     {"t": 548.22, "h": 187.3e3, "s": 1_617.0e3, "v": 6_917.3, "fpa": 0.608},
    "S-IVB ECO":     {"t": 699.34, "h": 191.1e3, "s": 2_634.0e3, "v": 7_791.2, "fpa": 0.015},
}
SV_MACH1 = {"t": 66.3, "h": 7.8e3}                        # [pub] AS506 Table 4-1
SV_MAXQ = {"t": 83.0, "q": 35.2e3, "h": 13.6e3}           # [pub] AS506 Table 4-1 (3.52 N/cm^2)
SV_ACC_OECO = 38.61                                       # [pub] AS506 Table 4-1, S-IC max acceleration at 161.7 s
SV_ACC_SII = 17.84                                        # [pub] AS506 Table 4-1, S-II max acceleration at 460.70 s
SV_ACC_SIVB = 6.73                                        # [pub] AS506 Table 4-1, S-IVB 1st burn max at 699.41 s
SV_V_INSERT = 7_793.1                                     # [pub] AS506 Table 4-5, insertion (709.33 s)


def sv_schedule() -> dict:
    """The Saturn V flight sequence as phase tables (start time and value per phase) and jettisons."""
    ae1, ae2 = F1_AE, J2_AE
    phases = [
        # t_start,      mdot,                       c,           Ae
        (0.0,           SIC_MDOT5,                  F1_C_VAC,    5 * ae1),
        (T_CECO,        SIC_MDOT4,                  F1_C_VAC,    4 * ae1),
        (T_OECO,        0.0,                        F1_C_VAC,    4 * ae1),
        (T_SII_START,   SII_T5 / SII_C_HIGH,        SII_C_HIGH,  5 * ae2),
        (T_SII_CECO,    SII_T4 / SII_C_HIGH,        SII_C_HIGH,  4 * ae2),
        (T_EMR,         SII_T4_LOW / SII_C_LOW,     SII_C_LOW,   4 * ae2),
        (T_SII_OECO,    0.0,                        SII_C_LOW,   4 * ae2),
        (T_SIVB_START,  SIVB_T / SIVB_C,            SIVB_C,      1 * ae2),
        (T_SIVB_ECO,    0.0,                        SIVB_C,      1 * ae2),
    ]
    jettisons = [
        # t, mass, what
        (T_SEP1, M_SEP1 - M_SII_IGN, "S-IC stage (with its interstage ring and the S-II ullage-motor propellant)"),
        (T_IS, M_INTERSTAGE, "S-II aft interstage"),
        (T_LET, M_LET, "launch escape tower"),
        (T_SEP2, M_SEP2 - M_SIVB_IGN, "S-II stage and S-II/S-IVB interstage (with the S-IVB ullage-motor propellant)"),
    ]
    # The run starts at range time 0 (range zero), the published mass is at holddown release (0.30 s):
    # add the S-IC flow of those 0.3 s.
    return {"phases": phases, "jettisons": jettisons, "m0": M_HDA + 0.30 * SIC_MDOT5, "configs": SV_CONFIGS}


def v2_schedule() -> dict:
    return {
        "phases": [(0.0, V2["mdot"], V2["c_vac"], V2["Ae"]), (V2["t_burn"], 0.0, V2["c_vac"], V2["Ae"])],
        "jettisons": [],
        "m0": V2["m0"],
        "configs": [("V-2", V2["rg_pitch"], V2["rg_roll"], V2["l_gimbal"])],
    }


# ------------------------------------------------------------------------- US Standard Atmosphere
_R_AIR = 8_314.32 / 28.9644        # [pub] US76 R*/M0, J/(kg K)
_R0_GEOP = 6_356_766.0             # [pub] US76 effective Earth radius for geopotential, m
_LAYERS = [                        # [pub] US76 base geopotential altitude (m'), lapse rate (K/m')
    (0.0, -6.5e-3), (11_000.0, 0.0), (20_000.0, 1.0e-3), (32_000.0, 2.8e-3),
    (47_000.0, 0.0), (51_000.0, -2.8e-3), (71_000.0, -2.0e-3), (84_852.0, 0.0),
]
# [pub] US76 tabulated values above 86 km (geometric altitude m, T K, p Pa, rho kg/m^3)
_UPPER = [
    (90e3, 186.87, 1.8359e-1, 3.416e-6),
    (100e3, 195.08, 3.2011e-2, 5.604e-7),
    (110e3, 240.00, 7.1042e-3, 9.708e-8),
    (120e3, 360.00, 2.5382e-3, 2.222e-8),
    (130e3, 469.27, 1.2505e-3, 8.152e-9),
    (150e3, 634.39, 4.5422e-4, 2.076e-9),
    (200e3, 854.56, 8.4736e-5, 2.541e-10),
    (250e3, 941.33, 2.4767e-5, 6.073e-11),
    (300e3, 976.01, 8.7704e-6, 1.916e-11),
]


def us76_lower(z: float) -> tuple[float, float, float]:
    """US76 temperature (K), pressure (Pa) and density (kg/m^3) at geometric altitude z <= 86 km."""
    h = _R0_GEOP * z / (_R0_GEOP + z)
    t_b, p_b = 288.15, P0
    for k, (h_b, lapse) in enumerate(_LAYERS):
        h_top = _LAYERS[k + 1][0] if k + 1 < len(_LAYERS) else math.inf
        dh = min(h, h_top) - h_b
        if lapse == 0.0:
            p = p_b * math.exp(-G0 * dh / (_R_AIR * t_b))
        else:
            p = p_b * (1.0 + lapse * dh / t_b) ** (-G0 / (_R_AIR * lapse))
        t = t_b + lapse * dh
        if h <= h_top:
            return t, p, p / (_R_AIR * t)
        t_b, p_b = t, p
    raise AssertionError


def atmosphere_table() -> dict:
    """Breakpoints for the model's table lookup: every km to 86 km, then the US76 table rows.

    The model interpolates ln(p) and ln(rho) linearly between breakpoints (exact for an
    isothermal layer) and T linearly.
    """
    hs, ts, lps, lrs = [], [], [], []
    for k in range(0, 87):
        t, p, r = us76_lower(1000.0 * k)
        hs.append(1000.0 * k), ts.append(t), lps.append(math.log(p)), lrs.append(math.log(r))
    for z, t, p, r in _UPPER:
        hs.append(z), ts.append(t), lps.append(math.log(p)), lrs.append(math.log(r))
    return {"h": hs, "T": ts, "lnp": lps, "lnrho": lrs}
