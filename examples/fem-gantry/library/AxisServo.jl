@block AxisServo begin
    # The servo drive of one linear-motor axis of the gantry: a cascade of a P position loop,
    # a PI velocity loop with acceleration feedforward, an optional notch filter and the
    # current loop of the drive, all on the encoder of the axis (position and speed of the
    # motor's own carriage).
    #
    #   v_cmd = wp (x_ref - x) + v_ref                      position loop, wp = 2 pi fp
    #   F_v   = M wv ((v_cmd - v) + wv/4 int(v_cmd - v))     velocity loop, wv = 2 pi fv, zero at fv/4
    #   F_cmd = notch(F_v + kff M a_ref)                    notch at fn (depth: 1 is off)
    #   F'    = wi (kf F_cmd - F)                           current (force) loop, first order at fi
    #
    # M is the moving mass the axis drives (the gains are per unit mass), kf the motor's force
    # constant relative to nominal (1: the drive's model is right; 0.9 makes the motor 10 %
    # weaker than the controller assumes, the cause of racking between two parallel axes).
    # The notch is the controllable canonical form of Notch (stdlib:continuous/Notch):
    # y = u + (depth - 1) bw x2, so depth = 1 leaves it out of the loop exactly.
    @inputs begin
        x_ref::Real, [unit = "m"]
        v_ref::Real, [unit = "m/s"]
        a_ref::Real, [unit = "m/s^2"]
        x::Real, [unit = "m"]
        v::Real, [unit = "m/s"]
    end
    @outputs begin
        F::Real, [unit = "N", description = "Motor force"]
        err::Real, [unit = "m", description = "Following error x_ref - x"]
    end
    @parameters begin
        M::Real = 10.0, [unit = "kg", min = 1.0e-9, description = "Moving mass of the axis (the loop gains are per unit mass)"]
        fp::Real = 15.0, [unit = "Hz", min = 0, description = "Position loop bandwidth"]
        fv::Real = 60.0, [unit = "Hz", min = 0, description = "Velocity loop bandwidth"]
        kff::Real = 1.0, [min = 0, description = "Acceleration feedforward gain (1: the full M a_ref)"]
        fi::Real = 1000.0, [unit = "Hz", min = 1.0e-3, description = "Current (force) loop bandwidth"]
        kf::Real = 1.0, [min = 0, description = "Motor force constant relative to nominal"]
        fn::Real = 50.0, [unit = "Hz", min = 1.0e-3, description = "Notch centre frequency"]
        bn::Real = 20.0, [unit = "Hz", min = 1.0e-3, description = "Notch width (-3 dB band of a full notch)"]
        dn::Real = 1.0, [min = 0, description = "Notch depth: gain at fn (1: no notch, 0: full)"]
    end
    @variables begin
        xi::Real = 0.0, [unit = "m", description = "Integral of the velocity error"]
        n1::Real = 0.0, [description = "Notch state z"]
        n2::Real = 0.0, [description = "Notch state z'"]
        Fs::Real = 0.0, [unit = "N", state = :prefer, description = "Motor force (current loop state)"]
        vc::Real, [unit = "m/s", description = "Velocity command"]
        ev::Real, [unit = "m/s", description = "Velocity error"]
        u::Real, [unit = "N", description = "Force command before the notch"]
        Fc::Real, [unit = "N", description = "Force command"]
    end
    @equations begin
        vc ~ 6.283185307179586 * fp * (x_ref - x) + v_ref
        ev ~ vc - v
        ddt(xi) ~ ev
        u ~ M * 6.283185307179586 * fv * (ev + 1.5707963267948966 * fv * xi) + kff * M * a_ref
        ddt(n1) ~ n2
        ddt(n2) ~ u - (6.283185307179586 * fn)^2 * n1 - 6.283185307179586 * bn * n2
        Fc ~ u + (dn - 1.0) * 6.283185307179586 * bn * n2
        ddt(Fs) ~ 6.283185307179586 * fi * (kf * Fc - Fs)
        F ~ Fs
        err ~ x_ref - x
    end
end
