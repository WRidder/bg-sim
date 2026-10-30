@block RubberMount begin
    # The M5 rubber shock mount between the arm tip and the end-effector: a rotational spring-damper
    # on the three rotations of the spherical joint (`stdlib:spatial/Spherical3D`).
    #
    # The joint's relative orientation is the unit quaternion Q = (w, v) (child in parent) and its
    # three Rotation ports carry the relative angular velocity components omega in the child frame.
    # The elastic energy U = 2 k (1 - w^2) = 2 k sin^2(theta/2) (about k theta^2 / 2) gives the exact
    # conservative torque on the child  -dU/d(theta) = -2 k w v  (child-frame components, because
    # dQ/dt = Q (x) (0, omega) / 2 gives dU/dt = 2 k w v . omega), and the damper adds -b omega.
    # The three outputs are the torque components on the child; the ports take them through `MSe`.
    # `angle` is the deflection angle (to first order, 2 |v|), a tap for the plots.
    @inputs begin
        qrel::Vec{4}
        om::Vec{3}
    end
    @outputs begin
        t1::Real, [unit = "N*m"]
        t2::Real, [unit = "N*m"]
        t3::Real, [unit = "N*m"]
        angle::Real, [unit = "rad"]
    end
    @parameters begin
        k::Real = 1.0, [unit = "N*m/rad", min = 0, description = "Rotational stiffness"]
        b::Real = 0.03, [unit = "N*m*s/rad", min = 0, description = "Rotational damping"]
    end
    @variables n2::Real = 1.0, [description = "Squared quaternion norm"]
    @equations begin
        n2 ~ qrel[1] * qrel[1] + qrel[2] * qrel[2] + qrel[3] * qrel[3] + qrel[4] * qrel[4]
        t1 ~ -2.0 * k * qrel[1] * qrel[2] / n2 - b * om[1]
        t2 ~ -2.0 * k * qrel[1] * qrel[3] / n2 - b * om[2]
        t3 ~ -2.0 * k * qrel[1] * qrel[4] / n2 - b * om[3]
        angle ~ 2.0 * sqrt((qrel[2] * qrel[2] + qrel[3] * qrel[3] + qrel[4] * qrel[4]) / n2 + 1.0e-18)
    end
end
