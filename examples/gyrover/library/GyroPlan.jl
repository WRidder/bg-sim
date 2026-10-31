@block GyroPlan begin
    # Mission of the controlled Gyrover: speed and heading set-points as smooth functions of
    # time (tanh steps, so the set-points create no events). The robot starts at rest, speeds
    # up to `v_cruise` around `t_go`, and turns by `dpsi` at `t_turn`, `t_turn + t_leg`,
    # `t_turn + 2 t_leg` and `t_turn + 3 t_leg` (four turns: with dpsi = pi/2 a closed square-ish
    # loop). The dashboard sliders set `v_cruise` and `dpsi`.
    @parameters begin
        v_cruise::Real = 1.5, [unit = "m/s", description = "Cruise speed"]
        dpsi::Real = 1.5707963267948966, [unit = "rad", description = "Heading change of each turn"]
        t_go::Real = 1.0, [unit = "s", description = "Start of the speed-up"]
        tau_v::Real = 0.8, [unit = "s", min = 1.0e-3, description = "Speed-up time constant"]
        t_turn::Real = 6.0, [unit = "s", description = "First turn"]
        t_leg::Real = 6.0, [unit = "s", min = 0, description = "Time between turns"]
        tau_psi::Real = 0.6, [unit = "s", min = 1.0e-3, description = "Heading set-point transition time"]
    end
    @outputs begin
        v_ref::Real, [unit = "m/s", description = "Speed set-point"]
        psi_ref::Real, [unit = "rad", description = "Heading set-point"]
    end
    @equations begin
        v_ref ~ v_cruise * 0.5 * (1 + tanh((t - t_go) / tau_v))
        psi_ref ~ dpsi * 0.5 * (4 + tanh((t - t_turn) / tau_psi) + tanh((t - t_turn - t_leg) / tau_psi) +
                                tanh((t - t_turn - 2 * t_leg) / tau_psi) + tanh((t - t_turn - 3 * t_leg) / tau_psi))
    end
end
