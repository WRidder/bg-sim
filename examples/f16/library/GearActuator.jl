@block GearActuator begin
    # The gear's retraction: the position x (0 up .. 1 down) follows the handle at a limited
    # rate, a traverse of t_gear seconds (JSBSim f16.xml: 5 s), as a fast loop with a rate limit:
    #
    #   c = clamp(cmd, 0, 1),   target = c + (1 - c) w,
    #   d x/dt = clamp(k (target - x), -1/t_gear, 1/t_gear)
    #
    # The weight-on-wheels term is the handle's interlock: with weight on the main wheels the
    # target stays 1, so the gear cannot be raised on the ground.
    #
    # `lift_rate` is the rate at which the retraction raises the contact point (m/s, positive up):
    # the flow of the MSf in series with the strut, so the leg's stroke is the contact point's
    # penetration minus the lifted length L (1 - x). Fully up, the contact point sits L higher
    # and the strut never touches.
    @inputs begin
        cmd::Real, [description = "Gear handle, 0 up .. 1 down"]
        w::Real, [description = "Weight on wheels, 0 .. 1"]
    end
    @outputs begin
        pos::Real, [description = "Gear position, 0 up .. 1 down"]
        lift_rate::Real, [unit = "m/s", description = "Rate at which the contact point rises"]
    end
    @parameters begin
        t_gear::Real = 5.0, [unit = "s", min = 1.0e-3, description = "Traverse time"]
        k::Real = 5.0, [min = 0, description = "Loop gain (1/s)"]
        L::Real = 3.0, [unit = "m", min = 0, description = "Travel of the contact point"]
    end
    @variables begin
        x::Real = 0.0, [state = :prefer, description = "Gear position"]
        dx::Real = 0.0, [description = "d x/dt (1/s)"]
        c::Real = 0.0, [description = "The handle, clamped"]
    end
    @equations begin
        c ~ clamp(cmd, 0.0, 1.0)
        dx ~ clamp(k * (c + (1.0 - c) * w - x), -1.0 / t_gear, 1.0 / t_gear)
        ddt(x) ~ dx
        pos ~ x
        lift_rate ~ -L * dx
    end
end
