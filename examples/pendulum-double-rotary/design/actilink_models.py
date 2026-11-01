# /// script
# requires-python = ">=3.11"
# dependencies = ["numpy>=2.0", "scipy>=1.13", "casadi>=3.6"]
# ///
"""Write the ACTILINK models (`actilink-*`) of pendulum-double-rotary, the generated controller block
`library/ALCtrl.jl`, the scene `scenes/actilink.sdf` and the project's model list, from
`design/actilink_design.json` (run `actilink_design.py` first). The bond graph is assembled by
`actilink_build.build`; this file holds the scenarios, plots and dashboards.

    uv run examples/pendulum-double-rotary/design/actilink_models.py
"""

from __future__ import annotations

import json
import math
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import actilink_build as ab
import actilink_lib as al

ROOT = HERE.parent


def plot(pid, title, signals):
    return {"id": pid, "title": title, "signals": signals}


def card(cid, kind, size, title, **kw):
    out = {"id": cid, "kind": kind, "size": size, "title": title}
    out.update(kw)
    return out


def dashboard(dz: dict, text: str, push: bool = False) -> dict:
    dr = al.drive(dz["size"])
    ilim = round(dr.iq_peak, 1)
    cards = [
        card("about", "text", "2x1", "ACTILINK-" + dr.name + " rotary double pendulum", options={"markdown": True, "text": text}),
        card("mode", "value", "1x1", "Controller mode (0 idle, 1 swing-up, 2 balance)", signals=["Ctrl/mode"],
             options={"decimals": 0, "unit": "", "zones": [{"from": -0.5, "to": 0.5, "tone": "info"}, {"from": 0.5, "to": 1.5, "tone": "warn"},
                                                       {"from": 1.5, "to": 2.5, "tone": "good"}]}),
        card("bal", "indicator", "1x1", "Balancing", signals=["Ctrl/mode"], options={"threshold": 1.5, "onWhen": "above"}),
        card("bus", "toggle", "1x1", "AS5048B over I2C (off: AS5048A over SPI)", parameter="Ctrl/bus"),
        card("nrd", "slider", "1x1", "AS5048 read every n EtherCAT cycles", parameter="global:enc_nrd",
             options={"min": 1, "max": 8, "step": 1, "decimals": 0, "unit": "cycles"}),
        card("bl", "slider", "1x1", "Gear backlash (total)", parameter="GearSpring/backlash",
             options={"min": 0.0, "max": 0.012, "step": 0.0005, "decimals": 4, "unit": "rad"}),
    ]
    if push:
        cards.append(card("push", "slider", "1x1", "Push on the link-2 tip (50 ms)", parameter="PushPulse/amplitude",
                          options={"min": 0.0, "max": 0.8, "step": 0.05, "decimals": 2, "unit": "N"}))
    cards += [
        card("dev", "value", "1x1", "Largest link deviation from upright", signals=["Angles/dev"],
             options={"decimals": 3, "unit": "rad", "sparkline": True,
                      "zones": [{"from": 0.0, "to": 0.0175, "tone": "good"}, {"from": 0.0175, "to": 0.1, "tone": "warn"},
                                {"from": 0.1, "to": 10.0, "tone": "bad"}]}),
        card("iq", "gauge", "1x1", "Motor q current (limit +-" + f"{ilim:g} A)", signals=["CurrentLoop/iq"],
             options={"min": -ilim, "max": ilim, "decimals": 1, "unit": "A",
                      "zones": [{"from": -ilim, "to": -0.8 * ilim, "tone": "bad"}, {"from": -0.8 * ilim, "to": 0.8 * ilim, "tone": "good"},
                                {"from": 0.8 * ilim, "to": ilim, "tone": "bad"}]}),
        card("defl", "value", "1x1", "Gear deflection (rotor/N - arm)", signals=["GearSpring/defl"],
             options={"decimals": 5, "unit": "rad", "sparkline": True}),
        card("angles", "plot", "2x2", "Link angles from upright (Angles) and the estimates (Ctrl)",
             signals=["Angles/phi1", "Angles/phi2", "Ctrl/q2e", "Ctrl/q3e"]),
        card("enc", "plot", "2x2", "Link 1: true angle, AS5048 reading (unwrapped), estimate", signals=["J2/qout", "Ctrl/th1", "Ctrl/q2e"]),
        card("arm", "plot", "2x2", "Arm angle: true and estimated", signals=["J1/qout", "Ctrl/q1e"]),
        card("torque", "plot", "2x2", "Torque: command, drive reference, gear", signals=["Ctrl/tau", "DriveLoop/tau_ref", "GearSpring/tau"]),
        card("current", "plot", "2x2", "q current [A] and voltage [V]", signals=["CurrentLoop/iq", "CurrentLoop/uq"]),
        card("gear", "plot", "2x2", "Gear deflection", signals=["GearSpring/defl"]),
        card("energy", "plot", "2x2", "Energy: mechanical, drive, electrical in, losses",
             signals=["Energy/E_mech", "Energy/E_drive", "Energy/W_in", "Energy/W_loss"]),
    ]
    return {"autoRerun": False, "cards": cards}


