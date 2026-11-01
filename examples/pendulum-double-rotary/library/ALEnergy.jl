@block ALEnergy begin
    # Energy bookkeeping of the ACTILINK rig (for plots and the invariant check):
    #
    #   E_mech  = sum_k (V_k . P_k / 2 + m_k g0 z_k)     the three rigid bodies (twist . momentum,
    #                                                    COM height z = g[7] of the composed pose)
    #   E_drive = J_m wm^2/2 + L_eq ie^2/2 + E_gear      rotor, winding, gear spring
    #   W_in    = int u_q ie dt                          electrical energy from the inverter
    #   W_loss  = int (R_eq ie^2 + sum of the friction and damping powers) dt
    #   H       = E_mech + E_drive + W_loss - W_in       constant (the stiff joint compliances of
    #                                                    Revolute3D store and dissipate a tiny rest)
    @inputs begin
        V1::Vec{6}
        P1::Vec{6}
        V2::Vec{6}
        P2::Vec{6}
        V3::Vec{6}
        P3::Vec{6}
        g1::Vec{7}, [description = "COM pose of the arm (qw qx qy qz x y z)"]
        g2::Vec{7}, [description = "COM pose of link 1"]
        g3::Vec{7}, [description = "COM pose of link 2"]
        wm::Real, [unit = "rad/s", description = "Motor shaft speed"]
        ie::Real, [unit = "A", description = "Winding flow"]
        uq::Real, [unit = "V", description = "Winding voltage"]
        E_gear::Real, [unit = "J"]
        P_fin::Real, [unit = "W", description = "Motor-side friction power"]
        P_fout::Real, [unit = "W", description = "Output-bearing friction power"]
        P_gear::Real, [unit = "W", description = "Gear contact damping power"]
        P_j1::Real, [unit = "W", description = "Joint 1 friction power"]
        P_j2::Real, [unit = "W", description = "Joint 2 friction power"]
    end
    @outputs begin
        E_mech::Real, [unit = "J"]
        E_drive::Real, [unit = "J"]
        W_in::Real, [unit = "J"]
        W_loss::Real, [unit = "J"]
        H::Real, [unit = "J", description = "E_mech + E_drive + W_loss - W_in"]
    end
    @parameters begin
        m::Vec{3} = [0.53, 0.413, 0.233], [unit = "kg", description = "Body masses"]
        g0::Real = 9.81, [unit = "m/s^2"]
        J_m::Real = 7.0e-5, [unit = "kg*m^2", description = "Rotor inertia (motor shaft)"]
        L_eq::Real = 1.113e-4, [unit = "H", description = "Equivalent winding inductance"]
        R_eq::Real = 0.18, [unit = "Ohm", description = "Equivalent winding resistance"]
    end
    @variables begin
        Win::Real = 0.0, [unit = "J", state = :prefer]
        Wl::Real = 0.0, [unit = "J", state = :prefer]
    end
    @equations begin
        E_mech ~ 0.5 * dot(V1, P1) + 0.5 * dot(V2, P2) + 0.5 * dot(V3, P3) + g0 * (m[1] * g1[7] + m[2] * g2[7] + m[3] * g3[7])
        E_drive ~ 0.5 * J_m * wm * wm + 0.5 * L_eq * ie * ie + E_gear
        ddt(Win) ~ uq * ie
        ddt(Wl) ~ R_eq * ie * ie + P_fin + P_fout + P_gear + P_j1 + P_j2
        W_in ~ Win
        W_loss ~ Wl
        H ~ E_mech + E_drive + W_loss - W_in
    end
end
