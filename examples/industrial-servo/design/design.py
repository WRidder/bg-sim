# /// script
# requires-python = ">=3.11"
# dependencies = ["numpy>=2.0", "scipy>=1.13"]
# ///
"""Gain design and model generation for the `industrial-servo` sample (plan 9.6b).

The sample is one Delta-ASDA-A3-style PMSM servo drive with five fidelity variants.
This script is the design record *and* the generator of the five model documents:
it computes the cascaded loop gains and the speed-loop notch from the nameplate
parameters, writes them (and the whole graph, whose plant is a bond graph) into
``models/*.bgmodel.json``, and prints the linear design summary that the README
quotes.

Nameplate / plan 9.6b parameters
--------------------------------
    V_dc = 300 V, V_max = V_dc/sqrt(3) = 173.2 V
    R_s = 0.5 ohm, L_d = L_q = 6 mH (surface-mount PMSM)
    p = 4 pole pairs, psi_m = 0.08 Wb
    k_t = 1.5 p psi_m = 0.48 N m/A, k_e = p psi_m = 0.32 V s/rad
    J_m = 4.4e-4 kg m^2, B_m = 1e-4 N m s/rad
    two-mass load: J_L = 4.4e-4, B_L = 1e-4, k_c = 800 N m/rad, c_c = 0.02 N m s/rad
    rated current 5 A peak, limit 15 A peak (7.2 N m)
    encoder 24 bit (2 pi / 2^24 rad), PWM 8 kHz, dead time 2 us, device drop 1.2 V
    current loop 8 kHz, speed loop 1 kHz, position loop 200 Hz, one-sample delay

Loop design
-----------
The current PI cancels the electrical pole: ``Kp = L w_ci``, ``Ki = R w_ci`` with
``w_ci = 2 pi 500 rad/s`` (a 500 Hz crossover at an 8 kHz sample rate).  The speed
loop sees ``k_t / (J s + B)``; ``Kp = J w_cs / k_t`` and the PI zero is placed at
``w_cs/5``, with ``w_cs = 2 pi 80 rad/s``.  The position loop is a P at 20 1/s
with a 200 rad/s speed limit.  The two-mass resonance
``sqrt(k_c (1/J_m + 1/J_L)) = 2 pi 303.5 Hz`` is notched (Q = 4) in the 1 kHz
speed feedback.

Run it with ``uv run examples/industrial-servo/design/design.py``.
"""

from __future__ import annotations

import json
import math
from pathlib import Path

from scipy.signal import iirnotch

ROOT = Path(__file__).resolve().parent.parent
MODELS = ROOT / "models"
PROJECT = ROOT / "bgsim.project.json"

# --------------------------------------------------------------------- parameters

RS = 0.5
LD = 0.006
LQ = 0.006
PSI = 0.08
PP = 4
KT = 1.5 * PP * PSI
KE = PP * PSI
JM = 4.4e-4
BM = 1e-4
JL = 4.4e-4
BL = 1e-4
KC = 800.0
CC = 0.02
VDC = 300.0
VMAX = VDC / math.sqrt(3.0)
I_MAX = 15.0
W_MAX = 200.0
T_END = 1.2
T_SPEED = 0.05
W_REF = 100.0
T_MODE = 0.15
T_LOAD = 0.9
LOAD = 2.0
ENC_BITS = 24
ENC_RES = 2.0 * math.pi / (1 << ENC_BITS)
TS_I = 125.0e-6
TS_W = 1.0e-3
TS_P = 5.0e-3
TS_PWM = 10.0e-6
F_PWM = 4000.0
TPWM = 1.0 / F_PWM
TD = 2.0e-6
VDROP = 1.2

W_CI = 2.0 * math.pi * 500.0
W_CS = 2.0 * math.pi * 80.0
KP_D = LD * W_CI
KI_D = RS * W_CI
KP_Q = LQ * W_CI
KI_Q = RS * W_CI
KP_S = JM * W_CS / KT
KI_S = KP_S * W_CS / 5.0
KP_POS = 20.0
NOTCH_HZ = math.sqrt(KC * (1.0 / JM + 1.0 / JL)) / (2.0 * math.pi)
NOTCH_Q = 4.0
BN, AN = iirnotch(NOTCH_HZ, NOTCH_Q, fs=1.0 / TS_W)
ENC_ALPHA = 0.8


def _num(value: float) -> str:
    return f"{value:.12g}"


