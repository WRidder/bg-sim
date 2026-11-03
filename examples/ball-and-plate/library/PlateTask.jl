@block PlateTask begin
    # The task of the ball-and-plate rig: the reference position of the ball on the plate and its
    # first three derivatives (for the feed-forward of a tracking controller).
    #   task 0  hold: the centre;
    #   task 1  steps: x to x1 at t1, y to y1 at t2, both back to the centre at t3; with
    #           t_s > 0 every step is a quintic transition of length t_s (a set-point filter,
    #           with its derivatives for the feed-forward), with t_s = 0 a hard step;
    #   task 2  circle of radius `rc`, period `Tc` (counter-clockwise);
    #   task 3  figure-8 (Lissajous 1:2): x = a8 sin(w tau), y = b8 sin(2 w tau), period `T8`.
    # The circle and the figure-8 start at t0 from the centre and grow to full size over t_ramp
    # with a quintic smooth step s(tau): p = A s(tau / t_ramp) sin(w tau + phi), tau = t - t0,
    # so the reference starts at rest; its derivatives follow from the product rule.
    @outputs begin
        xd::Real, [unit = "m", description = "Reference x"]
        vxd::Real, [unit = "m/s", description = "Reference x velocity"]
        axd::Real, [unit = "m/s^2", description = "Reference x acceleration"]
        jxd::Real, [unit = "m/s^3", description = "Reference x jerk"]
        yd::Real, [unit = "m", description = "Reference y"]
        vyd::Real, [unit = "m/s", description = "Reference y velocity"]
        ayd::Real, [unit = "m/s^2", description = "Reference y acceleration"]
        jyd::Real, [unit = "m/s^3", description = "Reference y jerk"]
    end
    @parameters begin
        task::Int = 1, [options = ["hold", "steps", "circle", "figure-8"], description = "Task: 0 hold, 1 steps, 2 circle, 3 figure-8"]
        t1::Real = 1.0, [unit = "s", description = "Steps: time of the x step"]
        x1::Real = 0.1, [unit = "m", description = "Steps: x set-point"]
        t2::Real = 6.0, [unit = "s", description = "Steps: time of the y step"]
        y1::Real = 0.08, [unit = "m", description = "Steps: y set-point"]
        t3::Real = 11.0, [unit = "s", description = "Steps: back to the centre"]
        t_s::Real = 0.0, [unit = "s", min = 0, description = "Steps: length of the smooth transition (0: hard steps)"]
        t0::Real = 1.0, [unit = "s", description = "Path tasks: start"]
        t_ramp::Real = 3.0, [unit = "s", min = 1.0e-3, description = "Path tasks: growth from the centre to full size"]
        rc::Real = 0.08, [unit = "m", description = "Circle radius"]
        Tc::Real = 6.0, [unit = "s", min = 0.1, description = "Circle period"]
        a8::Real = 0.1, [unit = "m", description = "Figure-8 half width (x)"]
        b8::Real = 0.06, [unit = "m", description = "Figure-8 half height (y)"]
        T8::Real = 8.0, [unit = "s", min = 0.1, description = "Figure-8 period"]
    end
    @variables begin
        tau::Real = 0.0, [unit = "s", description = "Time since the start of the path"]
        on::Real = 0.0, [unit = "1", description = "1 on a path task after t0"]
        u::Real = 0.0, [unit = "1", description = "tau / t_ramp clamped to [0, 1]"]
        rmp::Real = 0.0, [unit = "1", description = "1 while growing"]
        s0::Real = 0.0, [unit = "1", description = "Smooth step"]
        s1::Real = 0.0, [unit = "1/s", description = "Its first derivative"]
        s2::Real = 0.0, [unit = "1/s^2", description = "Its second derivative"]
        s3::Real = 0.0, [unit = "1/s^3", description = "Its third derivative"]
        Ax::Real = 0.0, [unit = "m", description = "Amplitude x"]
        Ay::Real = 0.0, [unit = "m", description = "Amplitude y"]
        wx::Real = 1.0, [unit = "rad/s", description = "Angular frequency x"]
        wy::Real = 1.0, [unit = "rad/s", description = "Angular frequency y"]
        px::Real = 0.0, [unit = "rad", description = "Phase x"]
        cx0::Real = 0.0, [unit = "1"]
        cx1::Real = 0.0, [unit = "1"]
        cy0::Real = 0.0, [unit = "1"]
        cy1::Real = 0.0, [unit = "1"]
        sx::Real = 0.0, [unit = "m", description = "Step set-point x"]
        sy::Real = 0.0, [unit = "m", description = "Step set-point y"]
        ts::Real = 1.0, [unit = "s", description = "Transition length used (t_s, or 1 s when t_s = 0)"]
        hard::Real = 1.0, [unit = "1", description = "1 for hard steps (t_s = 0)"]
        v1::Real = 0.0, [unit = "1", description = "Progress of the transition at t1"]
        v2::Real = 0.0, [unit = "1", description = "Progress of the transition at t2"]
        v3::Real = 0.0, [unit = "1", description = "Progress of the transition at t3"]
        a1::Real = 0.0, [unit = "1", description = "1 inside the transition at t1"]
        a2::Real = 0.0, [unit = "1", description = "1 inside the transition at t2"]
        a3::Real = 0.0, [unit = "1", description = "1 inside the transition at t3"]
        q1::Vec{4} = [0.0, 0.0, 0.0, 0.0], [description = "Transition at t1 and its derivatives"]
        q2::Vec{4} = [0.0, 0.0, 0.0, 0.0], [description = "Transition at t2 and its derivatives"]
        q3::Vec{4} = [0.0, 0.0, 0.0, 0.0], [description = "Transition at t3 and its derivatives"]
        ex::Vec{4} = [0.0, 0.0, 0.0, 0.0], [description = "Smooth step reference x and its derivatives"]
        ey::Vec{4} = [0.0, 0.0, 0.0, 0.0], [description = "Smooth step reference y and its derivatives"]
    end
    @equations begin
        tau ~ t - t0
        on ~ ifelse(task >= 2 && t >= t0, 1.0, 0.0)
        u ~ clamp(tau / t_ramp, 0.0, 1.0)
        rmp ~ ifelse(tau > 0 && tau < t_ramp, 1.0, 0.0)
        s0 ~ u * u * u * (10 - 15 * u + 6 * u * u)
        s1 ~ rmp * (30 * u * u - 60 * u * u * u + 30 * u * u * u * u) / t_ramp
        s2 ~ rmp * (60 * u - 180 * u * u + 120 * u * u * u) / (t_ramp * t_ramp)
        s3 ~ rmp * (60 - 360 * u + 360 * u * u) / (t_ramp * t_ramp * t_ramp)
        Ax ~ ifelse(task == 2, rc, a8)
        Ay ~ ifelse(task == 2, rc, b8)
        wx ~ ifelse(task == 2, 6.283185307179586 / Tc, 6.283185307179586 / T8)
        wy ~ ifelse(task == 2, 6.283185307179586 / Tc, 12.566370614359172 / T8)
        px ~ ifelse(task == 2, 1.5707963267948966, 0.0)
        cx0 ~ sin(wx * tau + px)
        cx1 ~ cos(wx * tau + px)
        cy0 ~ sin(wy * tau)
        cy1 ~ cos(wy * tau)
        sx ~ ifelse(task == 1 && t >= t1 && t < t3, x1, 0.0)
        sy ~ ifelse(task == 1 && t >= t2 && t < t3, y1, 0.0)
        # smooth steps: q = S((t - ti)/ts) and its time derivatives (S the quintic smooth step)
        hard ~ ifelse(t_s > 0, 0.0, 1.0)
        ts ~ ifelse(t_s > 0, t_s, 1.0)
        v1 ~ clamp((t - t1) / ts, 0.0, 1.0)
        v2 ~ clamp((t - t2) / ts, 0.0, 1.0)
        v3 ~ clamp((t - t3) / ts, 0.0, 1.0)
        a1 ~ ifelse(t > t1 && t < t1 + ts, 1.0, 0.0)
        a2 ~ ifelse(t > t2 && t < t2 + ts, 1.0, 0.0)
        a3 ~ ifelse(t > t3 && t < t3 + ts, 1.0, 0.0)
        q1[1] ~ v1 * v1 * v1 * (10 - 15 * v1 + 6 * v1 * v1)
        q1[2] ~ a1 * (30 * v1 * v1 - 60 * v1 * v1 * v1 + 30 * v1 * v1 * v1 * v1) / ts
        q1[3] ~ a1 * (60 * v1 - 180 * v1 * v1 + 120 * v1 * v1 * v1) / (ts * ts)
        q1[4] ~ a1 * (60 - 360 * v1 + 360 * v1 * v1) / (ts * ts * ts)
        q2[1] ~ v2 * v2 * v2 * (10 - 15 * v2 + 6 * v2 * v2)
        q2[2] ~ a2 * (30 * v2 * v2 - 60 * v2 * v2 * v2 + 30 * v2 * v2 * v2 * v2) / ts
        q2[3] ~ a2 * (60 * v2 - 180 * v2 * v2 + 120 * v2 * v2 * v2) / (ts * ts)
        q2[4] ~ a2 * (60 - 360 * v2 + 360 * v2 * v2) / (ts * ts * ts)
        q3[1] ~ v3 * v3 * v3 * (10 - 15 * v3 + 6 * v3 * v3)
        q3[2] ~ a3 * (30 * v3 * v3 - 60 * v3 * v3 * v3 + 30 * v3 * v3 * v3 * v3) / ts
        q3[3] ~ a3 * (60 * v3 - 180 * v3 * v3 + 120 * v3 * v3 * v3) / (ts * ts)
        q3[4] ~ a3 * (60 - 360 * v3 + 360 * v3 * v3) / (ts * ts * ts)
        for k in 1:4
            ex[k] ~ ifelse(task == 1, (1 - hard) * x1 * (q1[k] - q3[k]), 0.0)
            ey[k] ~ ifelse(task == 1, (1 - hard) * y1 * (q2[k] - q3[k]), 0.0)
        end
        # p = A s c, c = sin(w tau + phi): c' = w cos, c'' = -w^2 sin, c''' = -w^3 cos
        xd ~ hard * sx + ex[1] + on * Ax * s0 * cx0
        vxd ~ ex[2] + on * Ax * (s1 * cx0 + s0 * wx * cx1)
        axd ~ ex[3] + on * Ax * (s2 * cx0 + 2 * s1 * wx * cx1 - s0 * wx * wx * cx0)
        jxd ~ ex[4] + on * Ax * (s3 * cx0 + 3 * s2 * wx * cx1 - 3 * s1 * wx * wx * cx0 - s0 * wx * wx * wx * cx1)
        yd ~ hard * sy + ey[1] + on * Ay * s0 * cy0
        vyd ~ ey[2] + on * Ay * (s1 * cy0 + s0 * wy * cy1)
        ayd ~ ey[3] + on * Ay * (s2 * cy0 + 2 * s1 * wy * cy1 - s0 * wy * wy * cy0)
        jyd ~ ey[4] + on * Ay * (s3 * cy0 + 3 * s2 * wy * cy1 - 3 * s1 * wy * wy * cy0 - s0 * wy * wy * wy * cy1)
    end
end
