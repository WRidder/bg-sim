@block IPlanar begin
    @ports p::Power{Planar}, [frame = "body"]
    @parameters begin
        J::Real = 0.01, [unit = "kg*m^2", min = 0, description = "Yaw inertia about the body centre of mass"]
        m::Real = 1.0, [unit = "kg", min = 0, description = "Body mass"]
    end
    # Per-component units differ (a torque impulse is not a linear momentum), so the vector
    # is left open and every component is written on its own (D-MB3/D-MB10).
    @variables P::Vec{3} = [0.0, 0.0, 0.0], [state = :prefer, description = "Momentum [angular; linear]"]
    @outputs Pm::Vec{3}
    @equations begin
        ddt(P[1]) ~ p.e[1]
        ddt(P[2]) ~ p.e[2]
        ddt(P[3]) ~ p.e[3]
        p.f[1] ~ P[1] / J
        p.f[2] ~ P[2] / m
        p.f[3] ~ P[3] / m
        # The momentum tap: CoriolisPlanar reads it, so the inertia is never copied (D-MB3).
        Pm ~ P
    end
    @causality p => :flow_out
end
