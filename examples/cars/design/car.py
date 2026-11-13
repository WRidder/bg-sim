"""The vehicle bond graph of the `cars` example (one function per part), shared by every model.

Multibond structure (chassis frame x forward, y left, z up, at the sprung CG):

    PoseIntegrator3D -- Chassis (RigidBody3D) -- Aero wrench (ExternalWrenchSpatial)
                          |  per corner (FL, FR, RL, RR: instances of the library subsystems
                          |  <Vehicle>FrontCorner and <Vehicle>RearCorner, see corner_definition):
                          Mount (FixedTransform3DNeutral) -- Susp (Prismatic3D, chassis z)
                             front: -- Upright (RigidBody3D) -- Steer (Revolute3D, kingpin z) --
                             Hub (FixedTransform3DNeutral, Rx(-90 deg): axle = carrier z, to the left)
                             -- Carrier (RigidBody3D: wheel + hub) -- Wheel (Rotor3D) + Tyre (stdlib Tyre)

The suspension travel is the Prismatic3D's drive port on a 1-junction with the Strut (and the
anti-roll bar); the wheel spin is the Rotor3D's drive port on a 1-junction with the tyre's spin
port, the brake and (driven wheels) the drive shaft. The electric driveline is 1-D bond graph:

    Battery -- 0 (DC bus) -- TractionMachine (a modulated TF: inverter + motor, u = tau/V)
      -- 1 (rotor: I, drag R, speed)
      -- elastic shaft (C, R) -- 1 -- TF (reduction) -- 0 (differential carrier)
      -- TF 2 -- 1 (wheel spin)  x 2           (one motor per driven axle on the same bus)
plus a viscous limited-slip R between the two spin junctions of each driven axle.
"""

from __future__ import annotations

from copy import deepcopy

from bg import Diagram, Q_CARRIER, ex, num, pose_params, vec
from vehicles import CORNERS, G0

IDENT = (1.0, 0.0, 0.0, 0.0)


def _drv(drv: dict | None, role: str) -> str:
    """The node that carries a driver signal (`y`): the role's name unless `drv` renames it
    (the sim models use the lower-case export markers)."""
    return (drv or {}).get(role, role)


def tyre_params(ty: dict) -> dict:
    keys = ("R0", "kz", "cz", "Fz0", "mux", "muy", "dmu", "Kx", "Cx", "Ex", "Ky", "Ky2", "Cy", "Ey",
            "cx", "cy", "dx", "dy", "frr", "wrr", "vN")
    return {k: num(ty[k]) for k in keys}


