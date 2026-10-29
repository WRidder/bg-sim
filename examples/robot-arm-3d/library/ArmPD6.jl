@block ArmPD6 begin
    # 1 ms PD + gravity feedforward for the six-axis arm (X-MB3), sampled firmware (D28).
    #
    # Reference: a quintic smoothstep from the home angles `qh_i` to the target angles `qt_i`
    # that starts at `t0` and lasts `Tm` (the firmware reads the clock input `tm`):
    #
    #   tau  = clamp((tm - t0) / Tm, 0, 1),   s = tau^3 (10 - 15 tau + 6 tau^2)
    #   qr_i = qh_i + (qt_i - qh_i) s,        qdr_i = (qt_i - qh_i) 30 tau^2 (1 - tau)^2 / Tm
    #
    # Control law per joint (the reference rate is fed forward, so the settled error is zero
    # and there is no PD droop):
    #
    #   u_i = clamp(Kp_i (qr_i - q_i) + Kd_i (qdr_i - qd_i) + G_i(q), -umax_i, umax_i)
    #
    # `G_i(q)` is the gravity torque about joint i (the torque that holds the arm static),
    # computed here from the same geometry as the plant: the forward kinematics of the
    # standard-DH chain is unrolled below (`R<i>_<ab>` world rotation of link i, `o<i>_<a>` the
    # origin of its joint frame, `w<i>_<a>` its centre of mass) and
    # `G_i = g0 sum_{j>=i} m_j z_i . ((w_j - o_i) x e_z)`.
    # `clamp` inside `@discrete` is generated code, not a symbolic `ifelse`, so the torque limit
    # creates no event callback.
    @parameters begin
        Kp1::Real = 274.0, [unit = "N*m/rad", min = 0, description = "Joint 1 proportional gain"]
        Kd1::Real = 54.9, [unit = "N*m*s/rad", min = 0, description = "Joint 1 rate gain"]
        u1max::Real = 150.0, [unit = "N*m", min = 0, description = "Joint 1 torque limit"]
        qh1::Real = 0.0, [unit = "rad", description = "Joint 1 home angle"]
        qt1::Real = 0.8, [unit = "rad", description = "Joint 1 target angle"]
        Kp2::Real = 331.0, [unit = "N*m/rad", min = 0, description = "Joint 2 proportional gain"]
        Kd2::Real = 66.2, [unit = "N*m*s/rad", min = 0, description = "Joint 2 rate gain"]
        u2max::Real = 150.0, [unit = "N*m", min = 0, description = "Joint 2 torque limit"]
        qh2::Real = -1.2, [unit = "rad", description = "Joint 2 home angle"]
        qt2::Real = -0.8, [unit = "rad", description = "Joint 2 target angle"]
        Kp3::Real = 107.0, [unit = "N*m/rad", min = 0, description = "Joint 3 proportional gain"]
        Kd3::Real = 17.9, [unit = "N*m*s/rad", min = 0, description = "Joint 3 rate gain"]
        u3max::Real = 150.0, [unit = "N*m", min = 0, description = "Joint 3 torque limit"]
        qh3::Real = 1.2, [unit = "rad", description = "Joint 3 home angle"]
        qt3::Real = 0.9, [unit = "rad", description = "Joint 3 target angle"]
        Kp4::Real = 6.23, [unit = "N*m/rad", min = 0, description = "Joint 4 proportional gain"]
        Kd4::Real = 0.623, [unit = "N*m*s/rad", min = 0, description = "Joint 4 rate gain"]
        u4max::Real = 28.0, [unit = "N*m", min = 0, description = "Joint 4 torque limit"]
        qh4::Real = -1.5, [unit = "rad", description = "Joint 4 home angle"]
        qt4::Real = -1.9, [unit = "rad", description = "Joint 4 target angle"]
        Kp5::Real = 1.5, [unit = "N*m/rad", min = 0, description = "Joint 5 proportional gain"]
        Kd5::Real = 0.15, [unit = "N*m*s/rad", min = 0, description = "Joint 5 rate gain"]
        u5max::Real = 28.0, [unit = "N*m", min = 0, description = "Joint 5 torque limit"]
        qh5::Real = -1.5, [unit = "rad", description = "Joint 5 home angle"]
        qt5::Real = -1.2, [unit = "rad", description = "Joint 5 target angle"]
        Kp6::Real = 0.2, [unit = "N*m/rad", min = 0, description = "Joint 6 proportional gain"]
        Kd6::Real = 0.02, [unit = "N*m*s/rad", min = 0, description = "Joint 6 rate gain"]
        u6max::Real = 28.0, [unit = "N*m", min = 0, description = "Joint 6 torque limit"]
        qh6::Real = 0.0, [unit = "rad", description = "Joint 6 home angle"]
        qt6::Real = 0.6, [unit = "rad", description = "Joint 6 target angle"]
        g0::Real = 9.81, [unit = "m/s^2", min = 0, description = "Gravitational acceleration"]
        t0::Real = 0.1, [unit = "s", min = 0, description = "Start of the reference move"]
        Tm::Real = 0.8, [unit = "s", min = 1.0e-3, description = "Duration of the reference move"]
    end
    @inputs begin
        tm::Real
        q1::Real
        q2::Real
        q3::Real
        q4::Real
        q5::Real
        q6::Real
        qd1::Real
        qd2::Real
        qd3::Real
        qd4::Real
        qd5::Real
        qd6::Real
    end
    @outputs begin
        u1::Real = 6.790104400705741e-16
        u2::Real = -32.42608106128561
        u3::Real = -17.848001786548974
        u4::Real = -1.2448661815489752
        u5::Real = 0.022622410965966632
        u6::Real = 0.0
        e1::Real = 0.0
        e2::Real = 0.0
        e3::Real = 0.0
        e4::Real = 0.0
        e5::Real = 0.0
        e6::Real = 0.0
        qr1::Real = 0.0
        qr2::Real = -1.2
        qr3::Real = 1.2
        qr4::Real = -1.5
        qr5::Real = -1.5
        qr6::Real = 0.0
    end
    @discrete Ts = 1e-3 begin
        tau = clamp((tm - t0) / Tm, 0.0, 1.0)
        s = tau^3 * (10.0 - 15.0 * tau + 6.0 * tau^2)
        sd = 30.0 * tau^2 * (1.0 - tau)^2 / Tm
        c1 = cos(q1)
        s1 = sin(q1)
        c2 = cos(q2)
        s2 = sin(q2)
        c3 = cos(q3)
        s3 = sin(q3)
        c4 = cos(q4)
        s4 = sin(q4)
        c5 = cos(q5)
        s5 = sin(q5)
        c6 = cos(q6)
        s6 = sin(q6)
        A1_11 = 1.0*1.0
        A1_12 = 0.0
        A1_13 = 0.0
        A1_21 = 0.0
        A1_22 = 1.0*1.0
        A1_23 = 0.0
        A1_31 = 0.0
        A1_32 = 0.0
        A1_33 = 1.0*1.0
        R1_11 = A1_11*c1 + A1_12*s1
        R1_12 = -A1_11*s1 + A1_12*c1
        R1_13 = A1_13
        R1_21 = A1_21*c1 + A1_22*s1
        R1_22 = -A1_21*s1 + A1_22*c1
        R1_23 = A1_23
        R1_31 = A1_31*c1 + A1_32*s1
        R1_32 = -A1_31*s1 + A1_32*c1
        R1_33 = A1_33
        o1_1 = 0.0
        o1_2 = 0.0
        o1_3 = 0.0
        w1_1 = o1_1 + R1_12*-0.026 + R1_13*0.045
        w1_2 = o1_2 + R1_22*-0.026 + R1_23*0.045
        w1_3 = o1_3 + R1_32*-0.026 + R1_33*0.045
        A2_11 = R1_11*1.0
        A2_12 = R1_13*1.0
        A2_13 = R1_12*-1.0
        A2_21 = R1_21*1.0
        A2_22 = R1_23*1.0
        A2_23 = R1_22*-1.0
        A2_31 = R1_31*1.0
        A2_32 = R1_33*1.0
        A2_33 = R1_32*-1.0
        R2_11 = A2_11*c2 + A2_12*s2
        R2_12 = -A2_11*s2 + A2_12*c2
        R2_13 = A2_13
        R2_21 = A2_21*c2 + A2_22*s2
        R2_22 = -A2_21*s2 + A2_22*c2
        R2_23 = A2_23
        R2_31 = A2_31*c2 + A2_32*s2
        R2_32 = -A2_31*s2 + A2_32*c2
        R2_33 = A2_33
        o2_1 = o1_1 + R1_13*0.089159
        o2_2 = o1_2 + R1_23*0.089159
        o2_3 = o1_3 + R1_33*0.089159
        w2_1 = o2_1 + R2_11*-0.2125 + R2_13*0.1134
        w2_2 = o2_2 + R2_21*-0.2125 + R2_23*0.1134
        w2_3 = o2_3 + R2_31*-0.2125 + R2_33*0.1134
        A3_11 = R2_11*1.0
        A3_12 = R2_12*1.0
        A3_13 = R2_13*1.0
        A3_21 = R2_21*1.0
        A3_22 = R2_22*1.0
        A3_23 = R2_23*1.0
        A3_31 = R2_31*1.0
        A3_32 = R2_32*1.0
        A3_33 = R2_33*1.0
        R3_11 = A3_11*c3 + A3_12*s3
        R3_12 = -A3_11*s3 + A3_12*c3
        R3_13 = A3_13
        R3_21 = A3_21*c3 + A3_22*s3
        R3_22 = -A3_21*s3 + A3_22*c3
        R3_23 = A3_23
        R3_31 = A3_31*c3 + A3_32*s3
        R3_32 = -A3_31*s3 + A3_32*c3
        R3_33 = A3_33
        o3_1 = o2_1 + R2_11*-0.425
        o3_2 = o2_2 + R2_21*-0.425
        o3_3 = o2_3 + R2_31*-0.425
        w3_1 = o3_1 + R3_11*-0.196 + R3_13*0.0265
        w3_2 = o3_2 + R3_21*-0.196 + R3_23*0.0265
        w3_3 = o3_3 + R3_31*-0.196 + R3_33*0.0265
        A4_11 = R3_11*1.0
        A4_12 = R3_12*1.0
        A4_13 = R3_13*1.0
        A4_21 = R3_21*1.0
        A4_22 = R3_22*1.0
        A4_23 = R3_23*1.0
        A4_31 = R3_31*1.0
        A4_32 = R3_32*1.0
        A4_33 = R3_33*1.0
        R4_11 = A4_11*c4 + A4_12*s4
        R4_12 = -A4_11*s4 + A4_12*c4
        R4_13 = A4_13
        R4_21 = A4_21*c4 + A4_22*s4
        R4_22 = -A4_21*s4 + A4_22*c4
        R4_23 = A4_23
        R4_31 = A4_31*c4 + A4_32*s4
        R4_32 = -A4_31*s4 + A4_32*c4
        R4_33 = A4_33
        o4_1 = o3_1 + R3_11*-0.39225
        o4_2 = o3_2 + R3_21*-0.39225
        o4_3 = o3_3 + R3_31*-0.39225
        w4_1 = o4_1 + R4_12*-0.0018 + R4_13*0.055
        w4_2 = o4_2 + R4_22*-0.0018 + R4_23*0.055
        w4_3 = o4_3 + R4_32*-0.0018 + R4_33*0.055
        A5_11 = R4_11*1.0
        A5_12 = R4_13*1.0
        A5_13 = R4_12*-1.0
        A5_21 = R4_21*1.0
        A5_22 = R4_23*1.0
        A5_23 = R4_22*-1.0
        A5_31 = R4_31*1.0
        A5_32 = R4_33*1.0
        A5_33 = R4_32*-1.0
        R5_11 = A5_11*c5 + A5_12*s5
        R5_12 = -A5_11*s5 + A5_12*c5
        R5_13 = A5_13
        R5_21 = A5_21*c5 + A5_22*s5
        R5_22 = -A5_21*s5 + A5_22*c5
        R5_23 = A5_23
        R5_31 = A5_31*c5 + A5_32*s5
        R5_32 = -A5_31*s5 + A5_32*c5
        R5_33 = A5_33
        o5_1 = o4_1 + R4_13*0.10915
        o5_2 = o4_2 + R4_23*0.10915
        o5_3 = o4_3 + R4_33*0.10915
        w5_1 = o5_1 + R5_12*0.0018 + R5_13*0.047
        w5_2 = o5_2 + R5_22*0.0018 + R5_23*0.047
        w5_3 = o5_3 + R5_32*0.0018 + R5_33*0.047
        A6_11 = R5_11*1.0
        A6_12 = R5_13*-1.0
        A6_13 = R5_12*1.0
        A6_21 = R5_21*1.0
        A6_22 = R5_23*-1.0
        A6_23 = R5_22*1.0
        A6_31 = R5_31*1.0
        A6_32 = R5_33*-1.0
        A6_33 = R5_32*1.0
        R6_11 = A6_11*c6 + A6_12*s6
        R6_12 = -A6_11*s6 + A6_12*c6
        R6_13 = A6_13
        R6_21 = A6_21*c6 + A6_22*s6
        R6_22 = -A6_21*s6 + A6_22*c6
        R6_23 = A6_23
        R6_31 = A6_31*c6 + A6_32*s6
        R6_32 = -A6_31*s6 + A6_32*c6
        R6_33 = A6_33
        o6_1 = o5_1 + R5_13*0.09465
        o6_2 = o5_2 + R5_23*0.09465
        o6_3 = o5_3 + R5_33*0.09465
        w6_1 = o6_1 + R6_13*0.0412
        w6_2 = o6_2 + R6_23*0.0412
        w6_3 = o6_3 + R6_33*0.0412
        G1 = g0*(3.7*(R1_13*(w1_2 - o1_2) - R1_23*(w1_1 - o1_1)) + 8.393*(R1_13*(w2_2 - o1_2) - R1_23*(w2_1 - o1_1)) + 2.275*(R1_13*(w3_2 - o1_2) - R1_23*(w3_1 - o1_1)) + 1.219*(R1_13*(w4_2 - o1_2) - R1_23*(w4_1 - o1_1)) + 1.219*(R1_13*(w5_2 - o1_2) - R1_23*(w5_1 - o1_1)) + 0.74*(R1_13*(w6_2 - o1_2) - R1_23*(w6_1 - o1_1)))
        G2 = g0*(8.393*(R2_13*(w2_2 - o2_2) - R2_23*(w2_1 - o2_1)) + 2.275*(R2_13*(w3_2 - o2_2) - R2_23*(w3_1 - o2_1)) + 1.219*(R2_13*(w4_2 - o2_2) - R2_23*(w4_1 - o2_1)) + 1.219*(R2_13*(w5_2 - o2_2) - R2_23*(w5_1 - o2_1)) + 0.74*(R2_13*(w6_2 - o2_2) - R2_23*(w6_1 - o2_1)))
        G3 = g0*(2.275*(R3_13*(w3_2 - o3_2) - R3_23*(w3_1 - o3_1)) + 1.219*(R3_13*(w4_2 - o3_2) - R3_23*(w4_1 - o3_1)) + 1.219*(R3_13*(w5_2 - o3_2) - R3_23*(w5_1 - o3_1)) + 0.74*(R3_13*(w6_2 - o3_2) - R3_23*(w6_1 - o3_1)))
        G4 = g0*(1.219*(R4_13*(w4_2 - o4_2) - R4_23*(w4_1 - o4_1)) + 1.219*(R4_13*(w5_2 - o4_2) - R4_23*(w5_1 - o4_1)) + 0.74*(R4_13*(w6_2 - o4_2) - R4_23*(w6_1 - o4_1)))
        G5 = g0*(1.219*(R5_13*(w5_2 - o5_2) - R5_23*(w5_1 - o5_1)) + 0.74*(R5_13*(w6_2 - o5_2) - R5_23*(w6_1 - o5_1)))
        G6 = g0*(0.74*(R6_13*(w6_2 - o6_2) - R6_23*(w6_1 - o6_1)))
        qr1 = qh1 + (qt1 - qh1) * s
        e1 = qr1 - q1
        u1 = clamp(Kp1 * e1 + Kd1 * ((qt1 - qh1) * sd - qd1) + G1, -u1max, u1max)
        qr2 = qh2 + (qt2 - qh2) * s
        e2 = qr2 - q2
        u2 = clamp(Kp2 * e2 + Kd2 * ((qt2 - qh2) * sd - qd2) + G2, -u2max, u2max)
        qr3 = qh3 + (qt3 - qh3) * s
        e3 = qr3 - q3
        u3 = clamp(Kp3 * e3 + Kd3 * ((qt3 - qh3) * sd - qd3) + G3, -u3max, u3max)
        qr4 = qh4 + (qt4 - qh4) * s
        e4 = qr4 - q4
        u4 = clamp(Kp4 * e4 + Kd4 * ((qt4 - qh4) * sd - qd4) + G4, -u4max, u4max)
        qr5 = qh5 + (qt5 - qh5) * s
        e5 = qr5 - q5
        u5 = clamp(Kp5 * e5 + Kd5 * ((qt5 - qh5) * sd - qd5) + G5, -u5max, u5max)
        qr6 = qh6 + (qt6 - qh6) * s
        e6 = qr6 - q6
        u6 = clamp(Kp6 * e6 + Kd6 * ((qt6 - qh6) * sd - qd6) + G6, -u6max, u6max)
    end
end
