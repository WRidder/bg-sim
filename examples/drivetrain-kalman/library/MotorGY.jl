@block MotorGY begin
    # The electromechanical gyrator of the DC motor, with explicit domains.  The stdlib
    # `GY` has two `Generic` ports; a `Generic` two-port block may adopt only one domain,
    # so it cannot bridge the Electrical and Rotation islands once the GearWithBacklash
    # composite declares Rotation ports (E102).  The equations are the stdlib GY's,
    # verbatim: p1 is the electrical side (back-EMF) and p2 the mechanical side (torque).
    @ports begin
        a::Power{Electrical}
        b::Power{Rotation}
    end
    @parameters r::Real = 1.0, [unit = "V*s/rad", description = "Gyrator modulus (torque constant)"]
    @equations begin
        a.e ~ -r * b.f
        b.e ~ r * a.f
    end
    @causality (a, b) => :gyrator
end