def corner(v: dict, c: str, start: dict) -> Diagram:
    """One corner. Ports: power `mount` (to the chassis body), `travel` (the suspension
    1-junction, for the anti-roll bar), `spin` and `spin2` (the wheel spin junction: drive shaft,
    limited slip); inputs `gc` (chassis pose), `o`, `fr` (ground plane), `mus`, `brake` (torque
    capacity) and, steered, `steer` (road-wheel angle); outputs `g` (carrier pose), the tyre's
    world force `fx`, `fy`, `fz`, the spin angle `th` and `Fz`."""
    k = v["corners"][c]
    ty = v["tyre"]
    jt = v["joint"]
    d = Diagram()
    x0, y0 = 0, 0
    pos = (k["x"], k["y"], k["z"])
    re = ty["R0"] - k["defl"]
    w0 = start.get("v", 0.0) / re
    dz = start.get("dz", 0.0)
    # ---- suspension: mount transform, prismatic joint along chassis z, strut
    d.node("Mount", "stdlib:multibond/FixedTransform3DNeutral", x0, y0,
           params=pose_params(IDENT, (-pos[0], -pos[1], -pos[2])))
    d.node("Susp", "stdlib:spatial/Prismatic3D", x0 + 200, y0,
           params={"kr": num(jt["kr"]), "br": num(jt["br"]), "kt": num(jt["kt"]), "bt": num(jt["bt"]),
                   "q0": num(-dz)})
    d.bond("Mount", "a", "Susp", "parent")
    d.junction("Travel", 1, x0 + 200, y0 + 160)
    d.bond("Travel", None, "Susp", "drive")
    d.node("Strut", "project:Strut", x0 + 200, y0 + 300,
           params={"k": num(k["k"]), "F0": num(k["spring"]), "cb": num(k["c_bump"]), "cr": num(k["c_reb"]),
                   "bump": num(k["bump"]), "droop": num(k["droop"]), "k_stop": num(v["k_stop"])},
           starts={"x": num(-dz)})
    d.bond("Travel", None, "Strut", "j")
    # ---- poses
    d.node("MountPose", "stdlib:spatial/LocalPose3D", x0, y0 + 460, params=pose_params(IDENT, pos))
    d.node("Pm", "stdlib:multibond/ComposePose3D", x0 + 200, y0 + 460)
    d.node("Ps", "stdlib:multibond/ComposePose3D", x0 + 400, y0 + 460)
    d.sig("MountPose", "g", "Pm", "gl")
    d.sig("Pm", "g", "Ps", "gp")
    d.sig("Susp", "pose", "Ps", "gl")
    d.node("HubPose", "stdlib:spatial/LocalPose3D", x0 + 600, y0 + 600, params=pose_params(Q_CARRIER, (0, 0, 0)))
    d.node("Pc", "stdlib:multibond/ComposePose3D", x0 + 800, y0 + 460)
    d.sig("HubPose", "g", "Pc", "gl")
    mc, mu_ = v["m_carrier"], v["m_upright"]
    vs = start.get("v", 0.0)
    if k["steered"]:
        d.node("UprightFT", "stdlib:multibond/FixedTransform3DNeutral", x0 + 400, y0)
        d.node("Upright", "stdlib:spatial/RigidBody3D", x0 + 600, y0,
               params={"m": num(mu_), "J": vec(v["J_upright"]), "g0": num(G0)},
               starts={"inertia/P": vec([0, 0, 0, mu_ * vs, 0, 0])})
        d.bond("Susp", "child", "UprightFT", "a")
        d.bond("UprightFT", "b", "Upright", "p")
        d.node("KingFT", "stdlib:multibond/FixedTransform3DNeutral", x0 + 600, y0 - 160)
        d.node("Steer", "stdlib:spatial/Revolute3D", x0 + 800, y0 - 160,
               params={"kr": num(jt["kr"]), "br": num(jt["br"]), "kt": num(jt["kt"]), "bt": num(jt["bt"]),
                       "q0": num(start.get("steer", {}).get(c, 0.0))})
        d.bond("Upright", "p", "KingFT", "b")
        d.bond("KingFT", "a", "Steer", "parent")
        d.node("HubFT", "stdlib:multibond/FixedTransform3DNeutral", x0 + 1000, y0 - 160,
               params=pose_params(Q_CARRIER, (0, 0, 0)))
        d.bond("Steer", "child", "HubFT", "a")
        d.node("SteerAct", "stdlib:bondgraph/MSe", x0 + 800, y0 - 320)
        d.bond("SteerAct", "p", "Steer", "drive")
        d.node("Servo", "project:SteerServo", x0 + 1000, y0 - 320,
               params={"k": num(v["k_steer"]), "c": num(v["c_steer"])})
        d.sig("Steer", "qout", "Servo", "q")
        d.sig("Steer", "qdout", "Servo", "qd")
        d.sig("Servo", "tau", "SteerAct", "u")
        d.port("steer", "input", "Servo", "ref", "rad")
        d.node("Pk", "stdlib:multibond/ComposePose3D", x0 + 600, y0 + 460)
        d.sig("Ps", "g", "Upright", "g")
        d.sig("Ps", "g", "Pk", "gp")
        d.sig("Steer", "pose", "Pk", "gl")
        d.sig("Pk", "g", "Pc", "gp")
    else:
        d.node("HubFT", "stdlib:multibond/FixedTransform3DNeutral", x0 + 400, y0,
               params=pose_params(Q_CARRIER, (0, 0, 0)))
        d.bond("Susp", "child", "HubFT", "a")
        d.sig("Ps", "g", "Pc", "gp")
    # ---- wheel: carrier body, rotor, tyre, spin junction, brake
    d.node("Carrier", "stdlib:spatial/RigidBody3D", x0 + 1200, y0,
           params={"m": num(mc), "J": vec(v["J_carrier"]), "g0": num(G0)},
           starts={"inertia/P": vec([0, 0, 0, mc * vs, 0, 0])})
    d.bond("HubFT", "b", "Carrier", "p")
    d.sig("Pc", "g", "Carrier", "g")
    d.node("Wheel", "stdlib:spatial/Rotor3D", x0 + 1400, y0, params={"Ja": num(v["Jw"])},
           starts={"h": num(v["Jw"] * w0)})
    d.bond("Carrier", "p", "Wheel", "p")
    d.node("Tyre", "stdlib:contact/Tyre", x0 + 1400, y0 + 200, params=tyre_params(ty))
    d.bond("Carrier", "p", "Tyre", "p")
    d.sig("Pc", "g", "Tyre", "g")
    d.junction("Spin", 1, x0 + 1600, y0 + 100)
    d.bond("Spin", None, "Wheel", "drive")
    d.bond("Spin", None, "Tyre", "spin")
    d.node("Brake", "stdlib:rotation/Brake", x0 + 1800, y0 + 100,
           params={"mu_s": "1.0", "mu_c": "1.0", "r_eff": "1.0", "n_faces": "1.0", "w_s": "1.0",
                   "w_eps": num(v["brake_w_eps"])})
    d.bond("Spin", None, "Brake", "a")
    d.node("SpinAngle", "stdlib:continuous/Integrator", x0 + 1600, y0 + 300)
    d.sig("Wheel", "w_rel", "SpinAngle", "u")
    # ---- ports (a subsystem port is an element port, so the junctions get TF adapters)
    d.power_port("mount", "Spatial", "Mount", "b", size=6)
    if v["k_arb"][0 if k["front"] else 1] > 0:   # the anti-roll bar of this axle
        d.node("TravelTF", "stdlib:bondgraph/TF", x0 + 400, y0 + 160, params={"n": "1.0"})
        d.bond("Travel", None, "TravelTF", "p1")
        d.power_port("travel", "Translation", "TravelTF", "p2")
    if k["driven"]:
        # the differential's half shaft (TF 2: the carrier turns at the mean of the two wheels)
        d.node("HalfShaft", "stdlib:bondgraph/TF", x0 + 1800, y0 - 100, params={"n": "2.0"})
        d.bond("HalfShaft", "p2", "Spin", None)
        d.power_port("spin", "Rotation", "HalfShaft", "p1")
        d.node("LsdTF", "stdlib:bondgraph/TF", x0 + 1800, y0 + 300, params={"n": "1.0"})
        d.bond("Spin", None, "LsdTF", "p2")
        d.power_port("spin2", "Rotation", "LsdTF", "p1")
    d.port("gc", "input", "Pm", "gp", size=7)
    d.port("o", "input", "Tyre", "o", "m", size=3)
    d.port("fr", "input", "Tyre", "fr", size=9)
    d.port("mus", "input", "Tyre", "mus")
    d.port("brake", "input", "Brake", "f_n", "N")
    d.port("g", "output", "Pc", "g", size=7)
    d.port("fx", "output", "Tyre", "Fwx", "N")
    d.port("fy", "output", "Tyre", "Fwy", "N")
    d.port("fz", "output", "Tyre", "Fwz", "N")
    d.port("th", "output", "SpinAngle", "y", "rad")
    for p in ("xc", "yc", "zc"):
        d.port(p, "output", "Tyre", p, "m")
    d.port("load", "output", "Tyre", "Fz", "N")
    d.port("kappa", "output", "Tyre", "kappa")
    d.port("alpha", "output", "Tyre", "alpha", "rad")
    d.port("omega", "output", "Tyre", "omega", "rad/s")
    d.port("susp", "output", "Strut", "travel", "m")
    return d


