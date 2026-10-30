@block TailServo begin
    # Hobby-servo model of one tail flap: a first-order command lag (the servo's position bandwidth)
    # followed by a PD torque law on the joint angle with a smooth stall limit,
    #
    #   dqs/dt = (sat(sp) - qs) / Tsv ,    tau = tau_max tanh( (Kp (qs - q) - Kd qd) / tau_max )
    #
    # `sat` is the smooth deflection limit dmax tanh(sp / dmax). `tau` drives the joint through a
    # bond-graph effort source (`stdlib:bondgraph/MSe`); the joint puts the reaction on the airframe.
    @inputs begin
        sp::Real
        q::Real
        qd::Real
    end
    @outputs begin
        tau::Real, [unit = "N*m"]
        defl::Real, [unit = "rad"]
        cmd::Real, [unit = "rad"]
    end
    @parameters begin
        Tsv::Real = 0.04, [unit = "s", min = 1.0e-4, description = "Position servo time constant"]
        Kp::Real = 1.5, [unit = "N*m/rad", min = 0, description = "Position gain"]
        Kd::Real = 0.01, [unit = "N*m*s/rad", min = 0, description = "Rate gain"]
        tau_max::Real = 0.3, [unit = "N*m", min = 1.0e-6, description = "Stall torque"]
        dmax::Real = 0.6, [unit = "rad", min = 0.01, description = "Mechanical deflection limit"]
    end
    @variables qs::Real = 0.0, [unit = "rad", description = "Filtered command"]
    @equations begin
        ddt(qs) ~ (dmax * tanh(sp / dmax) - qs) / Tsv
        tau ~ tau_max * tanh((Kp * (qs - q) - Kd * qd) / tau_max)
        defl ~ q
        cmd ~ qs
    end
end
