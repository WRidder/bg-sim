@block TiltMeter begin
    # Orientation meter for the multibond cube (a sensor, not plant physics): from the body pose
    # chart (qw, qx, qy, qz, x, y, z) it gives the same two numbers the equation block
    # `CornerCube` reports, so the two models compare signal by signal.
    #
    #   tilt  angle between the body diagonal n0 = (1,1,1)/sqrt 3 and the vertical,
    #         atan(|u - (n0.u) n0|, n0.u) with u = (R31, R32, R33) the third row of R(q)
    #   qerr  |q| - 1, the quaternion norm error
    @inputs pose::Vec{7}
    @outputs begin
        tilt::Real, [unit = "rad"]
        qerr::Real
    end
    @variables begin
        r31::Real = 0.0, [description = "R(q)[3,1]"]
        r32::Real = 0.0, [description = "R(q)[3,2]"]
        r33::Real = 1.0, [description = "R(q)[3,3]"]
    end
    @equations begin
        r31 ~ 2 * (pose[2] * pose[4] - pose[1] * pose[3]) / (pose[1] * pose[1] + pose[2] * pose[2] + pose[3] * pose[3] + pose[4] * pose[4])
        r32 ~ 2 * (pose[3] * pose[4] + pose[1] * pose[2]) / (pose[1] * pose[1] + pose[2] * pose[2] + pose[3] * pose[3] + pose[4] * pose[4])
        r33 ~ (pose[1] * pose[1] - pose[2] * pose[2] - pose[3] * pose[3] + pose[4] * pose[4]) / (pose[1] * pose[1] + pose[2] * pose[2] + pose[3] * pose[3] + pose[4] * pose[4])
        tilt ~ atan(hypot(0.7071067811865476 * (r31 - r32), 0.4082482904638631 * (r31 + r32 - 2 * r33)), 0.5773502691896258 * (r31 + r32 + r33))
        qerr ~ sqrt(pose[1] * pose[1] + pose[2] * pose[2] + pose[3] * pose[3] + pose[4] * pose[4]) - 1.0
    end
end
