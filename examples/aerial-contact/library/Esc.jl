@block Esc begin
    # Electronic speed controller of one rotor, 250 Hz: closed-loop rotor-speed control with a
    # motor-model feedforward, output = average terminal voltage (the PWM duty times the pack voltage).
    #
    #   u_ff = k_e w_cmd + (R_w / k_t) (kQ w_cmd |w_cmd| + b_m w_cmd)     (steady-state voltage)
    #   u    = u_ff + Kp (w_cmd - w) + I,   I <- I + Ki (w_cmd - w) Ts
    #
    # The voltage is limited to [0, duty_max * V_bat] with the live pack voltage `vbat` (the battery
    # sag therefore limits the thrust at full throttle) and by a current limit (the spin-up from standstill
    # would otherwise draw R_w^-1 times the pack voltage, about 100 A); the integral is frozen while the limit is active and
    # the error pushes further into it.
    @inputs begin
        w_cmd::Real
        w::Real
        vbat::Real
    end
    @outputs u::Real = 0.0, [unit = "V"]
    @parameters begin
        k_e::Real = 0.01038, [unit = "V*s/rad", description = "Back-EMF constant of the motor (= k_t)"]
        k_t::Real = 0.01038, [unit = "N*m/A", description = "Torque constant of the motor"]
        R_w::Real = 0.11, [unit = "Ohm", description = "Winding resistance"]
        kQ::Real = 2.03e-7, [description = "Propeller drag coefficient (N m s^2/rad^2)"]
        b_m::Real = 2.0e-6, [unit = "N*m*s/rad", description = "Viscous loss of the rotor"]
        Kp::Real = 0.03, [unit = "V*s/rad", description = "Speed loop P gain"]
        Ki::Real = 1.5, [unit = "V/rad", description = "Speed loop I gain"]
        i_lim::Real = 25.0, [unit = "A", min = 0, description = "Current limit: the voltage is capped at k_e w + R_w i_lim"]
        duty_max::Real = 0.98, [min = 0, max = 1, description = "Maximum duty cycle"]
    end
    @variables I::Real = 0.0, [unit = "V", description = "Integral state"]
    @discrete Ts = 4e-3 begin
        uff = k_e * w_cmd + (R_w / k_t) * (kQ * w_cmd * abs(w_cmd) + b_m * w_cmd)
        e = w_cmd - w
        umax = min(duty_max * vbat, k_e * w + R_w * i_lim)
        v = uff + Kp * e + I
        if w_cmd < 1.0
            I = 0.0
            u = 0.0
        else
            if (v > umax && e > 0.0) || (v < 0.0 && e < 0.0)
                I = I
            else
                I = clamp(I + Ki * e * Ts, -3.0, 3.0)
            end
            u = clamp(uff + Kp * e + I, 0.0, umax)
        end
    end
end