def sysid_dashboard(text: str, signals: list[list[str]], titles: list[str]) -> dict:
    cards = [card("about", "text", "2x1", "Identification experiment", options={"markdown": True, "text": text})]
    for k, (sg, title) in enumerate(zip(signals, titles, strict=True)):
        cards.append(card(f"p{k + 1}", "plot", "2x2", title, signals=sg))
    return {"autoRerun": False, "cards": cards}


CTRL_PLOTS = [
    plot("p1", "Link angles from upright", ["Angles/phi1", "Angles/phi2"]),
    plot("p2", "Arm angle", ["J1/qout"]),
    plot("p3", "Torque command and drive reference", ["Ctrl/tau", "DriveLoop/tau_ref"]),
    plot("p4", "q current", ["CurrentLoop/iq"]),
    plot("p5", "Controller mode", ["Ctrl/mode"]),
    plot("p6", "Link 1: true, AS5048 (unwrapped), estimate", ["J2/qout", "Ctrl/th1", "Ctrl/q2e"]),
    plot("p7", "Gear deflection", ["GearSpring/defl"]),
    plot("p8", "Energy", ["Energy/E_mech", "Energy/E_drive", "Energy/W_in", "Energy/W_loss", "Energy/H"]),
]

SYSID = {
    "current_amp": 5.0,  # N m torque step (output side)
    "friction_levels": [0.05, -0.05, 0.15, -0.15, 0.4, -0.4, 1.0, -1.0, 3.0, -3.0, 8.0, -8.0],
    "friction_hold": 0.4,
    "gear_amp": 12.0,
    "gear_period": 3.0,
    "gear_periods": 1,
    "swing_amp": 0.7,
    "swing_t": 8.0,
    "enc_speed": 4.0,
    "enc_hold": 1.7,
    "chirp_amp": 1.0,
    "chirp_t": 10.0,
    "chirp_f0": 0.3,
    "chirp_f1": 3.0,
}


