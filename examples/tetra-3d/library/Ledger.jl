@block Ledger begin
    # Energy ledger of the tetrahedron (X5.6): a sensor, not plant physics.
    #
    #   Ed   = integral of the contact dissipation  sum_k Pd_k            (J)
    #   Wm   = integral of the motor input power    sum_j tau_m_j w_j      (J)
    #   Es   = energy kept by the four shafts and rotors,
    #          sum_j (1/2) tau_j^2 / k_s (shaft torque tau_j = k_s phi_j) + (1/2) J_m w_j^2                   (J)
    #
    # Electrical tap of the four motors (permanent magnet behind an ideal current loop): the terminal
    # voltage needed for the measured torque tm_j and speed w_j is  v_j = R_m tm_j / k_t + k_t w_j
    # (winding resistance plus back-EMF, k_e = k_t in SI), the current is  tm_j / k_t.
    #
    # With the mechanical energy `E_mech` of the five bodies and the contact spring energy `Ec`,
    # the balance  E_mech + sum Ec + Es + Ed - Wm  is constant (the joints' own spring energy
    # is below 1e-5 J).
    @inputs begin
        pd1::Real
        pd2::Real
        pd3::Real
        pd4::Real
        tm1::Real
        tm2::Real
        tm3::Real
        tm4::Real
        w1::Real
        w2::Real
        w3::Real
        w4::Real
        ts1::Real
        ts2::Real
        ts3::Real
        ts4::Real
    end
    @outputs begin
        Ed::Real, [unit = "J"]
        Wm::Real, [unit = "J"]
        Es::Real, [unit = "J"]
        v1::Real, [unit = "V"]
        v2::Real, [unit = "V"]
        v3::Real, [unit = "V"]
        v4::Real, [unit = "V"]
    end
    @parameters begin
        k_s::Real = 100.0, [unit = "N*m/rad", min = 0, description = "Shaft stiffness"]
        J_m::Real = 1.0e-8, [unit = "kg*m^2", min = 0, description = "Rotor inertia"]
        k_t::Real = 0.1, [unit = "N*m/A", min = 1.0e-9, description = "Motor torque constant"]
        R_m::Real = 0.4, [unit = "V/A", min = 0, description = "Winding resistance"]
    end
    @variables begin
        Ei::Real = 0.0, [state = :prefer, description = "Integral of the contact dissipation"]
        Wi::Real = 0.0, [state = :prefer, description = "Integral of the motor input power"]
    end
    @equations begin
        ddt(Ei) ~ pd1 + pd2 + pd3 + pd4
        ddt(Wi) ~ tm1 * w1 + tm2 * w2 + tm3 * w3 + tm4 * w4
        Ed ~ Ei
        Wm ~ Wi
        Es ~ 0.5 * (ts1 * ts1 + ts2 * ts2 + ts3 * ts3 + ts4 * ts4) / k_s + 0.5 * J_m * (w1 * w1 + w2 * w2 + w3 * w3 + w4 * w4)
        v1 ~ R_m * tm1 / k_t + k_t * w1
        v2 ~ R_m * tm2 / k_t + k_t * w2
        v3 ~ R_m * tm3 / k_t + k_t * w3
        v4 ~ R_m * tm4 / k_t + k_t * w4
    end
end
