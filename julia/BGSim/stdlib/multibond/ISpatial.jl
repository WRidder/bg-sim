@block ISpatial begin
    # Spatial rigid-body inertia at the centre of mass and on the principal axes (D-MB3):
    # the diagonal `J = (J1, J2, J3)` in kg*m^2 and the mass `m` in kg. The momentum
    # `P = [h; p]` is the state, the twist `p.f = [J^-1 h; p/m]` is its output, and `P` is
    # exposed as a signal for `CoriolisSpatial` (D-MB3: the inertia is never copied).
    #
    # `J` is a `Vec{3}` because all three entries are a moment of inertia; the momentum is a
    # `Vec{6}` **without** a unit because a torque impulse (N*m*s) and a linear momentum
    # (kg*m/s) do not share one, and every component is written on its own (D-MB10).
    #
    # Positivity: the block divides by every `J[k]` and by `m`, so a body needs
    # `J[k] > 0` and `m > 0`. `m` carries `min = 1e-12`; `J` is a vector declaration with a
    # single attribute set, so its positivity is documented here rather than enforced as an
    # attribute. A runtime positivity check with an E108 diagnostic does not exist yet (the
    # E108 wording is reserved for the numeric inertia helpers in `src/mech`), so the
    # requirement is a modelling precondition, not a checked error.
    @ports p::Power{Spatial}, [frame = "body"]
    @parameters begin
        J::Vec{3} = [0.1, 0.1, 0.1], [unit = "kg*m^2", description = "Principal moments of inertia about the body centre of mass (J[k] > 0)"]
        m::Real = 1.0, [unit = "kg", min = 1e-12, description = "Body mass (m > 0)"]
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
        # The momentum tap: CoriolisSpatial reads it, so the inertia lives only here (D-MB3).
        Pm ~ P
        # The twist tap for a floating-base orientation integrator (D-MB6).
        for k in 1:6
            twout[k] ~ p.f[k]
        end
    end
    @causality p => :flow_out
end
