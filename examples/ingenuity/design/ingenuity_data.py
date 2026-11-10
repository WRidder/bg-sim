"""Ingenuity (NASA Mars Helicopter) data, with the provenance of every number.

Tags in the comments:

* ``[PUB: ...]``  published value, with the source (see the README for the full references);
* ``[DIG: ...]``  digitised from a published figure (method and uncertainty in the data file);
* ``[EST]``       an estimate of this example (reasoning in the comment and the README);
* ``[FIT]``       fitted in ``design.py`` to the published JPL hover test (and only to that).

References (short keys, full list in the README):

* Grip17  Grip et al., "Flight Dynamics of a Mars Helicopter", ERF 2017.
* Grip18  Grip et al., "Guidance and Control for a Mars Helicopter", AIAA GNC 2018 (AIAA 2018-1849).
* Bal18   Balaram et al., "Mars Helicopter Technology Demonstrator", AIAA SciTech 2018 (AIAA 2018-0023).
* Kon18   Koning, Johnson, Allan, "Generation of Mars Helicopter Rotor Model for Comprehensive Analyses",
          AHS Technical Meeting 2018.
* Kon19   Koning, Johnson, Grip, "Improved Mars Helicopter Aerodynamic Rotor Model for Comprehensive
          Analyses", AIAA Journal 57(9), 2019.
* Dull22  Dull, Wagner, Young, Johnson, "Hover and Forward Flight Performance Modeling of the Ingenuity
          Mars Helicopter", VFS Aeromechanics for Advanced Vertical Flight, 2022.
* JPLqf   JPL Ingenuity press kit, quick facts (2021).
* NASA21  NASA Ingenuity blog, "What we're learning about Ingenuity's flight control and aerodynamic
          performance" (Grip, 2021): Flight One telemetry figures.
* NASA22  NASA Ingenuity blog, "Flying on Mars is getting harder and harder" (2021): densities, rpm.
"""

from __future__ import annotations

import math

# ----------------------------------------------------------------------------- Mars and the flight
G_MARS = 3.71                    # m/s^2  [PUB: Kon19, g = 3.71]
RHO_FLIGHT1 = 0.0165             # kg/m^3 Flight One density [PUB: NASA21]
RPM_FLIGHT1 = 2537.0             # rpm    rotor set point of flights 1-13 [PUB: NASA21, NASA22]
RHO_JPL = 0.0175                 # kg/m^3 JPL 25-ft Space Simulator hover test [PUB: Kon19, Grip17]
RPM_JPL = 2600.0                 # rpm    JPL hover test rotor speed [PUB: Kon19, Dull22]
A_SOUND_MC2 = 233.13             # m/s    Mars condition 2 (223 K, CO2) [PUB: Kon19 Table 1]

# ----------------------------------------------------------------------------- vehicle
MASS = 1.80                      # kg     [PUB: JPLqf, Kon19, Dull22]
FUSE_X, FUSE_Y, FUSE_Z = 0.136, 0.195, 0.163   # m fuselage box [PUB: JPLqf 13.6 x 19.5 x 16.3 cm]
LEG_LENGTH = 0.384               # m      [PUB: JPLqf]
GROUND_CLEARANCE = 0.13          # m      fuselage bottom above ground [PUB: JPLqf "about 13 cm"]
HEIGHT = 0.49                    # m      overall height [PUB: JPLqf]
DRAG_AREA = 0.065                # m^2    airframe D/q at speed (fuselage + solar panel) [DIG: Dull22 Fig. 20]