def specs(dz: dict) -> list[dict]:
    cfg = dz["cfg"]
    t_on, t_s = dz["t_on"], dz["t_s"]
    dr = al.drive(dz["size"])
    n = dr.name
    pre = f"ACTILINK-{n} rotary double pendulum (pendulum-double-rotary, actilink-*): "
    plant = ("Plant: a 0.3 m arm on the actuator's output (Revolute3D J1, RigidBody3D Arm), link 1 (0.6 m, J2) and link 2 "
             "(0.6 m, J3, 40 mm beside link 1) on passive joints with smooth Coulomb+viscous bearing friction. Drive as a bond "
             "graph: Uq (MSe) -> 1e [Rw, Lw, Isense] -> EMF (GY) -> 1m [Rotor, FricIn (Stribeck), Wm] -> Gear (TF 1/N) -> 0g "
             "[GearSpring: compliance, backlash, contact damping] -> 1o [FricOut] -> J1.drive. Firmware: CurrentLoop 16 kHz, "
             "DriveLoop 4 kHz (CST/CSV), the drive's motor and output encoders; AS5048A (SPI) and AS5048B (I2C) "
             "chains on both passive joints (14 bit, INL, noise, latency as the read offset).")
    bal_text = (f"**Balance with the real hardware.** ACTILINK-{n} (planetary {dr.N:g}:1, backlash {dr.backlash / al.ARCMIN:.0f} arcmin), "
                "a 1 kHz EtherCAT master (one cycle delay) running a discrete LQR on alpha-beta-gamma estimates from the 20-bit "
                "output encoder and two 14-bit AS5048 sensors. Toggle the sensor bus (SPI/I2C latency), slow the sensor reads, "
                "change the backlash and rerun.")
    out = []
    out.append({
        "name": "actilink-free", "t_end": cfg["t_free"], "q0": cfg["free_start"], "firmware": "none", "points": 1501,
        "comment": pre + "open-loop free swing from rest (drive in CST with a zero target, the current loop holds i_q = 0). "
                   "expected.json compares it with the Python twin (design/actilink_lib.py ALTwin). " + plant,
        "plots": [plot("p1", "Link angles", ["Angles/phi1", "Angles/phi2"]), plot("p2", "Arm angle", ["J1/qout"]),
                  plot("p3", "Gear deflection", ["GearSpring/defl"]), plot("p4", "q current", ["CurrentLoop/iq"]),
                  plot("p5", "Energy (H constant)", ["Energy/E_mech", "Energy/E_drive", "Energy/W_loss", "Energy/H"])],
        "dashboard": sysid_dashboard("**Free swing.** The drive is enabled with a zero torque target: the arm is backdriven through "
                                     "the planetary gear, the backlash and the rotor inertia. The twin check of expected.json uses this run.",
                                     [["Angles/phi1", "Angles/phi2"], ["J1/qout"], ["GearSpring/defl"], ["Energy/H"]],
                                     ["Link angles", "Arm angle", "Gear deflection", "Energy invariant H"]),
    })
    out.append({
        "name": "actilink-balance", "t_end": 5.0, "q0": cfg["balance_start"], "firmware": "ctrl", "t_on": 0.0,
        "balance_only": 1.0, "th1_init": 0.0,
        "comment": pre + f"balance from a disturbed upright ({math.degrees(cfg['balance_start'][1]):.1f} / "
                   f"{math.degrees(cfg['balance_start'][2]):.1f} deg), the LQR active from the first cycle. " + plant,
        "plots": CTRL_PLOTS, "dashboard": dashboard(dz, bal_text),
    })
    out.append({
        "name": "actilink-push", "t_end": 6.0, "q0": [0.0, 0.0, 0.0], "firmware": "ctrl", "t_on": 0.0, "balance_only": 1.0,
        "th1_init": 0.0, "push": {"force": cfg["push_force"], "t": 2.0, "dur": cfg["push_dur"]},
        "comment": pre + f"disturbance rejection: balancing upright, a {cfg['push_force']:g} N, {cfg['push_dur'] * 1e3:.0f} ms push "
                   "on the link-2 tip at 2 s (perpendicular to the link, in the pendulum plane). " + plant,
        "plots": CTRL_PLOTS, "dashboard": dashboard(dz, bal_text + " The slider sets the push force.", push=True),
    })
    out.append({
        "name": "actilink-swingup", "t_end": t_on + t_s + 4.0, "q0": [0.0, math.pi, 0.0], "firmware": "ctrl",
        "comment": pre + f"swing-up from hanging: idle until {t_on:g} s, then the collocation trajectory ({t_s:g} s, torque "
                   "bounded) tracked by a time-varying LQR, catch into the balance LQR. " + plant,
        "plots": CTRL_PLOTS, "dashboard": dashboard(dz, "**Swing-up and balance.** " + bal_text),
    })
    sy = SYSID
    out.append({
        "name": "actilink-sysid-current", "t_end": 0.06, "q0": [0.0, math.pi, 0.0], "firmware": "sysid", "clamps": {1: 1e6},
        "current_loop": "digital",
        "points": 6001, "sysid": {"kind": 1.0, "t0": 0.01, "amp": sy["current_amp"], "dur": 0.03},
        "comment": pre + "identification 1: winding and current loop. Output clamped, a torque-command step (CST); "
                   "fit R and L from the sampled u_q and i_q (design/actilink_sysid.py)." + " " + plant,
        "plots": [plot("p1", "q current", ["CurrentLoop/iq", "DriveLoop/iref"]), plot("p2", "q voltage", ["CurrentLoop/uq"])],
        "dashboard": sysid_dashboard("**Current step.** Arm clamped; the step response of the 16 kHz current loop. "
                                     "`actilink_sysid.py` fits R and L from u_q and i_q.",
                                     [["CurrentLoop/iq", "DriveLoop/iref"], ["CurrentLoop/uq"]], ["q current", "q voltage"]),
    })
    lv = sy["friction_levels"]
    out.append({
        "name": "actilink-sysid-friction", "t_end": 0.1 + len(lv) * sy["friction_hold"] + 0.2, "q0": [0.0, math.pi, 0.0],
        "firmware": "sysid", "clamps": {2: 1e5, 3: 1e5}, "drive_mode": 1.0, "points": 4001,
        "sysid": {"kind": 2.0, "t0": 0.1, "levels": lv, "t_hold": sy["friction_hold"]}, "sysid_nl": len(lv),
        "comment": pre + "identification 2: friction and back-EMF. Pendulum locked hanging (both passive joints clamped), the drive in "
                   "CSV: a speed staircase in both directions; the mean torque per level gives the Stribeck curve, the voltage "
                   "the back-EMF constant (design/actilink_sysid.py)." + " " + plant,
        "plots": [plot("p1", "Speed: target and estimate", ["Cmd/w_cmd", "DriveLoop/w_est"]),
                  plot("p2", "Torque reference", ["DriveLoop/tau_ref"]),
                  plot("p3", "q voltage and current", ["CurrentLoop/uq", "CurrentLoop/iq"])],
        "dashboard": sysid_dashboard("**Friction staircase.** CSV speed levels; the steady torque per level is the friction "
                                     "torque at that speed (Coulomb, Stribeck, viscous); the voltage gives the back-EMF constant.",
                                     [["Cmd/w_cmd", "DriveLoop/w_est"], ["DriveLoop/tau_ref"]], ["Speed", "Torque reference"]),
    })
    out.append({
        "name": "actilink-sysid-gear", "t_end": 0.1 + sy["gear_periods"] * sy["gear_period"] + 0.3, "q0": [0.0, math.pi, 0.0],
        "firmware": "sysid", "clamps": {1: 1e6}, "points": 4001,
        "sysid": {"kind": 3.0, "t0": 0.1, "amp": sy["gear_amp"], "period": sy["gear_period"], "n_per": float(sy["gear_periods"])},
        "comment": pre + "identification 3: gear stiffness and backlash. Output clamped, a slow torque triangle (CST); motor "
                   "encoder / N minus output encoder against the torque (design/actilink_sysid.py)." + " " + plant,
        "plots": [plot("p1", "Torque reference", ["DriveLoop/tau_ref"]), plot("p2", "Deflection: true", ["GearSpring/defl"]),
                  plot("p3", "Encoders: motor and output", ["MotorEnc/y", "OutputEnc/y"])],
        "dashboard": sysid_dashboard("**Locked-output torque reversal.** The deflection between the motor encoder (/N) and the "
                                     "output encoder against the torque: backlash, stiffness below and above the knee, friction hysteresis.",
                                     [["DriveLoop/tau_ref"], ["GearSpring/defl"]], ["Torque", "Gear deflection"]),
    })
    a0 = sy["swing_amp"]
    for k, (clamps, q0, what) in enumerate((({1: 1e6, 3: 1e5}, [0.0, math.pi - a0, 0.0], "links 1 and 2 locked together, swinging about joint 1"),
                                            ({1: 1e6, 2: 1e5}, [0.0, math.pi, a0], "link 1 locked hanging, link 2 swinging about joint 2")), start=1):
        sig_true, sig_enc = ("J2/qout", "Enc1A/y") if k == 1 else ("J3/qout", "Enc2A/y")
        out.append({
            "name": f"actilink-sysid-swing{k}", "t_end": sy["swing_t"], "q0": q0, "firmware": "none", "drive_off": True, "clamps": clamps,
            "points": round(sy["swing_t"] * 1000) + 1,
            "comment": pre + f"identification {3 + k}: free oscillation ({what}), released at {math.degrees(a0):.0f} deg from hanging; "
                       "period and decay of the AS5048 reading give the pendulum inertia and the bearing friction "
                       "(design/actilink_sysid.py)." + " " + plant,
            "plots": [plot("p1", "Joint angle: true and AS5048", [sig_true, sig_enc])],
            "dashboard": sysid_dashboard("**Swing-down.** A free oscillation of a passive joint (the arm and the other joint "
                                         "clamped). Period: J/(m g c); decay: Coulomb (linear envelope) and viscous (exponential).",
                                         [[sig_true], [sig_enc]], ["True angle", "AS5048 register"]),
        })
    out.append({
        "name": "actilink-sysid-encoder", "t_end": 0.1 + 2 * sy["enc_hold"] + 0.3, "q0": [0.0, math.pi, 0.0],
        "firmware": "sysid", "clamps": {2: 1e5, 3: 1e5}, "drive_mode": 1.0, "points": round((0.4 + 2 * sy["enc_hold"]) * 1000) + 1, "bench_encoder": True,
        "bench_latency": dz["enc"]["lat_a"], "sysid_nl": 2,
        "sysid": {"kind": 2.0, "t0": 0.1, "levels": [sy["enc_speed"], -sy["enc_speed"]], "t_hold": sy["enc_hold"]},
        "comment": pre + "identification 6: AS5048 latency, INL and noise on a bench (an AS5048A on the actuator output, read in "
                   "the 1 kHz cycle, against the 20-bit output encoder): one turn at constant speed each way (CSV) "
                   "(design/actilink_sysid.py)." + " " + plant,
        "plots": [plot("p1", "Arm: output encoder and bench AS5048", ["OutputEnc/y", "EncBench/y"])],
        "dashboard": sysid_dashboard("**Encoder bench.** One turn each way at constant speed: the AS5048 register against the "
                                     "20-bit output encoder gives the latency (sign change with the direction), the INL harmonics and the noise.",
                                     [["OutputEnc/y", "EncBench/y"]], ["Arm angle: reference and AS5048"]),
    })
    out.append({
        "name": "actilink-sysid-chirp", "t_end": 0.1 + sy["chirp_t"] + 0.5, "q0": [0.0, math.pi, 0.0], "firmware": "sysid",
        "clamps": {2: 1e5, 3: 1e5}, "points": round((sy["chirp_t"] + 0.6) * 1000) + 1,
        "sysid": {"kind": 4.0, "t0": 0.1, "amp": sy["chirp_amp"], "dur": sy["chirp_t"], "f0": sy["chirp_f0"], "f1": sy["chirp_f1"]},
        "comment": pre + "identification 7: rotor inertia. Pendulum locked hanging (both passive joints clamped), a torque chirp "
                   "on the arm (CST); the inertia of the locked rig follows from the swing tests and the geometry, the "
                   "regression of torque minus friction on the arm acceleration gives the rotor inertia J_out "
                   "(design/actilink_sysid.py)." + " " + plant,
        "plots": [plot("p1", "Torque reference", ["DriveLoop/tau_ref"]), plot("p2", "Arm angle", ["J1/qout", "OutputEnc/y"]),
                  plot("p3", "Gear deflection", ["GearSpring/defl"])],
        "dashboard": sysid_dashboard("**Chirp.** A torque sweep on the arm with the pendulum locked hanging: torque minus the "
                                     "identified friction against the arm acceleration gives the total inertia, minus the rig the rotor inertia.",
                                     [["DriveLoop/tau_ref"], ["J1/qout"], ["GearSpring/defl"]], ["Torque", "Arm angle", "Gear deflection"]),
    })
    return out


