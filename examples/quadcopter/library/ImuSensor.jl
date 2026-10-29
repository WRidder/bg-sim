@block ImuSensor begin
    # Strapdown IMU (gyro + accelerometer) sampled at 500 Hz, plus its anti-alias filters.
    #
    # Inputs are the TRUE body rates `w` and the TRUE specific force `f` (a sensor tap on the
    # plant, `RotorWrench.fs`); the outputs are what the firmware gets:
    #
    #   gyro, acc          raw samples = truth + constant bias + white noise (sigma per sample)
    #   gyro_f, acc_f      the same through a second-order Butterworth low-pass (direct form I,
    #                      coefficients `bgc/agc` and `bac/aac` from design/design.py)
    #
    # The white noise is deterministic: Box-Muller on the same sine hash the stdlib `Noise`
    # block uses, evaluated per tick and channel (6 channels per sample). It lives in the
    # discrete code because the stdlib `Noise` is a function of `t` (a `floor` staircase) and
    # every one of its steps would be a solver event at this rate. `seed` selects the sequence.
    @inputs begin
        w::Vec{3}
        f::Vec{3}
    end
    @outputs begin
        gyro::Vec{3} = [0.0, 0.0, 0.0]
        gyro_f::Vec{3} = [0.0, 0.0, 0.0]
        acc::Vec{3} = [0.0, 0.0, 9.81]
        acc_f::Vec{3} = [0.0, 0.0, 9.81]
    end
    @parameters begin
        bias_g::Vec{3} = [0.004, -0.003, 0.002], [unit = "rad/s", description = "Constant gyro bias (about 0.2 deg/s)"]
        bias_a::Vec{3} = [0.05, -0.04, 0.08], [unit = "m/s^2", description = "Constant accelerometer bias"]
        sigma_g::Real = 0.003, [unit = "rad/s", min = 0, description = "Gyro white noise per 500 Hz sample (0.01 deg/s/sqrt(Hz) over 250 Hz)"]
        sigma_a::Real = 0.05, [unit = "m/s^2", min = 0, description = "Accelerometer white noise per sample (300 ug/sqrt(Hz) over 250 Hz)"]
        seed::Real = 1.0, [description = "Noise sequence selector"]
        bgc::Vec{3} = [0.0, 0.0, 0.0], [description = "Gyro low-pass numerator b0 b1 b2"]
        agc::Vec{2} = [0.0, 0.0], [description = "Gyro low-pass denominator a1 a2 (a0 = 1)"]
        bac::Vec{3} = [0.0, 0.0, 0.0], [description = "Accelerometer low-pass numerator b0 b1 b2"]
        aac::Vec{2} = [0.0, 0.0], [description = "Accelerometer low-pass denominator a1 a2"]
    end
    @variables begin
        k::Real = 0.0, [description = "Sample counter"]
        gx1::Vec{3} = [0.0, 0.0, 0.0], [description = "Gyro input, one sample ago"]
        gx2::Vec{3} = [0.0, 0.0, 0.0], [description = "Gyro input, two samples ago"]
        gy1::Vec{3} = [0.0, 0.0, 0.0], [description = "Filtered gyro, one sample ago"]
        gy2::Vec{3} = [0.0, 0.0, 0.0], [description = "Filtered gyro, two samples ago"]
        ax1::Vec{3} = [0.0, 0.0, 9.81], [description = "Accel input, one sample ago"]
        ax2::Vec{3} = [0.0, 0.0, 9.81], [description = "Accel input, two samples ago"]
        ay1::Vec{3} = [0.0, 0.0, 9.81], [description = "Filtered accel, one sample ago"]
        ay2::Vec{3} = [0.0, 0.0, 9.81], [description = "Filtered accel, two samples ago"]
    end
    @discrete Ts = 2e-3 begin
        k = k + 1.0
        n = [0.0, 0.0, 0.0, 0.0, 0.0, 0.0]
        for j in 1:6
            u1 = mod(sin(seed * 12.9898 + k * 78.233 + j * 37.719) * 43758.5453, 1.0) + 1.0e-12
            u2 = mod(sin(seed * 39.3468 + k * 11.135 + j * 93.989) * 24634.6345, 1.0)
            n[j] = sqrt(-2.0 * log(u1)) * cos(6.283185307179586 * u2)
        end
        gr = w + bias_g + sigma_g * [n[1], n[2], n[3]]
        ar = f + bias_a + sigma_a * [n[4], n[5], n[6]]
        gf = bgc[1] * gr + bgc[2] * gx1 + bgc[3] * gx2 - agc[1] * gy1 - agc[2] * gy2
        af = bac[1] * ar + bac[2] * ax1 + bac[3] * ax2 - aac[1] * ay1 - aac[2] * ay2
        gx2 = gx1
        gx1 = gr
        gy2 = gy1
        gy1 = gf
        ax2 = ax1
        ax1 = ar
        ay2 = ay1
        ay1 = af
        gyro = gr
        gyro_f = gf
        acc = ar
        acc_f = af
    end
end
