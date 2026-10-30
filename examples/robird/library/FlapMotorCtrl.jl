@block FlapMotorCtrl begin
    # Speed regulator of the flapping motor (the analogue "ESC" of the bird): closed-loop speed control of the
    # flapping motor from the commanded flapping frequency `f_cmd` (Hz). The crank turns at 2 pi f and the motor at
    # N times that. A continuous PI with the motor model as feed-forward; output: the average terminal voltage.
    #
    #   w_cmd = N 2 pi f_cmd ,   u_ff = k_e w_cmd + (R_w / k_t) b_m w_cmd
    #   u = clamp(u_ff + Kp (w_cmd - w) + I, 0, duty_max V_bat) ,   dI/dt = Ki (w_cmd - w) + Kaw (u - u_unsat)
    #
    # (back-calculation anti-windup). The load torque of the flapping wings varies strongly within a stroke (wing
    # inertia and aerodynamics), so the loop only regulates the mean speed; the within-stroke speed ripple is a
    # result of the model, not an input (README).
    @inputs begin
        f_cmd::Real
        w::Real
        vbat::Real
    end
    @outputs begin
        u::Real, [unit = "V"]
        w_cmd::Real, [unit = "rad/s"]
    end
    @parameters begin
        N::Real = 28.0, [min = 1, description = "Gear ratio motor / crank"]
        k_e::Real = 0.0125, [unit = "V*s/rad", description = "Back-EMF constant of the motor (= k_t)"]
        k_t::Real = 0.0125, [unit = "N*m/A", description = "Torque constant"]
        R_w::Real = 0.15, [unit = "Ohm", description = "Winding resistance"]
        b_m::Real = 1.0e-5, [unit = "N*m*s/rad", description = "Viscous loss of the rotor"]
        Kp::Real = 0.012, [unit = "V*s/rad", description = "Speed loop P gain"]
        Ki::Real = 0.5, [unit = "V/rad", description = "Speed loop I gain"]
        Kaw::Real = 20.0, [unit = "1/s", description = "Back-calculation gain"]
        duty_max::Real = 0.98, [min = 0, max = 1, description = "Maximum duty cycle"]
    end
    @variables begin
        I::Real = 0.0, [unit = "V", description = "Integral state"]
        wc::Real = 0.0, [unit = "rad/s"]
        uun::Real = 0.0, [unit = "V", description = "Unsaturated voltage"]
    end
    @equations begin
        wc ~ N * 2.0 * 3.141592653589793 * f_cmd
        uun ~ k_e * wc + (R_w / k_t) * b_m * wc + Kp * (wc - w) + I
        u ~ max(0.0, min(uun, duty_max * vbat))
        ddt(I) ~ Ki * (wc - w) + Kaw * (u - uun)
        w_cmd ~ wc
    end
end
