@block VSTorque begin
    # The generator-torque law of the NREL 5 MW baseline controller (report section 7.2 and the
    # DISCON source of Appendix C, signal only), on the filtered generator speed w:
    #
    #   region 1     w <= w_ctin                        0
    #   region 1.5   w_ctin < w < w_rgn2                linear from 0 to the region-2 curve
    #   region 2     w_rgn2 <= w < w_tr                 k2 w^2 (optimal tip-speed ratio)
    #   region 2.5   w_tr <= w < w_rated                induction-machine line through the synchronous
    #                                                   speed w_sync = w_rated / (1 + slip/100)
    #   region 3     w >= w_rated or beta >= beta_rgn3  P_rated / w (constant power)
    #
    # and at most tq_max. The region-1.5 slope, the region-2.5 slope and the speed w_tr where the
    # region-2 curve meets the region-2.5 line follow from the parameters as in DISCON. beta is the
    # blade pitch: once the pitch controller has pitched the blades by beta_rgn3 the law stays in
    # region 3 even when the speed dips below w_rated.
    @inputs begin
        w::Real, [unit = "rad/s", description = "Filtered generator speed"]
        beta::Real, [unit = "rad", description = "Blade pitch"]
    end
    @outputs begin
        tq::Real, [unit = "N*m", description = "Generator torque command"]
        region::Real, [description = "Control region 1, 1.5, 2, 2.5 or 3"]
    end
    @parameters begin
        w_ctin::Real = 70.16224, [unit = "rad/s", description = "Cut-in generator speed (670 rpm)"]
        w_rgn2::Real = 91.21091, [unit = "rad/s", description = "Start of region 2 (871 rpm)"]
        w_rated::Real = 121.6805, [unit = "rad/s", description = "Start of region 3 (1161.963 rpm, 99 % of rated)"]
        k2::Real = 2.332287, [unit = "N*m*s^2/rad^2", min = 0, description = "Region-2 gain (0.0255764 N m/rpm^2)"]
        p_rated::Real = 5296610.0, [unit = "W", min = 0, description = "Rated mechanical power"]
        slip::Real = 10.0, [min = 0.1, description = "Generator slip of the region-2.5 line (%)"]
        tq_max::Real = 47402.91, [unit = "N*m", min = 0, description = "Maximum generator torque"]
        beta_rgn3::Real = 0.01745329, [unit = "rad", description = "Pitch above which the law stays in region 3 (1 deg)"]
    end
    @variables begin
        w_sync::Real = 110.6, [unit = "rad/s"]
        slope15::Real = 1.0e4, [unit = "N*m*s/rad"]
        slope25::Real = 4.0e3, [unit = "N*m*s/rad"]
        w_tr::Real = 120.0, [unit = "rad/s"]
        wp::Real = 100.0, [unit = "rad/s"]
        t_lin::Real = 0.0, [unit = "N*m"]
    end
    @equations begin
        w_sync ~ w_rated / (1.0 + 0.01 * slip)
        slope15 ~ k2 * w_rgn2 * w_rgn2 / (w_rgn2 - w_ctin)
        slope25 ~ p_rated / w_rated / (w_rated - w_sync)
        w_tr ~ (slope25 - sqrt(slope25 * (slope25 - 4.0 * k2 * w_sync))) / (2.0 * k2)
        wp ~ max(w, 1.0)
        t_lin ~ ifelse(w <= w_ctin, 0.0,
                    ifelse(w < w_rgn2, slope15 * (w - w_ctin),
                        ifelse(w < w_tr, k2 * w * w, slope25 * (w - w_sync))))
        tq ~ min(ifelse(w >= w_rated || beta >= beta_rgn3, p_rated / wp, t_lin), tq_max)
        region ~ ifelse(w >= w_rated || beta >= beta_rgn3, 3.0,
                     ifelse(w <= w_ctin, 1.0, ifelse(w < w_rgn2, 1.5, ifelse(w < w_tr, 2.0, 2.5))))
    end
end
