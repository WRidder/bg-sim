@block Steering begin
    # Steering geometry: the driver's steering input (-1 full left lock .. 1 full right lock)
    # to the road-wheel angles of the two front wheels (positive = turning left, about the
    # chassis z axis). The mean angle is d = -steer * dmax; Ackermann steering turns both
    # wheels about the centre of the rear axle's turning circle:
    #
    #   tan(d_left)  = L tan(d) / (L - t/2 tan(d))      (the inner wheel of a left turn)
    #   tan(d_right) = L tan(d) / (L + t/2 tan(d))
    #
    # and `ackermann` blends between parallel steering (0) and full Ackermann (1).
    @inputs steer::Real, [unit = "1", description = "Steering input, -1 (full left) .. 1 (full right)"]
    @outputs begin
        dl::Real, [unit = "rad", description = "Road-wheel angle, front left (positive left)"]
        dr::Real, [unit = "rad", description = "Road-wheel angle, front right (positive left)"]
        dm::Real, [unit = "rad", description = "Mean road-wheel angle"]
    end
    @parameters begin
        dmax::Real = 0.35, [unit = "rad", min = 0, description = "Mean road-wheel angle at full lock"]
        L::Real = 2.8, [unit = "m", min = 0, description = "Wheelbase"]
        track::Real = 1.6, [unit = "m", min = 0, description = "Front track"]
        ackermann::Real = 1.0, [unit = "1", description = "Ackermann share (0 parallel, 1 full)"]
    end
    @variables td::Real = 0.0, [unit = "1", description = "tan of the mean angle"]
    @equations begin
        dm ~ -clamp(steer, -1.0, 1.0) * dmax
        td ~ tan(dm)
        dl ~ (1 - ackermann) * dm + ackermann * atan(L * td / (L - 0.5 * track * td))
        dr ~ (1 - ackermann) * dm + ackermann * atan(L * td / (L + 0.5 * track * td))
    end
end