def _vec(values) -> str:
    return "[" + ", ".join(_num(float(v)) for v in values) + "]"


# --------------------------------------------------------------------- graph builder


class Graph:
    """A tiny deterministic writer for the model document's diagram."""

    def __init__(self) -> None:
        self.nodes: list[dict] = []
        self.connections: list[dict] = []
        self._node_ids = 0
        self._conn_ids = 0

    def node(
        self,
        name: str,
        block: dict,
        x: float,
        y: float,
        *,
        params: dict[str, str] | None = None,
        constants: dict[str, object] | None = None,
        starts: dict[str, str] | None = None,
    ) -> str:
        self._node_ids += 1
        node_id = f"n{self._node_ids:02d}"
        self.nodes.append(
            {
                "id": node_id,
                "name": name,
                "block": block,
                "position": {"x": x, "y": y},
                "rotation": 0,
                "flipX": False,
                "params": params or {},
                "constants": constants or {},
                "starts": starts or {},
                "ui": {"showLabel": True, "color": None},
            }
        )
        return node_id

    def bond(self, source, target, label: str | None = None) -> None:
        self._conn_ids += 1
        self.connections.append(
            {
                "id": f"b{self._conn_ids:02d}",
                "kind": "bond",
                "from": _endpoint(source),
                "to": _endpoint(target),
                "route": [],
                "label": label,
            }
        )

    def signal(self, source, target, label: str | None = None) -> None:
        self._conn_ids += 1
        self.connections.append(
            {
                "id": f"b{self._conn_ids:02d}",
                "kind": "signal",
                "from": _endpoint(source),
                "to": _endpoint(target),
                "route": [],
                "label": label,
            }
        )


def _endpoint(value) -> dict:
    if isinstance(value, tuple):
        node_id, port = value
        return {"node": node_id, "port": port}
    return {"node": value}


def ref(name: str) -> dict:
    return {"ref": name}


def junction(kind: str) -> dict:
    return {"junction": kind}


# --------------------------------------------------------------------- the model


