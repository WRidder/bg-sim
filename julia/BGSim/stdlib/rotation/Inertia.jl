@block Inertia begin
    @ports begin
        a::Power{Rotation}
        b::Power{Rotation}
    end
    @parameters J::Real = 0.01, [unit = "kg*m^2", min = 0, description = "Moment of inertia"]
    @variables begin
        phi::Real = 0.0, [unit = "rad", state = :prefer, description = "Relative angle"]
        w::Real = 0.0, [unit = "rad/s", state = :prefer, description = "Relative angular velocity"]
    end
    @equations begin
        w ~ a.f - b.f
        ddt(phi) ~ w
        a.e ~ J * ddt(w)
        b.e ~ -a.e
    end
end
