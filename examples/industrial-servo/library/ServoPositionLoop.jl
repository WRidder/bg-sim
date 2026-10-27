@block ServoPositionLoop begin
    # Plan 9.6b: the 200 Hz outer loop. A proportional position loop produces the speed
    # command, limited to +-w_max; a `mode` input selects the speed reference directly while
    # the drive is in speed mode (the first part of the run).  pos_err is exposed for the
    # acceptance checks.
    @constants sample_period::Real = 5.0e-3, [unit = "s", min = 1.0e-12, description = "Position-loop sample period (200 Hz)"]
    @parameters begin
        Kp::Real = 20.0, [unit = "1/s", description = "Position proportional gain"]
        w_max::Real = 200.0, [unit = "rad/s", min = 0.0, description = "Speed command limit"]
    end
    @inputs begin
        pos_ref::Real, [unit = "rad"]
        pos_meas::Real, [unit = "rad"]
        w_ref::Real, [unit = "rad/s"]
        mode::Real, [description = "0 = speed mode, 1 = position mode"]
    end
    @outputs begin
        w_cmd::Real = 0.0, [unit = "rad/s"]
        pos_err::Real = 0.0, [unit = "rad"]
        w_pos::Real = 0.0, [unit = "rad/s"]
    end
    @discrete Ts = sample_period begin
        pos_err = pos_ref - pos_meas
        w_pos = clamp(Kp * pos_err, -w_max, w_max)
        if mode > 0.5
            w_cmd = w_pos
        else
            w_cmd = clamp(w_ref, -w_max, w_max)
        end
    end
end
