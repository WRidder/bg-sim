# The pre-J2.6b flat DCMotor, kept as the equivalence oracle for the composite rewrite.
# It is a test fixture only: the stdlib block is now the textual composite.
@block DCMotorFlat begin
    @ports begin
        p::Power{Electrical}
        n::Power{Electrical}
        shaft::Power{Rotation}
        housing::Power{Rotation}
    end
    @parameters begin
        R::Real = 2.0, [unit = "Ohm", min = 0, description = "Winding resistance"]
        L::Real = 5e-4, [unit = "H", min = 0, description = "Winding inductance"]
        k_t::Real = 0.05, [unit = "N*m/A", description = "Torque constant"]
        J::Real = 1e-5, [unit = "kg*m^2", min = 0, description = "Rotor inertia"]
        d::Real = 0.0, [unit = "N*m*s/rad", min = 0, description = "Internal viscous damping"]
    end
    @variables begin
        i::Real = 0.0, [unit = "A", state = :prefer, description = "Winding current"]
        w_rel::Real = 0.0, [unit = "rad/s", state = :prefer, description = "Relative rotor speed"]
    end
    @equations begin
        i ~ p.f
        p.f + n.f ~ 0.0
        p.e - n.e ~ R * i + L * ddt(i) + k_t * w_rel
        w_rel ~ shaft.f - housing.f
        shaft.e ~ -k_t * i + J * ddt(w_rel) + d * w_rel
        housing.e ~ -shaft.e
    end
end
