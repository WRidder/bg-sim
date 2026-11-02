@block DemoPilot begin
    # The demonstration pilot (ours): the outer loops that fly a109-sim's default run by stick,
    # through the SCAS. In the exported FMU the host's pilot replaces it (the stick signals pass
    # through ExportInputPass markers).
    #
    #   speed     lon = -Ku (u - u_cmd) / k_th_stick        (an attitude command per speed error)
    #   bank      phi_des = sigma(u) phi_turn - (1 - sigma(u)) Kv v,  lat = phi_des / k_ph_stick
    #             (at low speed it holds the lateral velocity at zero, at speed it flies the
    #             scheduled bank of the coordinated turn)
    #   height    coll = coll_ff(u) + Kh (h_cmd - h) - Khd hdot  (fraction of travel)
    #   pedals    0 (the SCAS holds the heading and coordinates the turn)
    #
    # u_cmd, h_cmd and phi_turn come from the schedule (Lookup1D over time). demo = 0 holds the
    # hover sticks instead (with the SCAS on: the hover collective and centred cyclic and
    # pedals). The offsets (globals, from t_inp) are added to the sticks for hands-on tests.
    @inputs begin
        u_cmd::Real
        h_cmd::Real
        ph_turn::Real
        u::Real
        v::Real
        h::Real
        hdot::Real
        coll_ff::Real, [description = "Trim collective over airspeed (deg)"]
    end
    @outputs begin
        coll::Real
        lon::Real
        lat::Real
        ped::Real
    end
    @parameters begin
        demo::Real = 1.0, [description = "1: fly the demonstration; 0: hold the hover sticks"]
        scas::Real = 1.0
        Ku::Real = 0.6
        Kv::Real = 1.2
        Kh::Real = 0.012
        Khd::Real = 0.03
        k_th_stick::Real = 15.0
        k_ph_stick::Real = 30.0
        v_tc1::Real = 10.0
        v_tc2::Real = 20.0
        a_coll::Real = 0.0
        b_coll::Real = 1.0
        coll_h::Real = 0.5, [description = "Hover collective (fraction)"]
        lon_h::Real = 0.0, [description = "Hover longitudinal stick without the SCAS"]
        lat_h::Real = 0.0, [description = "Hover lateral stick without the SCAS"]
        ped_h::Real = 0.0, [description = "Hover pedals without the SCAS"]
        coll_off::Real = 0.0
        lon_off::Real = 0.0
        lat_off::Real = 0.0
        ped_off::Real = 0.0
        t_inp::Real = 1.0
    end
    @variables begin
        sig::Real = 0.0
        on::Real = 0.0
        c_d::Real = 0.5
        lon_d::Real = 0.0
        lat_d::Real = 0.0
    end
    @equations begin
        sig ~ clamp((u - v_tc1) / (v_tc2 - v_tc1), 0.0, 1.0)
        on ~ ifelse(t >= t_inp, 1.0, 0.0)
        c_d ~ (a_coll + b_coll * coll_ff) / 100.0 + Kh * (h_cmd - h) - Khd * hdot
        lon_d ~ clamp(-Ku * (u - u_cmd) / k_th_stick, -1.0, 1.0)
        lat_d ~ clamp((sig * ph_turn - (1.0 - sig) * Kv * v) / k_ph_stick, -1.0, 1.0)
        coll ~ demo * c_d + (1.0 - demo) * coll_h + on * coll_off
        lon ~ demo * lon_d + (1.0 - demo) * (1.0 - scas) * lon_h + on * lon_off
        lat ~ demo * lat_d + (1.0 - demo) * (1.0 - scas) * lat_h + on * lat_off
        ped ~ (1.0 - demo) * (1.0 - scas) * ped_h + on * ped_off
    end
end
