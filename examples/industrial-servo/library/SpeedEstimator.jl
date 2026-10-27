@block SpeedEstimator begin
    # Plan 9.6b `encoder` variant: the drive's speed estimate from the quantized absolute
    # encoder.  A 1 kHz backward difference of the 24-bit angle, followed by a first-order
    # low-pass (alpha = 0.8, about 285 Hz at 1 kHz), because a raw difference of a quantized
    # angle is a staircase.  This is sensor/firmware code, not plant physics.
    @constants sample_period::Real = 1.0e-3, [unit = "s", min = 1.0e-12, description = "Speed-estimate sample period (1 kHz)"]
    @parameters begin
        alpha::Real = 0.8, [min = 0.0, description = "Low-pass coefficient of the new sample"]
    end
    @inputs theta::Real, [unit = "rad"]
    @outputs begin
        w::Real = 0.0, [unit = "rad/s"]
        w_raw::Real = 0.0, [unit = "rad/s"]
    end
    @variables begin
        prev_theta::Real = 0.0, [description = "Quantized angle from the previous tick"]
        w_f::Real = 0.0, [description = "Filtered speed estimate"]
        started::Int = 0, [description = "0 before the first difference is available"]
    end
    @discrete Ts = sample_period begin
        if started == 0
            w_raw = 0.0
            w_f = 0.0
            started = 1
        else
            w_raw = (theta - prev_theta) / Ts
            w_f = w_f + alpha * (w_raw - w_f)
        end
        prev_theta = theta
        w = w_f
    end
end
