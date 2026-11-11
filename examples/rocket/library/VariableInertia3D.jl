@block VariableInertia3D begin
    # Modulated spatial inertia (an MI): the stdlib `ISpatial` with its mass and principal moments
    # of inertia read from signals instead of parameters, for a body that loses mass (a rocket
    # burning propellant and dropping stages). The state is the body-frame momentum
    # `P = [h; p]` (angular; linear), exactly as in `ISpatial`, and the twist is its output:
    #
    #     ddt(P) = p.e,        p.f = [h1/J1, h2/J2, h3/J3, p1/m, p2/m, p3/m]
    #
    # At constant momentum a falling `m` raises the speed `p/m`, so on its own this element would
    # *gain* speed while the rocket loses mass. The mass that leaves takes its momentum with it:
    # that is a separate element on the same 1-junction, an `MR` per twist component with
    # resistance `r = -dm/dt` (linear) and `r = -dJk/dt` (angular). Together the two give the
    # variable-mass law `m dv/dt = F` and `J dw/dt = M` (+ gyroscopic terms from
    # `CoriolisSpatial`) for mass that leaves at the body's own velocity; the thrust is the
    # separate wrench of the engine. See the README, "Variable mass on a bond graph".
    #
    # The body frame stays at the centre of mass (the CoM shift as propellant drains is not
    # modelled) on the principal axes. `m > 0` and `J[k] > 0` are preconditions, as for `ISpatial`.
    @ports p::Power{Spatial}, [frame = "body"]
    @inputs begin
        m::Real, [unit = "kg", description = "Current mass"]
        J::Vec{3}, [unit = "kg*m^2", description = "Current principal moments of inertia about the CoM"]
    end
    @variables P::Vec{6} = [0.0, 0.0, 0.0, 0.0, 0.0, 0.0], [state = :prefer, description = "Momentum [angular; linear] in the body frame"]
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
