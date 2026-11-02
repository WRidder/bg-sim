@block PoseQuat begin
    # The attitude quaternion (qw, qx, qy, qz) of a pose (qw, qx, qy, qz, x, y, z), normalised: the
    # FMU host of beaver-sim reads it (body FLU to the world x north, y west, z up).
    @inputs g::Vec{7}
    @outputs q::Vec{4}
    @variables s::Real = 1.0
    @equations begin
        s ~ sqrt(g[1] * g[1] + g[2] * g[2] + g[3] * g[3] + g[4] * g[4])
        q[1] ~ g[1] / s
        q[2] ~ g[2] / s
        q[3] ~ g[3] / s
        q[4] ~ g[4] / s
    end
end
