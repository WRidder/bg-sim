@block VariableInertia3D begin
    # Modulated spatial inertia (an MI): the stdlib `ISpatial` with its mass and principal
    # moments of inertia read from signals instead of parameters, for a missile that burns
    # propellant. The state is the body-frame momentum `P = [h; p]` (angular; linear) and the
    # twist is its output:
    #
    #     ddt(P) = p.e,        p.f = [h1/J1, h2/J2, h3/J3, p1/m, p2/m, p3/m]
    #
    # At constant momentum a falling `m` raises the speed `p/m`, so on its own this element
    # would *gain* speed while the missile loses mass. The propellant that leaves takes its
    # momentum with it through the `MR` elements on the same 1-junction (`r_lin = -dm/dt`,
    # `r_ang = -dJ/dt`); together they give `m dv/dt = F` and `J dw/dt = M` (+ the gyroscopic
    # term of `CoriolisSpatial`). This is the rocket example's block, unchanged.
    @ports p::Power{Spatial}, [frame = "body"]
    @inputs begin
        m::Real, [unit = "kg", description = "Current mass"]
        J::Vec{3}, [unit = "kg*m^2", description = "Current principal moments of inertia"]
    end
    @variables P::Vec{6} = [0.0, 0.0, 0.0, 0.0, 0.0, 0.0], [state = :prefer, description = "Momentum [angular; linear]"]
    @outputs begin
        Pm::Vec{6}
        twout::Vec{6}
    end
    @equations begin
        for k in 1:6
            ddt(P[k]) ~ p.e[k]
        end
        p.f[1] ~ P[1] / J[1]
        p.f[2] ~ P[2] / J[2]
        p.f[3] ~ P[3] / J[3]
        p.f[4] ~ P[4] / m
        p.f[5] ~ P[5] / m
        p.f[6] ~ P[6] / m
        Pm ~ P
        for k in 1:6
            twout[k] ~ p.f[k]
        end
    end
    @causality p => :flow_out
    @orientation p => :in
end