def main() -> None:
    dz = json.loads((HERE / "actilink_design.json").read_text(encoding="utf-8"))
    only = sys.argv[1:]
    (ROOT / "library" / "ALCtrl.jl").write_text(ab.ctrl_source(dz), encoding="utf-8", newline="\n")
    (ROOT / "scenes" / "actilink.sdf").write_text(ab.scene_sdf(dz), encoding="utf-8", newline="\n")
    names = []
    for spec in specs(dz):
        names.append(spec["name"])
        if only and spec["name"] not in only:
            continue
        doc = ab.build(dz, spec)
        if "sysid_nl" in spec:
            for node in doc["diagram"]["nodes"]:
                if node["id"] == "cmd":
                    node["constants"]["NL"] = str(spec["sysid_nl"])
        ab.rb.write_json(ROOT / "models" / f"{spec['name']}.bgmodel.json", doc)
    proj_path = ROOT / "bgsim.project.json"
    proj = json.loads(proj_path.read_text(encoding="utf-8"))
    proj["models"] = [m for m in proj["models"] if not m.startswith("actilink-")] + names
    ab.rb.write_json(proj_path, proj)
    print(f"wrote the ACTILINK models ({', '.join(only) if only else len(names)}), library/ALCtrl.jl, scenes/actilink.sdf")


if __name__ == "__main__":
    main()
