@block ExternalTarget begin
    # A target supplied by the host (the host-interface variant of TargetMotion). The seeker
    # only reads the target position, velocity and infrared intensity, so this block maps a
    # launch-relative NED target to the missile body's world (x north, y west, z up). The
    # inputs are local to the launch point: north and east are relative to it, and down is the
    # absolute NED down (negative altitude), as the missile pose's z is the absolute altitude.
    @inputs begin
        pn::Real, [unit = "m", description = "Target north, relative to the launch point"]
        pe::Real, [unit = "m", description = "Target east, relative to the launch point"]
        pd::Real, [unit = "m", description = "Target down (negative altitude)"]
        vn::Real, [unit = "m/s", description = "Target north velocity"]
        ve::Real, [unit = "m/s", description = "Target east velocity"]
        vd::Real, [unit = "m/s", description = "Target down velocity"]
        I::Real, [unit = "W", description = "Target infrared intensity"]
    end
    @outputs begin
        pose::Vec{7}
        vw_out::Vec{3}, [unit = "m/s"]
        ir::Real, [unit = "W"]
    end
    @equations begin
        pose[1] ~ 1.0
        pose[2] ~ 0.0
        pose[3] ~ 0.0
        pose[4] ~ 0.0
        pose[5] ~ pn
        pose[6] ~ -pe
        pose[7] ~ -pd
        vw_out[1] ~ vn
        vw_out[2] ~ -ve
        vw_out[3] ~ -vd
        ir ~ I
    end
end
