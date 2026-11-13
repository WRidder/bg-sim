@block SpiderStatus begin
    # Measurements of the spider: body pose and attitude, body speed, the eight contact
    # normal forces and their sum. The contact count is a smooth gate per foot,
    # `tanh(f_n / f_ref)`: 0 for an unloaded foot, 1 for a foot carrying more than a few
    # `f_ref`, so it counts the loaded feet without introducing switching events.
    @inputs begin
        g::Vec{7}, [description = "Body pose"]
        V::Vec{6}, [description = "Body twist [w; v] in the body frame"]
        f1::Real, [unit = "N"]
        f2::Real, [unit = "N"]
        f3::Real, [unit = "N"]
        f4::Real, [unit = "N"]
        f5::Real, [unit = "N"]
        f6::Real, [unit = "N"]
        f7::Real, [unit = "N"]
        f8::Real, [unit = "N"]
    end
    @outputs begin
        load::Real, [unit = "N", description = "Sum of the eight contact normal forces"]
        contact::Real, [unit = "1", description = "Smooth number of loaded feet"]
        height::Real, [unit = "m", description = "Body origin height"]
        x::Real, [unit = "m"]
        y::Real, [unit = "m"]
        z::Real, [unit = "m"]
        roll_deg::Real, [unit = "deg"]
        pitch_deg::Real, [unit = "deg"]
        yaw_deg::Real, [unit = "deg"]
        speed::Real, [unit = "m/s", description = "Body speed"]
        v_fwd::Real, [unit = "m/s", description = "Body velocity along the body x axis (forward)"]
        v_left::Real, [unit = "m/s", description = "Body velocity along the body y axis (left)"]
        wb::Real, [unit = "rad/s", description = "Body yaw rate"]
    end
    @parameters begin
        f_ref::Real = 0.08, [unit = "N", min = 1.0e-6, description = "Contact gate force scale"]
    end
    @variables begin
        sb::Real = 1.0, [unit = "1"]
        R::Mat{3,3} = [1.0 0.0 0.0; 0.0 1.0 0.0; 0.0 0.0 1.0], [unit = "1"]
    end
    @equations begin
        sb ~ g[1] * g[1] + g[2] * g[2] + g[3] * g[3] + g[4] * g[4]
        R[1, 1] ~ (g[1] * g[1] + g[2] * g[2] - g[3] * g[3] - g[4] * g[4]) / sb
        R[1, 2] ~ 2.0 * (g[2] * g[3] - g[1] * g[4]) / sb
        R[1, 3] ~ 2.0 * (g[2] * g[4] + g[1] * g[3]) / sb
        R[2, 1] ~ 2.0 * (g[2] * g[3] + g[1] * g[4]) / sb
        R[2, 2] ~ (g[1] * g[1] - g[2] * g[2] + g[3] * g[3] - g[4] * g[4]) / sb
        R[2, 3] ~ 2.0 * (g[3] * g[4] - g[1] * g[2]) / sb
        R[3, 1] ~ 2.0 * (g[2] * g[4] - g[1] * g[3]) / sb
        R[3, 2] ~ 2.0 * (g[3] * g[4] + g[1] * g[2]) / sb
        R[3, 3] ~ (g[1] * g[1] - g[2] * g[2] - g[3] * g[3] + g[4] * g[4]) / sb
        load ~ f1 + f2 + f3 + f4 + f5 + f6 + f7 + f8
        contact ~ tanh(f1 / f_ref) + tanh(f2 / f_ref) + tanh(f3 / f_ref) + tanh(f4 / f_ref) +
                  tanh(f5 / f_ref) + tanh(f6 / f_ref) + tanh(f7 / f_ref) + tanh(f8 / f_ref)
        height ~ g[7]
        x ~ g[5]
        y ~ g[6]
        z ~ g[7]
        roll_deg ~ 180.0 / pi * atan(2.0 * (g[1] * g[2] + g[3] * g[4]),
                                      1.0 - 2.0 * (g[2] * g[2] + g[3] * g[3]))
        pitch_deg ~ 180.0 / pi * asin(clamp(2.0 * (g[1] * g[3] - g[4] * g[2]), -1.0, 1.0))
        yaw_deg ~ 180.0 / pi * atan(2.0 * (g[1] * g[4] + g[2] * g[3]),
                                    1.0 - 2.0 * (g[3] * g[3] + g[4] * g[4]))
        speed ~ sqrt(V[4] * V[4] + V[5] * V[5] + V[6] * V[6])
        v_fwd ~ V[4]
        v_left ~ V[5]
        wb ~ V[3]
    end
end
