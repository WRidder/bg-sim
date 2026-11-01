@block AS5048 begin
    # ams AS5048A (SPI) / AS5048B (I2C) 14-bit magnetic angle sensor on a passive joint, as the
    # outer controller sees it in its 1 kHz EtherCAT cycle. The value in the process image is the
    # angle `lat` before the cycle: the sensor's 100 us propagation delay, the mean age of its
    # 11.25 kHz sample, the SPI or I2C transfer and the copy into the process image. The block
    # samples at the cycle and takes the angle `lat` earlier from the joint rate,
    # theta(t - lat) = theta - w lat (exact to 1/2 alpha lat^2, below 1e-6 rad here), so the
    # latency is a parameter (the A/B toggle) and adds no event instants. Per reading:
    #
    #   theta_s = theta - w lat + a1 sin(theta + p1) + a2 sin(2 theta + p2) + sigma z + zero
    #   count   = floor(theta_s 2^bits / (2 pi)) mod 2^bits,   y = count 2 pi / 2^bits
    #
    # a1, a2: integral non-linearity (first harmonic: magnet eccentricity, second: field
    # distortion; datasheet INL +-0.8 deg), sigma z: the output noise (0.06 deg rms, z a standard
    # normal sample from a seeded Noise block), zero: the magnet's mounting angle. y is the absolute
    # single-turn register, so the controller unwraps it. With nrd > 1 only every nrd-th cycle
    # brings a new reading (a slower bus), the register is held in between.
    @constants sample_period::Real = 1e-3, [unit = "s", description = "Read period (the EtherCAT cycle)"]
    @inputs begin
        theta::Real, [unit = "rad", description = "True joint angle"]
        w::Real, [unit = "rad/s", description = "True joint rate"]
        z::Real, [description = "Standard normal noise sample"]
    end
    @outputs begin
        count::Real = 0.0, [description = "Angle register (0 .. 2^bits - 1)"]
        y::Real = 0.0, [unit = "rad", description = "Register as an angle in [0, 2 pi)"]
    end
    @parameters begin
        bits::Real = 14.0, [description = "Resolution in bits"]
        lat::Real = 1.875e-4, [unit = "s", min = 0, description = "Chain latency (age of the reading at the cycle)"]
        a1::Real = 0.0043633, [unit = "rad", description = "INL, first harmonic"]
        p1::Real = 0.5236, [unit = "rad", description = "INL, first-harmonic phase"]
        a2::Real = 0.0026180, [unit = "rad", description = "INL, second harmonic"]
        p2::Real = -1.0472, [unit = "rad", description = "INL, second-harmonic phase"]
        sigma::Real = 0.0010472, [unit = "rad", min = 0, description = "Output noise (rms)"]
        zero::Real = 0.0, [unit = "rad", description = "Magnet mounting angle"]
        nrd::Real = 1.0, [min = 1, description = "Cycles per new reading (1: every cycle)"]
    end
    @variables cnt::Real = 0.0, [description = "Cycles since the last reading"]
    @discrete Ts = sample_period begin
        cnt = cnt + 1.0
        if cnt >= nrd - 0.5
            cnt = 0.0
            th = theta - w * lat
            ths = th + a1 * sin(th + p1) + a2 * sin(2.0 * th + p2) + sigma * z + zero
            nn = 2.0^bits
            c = floor(ths * nn / 6.283185307179586)
            c = c - nn * floor(c / nn)
            count = c
            y = c * 6.283185307179586 / nn
        end
    end
end