def build(name: str, *, two_mass: bool, switching: bool, encoder: bool) -> dict:
    g = Graph()
    y = 0.0

    # --- d-axis electrical 1-junction --------------------------------------------------
    vd = g.node("Vd", ref("stdlib:bondgraph/MSe"), 60, 120 + y, params={"gain": "1.0"})
    dj = g.node("DJ", junction("1"), 240, 220 + y)
    rd = g.node("Rd", ref("stdlib:bondgraph/R"), 240, 80 + y, params={"r": _num(RS)})
    ild = g.node("Id", ref("stdlib:bondgraph/I"), 240, 360 + y, params={"i": _num(LD)})
    ids = g.node("IdSens", ref("project:FlowSensor"), 420, 360 + y)
    mgy = g.node("MGY", ref("stdlib:bondgraph/MGY"), 420, 220 + y)
    g.bond((vd, "p"), dj, "v_d")
    g.bond(dj, (rd, "p"))
    g.bond(dj, (ild, "p"))
    g.bond(dj, (ids, "p"))
    g.bond((mgy, "p1"), dj, "cross-coupling -w_e L_q i_q")

    # --- q-axis electrical 1-junction --------------------------------------------------
    vq = g.node("Vq", ref("stdlib:bondgraph/MSe"), 60, 520 + y, params={"gain": "1.0"})
    qj = g.node("QJ", junction("1"), 620, 420 + y)
    rq = g.node("Rq", ref("stdlib:bondgraph/R"), 620, 300 + y, params={"r": _num(RS)})
    ilq = g.node("Iq", ref("stdlib:bondgraph/I"), 620, 540 + y, params={"i": _num(LQ)})
    iqs = g.node("IqSens", ref("project:FlowSensor"), 780, 540 + y)
    bemf = g.node(
        "Bemf", ref("stdlib:bondgraph/MSe"), 620, 180 + y,
        params={"gain": _num(KE)},
    )
    wm = g.node("WmSens", ref("project:FlowSensor"), 960, 420 + y)
    g.bond((vq, "p"), qj, "v_q")
    g.bond((mgy, "p2"), qj, "cross-coupling w_e L_d i_d")
    g.bond(qj, (rq, "p"))
    g.bond(qj, (ilq, "p"))
    g.bond(qj, (iqs, "p"))
    g.bond(qj, (bemf, "p"), "back-EMF -w_e psi_m")
    g.signal((wm, "y"), (bemf, "u"), "back-EMF speed")

    # --- torque gyrator: the measured i_q drives it through a flow source ---------------
    iqsrc = g.node("IqSrc", ref("stdlib:bondgraph/MSf"), 780, 420 + y,
                   params={"gain": "-1.0"})
    gy = g.node("GY", ref("stdlib:bondgraph/GY"), 960, 300 + y,
                params={"r": _num(KT)})
    g.bond((iqsrc, "p"), (gy, "p1"), "measured i_q")
    g.signal((iqs, "y"), (iqsrc, "u"), "measured i_q")

    # --- mechanical 1-junction and the rotor ------------------------------------------
    mj = g.node("MJ", junction("1"), 1140, 300 + y)
    g.bond((gy, "p2"), mj, "T_e = 1.5 p psi_m i_q")
    jm = g.node("Jm", ref("stdlib:bondgraph/I"), 1140, 160 + y, params={"i": _num(JM)})
    bm = g.node("Bm", ref("stdlib:bondgraph/R"), 1140, 440 + y, params={"r": _num(BM)})
    theta = g.node("Theta", ref("stdlib:continuous/Integrator"), 1320, 500 + y,
                   starts={"x": "0.0"})
    g.bond(mj, (jm, "p"))
    g.bond(mj, (bm, "p"))
    g.bond(mj, (wm, "p"))
    g.signal((wm, "y"), (theta, "u"), "motor speed")

    # --- mechanical load: rigid or flexible two-mass -----------------------------------
    if two_mass:
        tfm = g.node("TFm", ref("stdlib:bondgraph/TF"), 1320, 300 + y,
                     params={"n": "1.0"})
        s0 = g.node("S0", junction("0"), 1500, 300 + y)
        tfl = g.node("TFl", ref("stdlib:bondgraph/TF"), 1680, 300 + y,
                     params={"n": "1.0"})
        kj = g.node("KJ", junction("1"), 1500, 120 + y)
        kc = g.node("Kc", ref("stdlib:bondgraph/C"), 1320, 120 + y,
                    params={"c": _num(1.0 / KC)})
        dc = g.node("Dc", ref("stdlib:bondgraph/R"), 1680, 120 + y,
                    params={"r": _num(CC)})
        lj = g.node("LJ", junction("1"), 1860, 300 + y)
        jl = g.node("Jl", ref("stdlib:bondgraph/I"), 1860, 160 + y, params={"i": _num(JL)})
        bl = g.node("Bl", ref("stdlib:bondgraph/R"), 1860, 440 + y, params={"r": _num(BL)})
        wl = g.node("WlSens", ref("project:FlowSensor"), 2040, 300 + y)
        load = g.node("Load", ref("stdlib:bondgraph/MSe"), 2040, 460 + y,
                      params={"gain": "1.0"})
        g.bond(mj, (tfm, "p1"), "w_m")
        g.bond((tfm, "p2"), s0, "-w_m")
        g.bond(s0, (tfl, "p1"), "twist w_m - w_L")
        g.bond((tfl, "p2"), lj, "w_L")
        g.bond(s0, kj, "relative velocity")
        g.bond((kc, "p"), kj, "k_c = 800 N m/rad")
        g.bond((dc, "p"), kj, "c_c = 0.02 N m s/rad")
        g.bond(lj, (jl, "p"))
        g.bond(lj, (bl, "p"))
        g.bond(lj, (wl, "p"))
        g.bond((load, "p"), lj, "load torque")
    else:
        load = g.node("Load", ref("stdlib:bondgraph/MSe"), 1320, 300 + y,
                      params={"gain": "1.0"})
        g.bond((load, "p"), mj, "load torque")
        wl = None

    load_step = g.node("LoadStep", ref("stdlib:sources/Step"), 1140, 620 + y,
                       params={"t_step": _num(T_LOAD), "initial": "0.0",
                               "final": _num(-LOAD)})
    g.signal((load_step, "y"), (load, "u"), "2 N m resisting load at 0.9 s")

    # --- sensors: angle, encoder, speed estimate --------------------------------------
    enc = None
    if encoder:
        enc = g.node("Enc", ref("stdlib:discrete/Quantizer"), 1320, 620 + y,
                     params={"resolution": _num(ENC_RES)},
                     constants={"sample_period": _num(TS_I)})
        g.signal((theta, "y"), (enc, "u"), "true angle")
        speedest = g.node("SpeedEst", ref("project:SpeedEstimator"), 1500, 700 + y,
                          constants={"sample_period": _num(TS_W)},
                          params={"alpha": _num(ENC_ALPHA)})
        g.signal((enc, "y"), (speedest, "theta"), "24-bit angle")
        encmon = g.node("EncMon", ref("project:EncoderMonitor"), 1500, 580 + y,
                        constants={"sample_period": _num(TS_I)})
        g.signal((theta, "y"), (encmon, "theta"), "true angle")
        g.signal((enc, "y"), (encmon, "theta_q"), "quantized angle")
        speed_src = (speedest, "w")
        pos_src = (enc, "y")
    else:
        speed_src = (wm, "y")
        pos_src = (theta, "y")

    # --- firmware: position -> speed -> current ---------------------------------------
    posref = g.node("PosRef", ref("stdlib:sources/Constant"), 1320, 820 + y,
                    params={"value": "0.0"})
    refspeed = g.node("RefSpeed", ref("stdlib:sources/Step"), 1320, 940 + y,
                      params={"t_step": _num(T_SPEED), "initial": "0.0",
                              "final": _num(W_REF)})
    mode = g.node("Mode", ref("stdlib:sources/Step"), 1500, 940 + y,
                  params={"t_step": _num(T_MODE), "initial": "0.0", "final": "1.0"})
    posloop = g.node("PosLoop", ref("project:ServoPositionLoop"), 1700, 820 + y,
                     params={"Kp": _num(KP_POS), "w_max": _num(W_MAX)},
                     constants={"sample_period": _num(TS_P)})
    g.signal((posref, "y"), (posloop, "pos_ref"))
    g.signal(pos_src, (posloop, "pos_meas"), "position feedback")
    g.signal((refspeed, "y"), (posloop, "w_ref"), "speed step")
    g.signal((mode, "y"), (posloop, "mode"), "speed mode -> position mode at 0.15 s")

    # speed feedback path: optional notch (two-mass) after an optional encoder estimate
    speed_meas = speed_src
    notch = None
    if two_mass:
        notch = g.node("Notch", ref("stdlib:discrete/DiscreteTF"), 1700, 620 + y,
                       params={"b": _vec(BN), "a": _vec(AN)},
                       constants={"sample_period": _num(TS_W)})
        g.signal(speed_src, (notch, "u"), "motor speed")
        speed_meas = (notch, "y")
    speedloop = g.node("SpeedLoop", ref("project:ServoSpeedLoop"), 1900, 820 + y,
                       params={"Kp": _num(KP_S), "Ki": _num(KI_S), "i_max": _num(I_MAX)},
                       constants={"sample_period": _num(TS_W)})
    g.signal((posloop, "w_cmd"), (speedloop, "w_ref"), "speed command")
    g.signal(speed_meas, (speedloop, "w_meas"), "speed feedback")
    curloop = g.node("CurLoop", ref("project:ServoCurrentLoop"), 2100, 820 + y,
                     params={
                         "Ld": _num(LD), "Lq": _num(LQ),
                         "psi": _num(PSI), "pp": str(PP),
                         "Kp_d": _num(KP_D), "Ki_d": _num(KI_D),
                         "Kp_q": _num(KP_Q), "Ki_q": _num(KI_Q),
                         "vmax": _num(VMAX), "imax": _num(I_MAX),
                     },
                     constants={"sample_period": _num(TS_I)})
    g.signal((speedloop, "iq_cmd"), (curloop, "iq_cmd"))
    g.signal((speedloop, "id_cmd"), (curloop, "id_cmd"))
    g.signal((ids, "y"), (curloop, "id"), "i_d")
    g.signal((iqs, "y"), (curloop, "iq"), "i_q")
    g.signal(speed_src, (curloop, "w_m"), "speed for decoupling")

    # --- the 8 kHz computation delay, then the averaged or switching inverter ---------
    udd = g.node("Udd", ref("stdlib:discrete/UnitDelay"), 2280, 700 + y,
                 constants={"sample_period": _num(TS_I)})
    udq = g.node("Udq", ref("stdlib:discrete/UnitDelay"), 2280, 820 + y,
                 constants={"sample_period": _num(TS_I)})
    g.signal((curloop, "vd"), (udd, "u"))
    g.signal((curloop, "vq"), (udq, "u"))
    if switching:
        thetae = g.node("ThetaE", ref("stdlib:continuous/Gain"), 2280, 940 + y,
                        params={"k": str(PP)})
        g.signal(pos_src, (thetae, "u"), "electrical angle")
        pwm = g.node("PWM", ref("project:PwmInverter"), 2460, 700 + y,
                     params={
                         "Vdc": _num(VDC), "Tpwm": _num(TPWM),
                         "Td": _num(TD), "Vdrop": _num(VDROP),
                     },
                     constants={"sample_period": _num(TS_PWM)})
        g.signal((udd, "y"), (pwm, "vd"))
        g.signal((udq, "y"), (pwm, "vq"))
        g.signal((thetae, "y"), (pwm, "theta_e"))
        g.signal((ids, "y"), (pwm, "id"))
        g.signal((iqs, "y"), (pwm, "iq"))
        g.signal((pwm, "vd_app"), (vd, "u"), "v_d applied")
        g.signal((pwm, "vq_app"), (vq, "u"), "v_q applied")
    else:
        g.signal((udd, "y"), (vd, "u"), "v_d averaged")
        g.signal((udq, "y"), (vq, "u"), "v_q averaged")

    # --- modulator modulus and recording sensors --------------------------------------
    wel = g.node("WeL", ref("stdlib:continuous/Gain"), 420, 100 + y,
                 params={"k": _num(PP * LQ)})
    g.signal((wm, "y"), (wel, "u"), "w_e L_q")
    g.signal((wel, "y"), (mgy, "u"))
    iphase = g.node("Iphase", ref("project:PhaseCurrent"), 960, 620 + y)
    g.signal((ids, "y"), (iphase, "id"))
    g.signal((iqs, "y"), (iphase, "iq"))

    # --- document ---------------------------------------------------------------------
    plots = [
        {"id": "p1", "title": "Phase current", "signals": ["Iphase/y", "Iq/p.f"]},
        {"id": "p2", "title": "Speed", "signals": ["WmSens/p.f", "SpeedLoop/w_err"]},
        {"id": "p3", "title": "Position", "signals": ["Theta/y", "PosLoop/pos_err"]},
        {"id": "p4", "title": "Voltage", "signals": ["Vd/p.e", "Vq/p.e", "CurLoop/vd", "CurLoop/vq"]},
    ]
    if two_mass:
        plots[1]["signals"].insert(1, "WlSens/p.f")
    if encoder:
        plots[2]["signals"].append("Enc/y")

    settings = {
        "t_start": 0.0,
        "t_end": T_END,
        "solver": "auto",
        "reltol": 1.0e-4 if switching else 1.0e-8,
        "abstol": 1.0e-7 if switching else 1.0e-10,
        "max_step": None,
        "output": (
            {"mode": "interval", "interval": 1.0e-5}
            if switching
            else {"mode": "points", "points": 6001}
        ),
        "event_limit": 200000,
    }

    return {
        "format": "bgsim.model",
        "language": "0.1.0",
        "name": name,
        "$comment": _comment(two_mass, switching, encoder),
        "diagram": {
            "nodes": g.nodes,
            "connections": g.connections,
            "subsystemPorts": [],
            "annotations": [
                {
                    "id": "a1",
                    "kind": "text",
                    "text": _annotation(two_mass, switching, encoder),
                    "x": 40,
                    "y": 1050,
                    "w": 2600,
                    "h": 90,
                }
            ],
        },
        "settings": settings,
        "plots": plots,
        "scene": None,
        "bindings": [],
    }


