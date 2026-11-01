"""Parameters of the fanuc-pick example, shared by the builders, the reference and the optimizer.

Every value in `GLOBALS` becomes a global parameter of the models (`build_models.py`), so the
editor's Equations manager, the dashboard sliders, the batch runner (`run_model.jl`) and the
Python reference (`planner.py`, `reduced.py`) all read the same numbers.

The gripper is estimated from the video (FANUC LR-10iA/10 with the customer's 5-zone gripper,
00:29 to 00:35): five pneumatic cylinders, one in the centre and four around it, each rod
ending in a 1.5-fold bellows cup. Every dimension is a parameter for the real values.
"""

from __future__ import annotations

import math

G0 = 9.81
P_ATM = 101325.0
N_ZONES = 5

# ------------------------------------------------------------------ gripper (estimated from the video)
GRIPPER = dict(
    h_base=0.045,     # m     flange to the cylinder mounting face (adapter plate and valve block)
    m_base=0.50,      # kg    adapter, valve block, fittings
    L_cyl=0.150,      # m     cylinder body length
    D_cyl=0.032,      # m     cylinder body diameter (16 mm bore)
    m_cyl=0.10,       # kg    one cylinder body
    rod0=0.015,       # m     rod length out of the body when retracted (to the cup mount)
    m_rod=0.06,       # kg    rod, cup holder and cup (the moving mass of a zone)
    stroke=0.075,     # m     cylinder stroke
    r_p=0.040,        # m     pitch radius of the four outer cylinders
    lay_deg=0.0,      # deg   rotation of the outer four (0: on the gripper x/y axes, "+"; 45: "x")
    F_ext=120.0,      # N     extend force (6 bar on a 16 mm bore)
    F_ret=100.0,      # N     retract force (annulus, 6 mm rod)
    v_ext=0.5,        # m/s   extend speed (meter-out flow control)
    v_ret=0.5,        # m/s   retract speed
    k_stop=2.0e5,     # N/m   end-stop stiffness of the cylinder
    b_stop=300.0,     # N s/m end-stop damping (cushion)
    kt_rod=5.0e4,     # N/m   lateral stiffness of a rod in its guide (16 mm cylinder, rod out ~90 mm)
    kr_rod=200.0,     # N m/rad bending stiffness of the rod guide
    J_rod=2.0e-5,     # kg m^2 rod inertia about its tip (lumped at the cup mount)
)
#: cup positions in the gripper frame (unrotated layout): centre, +x, +y, -x, -y
ZONE_DIRS = [(0.0, 0.0), (1.0, 0.0), (0.0, 1.0), (-1.0, 0.0), (0.0, -1.0)]

CUP = dict(
    L0=0.030,         # m      mount-to-lip rest length
    A_eff=5.0e-4,     # m^2    effective suction area (25 mm effective diameter)
    D_lip=0.032,      # m      lip diameter
    k_ax=2500.0,      # N/m    bellows axial stiffness
    d_ax=8.0,         # N s/m
    k_lat=1500.0,     # N/m    bellows lateral stiffness
    d_lat=5.0,        # N s/m
    k_tilt=1.0,       # N m/rad
    k_tor=1.5,        # N m/rad
    d_rot=0.005,      # N m s/rad
    mu=0.5,           # lip friction on cardboard
    V_cup=8.0e-6,     # m^3    cup chamber and hose
    A_lip0=1.5e-8,    # m^2    sealed-lip roughness leak
    F_min=0.1,        # N      residual friction capacity of a free lip
    # nonlinear bellows (stdlib SuctionCup). ESTIMATES for a 1.5-fold bellows cup with a 32-33 mm
    # lip (the class of e.g. Schmalz FSGA 33 / Piab BL30-2): about 6 mm usable compression before
    # the folds stack, a vacuum lift stroke of about 4 mm at 60 kPa, and a bellows that is
    # noticeably stiffer sideways when evacuated and softer when pulled out.
    s_bot=0.006,      # m      compression stroke before the folds bottom
    k_bot=2.5e4,      # N/m    bottoming stiffness scale (slope n_bot k_bot at x_bot over-stroke)
    n_bot=3.0,        # 1      bottoming exponent
    x_bot=1.0e-3,     # m      reference over-stroke
    A_fold=1.7e-4,    # m^2    folded annulus: lift stroke A_fold dp / k_ax = 4.1 mm at 60 kPa
    c_vac=1.0,        # 1      lateral/tilt stiffness x (1 + dp/p_atm): +59 % at 60 kPa
    c_ext=3.0,        # 1      lateral/tilt stiffness x exp(-3 ext/L0): -26 % at 3 mm extension
)

