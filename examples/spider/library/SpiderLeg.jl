@block SpiderLeg begin
    # One reduced T8X leg: the three joint angles and rates are states, each joint carries
    # its servo torque, the gravity of the three links and the foot contact force through the
    # leg Jacobian, and the foot contact is the law of the stdlib `ContactPoint` (smooth
    # Hunt-Crossley normal force gated by d x/d penetration, regularised Coulomb friction).
    # The block returns the wrench on the body about the body origin, in the body frame, for
    # an `ExternalWrenchSpatial`.
    #
    # Reduction (quasi-static, signal-coupled leg):
    # * the body block carries the mass and inertia of the whole robot with the legs locked in
    #   the nominal stance (`design.py`, `composite_body`), and its weight at the body origin;
    # * the leg adds to the body the contact force at the true foot point and the moment of its
    #   own link weights about the body origin (the links at their current centres), so the
    #   weight acts where the links are, as in the joint equations;
    # * the joint equations use the diagonal of the leg mass matrix at the nominal pose (`I`)
    #   and the link-centre gravity Jacobian; they leave out the body acceleration and the
    #   coupling terms of the mass matrix;
    # * the servo torques and the inertial forces of a swinging leg are not applied to the
    #   body: the body feels the leg only through the foot contact and the link weights.
    # The README states what that neglects and how large it is.
    #
    # Servo: an analog P loop on a DC motor. The command passes a first-order filter `tau_s`;
    # the motor torque is `clamp(kp e - kd qd, -tau_max, tau_max) - tau_max qd / w_nl`: full
    # duty beyond a small error, and the back-EMF line from stall (`tau_max`) at rest to zero
    # at the no-load speed `w_nl`.
    @inputs begin
        g::Vec{7}, [description = "Body pose (qw qx qy qz x y z)"]
        V::Vec{6}, [description = "Body twist [w; v] in the body frame"]
        qcmd::Vec{3}, [unit = "rad", description = "Joint commands from the leg IK"]
    end
    @parameters begin
        hx::Real = 0.0, [unit = "m", description = "Hip x in the body frame"]
        hy::Real = 0.0, [unit = "m", description = "Hip y in the body frame"]
        hz::Real = 0.0, [unit = "m", description = "Hip z in the body frame"]
        yaw::Real = 0.0, [unit = "rad", description = "Hip x axis direction in the body frame"]
        a::Real = 0.045, [unit = "m", min = 1.0e-6, description = "Coxa length"]
        b::Real = 0.110, [unit = "m", min = 1.0e-6, description = "Femur length"]
        c::Real = 0.140, [unit = "m", min = 1.0e-6, description = "Tibia length"]
        m_c::Real = 0.015, [unit = "kg", min = 0, description = "Coxa mass (centre at a/2)"]
        m_f::Real = 0.030, [unit = "kg", min = 0, description = "Femur mass (centre at b/2)"]
        m_t::Real = 0.025, [unit = "kg", min = 0, description = "Tibia mass (centre at c/2)"]
        I::Vec{3} = [9.72e-4, 5.16e-4, 1.725e-4], [unit = "kg*m^2", min = 1.0e-9, description = "Joint inertias: diagonal of the leg mass matrix at the nominal pose"]
        b_joint::Vec{3} = [0.005, 0.005, 0.005], [unit = "N*m*s/rad", min = 0, description = "Gear-train viscous friction"]
        g0::Real = 9.80665, [unit = "m/s^2", min = 0, description = "Gravity"]
        kp::Vec{3} = [19.1, 19.1, 19.1], [unit = "N*m/rad", min = 0, description = "Servo position gain (full duty at tau_max/kp)"]
        kd::Vec{3} = [0.0, 0.0, 0.0], [unit = "N*m*s/rad", min = 0, description = "Servo derivative gain (0 for an analog servo)"]
        tau_max::Vec{3} = [0.333, 0.333, 0.333], [unit = "N*m", min = 0, description = "Servo stall torque"]
        w_nl::Vec{3} = [10.47, 10.47, 10.47], [unit = "rad/s", min = 1.0e-6, description = "Servo no-load speed"]
        tau_s::Real = 0.012, [unit = "s", min = 1.0e-6, description = "Servo command filter"]
        kc::Real = 1500.0, [unit = "N/m", min = 0, description = "Contact stiffness"]
        xref::Real = 1.0e-3, [unit = "m", min = 1.0e-9, description = "Contact reference penetration"]
        cc::Real = 3.0, [unit = "s/m", min = 0, description = "Hunt-Crossley damping"]
        mu::Real = 0.8, [unit = "1", min = 0, description = "Foot friction coefficient"]
        vs::Real = 0.01, [unit = "m/s", min = 1.0e-6, description = "Friction regularisation"]
        bt::Real = 0.0, [unit = "N*s/m", min = 0, description = "Viscous foot damping"]
        eps::Real = 1.0e-5, [unit = "m", min = 1.0e-9, description = "Contact smoothing"]
        feps::Real = 1.0e-6, [unit = "N", min = 1.0e-12, description = "No-pull smoothing"]
        gz::Real = 0.0, [unit = "m", description = "Ground height"]
    end
    @outputs begin
        q1::Real, [unit = "rad"]
        q2::Real, [unit = "rad"]
        q3::Real, [unit = "rad"]
        qd1::Real, [unit = "rad/s"]
        qd2::Real, [unit = "rad/s"]
        qd3::Real, [unit = "rad/s"]
        qf1::Real, [unit = "rad"]
        qf2::Real, [unit = "rad"]
        qf3::Real, [unit = "rad"]
        f_n::Real, [unit = "N", description = "Foot normal force"]
        pfoot::Vec{3}, [unit = "m", description = "Foot point in the world"]
        tau1::Real, [unit = "N*m", description = "Coxa servo torque"]
        tau2::Real, [unit = "N*m", description = "Femur servo torque"]
        tau3::Real, [unit = "N*m", description = "Tibia servo torque"]
        tx::Real, [unit = "N*m", description = "Body-frame torque about x"]
        ty::Real, [unit = "N*m", description = "Body-frame torque about y"]
        tz::Real, [unit = "N*m", description = "Body-frame torque about z"]
        fx::Real, [unit = "N", description = "Body-frame force x"]
        fy::Real, [unit = "N", description = "Body-frame force y"]
        fz::Real, [unit = "N", description = "Body-frame force z"]
    end
    @variables begin
        sb::Real = 1.0, [unit = "1"]
        R::Mat{3,3} = [1.0 0.0 0.0; 0.0 1.0 0.0; 0.0 0.0 1.0], [unit = "1"]
        ch::Real = 1.0, [unit = "1"]
        sh::Real = 0.0, [unit = "1"]
        rl::Real = 0.0, [unit = "m"]
        pfr::Vec{3} = [0.0, 0.0, 0.0], [unit = "m"]
        pfw::Vec{3} = [0.0, 0.0, 0.0], [unit = "m"]
        vb::Vec{3} = [0.0, 0.0, 0.0], [unit = "m/s"]
        vrel::Vec{3} = [0.0, 0.0, 0.0], [unit = "m/s"]
        vfw::Vec{3} = [0.0, 0.0, 0.0], [unit = "m/s"]
        rr::Real = 1.0e-5, [unit = "m"]
        x::Real = 1.0e-5, [unit = "m"]
        sig::Real = 0.5, [unit = "1"]
        xd::Real = 0.0, [unit = "m/s"]
        fk::Real = 0.0, [unit = "N"]
        fraw::Real = 0.0, [unit = "N"]
        fc::Real = 0.0, [unit = "N"]
        fn::Real = 0.0, [unit = "N"]
        ft1::Real = 0.0, [unit = "N"]
        ft2::Real = 0.0, [unit = "N"]
        fwx::Real = 0.0, [unit = "N"]
        fwy::Real = 0.0, [unit = "N"]
        fwz::Real = 0.0, [unit = "N"]
        fbx::Real = 0.0, [unit = "N"]
        fby::Real = 0.0, [unit = "N"]
        fbz::Real = 0.0, [unit = "N"]
        mwx::Real = 0.0, [unit = "N*m"]
        mwy::Real = 0.0, [unit = "N*m"]
        mwz::Real = 0.0, [unit = "N*m"]
        gb::Vec{3} = [0.0, 0.0, 0.0], [unit = "m/s^2"]
        sr::Real = 0.0, [unit = "kg*m"]
        sz::Real = 0.0, [unit = "kg*m"]
        pm::Vec{3} = [0.0, 0.0, 0.0], [unit = "kg*m"]
        dr2::Real = 0.0, [unit = "kg*m"]
        dz2::Real = 0.0, [unit = "kg*m"]
        dr3::Real = 0.0, [unit = "kg*m"]
        dz3::Real = 0.0, [unit = "kg*m"]
        tau::Vec{3} = [0.0, 0.0, 0.0], [unit = "N*m"]
        taug::Vec{3} = [0.0, 0.0, 0.0], [unit = "N*m"]
        tauc::Vec{3} = [0.0, 0.0, 0.0], [unit = "N*m"]
        J::Mat{3,3} = [0.0 0.0 0.0; 0.0 0.0 0.0; 0.0 0.0 0.0], [unit = "m"]
        q1s::Real = 0.0, [unit = "rad", state = :prefer]
        q2s::Real = 0.0, [unit = "rad", state = :prefer]
        q3s::Real = 0.0, [unit = "rad", state = :prefer]
        qd1s::Real = 0.0, [unit = "rad/s", state = :prefer]
        qd2s::Real = 0.0, [unit = "rad/s", state = :prefer]
        qd3s::Real = 0.0, [unit = "rad/s", state = :prefer]
        qf1s::Real = 0.0, [unit = "rad", state = :prefer]
        qf2s::Real = 0.0, [unit = "rad", state = :prefer]
        qf3s::Real = 0.0, [unit = "rad", state = :prefer]
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
        q1 ~ q1s
        q2 ~ q2s
        q3 ~ q3s
        qd1 ~ qd1s
        qd2 ~ qd2s
        qd3 ~ qd3s
        qf1 ~ qf1s
        qf2 ~ qf2s
        qf3 ~ qf3s
        ddt(q1s) ~ qd1s
        ddt(q2s) ~ qd2s
        ddt(q3s) ~ qd3s
        ddt(qf1s) ~ (qcmd[1] - qf1s) / tau_s
        ddt(qf2s) ~ (qcmd[2] - qf2s) / tau_s
        ddt(qf3s) ~ (qcmd[3] - qf3s) / tau_s
        # foot point in the body frame (coxa yaw, then the femur/tibia pair in the leg plane)
        ch ~ cos(yaw + q1s)
        sh ~ sin(yaw + q1s)
        rl ~ a + b * cos(q2s) + c * cos(q2s + q3s)
        pfr[1] ~ hx + rl * ch
        pfr[2] ~ hy + rl * sh
        pfr[3] ~ hz + b * sin(q2s) + c * sin(q2s + q3s)
        pfw[1] ~ g[5] + R[1, 1] * pfr[1] + R[1, 2] * pfr[2] + R[1, 3] * pfr[3]
        pfw[2] ~ g[6] + R[2, 1] * pfr[1] + R[2, 2] * pfr[2] + R[2, 3] * pfr[3]
        pfw[3] ~ g[7] + R[3, 1] * pfr[1] + R[3, 2] * pfr[2] + R[3, 3] * pfr[3]
        # leg Jacobian (columns: d p_foot / d q1, q2, q3, body frame)
        J[1, 1] ~ -rl * sh
        J[2, 1] ~ rl * ch
        J[3, 1] ~ 0.0
        J[1, 2] ~ (-b * sin(q2s) - c * sin(q2s + q3s)) * ch
        J[2, 2] ~ (-b * sin(q2s) - c * sin(q2s + q3s)) * sh
        J[3, 2] ~ b * cos(q2s) + c * cos(q2s + q3s)
        J[1, 3] ~ -c * sin(q2s + q3s) * ch
        J[2, 3] ~ -c * sin(q2s + q3s) * sh
        J[3, 3] ~ c * cos(q2s + q3s)
        # body point velocity and foot relative velocity (body frame)
        vb[1] ~ V[4] + (V[2] * pfr[3] - V[3] * pfr[2])
        vb[2] ~ V[5] + (V[3] * pfr[1] - V[1] * pfr[3])
        vb[3] ~ V[6] + (V[1] * pfr[2] - V[2] * pfr[1])
        vrel[1] ~ J[1, 1] * qd1s + J[1, 2] * qd2s + J[1, 3] * qd3s
        vrel[2] ~ J[2, 1] * qd1s + J[2, 2] * qd2s + J[2, 3] * qd3s
        vrel[3] ~ J[3, 1] * qd1s + J[3, 2] * qd2s + J[3, 3] * qd3s
        vfw[1] ~ R[1, 1] * (vb[1] + vrel[1]) + R[1, 2] * (vb[2] + vrel[2]) + R[1, 3] * (vb[3] + vrel[3])
        vfw[2] ~ R[2, 1] * (vb[1] + vrel[1]) + R[2, 2] * (vb[2] + vrel[2]) + R[2, 3] * (vb[3] + vrel[3])
        vfw[3] ~ R[3, 1] * (vb[1] + vrel[1]) + R[3, 2] * (vb[2] + vrel[2]) + R[3, 3] * (vb[3] + vrel[3])
        # contact: the ContactPoint law on the plane z = gz (normal +z, tangents x and y)
        rr ~ sqrt((pfw[3] - gz) * (pfw[3] - gz) + eps * eps)
        x ~ 0.5 * eps * eps / (rr - (gz - pfw[3]))
        sig ~ x / rr
        xd ~ -sig * vfw[3]
        fk ~ kc * x * sqrt(x / xref)
        fraw ~ fk * (1.0 + cc * xd)
        fc ~ 0.5 * (fraw + sqrt(fraw * fraw + feps * feps))
        fn ~ sig * fc
        ft1 ~ mu * fn * tanh(vfw[1] / vs) + bt * vfw[1]
        ft2 ~ mu * fn * tanh(vfw[2] / vs) + bt * vfw[2]
        fwx ~ -ft1
        fwy ~ -ft2
        fwz ~ fn
        # contact force in the body frame
        fbx ~ R[1, 1] * fwx + R[2, 1] * fwy + R[3, 1] * fwz
        fby ~ R[1, 2] * fwx + R[2, 2] * fwy + R[3, 2] * fwz
        fbz ~ R[1, 3] * fwx + R[2, 3] * fwy + R[3, 3] * fwz
        # gravity per unit mass in the body frame
        gb[1] ~ -g0 * R[3, 1]
        gb[2] ~ -g0 * R[3, 2]
        gb[3] ~ -g0 * R[3, 3]
        # first moments of the three link masses about the hip, radial and vertical
        sr ~ m_c * 0.5 * a + m_f * (a + 0.5 * b * cos(q2s)) +
             m_t * (a + b * cos(q2s) + 0.5 * c * cos(q2s + q3s))
        sz ~ m_f * 0.5 * b * sin(q2s) + m_t * (b * sin(q2s) + 0.5 * c * sin(q2s + q3s))
        # first moment of the leg about the body origin (body frame)
        pm[1] ~ (m_c + m_f + m_t) * hx + sr * ch
        pm[2] ~ (m_c + m_f + m_t) * hy + sr * sh
        pm[3] ~ (m_c + m_f + m_t) * hz + sz
        # wrench on the body about its origin, body frame: the contact force at the foot and
        # the moment of the link weights (the body block carries the weight force itself)
        mwx ~ (pfw[2] - g[6]) * fwz - (pfw[3] - g[7]) * fwy
        mwy ~ (pfw[3] - g[7]) * fwx - (pfw[1] - g[5]) * fwz
        mwz ~ (pfw[1] - g[5]) * fwy - (pfw[2] - g[6]) * fwx
        tx ~ R[1, 1] * mwx + R[2, 1] * mwy + R[3, 1] * mwz + (pm[2] * gb[3] - pm[3] * gb[2])
        ty ~ R[1, 2] * mwx + R[2, 2] * mwy + R[3, 2] * mwz + (pm[3] * gb[1] - pm[1] * gb[3])
        tz ~ R[1, 3] * mwx + R[2, 3] * mwy + R[3, 3] * mwz + (pm[1] * gb[2] - pm[2] * gb[1])
        fx ~ fbx
        fy ~ fby
        fz ~ fbz
        # gravity Jacobian of the link centres: d(first moment)/dq_j projected on gb
        dr2 ~ -(m_f * 0.5 * b + m_t * b) * sin(q2s) - m_t * 0.5 * c * sin(q2s + q3s)
        dz2 ~ (m_f * 0.5 * b + m_t * b) * cos(q2s) + m_t * 0.5 * c * cos(q2s + q3s)
        dr3 ~ -m_t * 0.5 * c * sin(q2s + q3s)
        dz3 ~ m_t * 0.5 * c * cos(q2s + q3s)
        taug[1] ~ sr * (-gb[1] * sh + gb[2] * ch)
        taug[2] ~ dr2 * (gb[1] * ch + gb[2] * sh) + dz2 * gb[3]
        taug[3] ~ dr3 * (gb[1] * ch + gb[2] * sh) + dz3 * gb[3]
        tauc[1] ~ J[1, 1] * fbx + J[2, 1] * fby + J[3, 1] * fbz
        tauc[2] ~ J[1, 2] * fbx + J[2, 2] * fby + J[3, 2] * fbz
        tauc[3] ~ J[1, 3] * fbx + J[2, 3] * fby + J[3, 3] * fbz
        # servo: saturated P(D) duty times stall torque, minus the back-EMF line
        tau[1] ~ clamp(kp[1] * (qf1s - q1s) - kd[1] * qd1s, -tau_max[1], tau_max[1]) - tau_max[1] / w_nl[1] * qd1s
        tau[2] ~ clamp(kp[2] * (qf2s - q2s) - kd[2] * qd2s, -tau_max[2], tau_max[2]) - tau_max[2] / w_nl[2] * qd2s
        tau[3] ~ clamp(kp[3] * (qf3s - q3s) - kd[3] * qd3s, -tau_max[3], tau_max[3]) - tau_max[3] / w_nl[3] * qd3s
        ddt(qd1s) ~ (tau[1] + taug[1] + tauc[1] - b_joint[1] * qd1s) / I[1]
        ddt(qd2s) ~ (tau[2] + taug[2] + tauc[2] - b_joint[2] * qd2s) / I[2]
        ddt(qd3s) ~ (tau[3] + taug[3] + tauc[3] - b_joint[3] * qd3s) / I[3]
        f_n ~ fn
        pfoot[1] ~ pfw[1]
        pfoot[2] ~ pfw[2]
        pfoot[3] ~ pfw[3]
        tau1 ~ tau[1]
        tau2 ~ tau[2]
        tau3 ~ tau[3]
    end
end