# What a corner instance sets for itself: the lateral position of the corner (the mount and its pose)
# and the start state (suspension travel, carrier and upright momentum, wheel spin). Everything
# else is the same at the left and right corner of an axle and in every model of the vehicle.
CORNER_PINS_PARAMS = ["Mount/y", "MountPose/y", "Susp/q0"]
CORNER_PINS_STARTS = ["Strut/x", "Carrier/inertia/P", "Wheel/h"]
CORNER_PINS_STARTS_STEERED = CORNER_PINS_STARTS + ["Upright/inertia/P"]


def corner_definition_name(v: dict, c: str) -> str:
    """The library subsystem of corner `c`: one per vehicle and axle (RacecarFrontCorner, ...)."""
    return f"{v['name'].capitalize()}{'Front' if v['corners'][c]['front'] else 'Rear'}Corner"


def _pins(v: dict, c: str) -> tuple[list[str], list[str]]:
    return CORNER_PINS_PARAMS, (CORNER_PINS_STARTS_STEERED if v["corners"][c]["steered"] else CORNER_PINS_STARTS)


def corner_definition(v: dict, c: str) -> dict:
    """library/<Vehicle><Front|Rear>Corner.bgsub.json: the corner of an axle (drawn from its left
    corner at rest; the instances pin the side and the start state). The four structural variants
    (steering group on the front corners, half shaft and limited-slip adapter on the driven ones,
    the anti-roll bar adapter where the axle has a bar) are exactly the four vehicle-axle pairs,
    whose parameters differ anyway, so there is one definition per pair and no nested core."""
    name = corner_definition_name(v, c)
    cd = corner(v, c[0] + "L", {})
    diagram = cd.doc("corner_")
    diagram.pop("subsystemPorts", None)
    params, starts = _pins(v, c)
    k = v["corners"][c]
    parts = ["front" if k["front"] else "rear"] + (["steered"] if k["steered"] else []) + \
        (["driven"] if k["driven"] else [])
    return {
        "format": "bgsim.subsystem", "name": name,
        "description": (f"One {' '.join(parts)} corner of the {v['title'].lower()}: mount, prismatic suspension "
                        "with the Strut, " + ("steering upright, kingpin revolute and servo, " if k["steered"] else "")
                        + "wheel carrier, wheel rotor, tyre, brake" + (", half shaft and limited-slip adapter" if k["driven"] else "")
                        + ". An instance pins the corner's side (Mount/y, MountPose/y), the start travel (Susp/q0, "
                        "Strut/x) and the start momenta. Generated by design/build_model.py (car.py)."),
        "ports": cd.ports,
        "diagram": diagram,
        "pins": {"params": params, "starts": starts},
    }


