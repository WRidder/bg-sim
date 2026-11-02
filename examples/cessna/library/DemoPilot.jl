@block DemoPilot begin
    # The test pilot of cessna-sim's default run (signal only; in the FMU the host's pilot
    # replaces it): a short-field takeoff from runway 36 (heading north, along world x from
    # x = 0), the climb and a turn to the east. Every phase switch is a smooth step
    # sig(x) = (1 + tanh x)/2 of the airframe's state, so the run needs no events:
    #
    #   throttle   idle until t_thr, then full over t_thr_ramp
    #   rotation   rot = sig((cas - vr)/dv_rot); airborne air = sig((agl - h_air)/0.5)
    #   pitch      attitude loop yoke = rot clamp(k_theta (theta_c - theta) - k_q q, +-1):
    #              theta_c = theta_rot on the runway; in the air the climb attitude
    #              clamp(theta_climb + kv (cas - v_cmd), 0, 0.22) for the speed
    #              v_cmd = min(v_climb, v_lift + dvdh agl)
    #   roll       bank loop clamp(k_phi (phi_c - phi) - k_p p, +-1); in the air the bank
    #              command holds the heading (north, then psi_turn from t_turn), within phi_max
    #   pedals     on the runway: heading and centre-line hold; in the air a yaw damper
    #   flaps      10 deg until agl > h_flaps_up, then up
    # With on = 0 the outputs hold the *_hold values instead (the trimmed starts of the other runs).
    @inputs begin
        cas::Real, [unit = "m/s"]
        theta::Real, [unit = "rad"]
        q::Real, [unit = "rad/s"]
        phi::Real, [unit = "rad"]
        p::Real, [unit = "rad/s"]
        psi::Real, [unit = "rad"]
        r::Real, [unit = "rad/s"]
        h::Real, [unit = "m"]
        y::Real, [unit = "m", description = "World y (west): the offset from the centre line"]
    end
    @outputs begin
        yoke_pitch::Real
        yoke_roll::Real
        pedals::Real
        throttle::Real
        flaps::Real
    end
    @parameters begin
        t_thr::Real = 1.0, [unit = "s"]
        t_thr_ramp::Real = 2.0, [unit = "s"]
        vr::Real = 23.15, [unit = "m/s", description = "Rotation speed (CAS; 45 kt)"]
        dv_rot::Real = 0.5, [unit = "m/s"]
        theta_rot::Real = 0.17, [unit = "rad"]
        h_air::Real = 3.0, [unit = "m"]
        dh_air::Real = 0.5, [unit = "m"]
        theta_climb::Real = 0.13, [unit = "rad"]
        kv::Real = 0.03, [unit = "s/m", description = "Attitude per speed error (rad per m/s)"]
        v_lift::Real = 30.0, [unit = "m/s"]
        v_climb::Real = 38.58, [unit = "m/s", description = "Climb speed (CAS; 75 kt)"]
        dvdh::Real = 0.5, [unit = "1/s"]
        k_theta::Real = 10.0
        k_q::Real = 2.0, [unit = "s"]
        h_flaps_up::Real = 20.0, [unit = "m"]
        t_turn::Real = 75.0, [unit = "s"]
        dt_turn::Real = 0.5, [unit = "s"]
        psi_turn::Real = 1.5707963267948966, [unit = "rad"]
        k_psi::Real = 1.2
        phi_max::Real = 0.3490658503988659, [unit = "rad"]
        k_phi::Real = 2.0
        k_p::Real = 0.3, [unit = "s"]
        k_ped_psi::Real = 3.0
        k_ped_r::Real = 1.5, [unit = "s"]
        k_ped_y::Real = 0.05, [unit = "1/m"]
        k_yd::Real = 0.5, [unit = "s"]
        h_cg0::Real = 1.2546, [unit = "m", description = "Static CG height above the runway"]
        ground_z::Real = 0.0, [unit = "m"]
        on::Real = 1.0, [description = "1: the demo flies; 0: the controls hold the *_hold values"]
        yoke_hold::Real = 0.0
        roll_hold::Real = 0.0
        ped_hold::Real = 0.0
        thr_hold::Real = 0.0
        flaps_hold::Real = 0.0
    end
    @variables begin
        agl::Real = 0.0, [unit = "m"]
        rot::Real = 0.0
        air::Real = 0.0
        turn::Real = 0.0
        v_cmd::Real = 30.0, [unit = "m/s"]
        th_climb::Real = 0.13, [unit = "rad"]
        th_c::Real = 0.17, [unit = "rad"]
        phi_c::Real = 0.0, [unit = "rad"]
        dpsi::Real = 0.0, [unit = "rad"]
        d_pitch::Real = 0.0
        d_roll::Real = 0.0
        d_ped::Real = 0.0
        d_thr::Real = 0.0
        d_flaps::Real = 1.0
    end
    @equations begin
        agl ~ h - ground_z - h_cg0
        rot ~ 0.5 * (1.0 + tanh((cas - vr) / dv_rot))
        air ~ 0.5 * (1.0 + tanh((agl - h_air) / dh_air))
        turn ~ 0.5 * (1.0 + tanh((t - t_turn) / dt_turn))
        v_cmd ~ min(v_climb, v_lift + dvdh * max(agl, 0.0))
        th_climb ~ clamp(theta_climb + kv * (cas - v_cmd), 0.0, 0.22)
        th_c ~ (1.0 - air) * theta_rot + air * th_climb
        d_pitch ~ rot * clamp(k_theta * (th_c - theta) - k_q * q, -1.0, 1.0)
        dpsi ~ atan(sin(turn * psi_turn - psi), cos(turn * psi_turn - psi))
        phi_c ~ air * clamp(k_psi * dpsi, -phi_max, phi_max)
        d_roll ~ clamp(k_phi * (phi_c - phi) - k_p * p, -1.0, 1.0)
        d_ped ~ clamp((1.0 - air) * (-k_ped_psi * atan(sin(psi), cos(psi)) - k_ped_r * r + k_ped_y * y) - air * k_yd * r, -1.0, 1.0)
        d_thr ~ clamp((t - t_thr) / t_thr_ramp, 0.0, 1.0)
        d_flaps ~ ifelse(agl < h_flaps_up, 1.0, 0.0)
        yoke_pitch ~ on * d_pitch + (1.0 - on) * yoke_hold
        yoke_roll ~ on * d_roll + (1.0 - on) * roll_hold
        pedals ~ on * d_ped + (1.0 - on) * ped_hold
        throttle ~ on * d_thr + (1.0 - on) * thr_hold
        flaps ~ on * d_flaps + (1.0 - on) * flaps_hold
    end
end
