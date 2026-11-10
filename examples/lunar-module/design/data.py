"""The numbers of the lunar-module example, each with its source.

Tags: [pub] published (source named), [der] derived from published numbers (how named),
[est] estimate (no published number found), [fit] fitted to published data (design.py).

Sources
  MR      Apollo 11 Mission Report, NASA MSC-00171, November 1969 (tables 5-I, 5-III, 5-V, 7-V,
          9.6-V, 9.9-I, the mass-properties table of appendix A, sections 5.3, 5.4, 9.8, 9.9)
  SP4029  R. W. Orloff, Apollo by the Numbers, NASA SP-2000-4029 (tables "LM Descent Stage
          Propellant Status", "LM Ascent Stage Propellant Status", "LM Lunar Landing",
          "Selected Mission Weights")
  TND6846 F. V. Bennett, Apollo Experience Report: Mission Planning for Lunar Module Descent and
          Ascent, NASA TN D-6846, 1972 (table I premission powered-descent event summary, table V
          ascent summary, the descent and ascent design text)
  TND6850 W. F. Rogers, Apollo Experience Report: Lunar Module Landing Gear Subsystem, NASA
          TN D-6850, 1972 (tread radius, footpad, probes, touchdown-velocity design envelope)
  SP4205  C. G. Brooks et al., Chariots for Apollo, NASA SP-4205, ch. 6 (DPS 43,900 N maximum,
          4,700 N minimum)
  ALSJ    Apollo Lunar Surface Journal, "The First Lunar Landing" (the air-to-ground and onboard
          transcript with Aldrin's altitude, descent-rate and forward-velocity callouts)
  WIKI    Wikipedia, "Apollo Lunar Module" and "Descent propulsion system" (DPS rated thrust
          10,500 lbf, specific impulse 311 s at full thrust, RCS 16 x 445 N)
"""

from __future__ import annotations

import math

LB = 0.45359237           # kg
FT = 0.3048               # m
LBF = 4.4482216152605     # N
SLUGFT2 = 1.3558179483    # kg m^2
G0 = 9.80665              # m/s^2 (Isp)
NMI = 1852.0              # m

# ------------------------------------------------------------------------------- the Moon
MU = 4.9028e12            # [pub] m^3/s^2 (task brief; JPL DE: 4.9028e12)
RM = 1737.4e3             # [pub] mean radius, m (IAU)

# ------------------------------------------------------------------------------- descent
# masses (MR appendix A mass properties; SP4029 "Selected Mission Weights")
M_PDI = 33401.6 * LB      # [pub] LM at descent-orbit-insertion cutoff, 33,401.6 lb (= the PDI mass:
                          #       between DOI cutoff and PDI only RCS was used)
M_LANDING = 16153.2 * LB  # [pub] LM at lunar landing, 16,153.2 lb
DPS_CONSUMED = 17414 * LB             # [pub] SP4029: DPS propellant consumed (DOI + PDI), 17,414 lb
DPS_DOI = (33669.6 - 33401.6) * LB    # [der] DOI burn: 268 lb (mass at DOI ignition - cutoff, MR)
DPS_PDI = DPS_CONSUMED - DPS_DOI      # [der] 17,146 lb burned in powered descent
DPS_REMAINING = 770 * LB  # [pub] SP4029: remaining at cutoff, 770 lb
DPS_USABLE_LEFT = 674 * LB  # [pub] SP4029: usable at cutoff, 674 lb
HOVER_LEFT = 45.0         # [pub] SP4029 "LM Lunar Landing": hover time remaining 45 s
PROP_PDI = DPS_PDI + DPS_REMAINING    # [der] propellant on board at PDI (8,127 kg)
PROP_UNUSABLE = DPS_REMAINING - DPS_USABLE_LEFT  # [der] 96 lb unusable
RCS_PDI = 95 * LB         # [pub] MR 5.3: RCS propellant used in powered descent, 95 lb (not modelled)

# principal moments of inertia (MR appendix A, slug ft^2): Ixx, Iyy, Izz (LM body axes: X up the
# thrust axis, Y right, Z forward through the hatch); the products of inertia are left out
J_PDI = [23480 * SLUGFT2, 25978 * SLUGFT2, 25871 * SLUGFT2]      # [pub] at DOI cutoff
J_LANDING = [12582 * SLUGFT2, 13667 * SLUGFT2, 16204 * SLUGFT2]  # [pub] at lunar landing

