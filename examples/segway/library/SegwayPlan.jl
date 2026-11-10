@block SegwayPlan begin
    # Mission of the figure-of-eight run: the speed set-point rises to `v_cruise` around
    # `t_go` (tanh, no events), and from `t_turn` the heading set-point turns at the constant rate
    # `dpsi / t_loop` for `t_loop` seconds and then back at the opposite rate for the next
    # `t_loop` seconds: two circles of opposite sense that join into an eight. The turn rate
    # switches smoothly (tanh over `tau_psi`), so the heading set-point is the integral
    #     psi_ref = (dpsi / t_loop) (G(t - t0) - 2 G(t - t0 - T) + G(t - t0 - 2 T)),
    #     G(x) = (x + tau_psi ln(2 cosh(x / tau_psi))) / 2   (the integral of the smooth unit step).
    @parameters begin
        v_cruise::Real = 1.5, [unit = "m/s", description = "Cruise speed"]
        t_go::Real = 1.0, [unit = "s", description = "Time of the speed-up"]
        tau_v::Real = 0.8, [unit = "s", min = 1.0e-3, description = "Speed-up time constant"]
        t_turn::Real = 4.0, [unit = "s", description = "Start of the first loop"]
        t_loop::Real = 11.0, [unit = "s", min = 1.0e-3, description = "Duration of one loop"]
        dpsi::Real = 6.283185307179586, [unit = "rad", description = "Heading change of the first loop"]
        tau_psi::Real = 0.4, [unit = "s", min = 1.0e-3, description = "Smoothing time of the turn-rate switches"]
    end
    @outputs begin
        v_ref::Real, [unit = "m/s", description = "Speed set-point"]
        psi_ref::Real, [unit = "rad", description = "Heading set-point"]
    end
    @equations begin
        v_ref ~ v_cruise * 0.5 * (1 + tanh((t - t_go) / tau_v))
        psi_ref ~ (dpsi / t_loop) * 0.5 * (
            ((t - t_turn) + tau_psi * log(2 * cosh((t - t_turn) / tau_psi))) -
            2 * ((t - t_turn - t_loop) + tau_psi * log(2 * cosh((t - t_turn - t_loop) / tau_psi))) +
            ((t - t_turn - 2 * t_loop) + tau_psi * log(2 * cosh((t - t_turn - 2 * t_loop) / tau_psi))))
    end
end