def _comment(two_mass: bool, switching: bool, encoder: bool) -> str:
    parts = [
        "Plan 9.6b industrial-servo (X2.6). The PMSM plant is a bond graph (D28): d/q "
        "1-junctions with R and I, an MGY cross-coupling w_e L from a Gain of the measured "
        "speed, an MSe back-EMF k_e w_m (the junction sees -k_e w_m), and a GY k_t = 1.5 p psi_m to the mechanical "
        "1-junction (the measured i_q drives the GY through an MSf, which closes the dq 3/2 "
        "power convention). The rotor is I(J_m)+R(B_m); the load is either rigid or an "
        "I-C-R two-mass coupling. Sensors: FlowSensors, the kinematic Theta integrator and, "
        "in the encoder variants, a 24-bit Quantizer and the SpeedEstimator. The only code "
        "is the sampled firmware (ServoCurrentLoop 8 kHz, ServoSpeedLoop 1 kHz, "
        "ServoPositionLoop 200 Hz) and the switching inverter (PwmInverter).",
    ]
    flags = [
        f"{'flexible I-C-R two-mass coupling + notch' if two_mass else 'rigid inertia'}",
        f"{'two-level PWM, dead time, device drops' if switching else 'averaged inverter'}",
        f"{'24-bit encoder + estimated speed' if encoder else 'ideal encoder'}",
    ]
    parts.append("Variant: " + "; ".join(flags) + ".")
    return " ".join(parts)