# descent propulsion system
DPS_RATED = 10500 * LBF   # [pub] WIKI: 10,500 lbf rated (100 %)
DPS_FTP = 9870 * LBF      # [pub] SP4205: 9,870 lbf (43,900 N) maximum: the fixed throttle position
DPS_MIN = 0.10            # [pub] TND6846: throttleable between 10 and 60 % ...
DPS_MAX = 0.60            # [pub] ... of the rated thrust
DPS_RECOVER = 0.57        # [pub] TND6846: throttled as commanded once the command falls to 57 %
T_TRIM = 26.0             # [pub] TND6846 and MR 9.8: 26 s at trim (minimum) throttle after ignition
TAU_ENGINE = 0.3          # [est] first-order lag of the thrust (not published)
DPS_ISP = 305.0           # [pub] enginehistory.org RPE 9.41 (LMDE "305 sec"); WIKI gives 311 s at
                          #       full thrust and 285 s at 10 %; see README

# reaction control system (WIKI: 16 thrusters of 100 lbf = 445 N in four quads)
RCS_F = 100 * LBF         # [pub]
RCS_ARM = 1.67            # [est] moment arm of a quad about the centre of mass
RCS_TORQUE = 4 * RCS_F * RCS_ARM   # [der/est] four jets per axis: about 2,970 N m

# attitude loop (an ideal loop on the RCS torque)
ATT_WN = 0.9              # [est] rad/s
ATT_ZETA = 0.9            # [est]

# landing gear (TND6850)
TREAD = 167.57 * 0.0254   # [pub] footpad centre 167.57 in from the X axis
PAD_D = 3.0 * FT          # [pub] footpad "approximately 3 feet in diameter"
PROBE = 5.6 * FT          # [pub] lunar-surface sensing probes 5.6 ft below the pads (TND6846, TND6850)
H_REF = 12 * FT - PROBE   # [der] height of the guidance altitude reference above the pad soles:
                          #       TND6846 table I gives 12 ft altitude at probe contact
D_CG = H_REF              # [est] the centre of mass is put at that height (1.95 m)
GEAR_V_MAX = 10 * FT      # [pub] TND6850: touchdown envelope, vertical up to 10 ft/s ...
GEAR_VH_MAX = 4 * FT      # [pub] ... horizontal up to 4 ft/s (for a vertical velocity up to 7 ft/s)
STRUT_CRUSH = 4500 * LBF  # [pub] TND6850 fig. 6: the primary strut's low-level honeycomb cartridge (4,500 lb)
STRUT_CRUSH_HIGH = 9500 * LBF  # [pub] TND6850 fig. 6: ... and its high-level cartridge (9,500 lb), which strokes after it
MU_SOIL = 0.4             # [pub] TND6850: postflight analysis, sliding friction 0.4
PAD_PEN = 3.0 * 0.0254    # [pub] MR 5.4: footpads penetrated the surface 2.5 to 3.5 in (3 in taken)
# ContactPoint (Hunt-Crossley, exponent 3/2) for pad + soil: k xref = 3 kN, about a pad's static
# load at the landing mass (7,330 kg x 1.62 / 4), at xref = PAD_PEN, so the LM settles about 3 in
# into the soil [fit to MR 5.4]; damping c and the friction regularisation [est]. The struts are
# rigid in the model (TND6850 table V: no primary-strut stroking recorded on Apollo 11).
GEAR_CONTACT = {"k": 3000.0 / PAD_PEN, "xref": PAD_PEN, "c": 2.0, "mu": MU_SOIL, "vs": 0.02, "bt": 0.0,
                "eps": 1e-3, "feps": 1e-6}