#: vacuum: one compact ejector per zone (see README: isolation and zone switching)
VACUUM = dict(
    dp_max=6.0e4,     # Pa     ejector end vacuum
    Q_max=2.0e-4,     # m^3/s  12 l/min free air per zone
    perm=4.0e-7,      # m/(s Pa) cardboard permeance
    G_rel=2.0e-7,     # m^3/(s Pa) release (vent) conductance
)

# ------------------------------------------------------------------ parcel and loose contents
PARCEL = dict(L_p=0.30, W_p=0.20, H_p=0.12, m_p=1.5, cx=0.0, cy=0.0, cz=0.0)
#: carton shell of the loose-content scenarios (the content is a separate body)
SHELL = dict(m_shell=0.6, wall=0.004)
SPHERE = dict(r_s=0.040, m_s=0.5)        # a rubber ball (80 mm, density 1.9)
CYLINDER = dict(r_c=0.035, l_c=0.120, m_c=0.5)   # a filled 0.46 l bottle
CONTENT_CONTACT = dict(k_w=3.0e4, xref_w=1.0e-3, c_w=3.0, mu_w=0.35, vs_w=2.0e-3)
#: parcel on the support surface (conveyor and place table, one plane)
FLOOR = dict(k=2.0e5, xref=1.0e-3, c=5.0, mu=0.5, vs=1.0e-3)

# ------------------------------------------------------------------ cell and task
CELL = dict(
    z_s=0.0,          # m      support surface (conveyor and place table) above the robot base
    xp=0.50, yp=-0.35, psip_deg=0.0,     # pick: parcel centre and yaw
    xq=0.50, yq=0.35, psiq_deg=90.0,     # place: parcel centre and yaw
    psig_deg=0.0,     # deg    gripper yaw relative to the parcel
    gx=0.0, gy=0.0,   # m      grip point (gripper centre) in the parcel frame
    e_m=0.005,        # m      edge margin of an active cup (lip inside the top face)
)

MOTION = dict(
    family=3.0,       # 1 joint PTP with stops, 2 Cartesian with stops, 3 Cartesian blended, 4 joint blended
    kv=0.8, ka=0.8,   # joint moves: share of the joint rate / acceleration (and jerk) limits
    v_c=1.5, a_c=8.0, j_c=150.0,  # Cartesian moves: TCP speed (m/s), acceleration (m/s^2), jerk (m/s^3)
    w_c=4.0, al_c=25.0, jw_c=500.0,  # Cartesian moves: yaw rate, acceleration, jerk (rad/s, rad/s^2, rad/s^3)
    lam=0.5,          # jerk phase as a share of each acceleration phase (0 trapezoid, 1 pure S)
    r_b=0.05,         # m      blend distance (families 3 and 4): the next move starts r_b before the corner
    H_lift=0.08,      # m      robot lift above the pick contact pose (and lower at the place)
    h_app=0.06,       # m      approach height above the pick contact pose
    h_dep=0.06,       # m      depart height above the place contact pose
    t0=0.05,          # s      start of the approach
    t_ext=0.20,       # s      cylinder extension starts this long before the pick contact
    t_vac=0.05,       # s      vacuum on this long before the pick contact
    T_seal=0.10,      # s      wait at the pick for the vacuum to build
    ret_hold=0.0,     # 1      retract the cylinders while holding (1) or keep them out (0)
    t_ret=0.05,       # s      retract this long after the lift start (ret_hold = 1)
    t_ext2=0.20,      # s      extend again this long before the place contact (ret_hold = 1)
    T_rel=0.08,       # s      wait at the place after the vacuum is off (vent)
    d_press=0.003,    # m      bellows press at the pick contact pose
    M_req=0.5,        # 1      required holding margin 1 - U (safety factor 2)
    # waiter (bartender) motion: the tool axis follows the specific force of the carried load
    tilt_gain=0.0,    # 1      share of the tilt that aligns the cup axis with a - g (0 off, 1 full)
    tilt_max_deg=25.0,  # deg  largest tilt (smooth saturation)
    T_tw=0.08,        # s      tilt filter: the acceleration is averaged over a triangle of +-T_tw
    T_tr=0.10,        # s      the tilt fades in after the lift start and out before the place contact
    # family 5 (free timing): every move has its own duration and start
    f5_Ta=0.20, f5_Tp=0.20,   # s  approach and depart durations
    f5_Tl=0.15, f5_Td=0.15,   # s  lift and lower durations (within the carry)
    f5_Tx=0.80, f5_ox=0.05, f5_ex=0.10,  # s  transfer duration, its start after the lift start, the carry after it
    f5_ax=0.40, f5_dx=0.40,   # 1  acceleration and deceleration phase of the transfer (fractions of f5_Tx)
    f5_y0=0.0, f5_y1=1.0,     # 1  the yaw turns between these fractions of the carry
)

