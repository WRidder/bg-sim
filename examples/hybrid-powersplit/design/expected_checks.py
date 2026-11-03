"""expected.json of the hybrid-powersplit example (imported by build_model.py).

Every number comes from design/design.json (analytic or from the cycle definition) or from a
published reference; the note of each check says which."""

from __future__ import annotations

# loss elements built as modulated effort sources (smooth Coulomb terms): dissipation
LOSS_OVERRIDES = {"SpinLoss": "dissipation", "Rolling": "dissipation", "EngineDrag": "dissipation"}


def willis(scale: float, tol: float, note_extra: str = "", sun="SunSpeed/y", ring="RingSpeed/y",
           carrier="CarrierSpeed/y", Zs=30.0, Zr=78.0) -> dict:
    return {"kind": "invariant", "terms": [{"signal": sun, "coeff": Zs}, {"signal": ring, "coeff": Zr},
                                           {"signal": carrier, "coeff": -(Zs + Zr)}],
            "scale": scale, "tol": tol,
            "note": "Willis equation of the planetary set, Zs w_sun + Zr w_ring - (Zs+Zr) w_carrier = 0 at every sample: "
                    "the flow balance of the bond graph's mesh 0-junction" + note_extra}


def expected(D: dict, no_diag: dict) -> dict:
    k, ev, nedc, psd = D["kin"], D["ev"], D["nedc"], D["psd"]
    Zs, Zr = psd["Zs"], psd["Zr"]
    kin = [
        {"kind": "final_value", "signal": "SunSpeed/y", "t": 10.0, "value": k["w_s"], "rtol": 1e-6,
         "note": "steady state: T_sun = Zs/(Zs+Zr) T_c = 16.67 N*m = b_s w_s (design.py kinematics)"},
        {"kind": "final_value", "signal": "RingSpeed/y", "t": 10.0, "value": k["w_r"], "rtol": 1e-6,
         "note": "T_ring = Zr/(Zs+Zr) T_c = 43.33 N*m = b_r w_r"},
        {"kind": "final_value", "signal": "CarrierSpeed/y", "t": 10.0, "value": k["w_c"], "rtol": 1e-6,
         "note": "w_c = (Zs w_s + Zr w_r)/(Zs+Zr) (Willis)"},
        {"kind": "final_value", "signal": "PCarrier/y", "t": 10.0, "value": k["P_c"], "rtol": 1e-6,
         "note": "carrier power T_c w_c"},
        willis(1.0e4, 1e-10),
        {"kind": "ratio", "signal": "SunTorque/y", "signal_b": "RingTorque/y", "t": 2.0, "value": Zs / Zr, "rtol": 1e-9,
         "note": "torque split T_sun : T_ring = Zs : Zr at every instant (the common effort of the mesh 0-junction)"},
        {"kind": "invariant", "terms": [{"signal": "PCarrier/y", "coeff": 1.0}, {"signal": "PSun/y", "coeff": -1.0},
                                        {"signal": "PRing/y", "coeff": -1.0}], "scale": 1.0e4, "tol": 1e-9,
         "note": "the planetary set is power conserving: P_carrier = P_sun + P_ring"},
        {"kind": "compare_signals", "signal": "RingSpeed/y", "signal_b": "Ring2Speed/y", "from_t": 0.0, "max_abs": 1e-5,
         "note": "the bond-graph planetary agrees with the stdlib PlanetaryGear (equation block)"},
        {"kind": "compare_signals", "signal": "SunSpeed/y", "signal_b": "Sun2Speed/y", "from_t": 0.0, "max_abs": 1e-5,
         "note": "the same for the sun"},
        {"kind": "energy_ledger", "tol": 1e-6, "note": "Tellegen over all port powers"},
        no_diag,
    ]
    evc = [
        {"kind": "zero_crossing", "signal": "VehicleSpeed/y", "level": ev["v_target"], "direction": "up", "n": 1,
         "value": ev["t_target"], "abs": 0.05,
         "note": f"EV launch with 150 N*m of MG2 from 0.5 s: the closed form v = V tanh(t sqrt(F0 k)/m) with "
                 f"F0 = T FD/r - c_rr m g and the reflected ring, MG2, sun and MG1 inertias (m = {ev['m_total']:.1f} kg) "
                 f"gives 30 km/h at {ev['t_target_closed']:.3f} s; a rigid 1-DOF ODE that adds the spin and iron losses "
                 f"(design.py) gives {ev['t_target']:.3f} s. The model differs by the half-shaft compliance and the "
                 "10 ms stator lag: 0.05 s"},
        willis(1.0e5, 1e-8),
        {"kind": "max_abs_le", "signal": "EngineSpeed/y", "value": 5.0,
         "note": "MG1's speed control holds the engine at rest against the reaction of the launch torque "
                 "(|w_e| < 5 rad/s, 50 rpm)"},
        {"kind": "ratio", "signal": "SunSpeed/y", "signal_b": "RingSpeed/y", "t": 8.0, "value": -Zr / Zs, "rtol": 0.01,
         "note": "with the carrier at rest the sun turns backwards at Zr/Zs = 2.6 times the ring speed"},
        {"kind": "max_abs_le", "signal": "PBat/y", "value": 21210.0,
         "note": "the HCU holds the battery within its 21 kW rating (ORNL Table 2.1) from the MG2 copper-loss "
                 "estimate; 1 % for the stator and DC-link transients"},
        {"kind": "energy_ledger", "tol": 1e-5, "overrides": LOSS_OVERRIDES, "note": "Tellegen over all port powers"},
        no_diag,
    ]

    def cycle(strategy: str) -> list:
        return [
            {"kind": "compare_signals", "signal": "Cycle/y", "signal_b": "VehicleSpeed/y", "from_t": 0.0,
             "max_abs": 2.0 / 3.6, "note": "the driver follows the NEDC within its +-2 km/h speed tolerance (UN ECE R83)"},
            {"kind": "final_value", "signal": "Meters/Distance/y", "t": nedc["t_end"], "value": nedc["distance_m"],
             "rtol": 0.003, "note": "NEDC distance from the cycle definition, 11.013 km (design.py)"},
            willis(1.0e5, 1e-8),
            {"kind": "final_value", "signal": "Battery/soc", "t": nedc["t_end"], "value": 0.6, "abs": 0.03,
             "note": "charge sustaining: the final SOC within +-3 % of the 60 % start (a +-3 % SOC swing of the 6.5 A*h "
                     "pack is about 0.16 MJ, 4 g of fuel)"},
            {"kind": "compare_signals", "signal": "BMS/y", "signal_b": "Battery/soc", "from_t": 0.0, "max_abs": 1e-4,
             "note": "the BMS coulomb count agrees with the battery's own SOC state"},
            {"kind": "final_value", "signal": "Meters/L100km/y", "t": nedc["t_end"], "value": 4.0, "abs": 0.7,
             "note": f"{strategy}: published 4.3 L/100 km NEDC combined (Toyota, EU type approval of the 2004 Prius, "
                     "cold start). The model starts hot and has no auxiliaries, so a lower value is expected: "
                     "the band 3.3-4.7 L/100 km"},
            {"kind": "final_value", "signal": "Meters/OnTime/y", "t": nedc["t_end"],
             "value": 0.5 * (nedc["t_above_spin"] + nedc["t_end"] - nedc["t_idle"]),
             "abs": 0.5 * (nedc["t_end"] - nedc["t_idle"] - nedc["t_above_spin"]),
             "note": f"engine on-time between the bounds of the cycle: at least the {nedc['t_above_spin']:.0f} s above "
                     f"{nedc['v_spin'] * 3.6:.0f} km/h (MG1 would overspeed with the engine at rest), at most the "
                     f"{nedc['t_end'] - nedc['t_idle']:.0f} s the car moves (the engine is off at standstill)"},
            {"kind": "final_value", "signal": "Meters/EBrakeDemand/y", "t": nedc["t_end"],
             "value": nedc["E_brake_demand"], "rtol": 0.05,
             "note": f"braking energy the driver asks for at the ring, {nedc['E_brake_demand'] / 1e6:.3f} MJ from the "
                     "cycle trace with the same road loads (design.py regen_share); the PI driver's +-2 km/h tracking "
                     "error: 5 %"},
            {"kind": "final_value", "signal": "Meters/RegenShare/y", "t": nedc["t_end"],
             "value": nedc["regen_share"], "abs": 0.02,
             "note": f"regenerative share of the braking energy, 1 - E_friction / E_brake = {nedc['regen_share']:.3f} "
                     "from the cycle trace: the NEDC decelerations are mild (at most 25 kW at the ring, within the "
                     "battery's charge limit), so the friction brakes only take the stops below the 6.6 km/h "
                     "fade-out of the regenerative torque"},
            {"kind": "energy_ledger", "tol": 1e-5, "overrides": LOSS_OVERRIDES,
             "note": "Tellegen over all port powers; the smooth Coulomb spin and rolling losses and the engine drag "
                     "are modulated effort sources classified as dissipation"},
            no_diag,
        ]

    return {"project": "hybrid-powersplit",
            "description": "Toyota Prius (THS-II) power-split hybrid: the planetary set as a bond graph, the engine, MG1, "
                           "MG2, NiMH battery and vehicle on the NEDC with a rule-based and an ECMS energy management. "
                           "Numbers from design/design.json and the published references in the README.",
            "models": {
                "hybrid-kinematics": {"checks": kin},
                "hybrid-ev-mode": {"checks": evc},
                "hybrid-rule-based": {"checks": cycle("rule-based")},
                "hybrid-ecms": {"checks": cycle("ECMS")},
            }}
