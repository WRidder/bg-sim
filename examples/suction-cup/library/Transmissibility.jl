@block Transmissibility begin
    # Lock-in demodulator for a chirp: the transmissibility from the tool's lateral motion to
    # the payload's. The response is the payload's lateral motion without the tool's slow
    # moves, y = y_P - x_T + x_c (y_P the payload centre of mass, x_T the tool position, x_c the
    # chirp part of it). It is multiplied by sin and cos of the chirp phase and low-passed by
    # two first-order stages at w_lp:
    #
    #   I = LP2(2 y sin(phase)),  Q = LP2(2 y cos(phase)),  |Y| = sqrt(I^2 + Q^2),
    #
    # so |Y| is the amplitude of y at the chirp frequency. The chirp amplitude and frequency go
    # through the same low-pass, so the outputs are aligned in time:
    #   TR = |Y| / A (1 below the resonance, the peak at the resonance, -> 0 above it).
    # The chirp must sweep slowly against w_lp (the demodulator then follows it). The filters run
    # only while the chirp amplitude is above A_min, so before the chirp TR is 0 and after it TR and
    # fl hold their last values (an XY plot of TR against fl ends at the end of the sweep).
    @inputs begin
        gp::Vec{7}, [description = "Payload pose (its x, gp[5], is the centre of mass lateral position)"]
        gt::Vec{7}, [description = "Tool pose (its x, gt[5], is the tool lateral position)"]
        xc::Real, [unit = "m", description = "Chirp displacement of the tool"]
        sp::Real, [unit = "1", description = "sin of the chirp phase"]
        cp::Real, [unit = "1", description = "cos of the chirp phase"]
        A::Real, [unit = "m", description = "Chirp amplitude"]
        f::Real, [unit = "Hz", description = "Chirp frequency"]
    end
    @parameters begin
        w_lp::Real = 6.0, [unit = "rad/s", min = 1.0e-6, description = "Corner of each low-pass stage"]
        A_min::Real = 5.0e-5, [unit = "m", min = 1.0e-12, description = "Smallest amplitude for which TR is reported"]
    end
    @variables begin
        yr::Real = 0.0, [unit = "m", description = "Response without the slow tool moves"]
        I1::Real = 0.0, [unit = "m", state = :prefer]
        I2::Real = 0.0, [unit = "m", state = :prefer]
        Q1::Real = 0.0, [unit = "m", state = :prefer]
        Q2::Real = 0.0, [unit = "m", state = :prefer]
        A1::Real = 0.0, [unit = "m", state = :prefer]
        A2::Real = 0.0, [unit = "m", state = :prefer]
        F1::Real = 0.0, [unit = "Hz", state = :prefer]
        F2::Real = 0.0, [unit = "Hz", state = :prefer]
        Y::Real = 0.0, [unit = "m", description = "Response amplitude at the chirp frequency"]
        on::Real = 0.0, [unit = "1", description = "1 while the chirp runs (A > A_min)"]
    end
    @outputs begin
        TR::Real, [unit = "1", description = "Transmissibility |Y| / A (0 before the chirp, held after it)"]
        fl::Real, [unit = "Hz", description = "Chirp frequency through the same low-pass"]
        Al::Real, [unit = "m", description = "Chirp amplitude through the same low-pass"]
    end
    @equations begin
        yr ~ gp[5] - gt[5] + xc
        on ~ ifelse(A > A_min, 1.0, 0.0)
        ddt(I1) ~ on * w_lp * (2 * yr * sp - I1)
        ddt(I2) ~ on * w_lp * (I1 - I2)
        ddt(Q1) ~ on * w_lp * (2 * yr * cp - Q1)
        ddt(Q2) ~ on * w_lp * (Q1 - Q2)
        ddt(A1) ~ on * w_lp * (A - A1)
        ddt(A2) ~ on * w_lp * (A1 - A2)
        ddt(F1) ~ on * w_lp * (f - F1)
        ddt(F2) ~ on * w_lp * (F1 - F2)
        Y ~ sqrt(I2 * I2 + Q2 * Q2 + 1.0e-30)
        TR ~ ifelse(A2 > A_min, Y / A2, 0.0)
        fl ~ F2
        Al ~ A2
    end
end
