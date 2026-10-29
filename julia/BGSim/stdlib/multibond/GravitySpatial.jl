@block GravitySpatial begin
    # Spatial gravity wrench at the body centre of mass. The pose input `g` is the body pose
    # in the world on the D-MB6 chart `(q_w, q_x, q_y, q_z, p_x, p_y, p_z)`. Gravity acts at
    # the CoM, which is the body origin (D-MB3), so the body-frame wrench is
    # `W = [0; R(g)^T (0, 0, -m g0)]` and its torque about the origin is zero.
    #
    # A 1-junction sums efforts, so the PORT effort that injects that wrench into the inertia
    # is its negative, `p.e = [0; +m g0 R(g)[3,:]]`, the same sign algebra as `GravityPlanar`.
    # `W` is constant in the world frame while `p` changes, so gravity reads the integrated /
    # composed pose and never a drifted copy (D-MB6).
    @ports p::Power{Spatial}, [frame = "body"]
    @parameters begin
        m::Real = 1.0, [unit = "kg", min = 0, description = "Body mass"]
        g0::Real = 9.81, [unit = "m/s^2", min = 0, description = "Gravitational acceleration"]
    end
    @inputs g::Vec{7}
    @equations begin
        # R(g)[3,1] = 2(x z - w y)/|q|^2, R(g)[3,2] = 2(y z + w x)/|q|^2,
        # R(g)[3,3] = (w^2 - x^2 - y^2 + z^2)/|q|^2, with w, x, y, z = g[1:4].
        p.e[1] ~ 0.0
        p.e[2] ~ 0.0
        p.e[3] ~ 0.0
        p.e[4] ~ 2 * m * g0 * (g[2] * g[4] - g[1] * g[3]) /
                 (g[1] * g[1] + g[2] * g[2] + g[3] * g[3] + g[4] * g[4])
        p.e[5] ~ 2 * m * g0 * (g[3] * g[4] + g[1] * g[2]) /
                 (g[1] * g[1] + g[2] * g[2] + g[3] * g[3] + g[4] * g[4])
        p.e[6] ~ m * g0 * (g[1] * g[1] - g[2] * g[2] - g[3] * g[3] + g[4] * g[4]) /
                 (g[1] * g[1] + g[2] * g[2] + g[3] * g[3] + g[4] * g[4])
    end
    @causality p => (:effort_out, :fixed)
end