def corner_instance(d: Diagram, v: dict, c: str, start: dict, x: float, y: float) -> str:
    """Corner `c` as an instance of its library subsystem. The instance values are read from the
    corner drawn for this model and start, and the instance is checked to flatten to exactly that
    corner: the definition with the pinned values written in is the same diagram."""
    definition = corner_definition(v, c)
    cd = corner(v, c, start)
    nodes = {n["name"]: n for n in cd.nodes}
    pin_params, pin_starts = _pins(v, c)
    params = {key: nodes[key.split("/", 1)[0]]["params"][key.split("/", 1)[1]] for key in pin_params}
    starts = {key: nodes[key.split("/", 1)[0]]["starts"][key.split("/", 1)[1]] for key in pin_starts}
    linked = deepcopy(definition["diagram"]["nodes"])
    for field, values in (("params", params), ("starts", starts)):
        for key, value in values.items():
            node, rest = key.split("/", 1)
            next(n for n in linked if n["name"] == node)[field][rest] = value
    assert linked == cd.nodes, f"{c}: the corner differs from {definition['name']} in more than its pins"
    assert definition["ports"] == cd.ports, c
    strip = [{k: x[k] for k in ("kind", "from", "to")} for x in definition["diagram"]["connections"]]
    assert strip == [{k: x[k] for k in ("kind", "from", "to")} for x in cd.doc()["connections"]], c
    d.node(c, "project:" + definition["name"], x, y, params=params, starts=starts)
    return c


