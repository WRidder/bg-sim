@block GantryMonitor begin
    # What the gantry's dashboard shows: the tool error, the racking, the beam's peak stress
    # against the allowable, and the settling time of the last move.
    #
    #   ex, ey, ez   tool position (world, from the composed tool pose g) minus where the tool
    #                belongs: (x0 + x_ref, y0, z0), in um;
    #   exy          the error in the plane of the moves, sqrt(ex^2 + ey^2), in um;
    #   rack         x1 - x2, the difference of the two X axes' positions (encoders), in um;
    #   util         sigma / sigma_allow in %;
    #   settle       the settling time of the last move: from the end of the reference motion
    #                to the last time the tool error left the band (|e| > band).
    #
    # The two times are tracked without events: while its condition holds (a smooth step of
    # width w_band, resp. of the reference speed), a state follows the time t with the rate
    # k_track (a lag of 1/k_track); otherwise it holds. settle is their difference (0 while
    # the tool is still moving), so after each move it reads that move's settling time.
    @inputs begin
        g::Vec{7}
        x_ref::Real, [unit = "m"]
        v_ref::Real, [unit = "m/s"]
        x1::Real, [unit = "m"]
        x2::Real, [unit = "m"]
        sigma::Real, [unit = "Pa"]
    end
    @outputs begin
        ex::Real, [description = "Tool error along x (the move), in um"]
        ey::Real, [description = "Tool error along y (the beam), in um"]
        ez::Real, [description = "Tool error along z, in um"]
        exy::Real, [description = "Tool error in the plane of the moves, in um"]
        rack::Real, [description = "Racking: X1 minus X2 position, in um"]
        sigma_MPa::Real, [description = "Peak von Mises stress of the beam, in MPa"]
        util::Real, [description = "Peak stress over the allowable, in %"]
        settle::Real, [unit = "s", description = "Settling time of the last move into the band"]
    end
    @parameters begin
        x0::Real = 0.0, [unit = "m", description = "Tool x at x_ref = 0"]
        y0::Real = 0.0, [unit = "m", description = "Tool y"]
        z0::Real = 0.0, [unit = "m", description = "Tool z"]
        band::Real = 1.0e-5, [unit = "m", min = 1.0e-9, description = "Settling band of the tool error"]
        w_band::Real = 1.0e-7, [unit = "m", min = 1.0e-12, description = "Width of the smooth band edge (an error 1 um inside the band counts 1e-9 as outside)"]
        v_eps::Real = 1.0e-5, [unit = "m/s", min = 1.0e-12, description = "Reference speed below which the move has ended"]
        k_track::Real = 4000.0, [unit = "1/s", min = 1.0e-3, description = "Rate of the time trackers"]
        sigma_allow::Real = 40.0e6, [unit = "Pa", min = 1.0e-9, description = "Allowable stress"]
    end
    @variables begin
        t_out::Real = 0.0, [unit = "s", description = "Last time the tool error was outside the band"]
        t_ref::Real = 0.0, [unit = "s", description = "Last time the reference moved"]
        dx::Real, [unit = "m"]
        dy::Real, [unit = "m"]
        dz::Real, [unit = "m"]
        em::Real, [unit = "m"]
        h_out::Real, [description = "1 outside the band, 0 inside (smooth)"]
        h_ref::Real, [description = "1 while the reference moves, 0 at rest (smooth)"]
    end
    @equations begin
        dx ~ g[5] - x0 - x_ref
        dy ~ g[6] - y0
        dz ~ g[7] - z0
        em ~ sqrt(dx * dx + dy * dy + 1.0e-18)
        h_out ~ 0.5 * (1.0 + tanh((em - band) / w_band))
        h_ref ~ 0.5 * (1.0 + tanh((sqrt(v_ref * v_ref + 1.0e-18) - v_eps) / (0.05 * v_eps)))
        ddt(t_out) ~ k_track * h_out * (t - t_out)
        ddt(t_ref) ~ k_track * h_ref * (t - t_ref)
        ex ~ 1.0e6 * dx
        ey ~ 1.0e6 * dy
        ez ~ 1.0e6 * dz
        exy ~ 1.0e6 * em
        rack ~ 1.0e6 * (x1 - x2)
        sigma_MPa ~ 1.0e-6 * sigma
        util ~ 100.0 * sigma / sigma_allow
        settle ~ max(t_out - t_ref, 0.0)
    end
end
