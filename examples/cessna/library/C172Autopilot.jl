@block C172Autopilot begin
    # A simple two-axis autopilot in the spirit of the KAP 140 (signal only): it adds to the
    # pilot's yoke and works within a limited authority, so the pilot can always override it.
    #
    #   roll_mode   0 off, 1 wing leveller (bank to 0), 2 heading hold: bank command
    #               clamp(k_psi wrap(hdg_ref - psi), +-phi_max)
    #               roll = clamp(k_phi (phi_c - phi) - k_p p, +-roll_max)
    #   alt_mode    0 off, 1 altitude hold:
    #               pitch = clamp(k_h e - k_hd hdot + k_hi xi - k_q q, +-pitch_max),
    #               e = clamp(alt_ref - h, +-h_err_max), xi' = e (decays with tau_reset when off)
    #
    # The trim (the elevator trim input of the airframe) stays with the pilot; the integrator
    # takes the steady elevator in a held altitude.
    @inputs begin
        yoke_pitch_in::Real, [description = "Pilot's yoke, pitch"]
        yoke_roll_in::Real, [description = "Pilot's yoke, roll"]
        roll_mode::Real, [description = "0 off, 1 wing leveller, 2 heading hold"]
        alt_mode::Real, [description = "0 off, 1 altitude hold"]
        hdg_ref::Real, [description = "Heading to hold (deg)"]
        alt_ref::Real, [unit = "m", description = "Altitude to hold"]
        phi::Real, [unit = "rad"]
        psi::Real, [unit = "rad"]
        p::Real, [unit = "rad/s"]
        q::Real, [unit = "rad/s"]
        h::Real, [unit = "m"]
        hdot::Real, [unit = "m/s"]
    end
    @outputs begin
        yoke_pitch::Real
        yoke_roll::Real
        ap_pitch::Real, [description = "Autopilot's share of the pitch yoke"]
        ap_roll::Real, [description = "Autopilot's share of the roll yoke"]
    end
    @parameters begin
        k_psi::Real = 1.0
        phi_max::Real = 0.3490658503988659, [unit = "rad"]
        k_phi::Real = 1.5
        k_p::Real = 0.3, [unit = "s"]
        roll_max::Real = 0.5
        k_h::Real = 0.01, [unit = "1/m"]
        k_hd::Real = 0.04, [unit = "s/m"]
        k_hi::Real = 0.002, [unit = "1/(m*s)"]
        k_q::Real = 0.5, [unit = "s"]
        h_err_max::Real = 30.0, [unit = "m"]
        pitch_max::Real = 0.6
        tau_reset::Real = 0.5, [unit = "s"]
    end
    @variables begin
        xi::Real = 0.0, [unit = "m*s", state = :prefer, description = "Integrated altitude error"]
        hdg_on::Real = 0.0
        on_r::Real = 0.0
        on_a::Real = 0.0
        phi_c::Real = 0.0, [unit = "rad"]
        dpsi::Real = 0.0, [unit = "rad"]
        e::Real = 0.0, [unit = "m"]
    end
    @equations begin
        hdg_on ~ ifelse(roll_mode >= 1.5, 1.0, 0.0)
        on_r ~ ifelse(roll_mode >= 0.5, 1.0, 0.0)
        on_a ~ ifelse(alt_mode >= 0.5, 1.0, 0.0)
        dpsi ~ atan(sin(hdg_ref / 57.29577951308232 - psi), cos(hdg_ref / 57.29577951308232 - psi))
        phi_c ~ hdg_on * clamp(k_psi * dpsi, -phi_max, phi_max)
        ap_roll ~ on_r * clamp(k_phi * (phi_c - phi) - k_p * p, -roll_max, roll_max)
        e ~ clamp(alt_ref - h, -h_err_max, h_err_max)
        ddt(xi) ~ on_a * e - (1.0 - on_a) * xi / tau_reset
        ap_pitch ~ on_a * clamp(k_h * e - k_hd * hdot + k_hi * xi - k_q * q, -pitch_max, pitch_max)
        yoke_pitch ~ clamp(yoke_pitch_in + ap_pitch, -1.0, 1.0)
        yoke_roll ~ clamp(yoke_roll_in + ap_roll, -1.0, 1.0)
    end
end
