@block ALClamp begin
    # A test fixture for the identification experiments: a stiff clamp (C) with damping (R) between
    # a joint and the frame, as one bond-graph element on the joint's 1-junction (flow in = joint
    # rate). It holds the joint at the angle it had at the start; k = 0 releases it.
    @ports p::Power{Rotation}
    @outputs tau::Real, [unit = "N*m", description = "Clamp torque"]
    @parameters begin
        k::Real = 1.0e5, [unit = "N*m/rad", min = 0, description = "Clamp stiffness"]
        d::Real = 50.0, [unit = "N*m*s/rad", min = 0, description = "Clamp damping"]
    end
    @variables phi::Real = 0.0, [unit = "rad", state = :prefer, description = "Clamp deflection"]
    @equations begin
        ddt(phi) ~ p.f
        p.e ~ k * phi + d * p.f
        tau ~ p.e
    end
end
