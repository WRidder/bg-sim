@block InvertedPendulumBody begin
    # The stdlib Inertia, modified: the body rotates about a fixed edge (absolute angle, no
    # second reference body) and gravity tips it over, so there is a destabilising torque
    # m*g*l*sin(theta) on top of the torque the two ports apply. Both ports sit on the same
    # absolute rotation, so a.f = b.f = w.
    @ports begin
        a::Power{Rotation}
        b::Power{Rotation}
    end
    @parameters begin
        J::Real = 4e-3, [unit = "kg*m^2", min = 0, description = "Moment of inertia about the edge"]
        m::Real = 0.6, [unit = "kg", min = 0, description = "Body mass"]
        l::Real = 0.085, [unit = "m", min = 0, description = "Distance from the edge to the centre of mass"]
        g::Real = 9.81, [unit = "m/s^2", min = 0, description = "Gravitational acceleration"]
    end
    @variables begin
        theta::Real = 0.05, [unit = "rad", state = :prefer, description = "Angle from upright"]
        w::Real = 0.0, [unit = "rad/s", state = :prefer, description = "Angular velocity"]
    end
    @equations begin
        J * ddt(w) ~ m * g * l * sin(theta) + a.e + b.e
        ddt(theta) ~ w
        a.f ~ w
        b.f ~ w
    end
end