def chassis(d: Diagram, v: dict, start: dict, x0=0, y0=0) -> None:
    """Chassis body, pose integrator and the aerodynamic wrench (top level)."""
    vs = start.get("v", 0.0)
    h0 = v["h_s"] + start.get("dz", 0.0)
    d.node("Chassis", "stdlib:spatial/RigidBody3D", x0, y0,
           params={"m": num(v["m_s"]), "J": vec(v["J_s"]), "g0": num(G0)},
           starts={"inertia/P": vec([0, 0, 0, v["m_s"] * vs, 0, 0])})
    q = start.get("q", IDENT)
    d.node("Pose", "stdlib:multibond/PoseIntegrator3D", x0, y0 + 200,
           starts={"qw": ex(q[0]), "qx": ex(q[1]), "qy": ex(q[2]), "qz": ex(q[3]),
                   "px": ex(start.get("x", 0.0)), "py": ex(start.get("y", 0.0)), "pz": ex(start.get("z", h0))})
    d.sig("Chassis", "V", "Pose", "tw")
    d.sig("Pose", "g", "Chassis", "g")
    d.node("Aero", "project:Aero", x0 - 220, y0 - 200,
           params={"rho": "1.225", "CdA": num(v["CdA"]), "CyA": num(v["CyA"]), "ClA": num(v["ClA"]),
                   "front": num(v["aero_front"]), "a": num(v["a"]), "b": num(v["b"]),
                   "zd": num(v["h_drag"] - v["h_s"])})
    d.sig("Chassis", "V", "Aero", "V")
    d.node("AeroWrench", "stdlib:multibond/ExternalWrenchSpatial", x0, y0 - 200)
    for p in ("tx", "ty", "tz", "fx", "fy", "fz"):
        d.sig("Aero", p, "AeroWrench", p)
    d.bond("AeroWrench", "p", "Chassis", "p")