# events and states (MR table 5-I, 9.6-V; SP4029; TND6846)
T_PDI_GET = 102 * 3600 + 33 * 60 + 5.01  # [pub] 102:33:05.01 descent engine ignition
T_THROTTLE_RECOVERY = 386.0   # [pub] MR 5.3: throttle reduction 386 s after ignition (384 predicted)
T_YAW_START = 232.0           # [pub] MR table 5-I: face-up yaw manoeuvre in process 102:36:57
T_YAW_END = 294.0             # [pub] MR table 5-I: face-up manoeuvre complete 102:37:59
T_HG = 507.0                  # [pub] MR table 5-I: P64 at 102:41:32 (premission 8:26 = 506 s)
H_HG = 7129 * FT              # [pub] MR 5.3: high gate at 7,129 ft ...
HDOT_HG = -125 * FT           # [pub] ... at a descent rate of 125 ft/s
V_HG_PREMISSION = 506 * FT    # [pub] TND6846 table I: inertial velocity at high gate 506 ft/s
RANGE_HG = 4.5 * NMI          # [pub] TND6846: high gate about 4.5 n mi from the landing site
T_P66 = 617.0                 # [pub] MR table 5-I: P66 at 102:43:22
T_LANDING = 102 * 3600 + 45 * 60 + 39.9 - T_PDI_GET   # [pub] MR 5.4: landing 102:45:39.9 -> 754.9 s
PDI_BURN = 756.39             # [pub] SP4029 / MR 9.6-V: PDI burn duration (to engine cutoff)
AIM_SHIFT = 1100 * FT         # [pub] MR 5.3: landed about 1,100 ft downrange of the initial aim point
H_PDI = 49376 * FT            # [pub] MR table 5-III: best-estimate altitude at PDI 49,376 ft
V_PDI = 5560 * FT             # [pub] TND6846: orbit velocity at PDI "approximately 5560 fps"
HDOT_PDI = -4 * FT            # [pub] TND6846 table I: altitude rate -4 ft/s at PDI
RANGE_PDI_PUB = 260 * NMI     # [pub] TND6846: PDI "approximately 260 nautical miles from the landing site"
DV_PDI = 6775 * FT            # [pub] MR 9.8: "a velocity change of approximately 6775 ft/sec"
TD_VZ = 1.7 * FT              # [pub] MR 5.4: touchdown 1.7 ft/s vertical ...
TD_VLAT = 2.1 * FT            # [pub] ... 2.1 ft/s to the crew's left, negligible forward velocity

# TND6846 table I, premission powered-descent event summary (time from ignition s, inertial velocity
# ft/s, altitude rate ft/s, altitude ft)
PREMISSION = [
    ("PDI", 0.0, 5560, -4, 48814),
    ("throttle to maximum", 26.0, 5529, -3, 48725),
    ("rotate to windows up", 176.0, 4000, -50, 44934),
    ("LR altitude update", 258.0, 3065, -89, 39201),
    ("throttle recovery", 384.0, 1456, -106, 24639),
    ("LR velocity update", 402.0, 1315, -127, 22644),
    ("high gate", 506.0, 506, -145, 7515),
    ("low gate", 606.0, 55, -16, 512),
]

# ALSJ: Aldrin's callouts in the landing phase (GET, altitude ft, descent rate ft/s, forward ft/s)
def _get(h, m, s):
    return h * 3600 + m * 60 + s - T_PDI_GET


CALLOUTS = [
    (_get(102, 43, 1), 750, 23, None), (_get(102, 43, 7), 700, 21, None), (_get(102, 43, 11), 600, 19, None),
    (_get(102, 43, 16), 540, 15, None), (_get(102, 43, 26), 400, 9, 58), (_get(102, 43, 33), 350, 4, None),
    (_get(102, 43, 35), 330, 3.5, None), (_get(102, 43, 46), 300, 3.5, 47), (_get(102, 43, 52), 270, 1.5, None),
    (_get(102, 44, 7), 250, 2.5, 19), (_get(102, 44, 16), 220, 3.5, 13), (_get(102, 44, 24), 200, 4.5, 11),
    (_get(102, 44, 31), 160, 6.5, 9), (_get(102, 44, 40), 120, None, None), (_get(102, 44, 45), 100, 3.5, 9),
    (_get(102, 44, 54), 75, 0.5, 6), (_get(102, 45, 17), 40, 2.5, None), (_get(102, 45, 21), 30, 2.5, None),
    (_get(102, 45, 25), 20, 0.5, 4),
]
T_QUANTITY_LIGHT = 102 * 3600 + 44 * 60 + 30.4 - T_PDI_GET   # [pub] MR 9.8.3: low-level light 102:44:30.4
QUANTITY_LIGHT_LEFT = 116.0   # [pub] MR 9.8.3: ... "approximately 116 seconds of total firing time remaining"

