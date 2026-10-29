@block CornerCube begin
    # A cube balanced on one corner (plan 9.9): rigid body on a frictionless ball joint at the
    # world origin, with three reaction wheels on the body axes. Hand-derived rigid-body dynamics
    # in an explicit ODE (no algebraic loop).
    #
    # Body frame: the axes lie along the three cube edges that meet at the pivot, so the cube
    # structure occupies [0, a]^3 with its centre of mass at (a/2)(1, 1, 1). The wheels spin about
    # the body x, y and z axes (wheel `i` axis is e_i). Wheel `i` is mounted on the inside of the
    # face opposite the pivot corner along axis `i` (face x_i = a), centred on the face, its centre
    # `d` inside the face: wheel 1 at (a-d, a/2, a/2), wheel 2 at (a/2, a-d, a/2), wheel 3 at
    # (a/2, a/2, a-d). The arrangement is symmetric under the permutations of the axes, so the
    # total centre of mass stays on the body diagonal (1,1,1) and the equilibrium is "diagonal vertical".
    #
    # Mass model (derived from the parameters, see the equations): total mass mt = ms + 3 mw,
    # centre of mass r = rc (1,1,1) with mt rc = ms a/2 + mw (s + a), s = a - d, and
    #   Thc = Ths I + ms (|c|^2 I - c c') + sum_i [ mw (|p_i|^2 I - p_i p_i') + Thwt (I - e_i e_i') ]
    # (c = (a/2)(1,1,1) the structure CoM, p_i the wheel centres). Thc has the diagonal Td and the
    # off-diagonal To on every axis (Thc = (Td-To) I + To u u'):
    #   Td = Ths + (ms + mw) a^2/2 + 2 mw (s^2 + a^2/4) + 2 Thwt
    #   To = -ms a^2/4 - mw (s a + a^2/4)
    # Each wheel contributes its axial inertia Thw only through Lw (the spin term of the equations).
    #
    # States: the unit quaternion q = (qw, qx, qy, qz) of the body in the world (body to world),
    # the body angular rate `om` (body frame) and the wheel rates `wr` relative to the body.
    #
    #   R(q)  explicit 3x3 entries,  g_b = R' [0, 0, -g]
    #   Thc   as above                                  inertia about the pivot (wheels' spin excluded)
    #   Lw    = Thw (om + wr)                         wheel momenta about their axes
    #   L     = Thc om + Lw                           angular momentum about the pivot (body frame)
    #   om'   = Thc^-1 (-om x L + r x (mt g_b) - T)    T = motor torques on the wheels
    #           Thc = c1 I - c2 u u' with u = (1,1,1), c2 = m a^2/4, c1 = Thcm + 3 c2, so
    #           Thc^-1 = (I + (c2/Thcm) u u') / c1 exactly (the language has no matrix solve)
    #   wr'   = T / Thw - om'
    #   q'    = 1/2 q (x) [0, om]                     = 1/2 Omega(om) q
    #
    # `T` is the torque the motors put on the wheels: each Rotation port `mi` has the wheel rate
    # `mi.f = wr[i]` and carries `mi.e = T[i]` into the block. The reaction `-T` on the cube is
    # already in the om' equation, so a motor whose housing is fixed is the right model, and the
    # motors' mechanical power sum T_i wr_i is exactly what the wheels gain relative to the body.
    # Thw is the full wheel inertia about its axis, rotor included. The motor rotor is therefore
    # ideally 0; the model keeps a tiny J_m = 1e-6 on the ElectricDrive (see the README, the
    # solver needs it) that spins at the relative rate wr and adds 0.5 % to the wheel momentum.
    #
    # Outputs (all derived, none a state of its own except the integrated wheel angles):
    #   pose      the 7-element pose chart (qw, qx, qy, qz, 0, 0, 0): the pivot corner is the world origin
    #   omega     body rates, wheel  wheel rates relative to the body (the controller inputs)
    #   tilt      angle between the body diagonal n0 = (1,1,1)/sqrt 3 and the vertical, atan(|u - (n0.u) n0|, n0.u) with u = (R31,R32,R33)
    #   qerr      |q| - 1, the quaternion norm error
    #   Hz        vertical angular momentum about the pivot, (R L)_z: a vertical force has no torque
    #             about a vertical axis through the pivot, so Hz is conserved by any controller
    #   Hzw       the part of Hz that the wheels carry, (R Lw)_z; it changes while the cube rotates
    #   phi1..3   the wheel angles relative to the body, int(wr_i, 0)
    #
    # The start value is the equilibrium (body diagonal up) tilted by 2 degrees about the world x axis:
    # q_eq rotates (1,1,1)/sqrt 3 onto (0,0,1), axis (1,-1,0)/sqrt 2 and angle acos(1/sqrt 3).
    @ports begin
        m1::Power{Rotation}
        m2::Power{Rotation}
        m3::Power{Rotation}
    end
    @parameters begin
        ms::Real = 0.18, [unit = "kg", min = 0, description = "Cube structure mass (frame, electronics, motors; wheels excluded)"]
        mw::Real = 0.08, [unit = "kg", min = 0, description = "Mass of one wheel"]
        a::Real = 0.15, [unit = "m", min = 0, description = "Cube side"]
        d::Real = 0.01, [unit = "m", min = 0, description = "Wheel centre inset from its face (half the wheel thickness plus the mounting gap)"]
        Ths::Real = 1.125e-3, [unit = "kg*m^2", min = 0, description = "Structure inertia about its centre (thin cubic shell, 5/18 ms a^2)"]
        Thw::Real = 1.9e-4, [unit = "kg*m^2", min = 1.0e-9, description = "Wheel inertia about its axis, rotor included"]
        Thwt::Real = 9.6e-5, [unit = "kg*m^2", min = 0, description = "Wheel inertia about a diameter, Thw/2 + mw h^2/12"]
        g::Real = 9.81, [unit = "m/s^2", min = 0, description = "Gravitational acceleration"]
    end
    @outputs begin
        pose::Vec{7}
        omega::Vec{3}, [unit = "rad/s"]
        wheel::Vec{3}, [unit = "rad/s"]
        tilt::Real, [unit = "rad"]
        qerr::Real
        Hz::Real, [unit = "N*m*s"]
        Hzw::Real, [unit = "N*m*s"]
        phi1::Real, [unit = "rad"]
        phi2::Real, [unit = "rad"]
        phi3::Real, [unit = "rad"]
    end
    @variables begin
        qw::Real = 0.8822655389649556, [state = :prefer, description = "Body orientation quaternion, scalar part"]
        qx::Real = 0.34050710132430834, [state = :prefer, description = "Body orientation quaternion x"]
        qy::Real = -0.3250080758274231, [state = :prefer, description = "Body orientation quaternion y"]
        qz::Real = -0.0056730370657627335, [state = :prefer, description = "Body orientation quaternion z"]
        om::Vec{3} = [0.0, 0.0, 0.0], [unit = "rad/s", state = :prefer, description = "Body angular rate (body frame)"]
        wr::Vec{3} = [0.0, 0.0, 0.0], [unit = "rad/s", state = :prefer, description = "Wheel rates relative to the body"]
        domega::Vec{3} = [0.0, 0.0, 0.0], [unit = "rad/s^2", description = "Body angular acceleration"]
        T::Vec{3} = [0.0, 0.0, 0.0], [unit = "N*m", description = "Motor torques on the wheels"]
        Rm::Mat{3,3} = [1.0 0.0 0.0; 0.0 1.0 0.0; 0.0 0.0 1.0], [description = "Body-to-world rotation"]
        gb::Vec{3} = [0.0, 0.0, 0.0], [unit = "m/s^2", description = "Gravity in the body frame"]
        mt::Real = 0.42, [unit = "kg", description = "Total mass"]
        Td::Real = 1.0, [unit = "kg*m^2", description = "Diagonal of the inertia about the pivot"]
        To::Real = 0.0, [unit = "kg*m^2", description = "Off-diagonal of the inertia about the pivot"]
        rv::Vec{3} = [0.0, 0.0, 0.0], [unit = "m", description = "Centre of mass relative to the pivot"]
        Thc::Mat{3,3} = [1.0 0.0 0.0; 0.0 1.0 0.0; 0.0 0.0 1.0], [unit = "kg*m^2", description = "Cube inertia about the pivot"]
        Lw::Vec{3} = [0.0, 0.0, 0.0], [unit = "N*m*s", description = "Wheel angular momenta"]
        Lm::Vec{3} = [0.0, 0.0, 0.0], [unit = "N*m*s", description = "Angular momentum about the pivot (body frame)"]
        Thi::Mat{3,3} = [1.0 0.0 0.0; 0.0 1.0 0.0; 0.0 0.0 1.0], [unit = "1/(kg*m^2)", description = "Inverse of Thc, closed form (Thc = (Td-To) I + To u u', u = (1,1,1))"]
        bv::Vec{3} = [0.0, 0.0, 0.0], [unit = "N*m", description = "Torque balance on the body, -om x L + r x mt g_b - T"]
    end
    @equations begin
        Rm[1, 1] ~ (qw * qw + qx * qx - qy * qy - qz * qz) / (qw * qw + qx * qx + qy * qy + qz * qz)
        Rm[1, 2] ~ 2 * (qx * qy - qw * qz) / (qw * qw + qx * qx + qy * qy + qz * qz)
        Rm[1, 3] ~ 2 * (qx * qz + qw * qy) / (qw * qw + qx * qx + qy * qy + qz * qz)
        Rm[2, 1] ~ 2 * (qx * qy + qw * qz) / (qw * qw + qx * qx + qy * qy + qz * qz)
        Rm[2, 2] ~ (qw * qw - qx * qx + qy * qy - qz * qz) / (qw * qw + qx * qx + qy * qy + qz * qz)
        Rm[2, 3] ~ 2 * (qy * qz - qw * qx) / (qw * qw + qx * qx + qy * qy + qz * qz)
        Rm[3, 1] ~ 2 * (qx * qz - qw * qy) / (qw * qw + qx * qx + qy * qy + qz * qz)
        Rm[3, 2] ~ 2 * (qy * qz + qw * qx) / (qw * qw + qx * qx + qy * qy + qz * qz)
        Rm[3, 3] ~ (qw * qw - qx * qx - qy * qy + qz * qz) / (qw * qw + qx * qx + qy * qy + qz * qz)
        gb[1] ~ -g * Rm[3, 1]
        gb[2] ~ -g * Rm[3, 2]
        gb[3] ~ -g * Rm[3, 3]
        mt ~ ms + 3 * mw
        Td ~ Ths + (ms + mw) * 0.5 * a * a + 2 * mw * ((a - d) * (a - d) + 0.25 * a * a) + 2 * Thwt
        To ~ -0.25 * ms * a * a - mw * ((a - d) * a + 0.25 * a * a)
        rv[1] ~ (0.5 * ms * a + mw * (2 * a - d)) / mt
        rv[2] ~ (0.5 * ms * a + mw * (2 * a - d)) / mt
        rv[3] ~ (0.5 * ms * a + mw * (2 * a - d)) / mt
        Thc[1, 1] ~ Td
        Thc[2, 2] ~ Td
        Thc[3, 3] ~ Td
        Thc[1, 2] ~ To
        Thc[1, 3] ~ To
        Thc[2, 1] ~ To
        Thc[2, 3] ~ To
        Thc[3, 1] ~ To
        Thc[3, 2] ~ To
        T ~ [m1.e, m2.e, m3.e]
        Lw ~ Thw * (om + wr)
        Lm ~ Thc * om + Lw
        bv[1] ~ -(om[2] * Lm[3] - om[3] * Lm[2]) + mt * (rv[2] * gb[3] - rv[3] * gb[2]) - T[1]
        bv[2] ~ -(om[3] * Lm[1] - om[1] * Lm[3]) + mt * (rv[3] * gb[1] - rv[1] * gb[3]) - T[2]
        bv[3] ~ -(om[1] * Lm[2] - om[2] * Lm[1]) + mt * (rv[1] * gb[2] - rv[2] * gb[1]) - T[3]
        Thi[1, 1] ~ (1.0 - To / (Td + 2 * To)) / (Td - To)
        Thi[2, 2] ~ (1.0 - To / (Td + 2 * To)) / (Td - To)
        Thi[3, 3] ~ (1.0 - To / (Td + 2 * To)) / (Td - To)
        Thi[1, 2] ~ -To / ((Td + 2 * To) * (Td - To))
        Thi[1, 3] ~ -To / ((Td + 2 * To) * (Td - To))
        Thi[2, 1] ~ -To / ((Td + 2 * To) * (Td - To))
        Thi[2, 3] ~ -To / ((Td + 2 * To) * (Td - To))
        Thi[3, 1] ~ -To / ((Td + 2 * To) * (Td - To))
        Thi[3, 2] ~ -To / ((Td + 2 * To) * (Td - To))
        domega ~ Thi * bv
        ddt(om) ~ domega
        ddt(wr) ~ T / Thw - domega
        ddt(qw) ~ -0.5 * (qx * om[1] + qy * om[2] + qz * om[3])
        ddt(qx) ~ 0.5 * (qw * om[1] + qy * om[3] - qz * om[2])
        ddt(qy) ~ 0.5 * (qw * om[2] - qx * om[3] + qz * om[1])
        ddt(qz) ~ 0.5 * (qw * om[3] + qx * om[2] - qy * om[1])
        m1.f ~ wr[1]
        m2.f ~ wr[2]
        m3.f ~ wr[3]
        pose[1] ~ qw
        pose[2] ~ qx
        pose[3] ~ qy
        pose[4] ~ qz
        pose[5] ~ 0.0
        pose[6] ~ 0.0
        pose[7] ~ 0.0
        omega ~ om
        wheel ~ wr
        tilt ~ atan(hypot(0.7071067811865476 * (Rm[3, 1] - Rm[3, 2]), 0.4082482904638631 * (Rm[3, 1] + Rm[3, 2] - 2 * Rm[3, 3])), 0.5773502691896258 * (Rm[3, 1] + Rm[3, 2] + Rm[3, 3]))
        qerr ~ sqrt(qw * qw + qx * qx + qy * qy + qz * qz) - 1.0
        Hz ~ Rm[3, 1] * Lm[1] + Rm[3, 2] * Lm[2] + Rm[3, 3] * Lm[3]
        Hzw ~ Rm[3, 1] * Lw[1] + Rm[3, 2] * Lw[2] + Rm[3, 3] * Lw[3]
        phi1 ~ int(wr[1], 0.0)
        phi2 ~ int(wr[2], 0.0)
        phi3 ~ int(wr[3], 0.0)
    end
end
