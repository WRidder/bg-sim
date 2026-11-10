@block RotorGovernor begin
    # Rotor-speed loop of one propulsion motor: Ingenuity flies at a fixed rotor speed (2537 rpm on
    # flights 1-13) and controls thrust with the blade pitch only (Grip et al. 2018); the FPGA's
    # outer motor loop holds that speed (Balaram et al. 2018). A PI law on the speed error with the
    # back-EMF as feedforward and back-calculation anti-windup,
    #
    #     u = clamp(k_e w_ref + Kp e + xi, 0, u_max),   xi' = Ki e + K_aw (u - u_unlimited)
    #
    # (a frozen integrator would slide along the voltage limit and chatter there; the
    # back-calculation keeps the law continuous).
    #
    # with e = w_ref - spin*w (the signed shaft speed relative to the airframe). The output is the
    # winding voltage of the motor's modulated effort source, signed with the spin direction.
    # `i` is the winding current (a flow detector on the electrical 1-junction), so P_el = u i is
    # the electrical power the battery delivers to this motor.
    @inputs begin
        w::Real, [unit = "rad/s", description = "Shaft speed relative to the airframe (signed)"]
        i::Real, [unit = "A", description = "Winding current (signed like the voltage)"]
        wset::Real, [unit = "rad/s", description = "Speed set point (magnitude)"]
    end
    @outputs begin
        u::Real, [unit = "V", description = "Winding voltage (signed)"]
        P_el::Real, [unit = "W", description = "Electrical power u i"]
        speed_rpm::Real, [unit = "1", description = "Rotor speed in rpm (`rpm` itself is the built-in constant 2 pi/60)"]
    end
    @parameters begin
        spin::Real = 1.0, [description = "+1 / -1: spin direction of the rotor"]
        k_e::Real = 0.05, [unit = "V*s/rad", description = "Back-EMF constant (feedforward)"]
        Kp::Real = 1.0, [unit = "V*s/rad", description = "Proportional gain"]
        Ki::Real = 5.0, [unit = "V/rad", description = "Integral gain"]
        u_max::Real = 22.0, [unit = "V", min = 0, description = "Battery voltage (output limit)"]
        K_aw::Real = 20.0, [unit = "1/s", min = 0, description = "Anti-windup back-calculation gain"]
        k_rpm::Real = 9.549296585513721, [unit = "s", description = "rpm per rad/s"]
    end
    @variables begin
        xi::Real = 0.0, [unit = "V", state = :prefer, description = "Integrator"]
        e::Real = 0.0, [unit = "rad/s", description = "Speed error"]
        uc::Real = 0.0, [unit = "V", description = "Unlimited command"]
        um::Real = 0.0, [unit = "V", description = "Limited command magnitude"]
    end
    @equations begin
        e ~ wset - spin * w
        uc ~ k_e * wset + Kp * e + xi
        um ~ clamp(uc, 0.0, u_max)
        ddt(xi) ~ Ki * e + K_aw * (um - uc)
        u ~ spin * um
        P_el ~ u * i
        speed_rpm ~ k_rpm * spin * w
    end
end