# ----------------------------------------------------------------------------- rotor
NB = 2                           # blades per rotor [PUB: Grip17, Bal18]
RADIUS = 0.605                   # m      1.21 m diameter [PUB: Grip17, Bal18, Kon19]
ROTOR_SPACING_FRAC = 0.17        # of the radius, upper to lower rotor [PUB: Grip17 "approximately 17 %"]
BLADE_MASS = 0.028               # kg     [PUB: Dull22 "about 28 grams each"]
COLL_MIN_DEG, COLL_MAX_DEG = -4.5, 17.5   # collective range [PUB: Bal18]
CYC_MAX_DEG = 10.0               # cyclic range [PUB: Bal18, Grip18]
FLAP_FREQ_HZ = 85.0              # rotating flap frequency 80-90 Hz [PUB: Grip17, Grip18]
SERVO_BW_HZ, SERVO_ZETA = 12.0, 0.85   # swashplate servo model [PUB: Grip18]
GNC_RATE_HZ = 500.0              # [PUB: Grip18, Bal18]
DRIVE_EFFICIENCY = 0.78          # motor + drive, motor power to shaft power [PUB: Kon18]

# Blade geometry: radial stations with chord and chordline twist [PUB: Kon18 Table 2]; the tip value at
# r/R = 1 is a linear extrapolation of the last two stations [EST].
BLADE_R = [0.0908, 0.2000, 0.2950, 0.3903, 0.5271, 0.7621, 0.9241, 0.9912, 1.0]
BLADE_C = [0.0506, 0.1407, 0.1968, 0.1968, 0.1627, 0.1209, 0.0860, 0.0341, 0.0273]
BLADE_TWIST_DEG = [16.32, 17.62, 15.92, 12.07, 8.43, 3.93, 1.39, 0.06, -0.10]

# Airfoil (clf5605 at 3/4 span, CFD at Mars Reynolds numbers):
CL_ALPHA = 5.5                   # 1/rad  linear lift slope [DIG: Grip17 Fig. 5, 0.096 per deg between 0 and 7 deg]
ALPHA_0_DEG = -3.9               # deg    zero-lift angle [DIG: Grip17 Fig. 5]
CL_MAX = 1.18                    # [DIG: Grip17 Fig. 5]
TIP_LOSS_B = 0.97                # lift dropped outboard of 0.97 R (HeliCAT practice, Grip17) [EST]

# Inflow: the lower rotor sees the entire uniform inflow of the upper rotor (one-way coupling)
# [PUB: Grip17 section 3.1.2]; momentum theory under-predicts the uniform inflow by about 20 %
# [PUB: Grip17 section 8.1.2] -> induced-velocity factor KAPPA.
KAPPA = 1.20                     # [PUB: Grip17 "approximately 20 %"]

# Flight-dynamics corrections identified by Grip17 (section 8.1.2):
APPARENT_INERTIA_FACTOR = 1.6    # roll/pitch apparent inertia, "adding approximately 60 %" [PUB: Grip17]
EDGEWISE_GAIN = 2.5              # inflow-gradient sensitivity to edgewise flow, "factor of ~2.5" [PUB: Grip17]
LP_MQ_IDENTIFIED = 0.4           # 1/s, identified on-axis roll/pitch "damping" (positive) [PUB: Grip17 0.4-0.45]

# ----------------------------------------------------------------------------- estimates
ROTOR_HUB_INERTIA = 2.0e-4       # kg m^2 hub, swashplate rotating ring and motor rotor about the spin axis [EST]
MOTOR_KT = 0.05                  # N m/A  [EST] (46-pole outrunner, Bal18; EMF 13 V at 2537 rpm)
MOTOR_L = 1.0e-4                 # H      [EST]
BATTERY_V = 22.0                 # V      6S Li-ion pack, 15-25.2 V [PUB: Bal18 range]; mid-flight value [EST]
TAKEOFF_POWER_SPIKE_W = 310.0    # W      Flight Two take-off spike [PUB: NASA21]
BATTERY_PEAK_W = 510.0           # W      [PUB: Bal18, NASA21]
HOVER_ELEC_POWER_W = 210.0       # W      Flight One hover, electrical rotor power [PUB: NASA21]
COLL_LOWER_FLIGHT1_DEG = 9.2     # deg    Flight One hover [PUB: NASA21]
COLL_UPPER_FLIGHT1_DEG = 8.2     # deg    Flight One hover [PUB: NASA21]


def omega(rpm: float) -> float:
    return rpm * 2.0 * math.pi / 60.0
