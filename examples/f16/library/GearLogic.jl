@block GearLogic begin
    # The signal side of the landing gear (no physics):
    #
    #   w      weight on wheels, 0 .. 1: (Fk_left + Fk_right - f0)/(f1 - f0), clamped. The load in
    #          the main struts' springs fades the fly-by-wire laws into the ground commands, and it
    #          holds the gear down (the handle's interlock). Exactly 0 in the air. The springs, not
    #          the wheel loads: the wheel load holds the damper force, which depends on the
    #          retraction's rate, so through the interlock it would close an algebraic loop.
    #   steer  nose-wheel angle: pedal * steer_max (deg), to rad, positive right. `steer_max`
    #          comes from a Lookup1D over the ground speed (design/gear.py).
    @inputs begin
        pedal::Real, [description = "Pedals, -1 (full left) .. +1 (full right)"]
        steer_max::Real, [description = "Steering angle at full pedal (deg)"]
        Fk_left::Real, [unit = "N", description = "Spring force of the left main strut"]
        Fk_right::Real, [unit = "N", description = "Spring force of the right main strut"]
    end
    @outputs begin
        w::Real, [description = "Weight on wheels, 0 .. 1"]
        steer::Real, [unit = "rad", description = "Nose-wheel angle, positive right"]
    end
    @parameters begin
        f0::Real = 500.0, [unit = "N", description = "Main-wheel load where the hand-over starts"]
        f1::Real = 9000.0, [unit = "N", description = "Main-wheel load where the hand-over is complete"]
    end
    @equations begin
        w ~ clamp((Fk_left + Fk_right - f0) / (f1 - f0), 0.0, 1.0)
        steer ~ pedal * steer_max / 57.29577951308232
    end
end
