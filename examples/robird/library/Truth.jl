@block Truth begin
    # Ground-truth read-out of a floating body (a sensor tap, not plant physics): from the pose
    # chart (qw, qx, qy, qz, x, y, z) and the body twist (w; v) of the `RigidBody3D` it gives the
    # signals the sensors, the plots, the checks and the 3D bindings use. The sensors read this
    # block; the flight controller never does.
    #
    #   q      attitude quaternion, p position (m), vw velocity in the world frame, wb body rates
    #   roll, pitch, yaw   ZYX Euler angles (rad); tilt   angle between the body z axis and the vertical
    #   x, y, z            the position again as scalars with unit m (what the 3D pose binding needs)
    #   qerr               quaternion norm error
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
        roll::Real, [unit = "rad"]
        pitch::Real, [unit = "rad"]
        yaw::Real, [unit = "rad"]
        tilt::Real, [unit = "rad"]
        qerr::Real
    end
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
        vw[1] ~ R[1, 1] * V[4] + R[1, 2] * V[5] + R[1, 3] * V[6]
        vw[2] ~ R[2, 1] * V[4] + R[2, 2] * V[5] + R[2, 3] * V[6]
        vw[3] ~ R[3, 1] * V[4] + R[3, 2] * V[5] + R[3, 3] * V[6]
        wb[1] ~ V[1]
        wb[2] ~ V[2]
        wb[3] ~ V[3]
        roll ~ atan(R[3, 2], R[3, 3])
        pitch ~ atan(-R[3, 1], hypot(R[3, 2], R[3, 3]))
        yaw ~ atan(R[2, 1], R[1, 1])
        tilt ~ atan(hypot(R[3, 1], R[3, 2]), R[3, 3])
        qerr ~ sqrt(s) - 1.0
    end
end
