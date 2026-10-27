@block RoadProfile begin
    # The road-velocity table of plan 9.4 (a 5 cm plateau bump) as a signal source:
    # +0.5 m/s for 0.1 s at t = 0.5 s, then 0, then -0.5 m/s for 0.1 s at t = 1.5 s.
    # It is a source block, not plant physics (D28); the plant sees it only through the
    # VelocitySource's flow port. This replaces `stdlib:sources/TimeTable` in this sample:
    # that block's hold/interpolate conditions are identically zero inside every sample
    # interval, so the event collector fires at every integrator step (W206).
    @outputs y::Real = 0.0, [unit = "m/s", description = "Road velocity"]
    @parameters begin
        t_up::Real = 0.5, [unit = "s", description = "Start of the rising ramp"]
        t_hold::Real = 0.6, [unit = "s", description = "End of the rising ramp; start of the plateau"]
        t_down::Real = 1.5, [unit = "s", description = "Start of the falling ramp"]
        t_flat::Real = 1.6, [unit = "s", description = "End of the falling ramp; back to the flat road"]
        v_rise::Real = 0.5, [unit = "m/s", description = "Road velocity while the bump is climbed"]
    end
    @equations begin
        y ~ ifelse(
            t >= t_up && t < t_hold,
            v_rise,
            ifelse(t >= t_down && t < t_flat, -v_rise, 0.0),
        )
    end
end
