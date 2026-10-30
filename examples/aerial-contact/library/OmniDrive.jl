@block OmniDrive begin
    # Kinematics of the three omnidirectional wheels at 120 degrees (open loop, X5.8). The end-effector
    # locomotion command `cmd` = (vy, vz) in [-1, 1] is a body-velocity command in the plane of the wall
    # (y_e, z_e), scaled by `v_max` (m/s at command 1). Wheel k has the drive direction
    # d_k = (0, -sin a_k, cos a_k) (tangential to the circle of the wheel contacts, angle a_k) and free
    # rollers along the radius, so rolling without slip needs the surface speed
    #
    #   u_k = -v_max d_k . (vy, vz)          (the end-effector moves at -u_k along d_k)
    #
    # The three u_k sum to zero: a pure translation, the wheels hold the end-effector's rotation about
    # its axis. The animated wheel angles phi_k integrate u_k / r_wheel.
    @inputs cmd::Vec{2}
    @outputs begin
        u1::Real, [unit = "m/s"]
        u2::Real, [unit = "m/s"]
        u3::Real, [unit = "m/s"]
        phi1::Real, [unit = "rad"]
        phi2::Real, [unit = "rad"]
        phi3::Real, [unit = "rad"]
    end
    @parameters begin
        v_max::Real = 0.4, [unit = "m/s", min = 0, description = "End-effector speed at a velocity command of 1"]
        r_w::Real = 0.02, [unit = "m", min = 1.0e-6, description = "Wheel radius (animation only)"]
        a1::Real = 1.5707963267948966, [unit = "rad", description = "Angular position of wheel 1 about the end-effector axis"]
        a2::Real = 3.665191429188092, [unit = "rad", description = "Angular position of wheel 2"]
        a3::Real = 5.759586531581287, [unit = "rad", description = "Angular position of wheel 3"]
    end
    @variables begin
        p1::Real = 0.0, [state = :prefer, description = "Wheel 1 angle"]
        p2::Real = 0.0, [state = :prefer, description = "Wheel 2 angle"]
        p3::Real = 0.0, [state = :prefer, description = "Wheel 3 angle"]
    end
    @equations begin
        u1 ~ -v_max * (-sin(a1) * cmd[1] + cos(a1) * cmd[2])
        u2 ~ -v_max * (-sin(a2) * cmd[1] + cos(a2) * cmd[2])
        u3 ~ -v_max * (-sin(a3) * cmd[1] + cos(a3) * cmd[2])
        ddt(p1) ~ u1 / r_w
        ddt(p2) ~ u2 / r_w
        ddt(p3) ~ u3 / r_w
        phi1 ~ p1
        phi2 ~ p2
        phi3 ~ p3
    end
end
