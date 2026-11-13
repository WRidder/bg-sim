@block SmoothBacklash begin
    # Gear backlash (dead-zone spring and damper) without solver events: the law of
    # stdlib:rotation/GearBacklash with its kinks smoothed over `wb`, for models that carry many
    # of them (the 14 servos of the microduck). Port `a` is the gear side, `b` the load side.
    #
    #   x1 = phi - gap/2,  x2 = -phi - gap/2            penetration of each flank
    #   c_i = (x_i + sqrt(x_i^2 + wb^2)) / 2            smooth positive part, dc_i/dx_i = c_i/r_i
    #   T1 = k c1 + d w c1/r1,  T2 = k c2 - d w c2/r2    flank forces (damping only in contact)
    #   T  = pos(T1) - pos(T2),  pos(x) = (x + sqrt(x^2 + feps^2)) / 2
    #
    # The damping never pulls a flank (the smooth `pos` clamp, like the `max` of GearBacklash).
    # With gap = 0 the spring is exactly k phi (c1 - c2 = phi) and the damping exactly d w.
    @ports begin
        a::Power{Rotation}
        b::Power{Rotation}
    end
    @parameters begin
        k::Real = 100.0, [unit = "N*m/rad", min = 0, description = "Tooth contact stiffness"]
        d::Real = 0.1, [unit = "N*m*s/rad", min = 0, description = "Contact damping"]
        gap::Real = 0.0349, [unit = "rad", min = 0, description = "Total backlash"]
        wb::Real = 1.0e-4, [unit = "rad", min = 1.0e-12, description = "Smoothing angle of the contact onset"]
        feps::Real = 1.0e-5, [unit = "N*m", min = 1.0e-12, description = "Smoothing torque of the no-pull clamp"]
    end
    @variables begin
        phi::Real = 0.0, [unit = "rad", state = :prefer, description = "Relative angle a minus b"]
        w::Real = 0.0, [unit = "rad/s", description = "Relative angular velocity"]
        x1::Real = 0.0, [unit = "rad", description = "Penetration of the forward flank"]
        x2::Real = 0.0, [unit = "rad", description = "Penetration of the backward flank"]
        r1::Real = 1.0e-4, [unit = "rad", description = "sqrt(x1^2 + wb^2)"]
        r2::Real = 1.0e-4, [unit = "rad", description = "sqrt(x2^2 + wb^2)"]
        c1::Real = 0.0, [unit = "rad", description = "Smooth positive part of x1"]
        c2::Real = 0.0, [unit = "rad", description = "Smooth positive part of x2"]
        T1::Real = 0.0, [unit = "N*m", description = "Forward flank force before the clamp"]
        T2::Real = 0.0, [unit = "N*m", description = "Backward flank force before the clamp"]
        T::Real = 0.0, [unit = "N*m", description = "Torque carried from a to b"]
    end
    @equations begin
        w ~ a.f - b.f
        ddt(phi) ~ w
        x1 ~ phi - gap / 2
        x2 ~ -phi - gap / 2
        r1 ~ sqrt(x1 * x1 + wb * wb)
        r2 ~ sqrt(x2 * x2 + wb * wb)
        c1 ~ 0.5 * wb * wb / (r1 - x1)
        c2 ~ 0.5 * wb * wb / (r2 - x2)
        T1 ~ k * c1 + d * w * c1 / r1
        T2 ~ k * c2 - d * w * c2 / r2
        T ~ 0.5 * (T1 + sqrt(T1 * T1 + feps * feps)) - 0.5 * (T2 + sqrt(T2 * T2 + feps * feps))
        a.e ~ T
        b.e ~ -T
    end
    @orientation begin
        a => :in
        b => :in
    end
end
