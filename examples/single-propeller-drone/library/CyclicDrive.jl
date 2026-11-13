@block CyclicDrive begin
    # The motor controller's fast part (the moteus current loop and its cyclic modulation),
    # continuous because it runs at the PWM rate. It turns a torque request into the duty of the
    # inverter (the `MTF` between the battery bus and the motor winding in `Motor`):
    #
    #   tau_ref = clamp(arm (tau_base + cyc_x cos(psi + phase0) + cyc_y sin(psi + phase0)), +-tau_max)
    #   i_ref   = tau_ref / k_t
    #   v       = R_w i_ref + k_t w + K_c (i_ref - i)          (feed-forward + P on the current)
    #   duty    = clamp(v / v_bus, -1, 1)
    #
    # `tau_base` is the collective torque of the speed loop (`RotorEsc`), `cyc_x, cyc_y` the
    # cyclic torque components of the allocation, `psi` the encoder azimuth. With the winding
    # `L di/dt = duty V_bus - R_w i - k_t w` the current follows `i_ref` with the bandwidth
    # (R_w + K_c)/L. `v_bus` is the bus voltage the drive sampled on its last tick (held), so the
    # duty does not form an algebraic loop with the pack's series resistance. Disarmed, the
    # current reference is zero and the inverter keeps the winding current at zero: the
    # propeller coasts (a duty of zero would short the winding and brake it).
    @inputs begin
        tau_base::Real, [unit = "N*m", description = "Collective torque from the speed loop"]
        cyc_x::Real, [unit = "N*m", description = "Cosine component of the cyclic torque"]
        cyc_y::Real, [unit = "N*m", description = "Sine component of the cyclic torque"]
        psi::Real, [unit = "rad", description = "Rotor azimuth from the encoder"]
        arm::Real, [description = "1 = motor enabled"]
        w::Real, [unit = "rad/s", description = "Rotor speed relative to the stator"]
        i::Real, [unit = "A", description = "Measured winding current"]
        v_bus::Real, [unit = "V", description = "Sampled bus voltage"]
    end
    @outputs begin
        duty::Real, [description = "Inverter duty, the MTF modulus"]
        tau_ref::Real, [unit = "N*m", description = "Torque request after the limit"]
        i_ref::Real, [unit = "A", description = "Current reference"]
        cyc::Real, [unit = "N*m", description = "Instantaneous cyclic torque component"]
    end
    @parameters begin
        k_t::Real = 0.03, [unit = "N*m/A", min = 1.0e-6, description = "Motor torque constant (the drive's model of it)"]
        R_w::Real = 0.08, [unit = "Ohm", min = 0, description = "Winding resistance (the drive's model of it)"]
        K_c::Real = 0.1, [unit = "Ohm", min = 0, description = "Current-loop proportional gain"]
        tau_max::Real = 1.6, [unit = "N*m", min = 0, description = "Torque limit of the drive"]
        phase0::Real = 0.0, [unit = "rad", description = "Phase calibration of the cyclic frame"]
    end
    @variables begin
        raw::Real = 0.0, [unit = "N*m", description = "Unlimited torque request"]
        v::Real = 0.0, [unit = "V", description = "Requested winding voltage"]
    end
    @equations begin
        cyc ~ cyc_x * cos(psi + phase0) + cyc_y * sin(psi + phase0)
        raw ~ arm * (tau_base + cyc)
        tau_ref ~ clamp(raw, -tau_max, tau_max)
        i_ref ~ tau_ref / k_t
        v ~ R_w * i_ref + k_t * w + K_c * (i_ref - i)
        duty ~ clamp(v / max(v_bus, 1.0), -1.0, 1.0)
    end
end
