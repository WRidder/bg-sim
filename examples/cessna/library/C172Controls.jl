@block C172Controls begin
    # The flight control system of JSBSim's c172p (signal only: the surfaces follow the controls
    # without hinge dynamics, as in c172p.xml). Commands -1 .. +1; signs as JSBSim's:
    #
    #   elevator  de = e (25.5 - 2.5 tanh(e/ks)) deg,  e = clamp(-(yoke_pitch + trim), -1, 1):
    #             +23 deg trailing edge down at full forward yoke, -28 deg (up) at full aft
    #   aileron   da = a (17.5 - 2.5 tanh(a/ks)) deg,  a = clamp(yoke_roll, -1, 1): the left
    #             aileron, +15 deg down / -20 deg up; the right one moves the opposite way
    #   rudder    dr = -16 deg clamp(pedals, -1, 1): right pedal moves the trailing edge right
    #   steering  the nose wheel turns 10 deg right at full right pedal
    #
    # The zero-centred scales of JSBSim (positive commands scaled by the maximum, negative by the
    # minimum) are blended over +-ks of the command, so the map is smooth.
    @inputs begin
        yoke_pitch::Real, [description = "Yoke, -1 full forward .. +1 full aft"]
        yoke_roll::Real, [description = "Yoke, -1 full left .. +1 full right"]
        pedals::Real, [description = "Pedals, -1 full left .. +1 full right"]
        trim::Real, [description = "Elevator trim, -1 nose down .. +1 nose up (added to the yoke)"]
    end
    @outputs begin
        de::Real, [unit = "rad", description = "Elevator, positive trailing edge down"]
        da::Real, [unit = "rad", description = "Left aileron, positive trailing edge down (roll right)"]
        dr::Real, [unit = "rad", description = "Rudder, positive trailing edge left (nose left)"]
        de_deg::Real
        da_deg::Real
        dr_deg::Real
        steer::Real, [unit = "rad", description = "Nose-wheel steering angle, positive right"]
    end
    @parameters begin
        ks::Real = 0.02, [description = "Command band over which the zero-centred scales blend"]
        steer_max::Real = 10.0, [description = "Nose-wheel steering at full pedal (deg)"]
    end
    @variables begin
        e::Real = 0.0
        ac::Real = 0.0
        rc::Real = 0.0
    end
    @equations begin
        e ~ clamp(-(yoke_pitch + trim), -1.0, 1.0)
        ac ~ clamp(yoke_roll, -1.0, 1.0)
        rc ~ clamp(-pedals, -1.0, 1.0)
        de_deg ~ e * (25.5 - 2.5 * tanh(e / ks))
        da_deg ~ ac * (17.5 - 2.5 * tanh(ac / ks))
        dr_deg ~ 16.0 * rc
        de ~ de_deg / 57.29577951308232
        da ~ da_deg / 57.29577951308232
        dr ~ dr_deg / 57.29577951308232
        steer ~ steer_max * clamp(pedals, -1.0, 1.0) / 57.29577951308232
    end
end
