@block Nav begin
    # Navigation solution, taken as perfect: a read-out of the floating body's pose chart
    # (qw qx qy qz x y z) and body twist [w; v]. Ingenuity fuses an IMU, a laser altimeter and a
    # downward camera (Grip et al. 2018); this example assumes their estimate equals the truth, so
    # the flight controller and the plots read this block.
    #
    #   q, p, vw    attitude quaternion, CoM position and world velocity
    #   alt         height of the CoM above its resting height on the gear (`z_rest`)
    #   roll, pitch, yaw   ZYX Euler angles; tilt   angle of the body z axis from the vertical
    #   x, y, z     scalar position (what the 3D pose binding needs), yaw_deg for the plots
    @inputs begin
        pose::Vec{7}
        V::Vec{6}
    end
    @outputs begin
        q::Vec{4}
        p::Vec{3}
        vw::Vec{3}
        wb::Vec{3}
        x::Real, [unit = "m"]
        y::Real, [unit = "m"]
        z::Real, [unit = "m"]
        alt::Real, [unit = "m"]
        vz::Real, [unit = "m/s"]
        roll::Real, [unit = "rad"]
        pitch::Real, [unit = "rad"]
        yaw::Real, [unit = "rad"]
        yaw_deg::Real, [unit = "deg"]
        tilt_deg::Real, [unit = "deg"]
        ground_speed::Real, [unit = "m/s"]
    end
    @parameters z_rest::Real = 0.0, [unit = "m", description = "CoM height resting on the gear"]
    @variables begin
        s::Real = 1.0, [description = "Squared quaternion norm"]
        R::Mat{3,3} = [1.0 0.0 0.0; 0.0 1.0 0.0; 0.0 0.0 1.0], [description = "Body-to-world rotation"]
    end
    @equations begin
        s ~ pose[1] * pose[1] + pose[2] * pose[2] + pose[3] * pose[3] + pose[4] * pose[4]
        R[1, 1] ~ (pose[1] * pose[1] + pose[2] * pose[2] - pose[3] * pose[3] - pose[4] * pose[4]) / s
        R[1, 2] ~ 2 * (pose[2] * pose[3] - pose[1] * pose[4]) / s
        R[1, 3] ~ 2 * (pose[2] * pose[4] + pose[1] * pose[3]) / s
        R[2, 1] ~ 2 * (pose[2] * pose[3] + pose[1] * pose[4]) / s
        R[2, 2] ~ (pose[1] * pose[1] - pose[2] * pose[2] + pose[3] * pose[3] - pose[4] * pose[4]) / s
        R[2, 3] ~ 2 * (pose[3] * pose[4] - pose[1] * pose[2]) / s
        R[3, 1] ~ 2 * (pose[2] * pose[4] - pose[1] * pose[3]) / s
        R[3, 2] ~ 2 * (pose[3] * pose[4] + pose[1] * pose[2]) / s
        R[3, 3] ~ (pose[1] * pose[1] - pose[2] * pose[2] - pose[3] * pose[3] + pose[4] * pose[4]) / s
        q[1] ~ pose[1]
        q[2] ~ pose[2]
        q[3] ~ pose[3]
        q[4] ~ pose[4]
        p[1] ~ pose[5]
        p[2] ~ pose[6]
        p[3] ~ pose[7]
        x ~ pose[5]
        y ~ pose[6]
        z ~ pose[7]
        alt ~ pose[7] - z_rest
        vw[1] ~ R[1, 1] * V[4] + R[1, 2] * V[5] + R[1, 3] * V[6]
        vw[2] ~ R[2, 1] * V[4] + R[2, 2] * V[5] + R[2, 3] * V[6]
        vw[3] ~ R[3, 1] * V[4] + R[3, 2] * V[5] + R[3, 3] * V[6]
        vz ~ vw[3]
        wb[1] ~ V[1]
        wb[2] ~ V[2]
        wb[3] ~ V[3]
        roll ~ atan(R[3, 2], R[3, 3])
        pitch ~ atan(-R[3, 1], hypot(R[3, 2], R[3, 3]))
        yaw ~ atan(R[2, 1], R[1, 1])
        yaw_deg ~ 57.29577951308232 * atan(R[2, 1], R[1, 1])
        tilt_deg ~ 57.29577951308232 * atan(hypot(R[3, 1], R[3, 2]), R[3, 3])
        ground_speed ~ hypot(vw[1], vw[2])
    end
end
