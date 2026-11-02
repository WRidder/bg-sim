"""Published Cessna 172P data the model is checked against, each value with its source.

Sources
-------
POH   Cessna Model 172P Pilot's Operating Handbook (1981, Section 5 dated 30 May 1980). Read from
      the performance-chart extract "Cessna 172P performance charts" (Civil Air Patrol, Kerrville
      squadron: Figures 5-5, 5-6 and 5-11 as scans) and the scanned handbook on manualslib
      (manual 2382555: Figure 5-3 page 5-11, Figure 3-1 page 3-1, emergency airspeeds page 3-3).
SPEC  POH Section 1 "Performance - Specifications" as transcribed by 172guide.com
      (models/172P-81.htm): speeds, climb, takeoff, landing, stall, weights, engine, propeller.
TCDS  EASA type-certificate data sheet IM.A.051 (Model 172, issue 11, 17 November 2025). It lists
      the 172R/S, which share the 172P's wing, datum and control-surface limits; the 172P itself
      is on FAA TCDS 3A12 (not read here).

Temperatures: the POH tables are at 0, 10, 20, 30, 40 C; the values at the standard 15 C of sea
level are the linear interpolation, marked "interp".
"""

from __future__ import annotations

KT = 0.514444444          # m/s per knot
FT = 0.3048
FPM = FT / 60.0           # m/s per ft/min

GROSS_WEIGHT_LB = 2400.0  # SPEC: maximum takeoff or landing weight (normal category)

# (value, unit, source, note)
GEOMETRY = {
    "wing_span": (36.08, "ft", "TCDS", "10.9982 m (172R/S); JSBSim uses 35.8 ft (Roskam's C182)"),
    "mac": (58.8, "in", "TCDS", "1.4935 m, leading edge 25.9 in aft of datum; JSBSim chord 4.9 ft = 58.8 in"),
    "wing_area": (174.0, "ft^2", "SPEC", "2400 lb / 13.8 lb/ft^2 = 174 ft^2 (wing loading); TCDS (172R/S) 16.3045 m^2 = 175.5 ft^2"),
    "aft_cg_limit": (47.3, "in", "TCDS", "aft of datum at the maximum weight or less"),
    "fwd_cg_limit_gross": (40.0, "in", "TCDS", "172R/S at 2450 lb (35.0 in at 1950 lb or less)"),
    "elevator": ((-28.0, 23.0), "deg", "TCDS", "up 28 / down 23 (JSBSim: the same)"),
    "ailerons": ((-20.0, 15.0), "deg", "TCDS", "up 20 / down 15 (JSBSim: the same)"),
    "rudder": (16.17, "deg", "TCDS", "16 deg 10 min each way, parallel to the waterline (JSBSim: 16)"),
    "flaps": (30.0, "deg", "TCDS", "takeoff 0-10, landing 0-30 (JSBSim detents 0/10/20/30)"),
    "baggage_arm": (95.0, "in", "TCDS", "JSBSim's baggage station is at 95 in: same datum"),
    "front_seats": ((34.0, 46.0), "in", "TCDS", "JSBSim's pilot station 36 in"),
    "rear_seats": (73.0, "in", "TCDS", "JSBSim's passenger station 70 in"),
    "tires": ("5.00x5 nose, 6.00x6 main", None, "TCDS", ""),
    "engine": ("Lycoming O-320-D2J, 160 BHP at 2700 RPM", None, "SPEC",
               "JSBSim models it with its IO-320 file (160 hp, 2700 rpm, 320 in^3)"),
    "propeller": ("75 in, fixed pitch", None, "SPEC", "JSBSim prop_75in2f: 75 in, two blades"),
    "empty_weight": (1414.0, "lb", "SPEC", "Skyhawk; 1440 lb Skyhawk II. JSBSim's empty weight is 1500 lb"),
}

PERFORMANCE = {
    # stall speeds, 2400 lb, power off, wings level (Figure 5-3)
    "stall_clean_kcas_aft": (51.0, "KCAS", "POH Fig. 5-3", "flaps up, most rearward CG (44 KIAS); 52 KCAS at the most forward CG"),
    "stall_clean_kcas_fwd": (52.0, "KCAS", "POH Fig. 5-3", "flaps up, most forward CG"),
    "stall_flaps10_kcas": (48.0, "KCAS", "POH Fig. 5-3", "flaps 10, rearward CG (49 forward)"),
    "stall_flaps30_kcas": (46.0, "KCAS", "POH Fig. 5-3", "flaps 30, both CG limits (33 KIAS)"),
    # climb (Figure 5-6: flaps up, full throttle, 2400 lb)
    "vy_sl_kias": (76.0, "KIAS", "POH Fig. 5-6", "climb speed at sea level"),
    "roc_sl_fpm": (700.0, "ft/min", "POH Fig. 5-6", "interp 15 C (745 at 0 C, 685 at 20 C); SPEC: 700"),
    "vy_8000_kias": (72.0, "KIAS", "POH Fig. 5-6", "climb speed at 8000 ft"),
    "roc_8000_fpm": (332.0, "ft/min", "POH Fig. 5-6", "interp at the standard -0.8 C (380 at -20 C, 330 at 0 C)"),
    "service_ceiling_ft": (13000.0, "ft", "SPEC", ""),
    # speeds (Section 1)
    "vmax_sl_kt": (123.0, "kt", "SPEC", "maximum speed at sea level (full throttle)"),
    "cruise75_8000_ktas": (120.0, "KTAS", "SPEC", "cruise at 75 % power, 8000 ft"),
    # takeoff (Figure 5-5, short field, 2400 lb, flaps 10, full throttle before brake release,
    # paved level dry runway, zero wind)
    "takeoff_roll_ft": (892.5, "ft", "POH Fig. 5-5", "interp 15 C (860 at 10 C, 925 at 20 C); SPEC: 890"),
    "takeoff_50ft_ft": (1627.5, "ft", "POH Fig. 5-5", "interp 15 C; SPEC: 1625"),
    "liftoff_kias": (51.0, "KIAS", "POH Fig. 5-5", "lift off; 56 KIAS at 50 ft"),
    # landing (Figure 5-11, short field, flaps 30, power off, maximum braking)
    "landing_roll_ft": (540.0, "ft", "POH Fig. 5-11", "interp 15 C (530 at 10 C, 550 at 20 C); 61 KIAS at 50 ft"),
    # glide (Figure 3-1, page 3-3)
    "best_glide_kias": (65.0, "KIAS", "POH p. 3-3 / Fig. 3-1", "2400 lb, flaps up, propeller windmilling, zero wind"),
    "glide_ratio": (9.1, "1", "POH Fig. 3-1 (unverified)",
                    "the commonly quoted reading of the chart, 1.5 nm per 1000 ft; the scanned curve "
                    "could not be read here, so this value is flagged"),
}
