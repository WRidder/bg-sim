@block GearBacklash begin
    @ports begin
        a::Power{Rotation}
        b::Power{Rotation}
    end
    @parameters begin
        k::Real   = 1e4,  [unit = "N*m/rad", min = 0, description = "Tooth contact stiffness"]
        d::Real   = 5.0,  [unit = "N*m*s/rad", min = 0, description = "Contact damping"]
        gap::Real = 0.01, [unit = "rad", min = 0, description = "Total backlash"]
    end
    @variables begin
        phi::Real = 0.0, [unit = "rad", description = "Relative angle a minus b"]
        w::Real,         [unit = "rad/s"]
        T::Real,         [unit = "N*m"]
    end
    @equations begin
        w ~ a.f - b.f
        ddt(phi) ~ w
        # damping acts only in contact and never pulls the teeth together
        T ~ ifelse(phi >  gap/2, max(k*(phi - gap/2) + d*w, 0.0),
            ifelse(phi < -gap/2, min(k*(phi + gap/2) + d*w, 0.0), 0.0))
        a.e ~ T
        b.e ~ -T
    end
end