FAMILY_NAMES = {1: "joint PTP, stops", 2: "Cartesian, stops", 3: "Cartesian, blended", 4: "joint, blended", 5: "free timing"}

TS = 0.001            # s      planner period (the robot interpolation tick)
T_END_PAD = 0.30      # s      simulated time after the cycle end


# ================================================================== the global parameter table
def _n(x: float) -> str:
    text = repr(float(x))
    return text[:-2] if text.endswith(".0") and "e" not in text else text


def rest_penetration(mass: float) -> float:
    """Penetration of the four parcel corners at rest on the support (Hertz law of ContactPoint)."""
    f = mass * G0 / 4.0
    return (f * math.sqrt(FLOOR["xref"]) / FLOOR["k"]) ** (2.0 / 3.0)


def global_rows() -> list[tuple[str, str, str, str]]:
    """(name, value expression, unit, description) of every global parameter, in order."""
    import fanuc as fz

    g, c, v, pa, m, ce = GRIPPER, CUP, VACUUM, PARCEL, MOTION, CELL
    rows = [
        # task
        ("family", _n(m["family"]), "1", "Trajectory family: 1 joint PTP with stops, 2 Cartesian with stops, 3 Cartesian blended, 4 joint blended"),
        ("kv", _n(m["kv"]), "1", "Joint moves: share of the datasheet joint rate limits"),
        ("ka", _n(m["ka"]), "1", "Joint moves: share of the joint acceleration and jerk limits"),
        ("v_c", _n(m["v_c"]), "m/s", "Cartesian moves: TCP speed limit"),
        ("a_c", _n(m["a_c"]), "m/s^2", "Cartesian moves: TCP acceleration limit"),
        ("j_c", _n(m["j_c"]), "m/s^3", "Cartesian moves: TCP jerk limit"),
        ("w_c", _n(m["w_c"]), "rad/s", "Cartesian moves: yaw rate limit"),
        ("al_c", _n(m["al_c"]), "rad/s^2", "Cartesian moves: yaw acceleration limit"),
        ("jw_c", _n(m["jw_c"]), "rad/s^3", "Cartesian moves: yaw jerk limit"),
        ("lam", _n(m["lam"]), "1", "Jerk phase as a share of each acceleration phase (0 trapezoid, 1 pure S-curve)"),
        ("r_b", _n(m["r_b"]), "m", "Blend distance (families 3, 4): the transfer starts when the lift has r_b to go"),
        ("H_lift", _n(m["H_lift"]), "m", "Robot lift above the pick contact pose (and lowering at the place)"),
        ("h_app", _n(m["h_app"]), "m", "Approach height above the pick contact pose"),
        ("h_dep", _n(m["h_dep"]), "m", "Depart height above the place contact pose"),
        ("t0", _n(m["t0"]), "s", "Start of the approach"),
        ("t_ext", _n(m["t_ext"]), "s", "Cylinder extension starts this long before the pick contact"),
        ("t_vac", _n(m["t_vac"]), "s", "Vacuum on this long before the pick contact"),
        ("T_seal", _n(m["T_seal"]), "s", "Wait at the pick for the vacuum to build"),
        ("ret_hold", _n(m["ret_hold"]), "1", "Retract the cylinders while holding (1) or keep them extended (0)"),
        ("t_ret", _n(m["t_ret"]), "s", "Retract this long after the lift start (ret_hold = 1)"),
        ("t_ext2", _n(m["t_ext2"]), "s", "Extend again this long before the place contact (ret_hold = 1)"),
        ("T_rel", _n(m["T_rel"]), "s", "Wait at the place after the vacuum is switched off"),
        ("d_press", _n(m["d_press"]), "m", "Bellows press at the pick contact pose"),
        ("M_req", _n(m["M_req"]), "1", "Required holding margin 1 - U (0.5 = safety factor 2)"),
        ("tilt_gain", _n(m["tilt_gain"]), "1", "Waiter motion: share of the tilt that turns the cup axis into the specific force a - g of the load (0 off, 1 full)"),
        ("tilt_max_deg", _n(m["tilt_max_deg"]), "deg", "Waiter motion: largest tool tilt (smooth saturation)"),
        ("T_tw", _n(m["T_tw"]), "s", "Waiter motion: the planned load acceleration is averaged over a triangle window of +-T_tw (smooth wrist motion)"),
        ("T_tr", _n(m["T_tr"]), "s", "Waiter motion: the tilt fades in over T_tr after the lift start and out over T_tr before the place contact"),
        ("f5_Ta", _n(m["f5_Ta"]), "s", "Family 5: approach duration"),
        ("f5_Tp", _n(m["f5_Tp"]), "s", "Family 5: depart duration"),
        ("f5_Tl", _n(m["f5_Tl"]), "s", "Family 5: lift duration (H_lift, from the lift start)"),
        ("f5_Td", _n(m["f5_Td"]), "s", "Family 5: lower duration (H_lift, ending at the place contact)"),
        ("f5_Tx", _n(m["f5_Tx"]), "s", "Family 5: transfer duration (straight line, own profile)"),
        ("f5_ox", _n(m["f5_ox"]), "s", "Family 5: transfer start after the lift start"),
        ("f5_ex", _n(m["f5_ex"]), "s", "Family 5: carry time after the transfer end (the lower finishes)"),
        ("f5_ax", _n(m["f5_ax"]), "1", "Family 5: acceleration phase of the transfer, share of its duration"),
        ("f5_dx", _n(m["f5_dx"]), "1", "Family 5: deceleration phase of the transfer, share of its duration"),
        ("f5_y0", _n(m["f5_y0"]), "1", "Family 5: the yaw turn starts at this share of the carry"),
        ("f5_y1", _n(m["f5_y1"]), "1", "Family 5: the yaw turn ends at this share of the carry"),
        # cell
        ("z_s", _n(ce["z_s"]), "m", "Support surface (conveyor and place table) above the robot base"),
        ("xp", _n(ce["xp"]), "m", "Pick: parcel centre x"),
        ("yp", _n(ce["yp"]), "m", "Pick: parcel centre y"),
        ("psip_deg", _n(ce["psip_deg"]), "deg", "Pick: parcel yaw"),
        ("xq", _n(ce["xq"]), "m", "Place: parcel centre x"),
        ("yq", _n(ce["yq"]), "m", "Place: parcel centre y"),
        ("psiq_deg", _n(ce["psiq_deg"]), "deg", "Place: parcel yaw"),
        ("psig_deg", _n(ce["psig_deg"]), "deg", "Gripper yaw relative to the parcel"),
        ("gx", _n(ce["gx"]), "m", "Grip point (gripper centre) in the parcel frame, x"),
        ("gy", _n(ce["gy"]), "m", "Grip point in the parcel frame, y"),
        ("e_m", _n(ce["e_m"]), "m", "Edge margin of an active cup (its lip inside the top face)"),
        ("zone1", "1", "1", "Zone 1 (centre) allowed (1) or off (0)"),
        ("zone2", "1", "1", "Zone 2 (+x) allowed"),
        ("zone3", "1", "1", "Zone 3 (+y) allowed"),
        ("zone4", "1", "1", "Zone 4 (-x) allowed"),
        ("zone5", "1", "1", "Zone 5 (-y) allowed"),
        # parcel
        ("L_p", _n(pa["L_p"]), "m", "Parcel length (parcel x)"),
        ("W_p", _n(pa["W_p"]), "m", "Parcel width (parcel y)"),
        ("H_p", _n(pa["H_p"]), "m", "Parcel height"),
        ("m_shell", _n(SHELL["m_shell"]), "kg", "Carton shell mass (loose-content models)"),
        ("wall", _n(SHELL["wall"]), "m", "Carton wall thickness (loose-content models)"),
        ("r_s", _n(SPHERE["r_s"]), "m", "Loose sphere radius"),
        ("m_s", _n(SPHERE["m_s"]), "kg", "Loose sphere mass"),
        ("r_c", _n(CYLINDER["r_c"]), "m", "Loose cylinder radius"),
        ("l_c", _n(CYLINDER["l_c"]), "m", "Loose cylinder length"),
        ("m_c", _n(CYLINDER["m_c"]), "kg", "Loose cylinder mass"),
        ("m_p", _n(pa["m_p"]), "kg", "Parcel mass (the plain carton; shell + content in the loose-content models)"),
        ("cx", _n(pa["cx"]), "m", "Centre of mass offset from the box centre, x (parcel frame)"),
        ("cy", _n(pa["cy"]), "m", "Centre of mass offset, y"),
        ("cz", _n(pa["cz"]), "m", "Centre of mass offset, z (up)"),
        ("Jpx", "m_p*(W_p^2 + H_p^2)/12", "kg*m^2", "Parcel inertia about its x axis (uniform box)"),
        ("Jpy", "m_p*(L_p^2 + H_p^2)/12", "kg*m^2", "Parcel inertia about y"),
        ("Jpz", "m_p*(L_p^2 + W_p^2)/12", "kg*m^2", "Parcel inertia about z"),
        ("k_w", _n(CONTENT_CONTACT["k_w"]), "N/m", "Content-wall contact stiffness"),
        ("c_w", _n(CONTENT_CONTACT["c_w"]), "s/m", "Content-wall Hunt-Crossley damping"),
        ("mu_w", _n(CONTENT_CONTACT["mu_w"]), "1", "Content-wall friction coefficient"),
        # gripper
        ("h_base", _n(g["h_base"]), "m", "Flange to the cylinder mounting face"),
        ("m_base", _n(g["m_base"]), "kg", "Adapter plate, valve block and fittings"),
        ("L_cyl", _n(g["L_cyl"]), "m", "Cylinder body length"),
        ("D_cyl", _n(g["D_cyl"]), "m", "Cylinder body diameter"),
        ("m_cyl", _n(g["m_cyl"]), "kg", "Mass of one cylinder body"),
        ("rod0", _n(g["rod0"]), "m", "Rod length out of the body when retracted (to the cup mount)"),
        ("m_rod", _n(g["m_rod"]), "kg", "Moving mass of a zone: rod, cup holder and cup"),
        ("stroke", _n(g["stroke"]), "m", "Cylinder stroke"),
        ("r_p", _n(g["r_p"]), "m", "Pitch radius of the four outer cylinders"),
        ("lay_deg", _n(g["lay_deg"]), "deg", "Rotation of the outer four cylinders (0 '+', 45 'x')"),
        ("F_ext", _n(g["F_ext"]), "N", "Cylinder extend force"),
        ("F_ret", _n(g["F_ret"]), "N", "Cylinder retract force"),
        ("v_ext", _n(g["v_ext"]), "m/s", "Cylinder extend speed (flow control)"),
        ("v_ret", _n(g["v_ret"]), "m/s", "Cylinder retract speed"),
        ("k_stop", _n(g["k_stop"]), "N/m", "Cylinder end-stop stiffness"),
        ("b_stop", _n(g["b_stop"]), "N*s/m", "Cylinder end-stop damping (cushion)"),
        ("kt_rod", _n(g["kt_rod"]), "N/m", "Lateral stiffness of a rod in its guide"),
        ("bt_rod", "0.6*sqrt(kt_rod*m_rod)", "N*s/m", "Lateral damping of a rod (damping ratio 0.3)"),
        ("kr_rod", _n(g["kr_rod"]), "N*m/rad", "Bending stiffness of a rod in its guide"),
        ("J_rod", _n(g["J_rod"]), "kg*m^2", "Rod inertia about its tip (bending)"),
        ("br_rod", "0.6*sqrt(kr_rod*J_rod)", "N*m*s/rad", "Bending damping of a rod (damping ratio 0.3)"),
        ("q_r0", "-(F_ret - m_rod*9.81)/k_stop", "m", "Rod start position: pressed into the retract stop"),
        # cups
        ("L0", _n(c["L0"]), "m", "Cup rest length (mount to lip)"),
        ("A_eff", _n(c["A_eff"]), "m^2", "Effective suction area per cup"),
        ("D_lip", _n(c["D_lip"]), "m", "Lip diameter"),
        ("k_ax", _n(c["k_ax"]), "N/m", "Bellows axial stiffness"),
        ("d_ax", _n(c["d_ax"]), "N*s/m", "Bellows axial damping"),
        ("k_lat", _n(c["k_lat"]), "N/m", "Bellows lateral stiffness"),
        ("d_lat", _n(c["d_lat"]), "N*s/m", "Bellows lateral damping"),
        ("k_tilt", _n(c["k_tilt"]), "N*m/rad", "Bellows bending stiffness"),
        ("k_tor", _n(c["k_tor"]), "N*m/rad", "Bellows torsional stiffness"),
        ("d_rot", _n(c["d_rot"]), "N*m*s/rad", "Bellows rotational damping"),
        ("mu", _n(c["mu"]), "1", "Lip friction coefficient on cardboard"),
        ("V_cup", _n(c["V_cup"]), "m^3", "Cup chamber and hose volume"),
        ("A_lip0", _n(c["A_lip0"]), "m^2", "Sealed-lip leak area per cup"),
        ("F_min", _n(c["F_min"]), "N", "Residual friction capacity of a free lip"),
        ("s_bot", _n(c["s_bot"]), "m", "Cup compression stroke before the folds bottom (estimate)"),
        ("k_bot", _n(c["k_bot"]), "N/m", "Cup bottoming stiffness scale (estimate)"),
        ("n_bot", _n(c["n_bot"]), "1", "Cup bottoming exponent"),
        ("x_bot", _n(c["x_bot"]), "m", "Reference over-stroke of the bottoming law"),
        ("A_fold", _n(c["A_fold"]), "m^2", "Folded bellows annulus: vacuum lift stroke A_fold*dp/k_ax (estimate)"),
        ("c_vac", _n(c["c_vac"]), "1", "Cup lateral/tilt stiffness rise with vacuum, 1 + c_vac*dp/p_atm (estimate)"),
        ("c_ext", _n(c["c_ext"]), "1", "Cup lateral/tilt stiffness fall with extension, exp(-c_ext*ext/L0) (estimate)"),
        ("h_stack", "h_base + L_cyl + rod0 + stroke + L0 - d_press", "m", "Flange to the pressed cup lip with the cylinders extended"),
        ("dp_max", _n(v["dp_max"]), "Pa", "Ejector end vacuum (per zone)"),
        ("Q_max", _n(v["Q_max"]), "m^3/s", "Ejector suction flow at zero vacuum (free air, per zone)"),
        ("perm", _n(v["perm"]), "m/(s*Pa)", "Air permeance of the parcel (cardboard)"),
        ("G_rel", _n(v["G_rel"]), "m^3/(s*Pa)", "Release (vent) conductance of an ejector"),
        # tool mass (wrist load check; the rods also move in the model)
        ("m_g", "m_base + 5*(m_cyl + m_rod)", "kg", "Gripper mass"),
        ("zc_g", "(m_base*h_base/2 + 5*m_cyl*(h_base + L_cyl/2) + 5*m_rod*(h_base + L_cyl + rod0 + stroke))/m_g",
         "m", "Gripper centre of mass below the flange (cylinders extended)"),
        ("Jg45", "m_base*(h_base/2 - zc_g)^2 + 5*m_cyl*((h_base + L_cyl/2 - zc_g)^2 + L_cyl^2/12) + 5*m_rod*(h_base + L_cyl + rod0 + stroke - zc_g)^2 + 2*(m_cyl + m_rod)*r_p^2",
         "kg*m^2", "Gripper inertia about a horizontal axis through its centre of mass (point-mass estimate)"),
        ("Jg6", "4*(m_cyl + m_rod)*r_p^2 + m_base*0.1^2/6", "kg*m^2", "Gripper inertia about the tool axis (point-mass estimate)"),
        # robot: LR-10iA/10 datasheet limits (fanuc.py)
        ("m_max", _n(fz.LR10_PAYLOAD), "kg", "LR-10iA/10 payload"),
        ("M45_max", _n(fz.LR10_M_WRIST[0]), "N*m", "LR-10iA/10 allowable load moment at the wrist, J4 and J5"),
        ("M6_max", _n(fz.LR10_M_WRIST[2]), "N*m", "LR-10iA/10 allowable load moment at the wrist, J6"),
        ("I45_max", _n(fz.LR10_I_WRIST[0]), "kg*m^2", "LR-10iA/10 allowable load inertia at the wrist, J4 and J5"),
        ("I6_max", _n(fz.LR10_I_WRIST[2]), "kg*m^2", "LR-10iA/10 allowable load inertia at the wrist, J6"),
    ]
    for j in range(6):
        rows.append((f"qdmax{j + 1}", _n(fz.QD_MAX[j]), "rad/s",
                     f"J{j + 1} rate limit (LR-10iA/10 datasheet {fz.QD_MAX[j] / fz.DEG:.0f} deg/s)"))
    for j in range(6):
        rows.append((f"qddmax{j + 1}", _n(fz.QDD_MAX[j]), "rad/s^2",
                     f"J{j + 1} acceleration limit (assumed: the rate limit in {fz.T_ACC[j]:.2f} s)"))
    for j in range(6):
        rows.append((f"qdddmax{j + 1}", _n(fz.QDDD_MAX[j]), "rad/s^3",
                     f"J{j + 1} jerk limit (assumed: the acceleration limit in {fz.T_JERK:.2f} s)"))
    for j in range(6):
        rows.append((f"qmin{j + 1}", _n(fz.Q_MIN[j]), "rad", f"J{j + 1} lower range limit ({fz.Q_MIN[j] / fz.DEG:.0f} deg)"))
        rows.append((f"qmax{j + 1}", _n(fz.Q_MAX[j]), "rad", f"J{j + 1} upper range limit ({fz.Q_MAX[j] / fz.DEG:.0f} deg)"))
    rows += [
        # start pose of the gripper (approach start A) and the parcel at rest
        ("psA", "(psip_deg + psig_deg)*deg", "rad", "Gripper yaw at the pick"),
        ("xA", "xp + cos(psip_deg*deg)*gx - sin(psip_deg*deg)*gy", "m", "Gripper (flange) x at the pick"),
        ("yA", "yp + sin(psip_deg*deg)*gx + cos(psip_deg*deg)*gy", "m", "Gripper (flange) y at the pick"),
        ("zA", "z_s + H_p + h_stack + h_app", "m", "Gripper (flange) height at the approach start"),
        ("pen0", _n(rest_penetration(PARCEL["m_p"])), "m", "Rest penetration of the parcel corners in the support"),
        ("rz0", "-(h_app + stroke + L0 - d_press + pen0 - q_r0)", "m", "Cup lip to parcel top at the start, cylinders retracted (cup frame z)"),
    ]
    return rows


def eval_globals(rows, overrides: dict | None = None) -> dict:
    """Numeric values of the global table (expressions in the bgsim syntax: ^ is a power)."""
    overrides = overrides or {}
    env: dict = {"deg": math.pi / 180.0, "pi": math.pi, "sqrt": math.sqrt, "sin": math.sin, "cos": math.cos,
                 "max": max, "min": min, "abs": abs}
    out = {}
    for name, value, _unit, _desc in rows:
        expr = str(overrides.get(name, value)).replace("^", "**")
        out[name] = float(eval(expr, {"__builtins__": {}}, env))  # noqa: S307 - our own table
        env[name] = out[name]
    unknown = set(overrides) - set(out)
    if unknown:
        raise KeyError(f"unknown globals {sorted(unknown)}")
    return out


def global_values(overrides: dict | None = None) -> dict:
    return eval_globals(global_rows(), overrides)
