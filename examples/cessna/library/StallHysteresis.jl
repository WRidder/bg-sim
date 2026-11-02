@block StallHysteresis begin
    # The stall-hysteresis flag of c172p.xml (aero/stall-hyst-norm, signal only): it sets above
    # alpha `hi` (the stall) and clears below `lo` (recovery); between them it keeps its value,
    # which switches the stalled lift and drag tables of C172Aero (CLWBH1, CDWBH*). JSBSim switches
    # it at once; here a fast first-order follower (time constant 1/k) holds the flag, so the model
    # has no discrete state and exports to a fixed-step FMU:
    #
    #   d(x)/dt = k (target - x),  target = 1 above hi, 0 below lo, x in between
    @inputs u::Real, [unit = "rad", description = "Angle of attack"]
    @outputs y::Real, [description = "Stall flag 0 .. 1"]
    @parameters begin
        hi::Real = 0.36, [unit = "rad", description = "Sets above (20.6 deg)"]
        lo::Real = 0.09, [unit = "rad", description = "Clears below (5.2 deg)"]
        k::Real = 50.0, [unit = "1/s", min = 0, description = "Follower rate"]
    end
    @variables x::Real = 0.0, [state = :prefer, description = "The flag"]
    @equations begin
        ddt(x) ~ k * (ifelse(u > hi, 1.0, ifelse(u < lo, 0.0, x)) - x)
        y ~ x
    end
end