def _annotation(two_mass: bool, switching: bool, encoder: bool) -> str:
    return (
        "Bond-graph plant (D28): Vd/Vq MSe -> d/q 1-junctions (R_s, L_d/L_q) with the MGY "
        "cross-coupling and the q-axis MSe back-EMF -> GY k_t to the mechanical 1-junction. "
        + ("Two-mass: MJ -TF(1)-> S0(0) <-TF(1)- LJ, with C=1/k_c and R=c_c in parallel on the 1-junction KJ fed by S0. "
           if two_mass else "Rigid rotor and load on MJ. ")
        + ("Switching: PwmInverter at 100 kHz on a 4 kHz carrier, 2 us dead time, 1.2 V drop. "
           if switching else "Averaged inverter limited to Vdc/sqrt(3). ")
        + ("Sensor: 24-bit encoder, 1 kHz differenced speed estimate. "
           if encoder else "Sensor: ideal angle and speed. ")
        + "Loop rates 8/1/0.2 kHz; one 8 kHz computation delay."
    )


# --------------------------------------------------------------------- main


def main() -> None:
    print("industrial-servo design (plan 9.6b)")
    print(f"  V_max = Vdc/sqrt(3) = {VMAX:.3f} V, k_t = {KT:.3f} N m/A, k_e = {KE:.3f} V s/rad")
    print(f"  current PI: Kp = L*w_ci = {KP_D:.4f} V/A, Ki = R*w_ci = {KI_D:.1f} V/(A s), "
          f"w_ci = {W_CI:.1f} rad/s ({W_CI / 2 / math.pi:.0f} Hz)")
    print(f"  speed PI:   Kp = J*w_cs/k_t = {KP_S:.4f} A/(rad/s), Ki = {KI_S:.3f} A/(rad/s^2), "
          f"w_cs = {W_CS:.1f} rad/s ({W_CS / 2 / math.pi:.0f} Hz), zero at {W_CS / 5 / 2 / math.pi:.1f} Hz")
    print(f"  position P: {KP_POS:.1f} 1/s, speed limit {W_MAX:.0f} rad/s")
    print(f"  two-mass resonance: sqrt(k_c(1/Jm+1/JL))/2pi = {NOTCH_HZ:.2f} Hz")
    print(f"  notch: {NOTCH_Q:.0f} Q at {NOTCH_HZ:.2f} Hz, fs = {1 / TS_W:.0f} Hz, "
          f"b = {_vec(BN)}, a = {_vec(AN)}")
    print(f"  encoder: {ENC_BITS} bit, {ENC_RES:.6g} rad LSB, estimate alpha = {ENC_ALPHA}")
    print(f"  PWM: {F_PWM:.0f} Hz, Td = {TD * 1e6:.1f} us, drop = {VDROP:.1f} V, "
          f"comparator Ts = {TS_PWM * 1e6:.1f} us")

    variants = [
        ("baseline", dict(two_mass=False, switching=False, encoder=False)),
        ("two-mass", dict(two_mass=True, switching=False, encoder=False)),
        ("switching", dict(two_mass=False, switching=True, encoder=False)),
        ("encoder", dict(two_mass=False, switching=False, encoder=True)),
        ("full", dict(two_mass=True, switching=True, encoder=True)),
    ]
    MODELS.mkdir(parents=True, exist_ok=True)
    for model_name, flags in variants:
        document = build(model_name, **flags)
        path = MODELS / f"{model_name}.bgmodel.json"
        path.write_text(json.dumps(document, indent=2, ensure_ascii=False) + "\n",
                        encoding="utf-8", newline="\n")
        print(f"  wrote {path.relative_to(ROOT)} ({len(document['diagram']['nodes'])} nodes, "
              f"{len(document['diagram']['connections'])} connections)")

    project = {
        "format": "bgsim.project",
        "language": "0.1.0",
        "name": "industrial-servo",
        "models": [model_name for model_name, _ in variants],
        "libraryDir": "library",
        "scenesDir": "scenes",
    }
    PROJECT.write_text(json.dumps(project, indent=2) + "\n", encoding="utf-8", newline="\n")
    print(f"  wrote {PROJECT.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
