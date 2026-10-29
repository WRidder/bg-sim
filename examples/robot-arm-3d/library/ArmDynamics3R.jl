@block ArmDynamics3R begin
    # Hand-derived dynamics of a revolute-revolute-revolute arm with point masses (plan 9.8),
    # written in Hamiltonian form: the states are the joint angles `q` and the generalised
    # momenta `p = M(q) qd`, and every joint is a `Rotation` power port with `port.f = qd_i` and
    # `port.e = tau_i` into the arm.
    #
    #   joint 1  base yaw about the world z axis, inertia Jb
    #   joint 2  shoulder pitch, q2 = elevation of the upper arm above horizontal
    #   joint 3  elbow, q3 measured from the upper arm (positive raises the forearm)
    #   m2 sits at the elbow, m3 at the tip, links l2 and l3 are massless
    #
    #   r_e = l2 cos q2             z_e = l2 sin q2
    #   r_t = r_e + l3 cos(q2+q3)   z_t = z_e + l3 sin(q2+q3)
    #   T = 1/2 qd' M qd,   V = g (m2 z_e + m3 z_t)
    #   M11 = Jb + m2 r_e^2 + m3 r_t^2,   M12 = M13 = 0
    #   M22 = m2 l2^2 + m3 (l2^2 + l3^2 + 2 l2 l3 cos q3)
    #   M23 = m3 (l3^2 + l2 l3 cos q3),   M33 = m3 l3^2
    #
    # Lagrange's equations in momentum form are  ddt(p) = tau + dT/dq - dV/dq  with
    # dT/dq_k = 1/2 qd' (dM/dq_k) qd. Only M11, M22 and M23 depend on q, so dT/dq1 = 0 and
    # the three partial derivatives below are the whole Coriolis and centrifugal term
    # (checked symbolically against sympy: M, dT/dq and dV/dq all agree to zero).
    #
    # `E` is the total mechanical energy T + V (the potential is measured from the shoulder
    # height), the output the free-motion energy check reads. Power balance:
    # sum_i port_i.e port_i.f = dT/dt + dV/dt, so with no motors and g = 0, E is constant.
    @ports begin
        j1::Power{Rotation}
        j2::Power{Rotation}
        j3::Power{Rotation}
    end
    @parameters begin
        l2::Real = 0.4, [unit = "m", min = 0, description = "Upper arm length (shoulder to elbow)"]
        l3::Real = 0.3, [unit = "m", min = 0, description = "Forearm length (elbow to tip)"]
        m2::Real = 2.0, [unit = "kg", min = 0, description = "Point mass at the elbow"]
        m3::Real = 1.0, [unit = "kg", min = 0, description = "Point mass at the tip"]
        Jb::Real = 0.05, [unit = "kg*m^2", min = 0, description = "Base yaw inertia about the world z axis"]
        g::Real = 9.81, [unit = "m/s^2", min = 0, description = "Gravitational acceleration"]
    end
    @outputs begin
        q1::Real, [unit = "rad"]
        q2::Real, [unit = "rad"]
        q3::Real, [unit = "rad"]
        qd1::Real, [unit = "rad/s"]
        qd2::Real, [unit = "rad/s"]
        qd3::Real, [unit = "rad/s"]
        E::Real, [unit = "N*m"]
    end
    @variables begin
        q::Vec{3} = [0.0, 0.0, 0.0], [unit = "rad", state = :prefer, description = "Joint angles"]
        p::Vec{3} = [0.0, 0.0, 0.0], [unit = "N*m*s", state = :prefer, description = "Generalised momenta M qd"]
        qd::Vec{3} = [0.0, 0.0, 0.0], [unit = "rad/s", description = "Joint rates"]
        tau::Vec{3} = [0.0, 0.0, 0.0], [unit = "N*m", description = "Joint torques into the arm"]
        M::Mat{3,3} = [1.0 0.0 0.0; 0.0 1.0 0.0; 0.0 0.0 1.0], [unit = "kg*m^2", description = "Mass matrix"]
        dTdq::Vec{3} = [0.0, 0.0, 0.0], [unit = "N*m", description = "Velocity-dependent generalised forces dT/dq"]
        dVdq::Vec{3} = [0.0, 0.0, 0.0], [unit = "N*m", description = "Gravity generalised forces dV/dq"]
        re::Real = 0.0, [unit = "m", description = "Elbow radius from the base axis"]
        ze::Real = 0.0, [unit = "m", description = "Elbow height"]
        rt::Real = 0.0, [unit = "m", description = "Tip radius from the base axis"]
        zt::Real = 0.0, [unit = "m", description = "Tip height"]
        dM11dq2::Real = 0.0, [unit = "kg*m^2", description = "dM11/dq2"]
        dM11dq3::Real = 0.0, [unit = "kg*m^2", description = "dM11/dq3"]
        dM22dq3::Real = 0.0, [unit = "kg*m^2", description = "dM22/dq3"]
        dM23dq3::Real = 0.0, [unit = "kg*m^2", description = "dM23/dq3"]
    end
    @equations begin
        re ~ l2 * cos(q[2])
        ze ~ l2 * sin(q[2])
        rt ~ re + l3 * cos(q[2] + q[3])
        zt ~ ze + l3 * sin(q[2] + q[3])
        M[1, 1] ~ Jb + m2 * re^2 + m3 * rt^2
        M[1, 2] ~ 0.0
        M[1, 3] ~ 0.0
        M[2, 1] ~ 0.0
        M[2, 2] ~ m2 * l2^2 + m3 * (l2^2 + l3^2 + 2.0 * l2 * l3 * cos(q[3]))
        M[2, 3] ~ m3 * (l3^2 + l2 * l3 * cos(q[3]))
        M[3, 1] ~ 0.0
        M[3, 2] ~ m3 * (l3^2 + l2 * l3 * cos(q[3]))
        M[3, 3] ~ m3 * l3^2
        dM11dq2 ~ -2.0 * (m2 * re * ze + m3 * rt * zt)
        dM11dq3 ~ -2.0 * m3 * rt * l3 * sin(q[2] + q[3])
        dM22dq3 ~ -2.0 * m3 * l2 * l3 * sin(q[3])
        dM23dq3 ~ -m3 * l2 * l3 * sin(q[3])
        dVdq[1] ~ 0.0
        dVdq[2] ~ g * (m2 * re + m3 * rt)
        dVdq[3] ~ g * m3 * l3 * cos(q[2] + q[3])
        dTdq[1] ~ 0.0
        dTdq[2] ~ 0.5 * dM11dq2 * qd[1]^2
        dTdq[3] ~ 0.5 * dM11dq3 * qd[1]^2 + 0.5 * dM22dq3 * qd[2]^2 + dM23dq3 * qd[2] * qd[3]
        ddt(q) ~ qd
        p ~ M * qd
        ddt(p) ~ tau + dTdq - dVdq
        tau ~ [j1.e, j2.e, j3.e]
        j1.f ~ qd[1]
        j2.f ~ qd[2]
        j3.f ~ qd[3]
        q1 ~ q[1]
        q2 ~ q[2]
        q3 ~ q[3]
        qd1 ~ qd[1]
        qd2 ~ qd[2]
        qd3 ~ qd[3]
        E ~ 0.5 * dot(qd, p) + g * (m2 * ze + m3 * zt)
    end
end
