@block WheelTap begin
    # Null-space allocation tap on the **measured** motor torques of the four-wheel pyramid
    # (X-MB4): a sensor. With A = [a_1 a_2 a_3 a_4] the allocation matrix (see `Allocator`):
    #
    #   Tbx, Tby, Tbz = -A tau        the torque the four motors actually put on the body
    #   nsp           = n . tau       the null-space component, n = (1, -1, 1, -1) / 2
    #   ntau          = |tau|^2       total squared torque (min-norm solutions minimise it)
    #   proj          = |A^+ A tau|^2 the part of it that reaches the body
    #   resid         = ntau - proj - nsp^2, identically 0 (range and null space are orthogonal,
    #                   A^+ A + n n^T = I on the four wheel torques)
    @parameters begin
        beta::Real = 0.9553166181245093, [unit = "rad", description = "Wheel axis tilt from the body z axis"]
    end
    @inputs begin
        t1::Real
        t2::Real
        t3::Real
        t4::Real
    end
    @outputs begin
        Tbx::Real
        Tby::Real
        Tbz::Real
        nsp::Real
        ntau::Real
        proj::Real
        resid::Real
    end
    @equations begin
        Tbx ~ -sin(beta) * (t1 - t3)
        Tby ~ -sin(beta) * (t2 - t4)
        Tbz ~ -cos(beta) * (t1 + t2 + t3 + t4)
        nsp ~ 0.5 * (t1 - t2 + t3 - t4)
        ntau ~ t1 * t1 + t2 * t2 + t3 * t3 + t4 * t4
        proj ~ Tbx * Tbx / (2 * sin(beta)^2) + Tby * Tby / (2 * sin(beta)^2) + Tbz * Tbz / (4 * cos(beta)^2)
        resid ~ ntau - proj - nsp * nsp
    end
end
