@block Metrics begin
    # Flight-test read-outs for the acceptance checks (a measurement tap, not plant physics), 50 Hz. After `t_from`
    # (the convergence time) it keeps the running RMS of the cross-track and altitude errors, the extents of the
    # flown figure and the number of sign changes of x and y (a figure-eight lap has 2 zero crossings of x and 4 of y).
    @inputs begin
        x::Real
        y::Real
        e_ct::Real
        e_z::Real
        tm::Real
    end
    @outputs begin
        rms_ct::Real = 0.0, [unit = "m"]
        rms_z::Real = 0.0, [unit = "m"]
        x_max::Real = 0.0, [unit = "m"]
        x_min::Real = 0.0, [unit = "m"]
        y_max::Real = 0.0, [unit = "m"]
        y_min::Real = 0.0, [unit = "m"]
        nx::Real = 0.0
        ny::Real = 0.0
        n_samples::Real = 0.0
    end
    @parameters t_from::Real = 8.0, [unit = "s", description = "Start of the statistics"]
    @variables begin
        sct::Real = 0.0
        szz::Real = 0.0
        cnt::Real = 0.0
        sx::Real = 0.0
        sy::Real = 0.0
        cx::Real = 0.0
        cy::Real = 0.0
    end
    @discrete Ts = 20e-3 begin
        if tm >= t_from
            cnt = cnt + 1.0
            sct = sct + e_ct * e_ct
            szz = szz + e_z * e_z
            rms_ct = sqrt(sct / cnt)
            rms_z = sqrt(szz / cnt)
            x_max = max(x_max, x)
            x_min = min(x_min, x)
            y_max = max(y_max, y)
            y_min = min(y_min, y)
            sxn = ifelse(x > 0.0, 1.0, -1.0)
            syn = ifelse(y > 0.0, 1.0, -1.0)
            if sx != 0.0 && sxn != sx
                cx = cx + 1.0
            end
            if sy != 0.0 && syn != sy
                cy = cy + 1.0
            end
            sx = sxn
            sy = syn
            nx = cx
            ny = cy
            n_samples = cnt
        end
    end
end