# P66 "pilot model" (ALSJ callouts): commanded descent rate and forward speed as functions of the
# altitude of the guidance reference (ft -> ft/s). Built from the callouts above; at the pads'
# touchdown (altitude H_REF) the descent rate is the MR's 1.7 ft/s and the forward speed 0.
P66_H = [H_REF / FT, 20, 30, 40, 75, 100, 160, 200, 220, 250, 270, 300, 350, 400]
P66_RATE = [1.7, 1.5, 2.5, 2.5, 0.5, 3.5, 6.0, 4.5, 3.5, 2.5, 1.5, 3.5, 4.0, 9.0]
P66_FWD_H = [H_REF / FT, 20, 75, 100, 160, 200, 220, 250, 300, 400]
P66_FWD = [0.0, 4, 6, 9, 9, 11, 13, 19, 47, 58]
TAU_V = 2.0               # [est] P66: time constant of the rate-of-descent loop (throttle)
TAU_H = 5.0               # [est] P66: time constant of the horizontal-velocity loop (attitude)
A_H_MAX = 0.6             # [est] P66: horizontal acceleration limit (about 20 deg of tilt at lunar g)

# ------------------------------------------------------------------------------- ascent
M_LIFTOFF = 10776.6 * LB          # [pub] MR appendix A / SP4029: LM ascent stage at lunar lift-off
M_INSERTION = 5928.6 * LB         # [pub] ... at orbit insertion
J_LIFTOFF = [6808 * SLUGFT2, 3475 * SLUGFT2, 5971 * SLUGFT2]      # [pub] MR appendix A
J_INSERTION = [3457 * SLUGFT2, 3082 * SLUGFT2, 2273 * SLUGFT2]    # [pub]
APS_PROP = 5238 * LB              # [pub] SP4029: APS propellant loaded, 5,238 lb
APS_CONSUMED = 4767 * LB          # [pub] SP4029: consumed by the APS (the ascent burn), 4,767 lb
APS_THRUST = 3464 * LBF           # [pub] MR table 9.9-I: 3,464 lb (10 s after ignition)
APS_ISP = 309.4                   # [pub] MR table 9.9-I: 309.4 s (10 s after ignition)
T_LIFTOFF_GET = 124 * 3600 + 22 * 60 + 0.79   # [pub] 124:22:00.79
ASC_BURN = 434.88                 # [pub] MR 9.6-V: 434.88 s (TND6846: insertion at 7:15)
ASC_VRISE_RATE = 40 * FT          # [pub] TND6846: vertical rise ends at 40 ft/s radial rate (about 10 s)
ASC_T_VRISE = 10.0                # [pub] TND6846: vertical rise terminated 10 s after lift-off
ASC_H_T = 60000 * FT              # [pub] TND6846 table V(c): target altitude 60,000 ft ...
ASC_RDOT_T = 32.2 * FT            # [pub] ... radial velocity 32.2 ft/s ...
ASC_VH_T = 5534.9 * FT            # [pub] ... down-range velocity 5,534.9 ft/s
ASC_INS = {"h": 60300 * FT, "rdot": 32 * FT, "vh": 5537.0 * FT}   # [pub] TND6846 table V(b) postflight
ASC_ORBIT = (47.3 * NMI, 9.5 * NMI)   # [pub] MR 5.6 / TND6846: apolune, perilune after the residual trim
ASC_ORBIT_RAW = (48.0 * NMI, 9.1 * NMI)   # [pub] MR table 7-V: resultant orbit of the ascent burn
ASC_DV = 6070.1 * FT              # [pub] MR table 7-V: ascent velocity change 6,070.1 ft/s
H_ASC0 = 4.3                      # [est] ascent-stage centre of mass above the surface at lift-off
TAU_APS = 0.2                     # [est] thrust lag of the APS


def pdi_state(range_m: float) -> dict:
    """Position and velocity at PDI in the site frame (origin at the landing site, x downrange,
    z up, Moon centre at (0, 0, -R)) for a PDI `range_m` metres uprange along the surface."""
    th = -range_m / RM
    r = RM + H_PDI
    er = (math.sin(th), 0.0, math.cos(th))
    eh = (math.cos(th), 0.0, -math.sin(th))
    vh = math.sqrt(V_PDI ** 2 - HDOT_PDI ** 2)
    p = (r * er[0], 0.0, r * er[2] - RM)
    v = tuple(vh * eh[k] + HDOT_PDI * er[k] for k in range(3))
    return {"p": p, "v": v}


def j_of_m(m: float, ma: float, ja: list, mb: float, jb: list) -> list:
    """Moments of inertia linear in the mass between two published points."""
    return [jb[k] + (ja[k] - jb[k]) * (m - mb) / (ma - mb) for k in range(3)]
