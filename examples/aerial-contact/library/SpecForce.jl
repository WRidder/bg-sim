@block SpecForce begin
    # Accelerometer tap at 250 Hz: the specific force (every non-gravitational force over the mass,
    # in the body frame) that an accelerometer at the centre of mass of the multirotor measures,
    # from the TRUE body twist V = [w; v] (body frame) and the pose chart (gravity direction):
    #
    #   f = dv/dt + w x v + g R^T e_z      (R = body-to-world rotation)
    #
    # The derivative is the backward difference of the twist over one tick. It sees the thrust, the
    # air drag AND the reaction of the manipulator, which is what the navigation filter needs once
    # the end-effector pushes on the wall (the reaction is large: m g tan(theta_sp)).
    @inputs begin
        V::Vec{6}
        pose::Vec{7}
    end
    @outputs fs::Vec{3} = [0.0, 0.0, 9.81]
    @parameters g0::Real = 9.81, [unit = "m/s^2", description = "Gravity"]
    @variables begin
        vprev::Vec{3} = [0.0, 0.0, 0.0], [description = "Body-frame velocity of the previous tick"]
    end
    @discrete Ts = 4e-3 begin
        s = pose[1] * pose[1] + pose[2] * pose[2] + pose[3] * pose[3] + pose[4] * pose[4]
        r31 = 2 * (pose[2] * pose[4] - pose[1] * pose[3]) / s
        r32 = 2 * (pose[3] * pose[4] + pose[1] * pose[2]) / s
        r33 = (pose[1] * pose[1] - pose[2] * pose[2] - pose[3] * pose[3] + pose[4] * pose[4]) / s
        vb = [V[4], V[5], V[6]]
        wv = cross([V[1], V[2], V[3]], vb)
        fs = (vb - vprev) / Ts + wv + g0 * [r31, r32, r33]
        vprev = vb
    end
end
