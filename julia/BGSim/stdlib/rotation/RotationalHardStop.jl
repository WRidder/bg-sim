@block RotationalHardStop begin
    @ports begin
        a::Power{Rotation}
        b::Power{Rotation}
    end
    @parameters begin
        lower::Real = -0.1, [unit = "rad", description = "Lower limit of the free rotation (relative angle a minus b)"]
        upper::Real = 0.1, [unit = "rad", description = "Upper limit of the free rotation (relative angle a minus b)"]
        k::Real = 1.0e4, [unit = "N*m/rad", min = 0, description = "Contact stiffness"]
        d::Real = 10.0, [unit = "N*m*s/rad", min = 0, description = "Contact damping coefficient"]
    end
    @variables phi::Real = 0.0, [unit = "rad", state = :prefer, description = "Relative angle a minus b"]
    @equations begin
        ddt(phi) ~ a.f - b.f
        # The rotational twin of the translational HardStop: no torque between the limits, a
        # torsional spring-damper outside them. The two `ifelse` conditions are the
        # switching instants the event collector lands on.
        a.e ~ ifelse(
            phi > upper,
            k * (phi - upper) + d * (a.f - b.f),
            ifelse(phi < lower, k * (phi - lower) + d * (a.f - b.f), 0.0),
        )
        b.e ~ -a.e
    end
    @orientation begin
        a => :in
        b => :in
    end
end
