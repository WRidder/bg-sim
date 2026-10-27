@block EncoderMonitor begin
    # A recording sensor for the `encoder` variants: the difference between the quantized
    # angle and the true angle, sampled on the encoder tick.  At that instant the difference
    # is the quantizer's rounding error (<= half an LSB), which is what the acceptance check
    # bounds.  This is not part of the plant or the control law.
    @constants sample_period::Real = 125.0e-6, [unit = "s", min = 1.0e-12, description = "Encoder tick"]
    @inputs begin
        theta::Real, [unit = "rad"]
        theta_q::Real, [unit = "rad"]
    end
    @outputs err::Real = 0.0, [unit = "rad"]
    @discrete Ts = sample_period begin
        err = theta_q - theta
    end
end
