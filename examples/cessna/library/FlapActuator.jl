@block FlapActuator begin
    # The electric flap drive of the c172p: the flap angle follows the selected detent
    # (0, 10, 20, 30 deg) at 5 deg/s up to 10 deg and 10 deg/s above (JSBSim's traverse: 2 s from
    # 0 to 10 deg, 1 s per detent beyond), as a fast loop with a rate limit that switches
    # smoothly over +-0.5 deg around 10 deg:
    #
    #   d(flap)/dt = clamp(k (10 detent - flap), -rate, rate),  rate = 7.5 + 2.5 tanh((flap - 10)/0.5)
    @inputs cmd::Real, [description = "Flap lever detent 0 .. 3 (0, 10, 20, 30 deg)"]
    @outputs begin
        flap::Real, [description = "Flap angle (deg)"]
        flap_rad::Real, [unit = "rad"]
    end
    @parameters k::Real = 20.0, [min = 0, description = "Loop gain (1/s)"]
    @variables begin
        x::Real = 0.0, [state = :prefer, description = "Flap angle (deg)"]
        rate::Real = 5.0, [description = "Rate limit (deg/s)"]
    end
    @equations begin
        rate ~ 7.5 + 2.5 * tanh((x - 10.0) / 0.5)
        ddt(x) ~ clamp(k * (10.0 * clamp(cmd, 0.0, 3.0) - x), -rate, rate)
        flap ~ x
        flap_rad ~ x / 57.29577951308232
    end
end