def driveline(d: Diagram, v: dict, start: dict, x0=0, y0=0, drv: dict | None = None) -> None:
    """Battery, traction motor(s), reductions and differentials (top level); expects the driver
    signals `Throttle/y`, `Brake/y`, `Reverse/y` to exist under those node names.

    Bond graph: the battery on a 0-junction (the DC bus); per motor a TractionMachine (an MTF
    with an electrical and a rotational port) from the bus to the
    rotor 1-junction (the inverter and the machine: torque u V, current u w, u from
    `EMotorControl`), the rotor inertia, its drag and a speed sensor on that junction, an
    elastic shaft (C and R) to the reduction TF, then the open axle differential (a
    0-junction) to the two half shafts. Outputs for the brake blending: `Motor<A>/regen`."""
    m = v["motor"]
    b = v["battery"]
    vs = start.get("v", 0.0)
    d.node("Battery", "project:TractionBattery", x0, y0,
           params={"Q": num(b["Q"]), "V_empty": num(b["V_empty"]), "V_full": num(b["V_full"]), "R": num(b["R"])},
           starts={"x": ex(start.get("soc", b["soc0"]))})
    d.junction("Bus", 0, x0 + 200, y0)
    d.bond("Bus", None, "Battery", "p")
    for k, ax in enumerate(v["motors"]):
        yy = y0 + 400 * k
        cl, cr = ("FL", "FR") if ax == "F" else ("RL", "RR")
        re = v["tyre"]["R0"] - v["corners"][cl]["defl"]
        w0 = m["n"] * vs / re
        ctl, mot, rot = "Motor" + ax, "Machine" + ax, "Rotor" + ax
        d.node(ctl, "project:EMotorControl", x0 + 400, yy + 200,
               params={"T_max": num(m["T_max"]), "P_max": num(m["P_max"]), "w_max": num(m["w_max"]),
                       "w_cut": num(m["w_cut"]), "T_regen": num(m["T_regen"]), "P_regen": num(m["P_regen"]),
                       "w_fade": num(m["w_fade"]), "n": num(m["n"]), "R": num(b["R"]),
                       "R_w": num(re)})
        d.sig("Telemetry", "speed", ctl, "v")
        d.sig(_drv(drv, "Throttle"), "y", ctl, "thr")
        d.sig("Brakes", "dem_" + ax.lower(), ctl, "dem")
        d.sig(_drv(drv, "Reverse"), "y", ctl, "rev")
        d.sig("Battery", "ocv", ctl, "ocv")
        d.sig("Battery", "soc", ctl, "soc")
        d.node(mot, "project:TractionMachine", x0 + 400, yy)
        d.sig(ctl, "u", mot, "u")
        d.bond("Bus", None, mot, "dc")
        d.junction(rot, 1, x0 + 600, yy)
        d.bond(mot, "shaft", rot, None)
        d.node(rot + "J", "stdlib:bondgraph/I", x0 + 600, yy - 160, params={"i": num(m["J"])},
               starts={"P": num(m["J"] * w0)})
        d.bond(rot, None, rot + "J", "p")
        d.node(rot + "Drag", "stdlib:bondgraph/R", x0 + 700, yy - 160, params={"r": num(m["b"])})
        d.bond(rot, None, rot + "Drag", "p")
        d.node(rot + "Speed", "stdlib:converters/SpeedSensor", x0 + 600, yy + 160)
        d.bond(rot, None, rot + "Speed", "a")
        d.sig(rot + "Speed", "y", ctl, "w")
        sh = "Shaft" + ax
        d.node(sh, "stdlib:rotation/ElasticShaft", x0 + 800, yy,
               params={"k": num(m["k_shaft"]), "d": num(m["d_shaft"])},
               starts={"phi": num(start.get("twist" + ax, 0.0))})
        d.bond(rot, None, sh, "a")
        di = "DriveIn" + ax
        d.junction(di, 1, x0 + 1000, yy)
        d.bond(di, None, sh, "b")
        red = "Reduction" + ax
        d.node(red, "stdlib:bondgraph/TF", x0 + 1200, yy, params={"n": num(1.0 / m["n"])})
        d.bond(di, None, red, "p1")
        axle_diff(d, "Diff" + ax, (red, "p2"), (cl, "spin"), (cr, "spin"), x0 + 1400, yy)
        lsd(d, "Lsd" + ax, cl, cr, v["lsd"], x0 + 1600, yy + 200)
    # the bus power of the other motor (the voltage each controller expects)
    if len(v["motors"]) == 1:
        constant(d, "NoAux", 0.0, x0 + 200, y0 + 200)
        d.sig("NoAux", "y", "Motor" + v["motors"][0], "p_aux")
    else:
        d.sig("MotorF", "P", "MotorR", "p_aux")
        d.sig("MotorR", "P", "MotorF", "p_aux")


def axle_diff(d: Diagram, name: str, src, left, right, x, y) -> None:
    """Open differential: a 0-junction (the carrier torque, common to both sides) bonded to
    the half shafts of the two corners (a TF 2 each, inside the corner), so the carrier turns
    at the mean wheel speed and each wheel gets half the torque."""
    d.junction(name, 0, x, y)
    d.bond(src[0], src[1], name, None)
    for dst in (left, right):
        d.bond(name, None, dst[0], dst[1])


def lsd(d: Diagram, name: str, left: str, right: str, r: float, x, y) -> None:
    """Viscous limited slip: a rotational damper between the two wheel spins of an axle."""
    d.node(name, "stdlib:rotation/RotationalDamper", x, y, params={"d": num(r)})
    # Out of the corner's LsdTF (a `through` TF whose other bond arrives from the spin junction)
    # into the damper's terminals (iconic ports are `in`).
    d.bond(left, "spin2", name, "a")
    d.bond(right, "spin2", name, "b")


