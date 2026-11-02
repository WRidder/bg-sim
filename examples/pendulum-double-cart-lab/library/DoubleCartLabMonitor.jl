@block DoubleCartLabMonitor begin
    # What the dashboards of the double-cart lab rig show (written by design/dashboards.py: do not edit).
    # Sampled at the controller's own rate (`sample_time`), so the block adds no solver stops: the absolute
    # link angles from the upward vertical in degrees, wrapped to [-181, 179) (from the joint encoders,
    # th1 = q1 - 90 deg, th2 = th1 + q2, the convention of the firmware; the cut sits 1 deg past -180 deg,
    # so a link hanging at rest does not flicker between -180 and +180), the larger of the two, and the peak
    # cart travel |x| since the start. The constant outputs are the limit lines of the cart plot: the rubber
    # end stops at +-x_rail and the robustness test's pass limit +-x_pass.
    @constants sample_time::Real = 0.001, [unit = "s", min = 1.0e-12, description = "Sample time (the controller's period)"]
    @inputs begin
        x::Real, [unit = "m", description = "Cart position (Rail/qout)"]
        q1::Real, [unit = "rad", description = "Joint 1 encoder: link 1 from the rail's x axis (Joint1/qout)"]
        q2::Real, [unit = "rad", description = "Joint 2 encoder: link 2 relative to link 1 (Joint2/qout)"]
    end
    @parameters begin
        x_rail::Real = 1.0, [unit = "m", description = "End stops: the free travel of the cart centre"]
        x_pass::Real = 0.95, [unit = "m", description = "Travel limit of the robustness test's pass rule"]
    end
    @variables begin
        a1::Real = -180.0, [description = "Link 1 from upright (deg), sampled"]
        a2::Real = -180.0, [description = "Link 2 from upright (deg), sampled"]
        xp::Real = 0.0, [unit = "m", description = "Peak |x| so far, sampled"]
    end
    @outputs begin
        th1::Real, [description = "Link 1 from the upward vertical (deg), wrapped to [-181, 179)"]
        th2::Real, [description = "Link 2 from the upward vertical (deg), wrapped to [-181, 179)"]
        dev::Real, [description = "The larger |angle| of the two links from upright (deg)"]
        x_peak::Real, [unit = "m", description = "Peak cart travel |x| since the start"]
        stop_hi::Real, [unit = "m", description = "End stop at +x_rail"]
        stop_lo::Real, [unit = "m", description = "End stop at -x_rail"]
        lim_hi::Real, [unit = "m", description = "Pass limit of the robustness test, +x_pass"]
        lim_lo::Real, [unit = "m", description = "Pass limit of the robustness test, -x_pass"]
    end
    @discrete Ts = sample_time begin
        t1 = q1 - 1.5707963267948966
        t2 = t1 + q2
        a1 = (mod(t1 + 3.159045946109736, 6.283185307179586) - 3.159045946109736) * 57.29577951308232
        a2 = (mod(t2 + 3.159045946109736, 6.283185307179586) - 3.159045946109736) * 57.29577951308232
        xp = max(xp, abs(x))
    end
    @equations begin
        th1 ~ a1
        th2 ~ a2
        dev ~ max(abs(a1), abs(a2))
        x_peak ~ xp
        stop_hi ~ x_rail
        stop_lo ~ -x_rail
        lim_hi ~ x_pass
        lim_lo ~ -x_pass
    end
end
