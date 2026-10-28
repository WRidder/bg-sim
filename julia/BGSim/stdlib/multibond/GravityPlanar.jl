@block GravityPlanar begin
    @ports p::Power{Planar}, [frame = "body"]
    @parameters begin
        m::Real = 1.0, [unit = "kg", min = 0, description = "Body mass"]
        g0::Real = 9.81, [unit = "m/s^2", min = 0, description = "Gravitational acceleration"]
    end
    @inputs g::Vec{3}
    @equations begin
        # g = (theta, x, y) is the body pose in the world. Gravity acts at the body origin
        # (the CoM, D-MB3), so the body-frame wrench is [0, -sin(theta)*m*g0,
        # -cos(theta)*m*g0]. A 1-junction sums efforts, so the PORT effort that injects
        # that wrench into the inertia is its negative: e_gravity = -W_gravity.
        p.e[1] ~ 0.0
        p.e[2] ~ sin(g[1]) * m * g0
        p.e[3] ~ cos(g[1]) * m * g0
    end
    @causality p => (:effort_out, :fixed)
end
