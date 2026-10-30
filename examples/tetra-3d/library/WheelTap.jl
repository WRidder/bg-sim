@block WheelTap begin
    # Null-space allocation tap on the **measured** motor torques of the
    # four face-normal wheels of the tetrahedron (X5.6): a sensor. With A = [a_1 a_2 a_3 a_4]
    # the allocation matrix (see `Allocator`, A A^T = 4/3 I, n = (1, 1, 1, 1)/2):
    #
    #   Tbx, Tby, Tbz = -A tau        the torque the four motors actually put on the body
    #   nsp           = n . tau       the null-space component
    #   ntau          = |tau|^2       total squared torque (min-norm solutions minimise it)
    #   proj          = |A^+ A tau|^2 = 3/4 |A tau|^2, the part of it that reaches the body
    #   resid         = ntau - proj - nsp^2, identically 0 (range and null space are orthogonal)
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
        Tbx ~ -0.816496580927726 * (t2 - t3)
        Tby ~ 0.9428090415820634 * t1 - 0.4714045207910317 * (t2 + t3)
        Tbz ~ t4 - (t1 + t2 + t3) / 3
        nsp ~ 0.5 * (t1 + t2 + t3 + t4)
        ntau ~ t1 * t1 + t2 * t2 + t3 * t3 + t4 * t4
        proj ~ 0.75 * (Tbx * Tbx + Tby * Tby + Tbz * Tbz)
        resid ~ ntau - proj - nsp * nsp
    end
end