def vehicle(d: Diagram, v: dict, start: dict, ground: str = "flat", terrain: dict | None = None,
            drv: dict | None = None) -> None:
    """The whole vehicle at the top level of `d`: chassis, corners, anti-roll bars, steering,
    brakes, electric driveline, ground, telemetry. Driver signals are the outputs `y` of the nodes
    Steer, Throttle, Brake, Reverse, Handbrake and Mu1..Mu4 (created by the caller)."""
    chassis(d, v, start, 0, 0)
    for i, c in enumerate(CORNERS):
        cx = 400 + 300 * (i % 2)
        cy = -300 + 600 * (i // 2)
        corner_instance(d, v, c, start, cx, cy)
        d.bond("Chassis", "p", c, "mount")
        d.sig("Pose", "g", c, "gc")
        d.sig(_drv(drv, f"Mu{i + 1}"), "y", c, "mus")
    # anti-roll bars
    for ax, (l, r) in enumerate((("FL", "FR"), ("RL", "RR"))):
        if v["k_arb"][ax] > 0:
            nm = "ArbF" if ax == 0 else "ArbR"
            d.node(nm, "project:AntiRollBar", 550, -450 + 900 * ax, params={"k": num(v["k_arb"][ax])})
            d.bond(l, "travel", nm, "jl")
            d.bond(r, "travel", nm, "jr")
    # steering and brakes
    d.node("Steering", "project:Steering", 900, -700,
           params={"dmax": num(v["steer_max"]), "L": num(v["L"]), "track": num(v["track"][0]),
                   "ackermann": num(v["ackermann"])})
    d.sig(_drv(drv, "Steer"), "y", "Steering", "steer")
    d.sig("Steering", "dl", "FL", "steer")
    d.sig("Steering", "dr", "FR", "steer")
    d.node("Brakes", "project:BrakeSystem", 900, 700,
           params={"Tf": num(v["brake_max"][0]), "Tr": num(v["brake_max"][1]), "Th": num(v["handbrake_max"])})
    d.sig(_drv(drv, "Brake"), "y", "Brakes", "brake")
    d.sig(_drv(drv, "Handbrake"), "y", "Brakes", "handbrake")
    for ax in ("F", "R"):
        if ax in v["motors"]:
            d.sig("Motor" + ax, "regen", "Brakes", "regen_" + ax.lower())
        else:
            constant(d, "NoRegen" + ax, 0.0, 800, 820)
            d.sig("NoRegen" + ax, "y", "Brakes", "regen_" + ax.lower())
    for c, p in zip(CORNERS, ("fl", "fr", "rl", "rr")):
        d.sig("Brakes", p, c, "brake")
    driveline(d, v, start, 1200, 0, drv)
    # ground
    if ground == "flat":
        d.node("Ground", "stdlib:contact/ContactSurface", 100, 500)
        for c in CORNERS:
            d.sig("Ground", "o", c, "o")
            d.sig("Ground", "fr", c, "fr")
    else:
        t = terrain
        for i, c in enumerate(CORNERS):
            nm = "Terrain" + c
            d.node(nm, "stdlib:contact/TerrainSurface", 100 + 150 * i, 650,
                   params={"h0": num(t["h0"]), "sx": num(t["sx"]), "sy": num(t["sy"]), "a": vec(t["a"]),
                           "kx": vec(t["kx"]), "ky": vec(t["ky"]), "ph": vec(t["ph"])},
                   constants={"N": len(t["a"])})
            d.sig(c, "g", nm, "g")
            d.sig(nm, "o", c, "o")
            d.sig(nm, "fr", c, "fr")
    # telemetry
    d.node("Telemetry", "project:Telemetry", 0, 600, params={"m": num(v["m_tot"])})
    d.sig("Pose", "g", "Telemetry", "g")
    d.sig("Chassis", "V", "Telemetry", "V")
    for i, c in enumerate(CORNERS):
        for a in "xyz":
            d.sig(c, "f" + a, "Telemetry", f"f{a}{i + 1}")
    d.sig("Aero", "fx", "Telemetry", "fax")
    d.sig("Aero", "fy", "Telemetry", "fay")
    d.sig("Aero", "fz", "Telemetry", "faz")


def view(d: Diagram) -> None:
    d.node("View", "project:CarView", 200, 900)
    d.sig("Pose", "g", "View", "gc")
    for i, c in enumerate(CORNERS):
        d.sig(c, "g", "View", f"g{i + 1}")
        d.sig(c, "th", "View", f"th{i + 1}")


def constant(d: Diagram, name: str, value, x, y) -> None:
    d.node(name, "stdlib:sources/Constant", x, y, params={"value": ex(value)})
