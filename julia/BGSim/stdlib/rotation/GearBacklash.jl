@block GearBacklash begin
    @ports begin
        a::Power{Rotation}
        b::Power{Rotation}
    end
    @parameters begin
        k::Real = 1.0e4, [unit = "N*m/rad", min = 0, description = "Tooth contact stiffness"]
        d::Real = 5.0, [unit = "N*m*s/rad", min = 0, description = "Contact damping"]
        gap::Real = 0.01, [unit = "rad", min = 0, description = "Total backlash"]
    end
    @variables begin
        phi::Real = 0.0, [unit = "rad", state = :prefer, description = "Relative angle a minus b"]
        w::Real = 0.0, [unit = "rad/s", description = "Relative angular velocity"]
        T::Real = 0.0, [unit = "N*m", description = "Torque carried from a to b"]
    end
    @equations begin
        w ~ a.f - b.f
        ddt(phi) ~ w
        # Dead-zone contact spring: no torque inside the gap, stiff contact outside it, and
        # the damping only acts in contact and never pulls the teeth together.
        T ~ ifelse(phi > gap / 2, max(k * (phi - gap / 2) + d * w, 0.0),
            ifelse(phi < -gap / 2, min(k * (phi + gap / 2) + d * w, 0.0), 0.0))
        a.e ~ T
        b.e ~ -T
    end
end
