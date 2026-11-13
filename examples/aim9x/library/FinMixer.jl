@block FinMixer begin
    # Mix the three virtual control commands into the four cruciform canards. The canards sit
    # at 45, 135, 225 and 315 deg in the body y-z plane. A pure pitch command deflects the
    # first pair oppositely, a pure yaw command the diagonal pair, and a pure roll command all
    # four together (which produces no net force: the tangential forces cancel, the roll
    # moments add).
    #
    #     d1 = -dp + dy + dr
    #     d2 = +dp      + dr
    #     d3 =           dr
    #     d4 =      -dy + dr
    #
    # Positive dp pitches the nose up, positive dy pushes the nose left, positive dr rolls
    # right wing down.
    @inputs begin
        dp::Real, [unit = "deg", description = "Virtual pitch command"]
        dy::Real, [unit = "deg", description = "Virtual yaw command"]
        dr::Real, [unit = "deg", description = "Virtual roll command"]
    end
    @outputs begin
        d1::Real, [unit = "deg"]
        d2::Real, [unit = "deg"]
        d3::Real, [unit = "deg"]
        d4::Real, [unit = "deg"]
        dp_eff::Real, [unit = "deg"]
        dy_eff::Real, [unit = "deg"]
        dr_eff::Real, [unit = "deg"]
    end
    @equations begin
        d1 ~ -dp + dy + dr
        d2 ~ dp + dr
        d3 ~ dr
        d4 ~ -dy + dr
        dp_eff ~ dp
        dy_eff ~ dy
        dr_eff ~ dr
    end
end
