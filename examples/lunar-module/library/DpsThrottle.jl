@block DpsThrottle begin
    # The descent engine's throttle logic (TN D-6846). The engine lights at the trim setting (10 %
    # of the rated thrust) for `t_trim` seconds while the gimbal trims through the centre of
    # mass, then goes to the fixed throttle position (FTP, about 94 %). It stays there while
    # the guidance asks for more than the throttleable range; once the request falls below
    # `recover` (57 %, the 60 % limit with a 3 % low bias) the engine is throttled as commanded
    # between `lo` and `hi` (10 .. 60 %) for the rest of the descent ("throttle recovery", a
    # latched event). It shuts down for good when a footpad touches the surface (`h_pad`
    # crosses zero: Armstrong kept the engine running until touchdown) or when the usable
    # propellant is gone.
    @inputs begin
        T_req::Real, [unit = "N", description = "Thrust the guidance asks for"]
        h_pad::Real, [unit = "m", description = "Height of the lowest footpad above the surface"]
        prop::Real, [unit = "kg", description = "Usable propellant left"]
    end
    @parameters begin
        T_rated::Real = 46706.0, [unit = "N", description = "Rated thrust (100 %)"]
        T_ftp::Real = 43904.0, [unit = "N", description = "Thrust at the fixed throttle position"]
        lo::Real = 0.1, [description = "Lower end of the throttleable range (fraction of rated)"]
        hi::Real = 0.6, [description = "Upper end of the throttleable range"]
        recover::Real = 0.57, [description = "Request below which the engine leaves FTP"]
        t_trim::Real = 26.0, [unit = "s", description = "Time at trim throttle after ignition"]
        prop_eps::Real = 0.0, [unit = "kg", description = "Shutdown when prop falls below this"]
    end
    @variables begin
        ftp::Real = 1.0, [description = "1 while at the fixed throttle position (latched)"]
        off::Real = 0.0, [description = "1 once the engine is shut down (latched)"]
        zr::Real, [unit = "N", description = "Throttle-recovery guard (after trim)"]
        ztd::Real, [unit = "m", description = "Touchdown guard: footpad below the surface"]
        zfuel::Real, [unit = "kg", description = "Depletion guard"]
    end
    @outputs begin
        T_cmd::Real, [unit = "N"]
        throttle::Real, [description = "Commanded thrust as a fraction of rated"]
    end
    @equations begin
        ddt(ftp) ~ 0.0
        ddt(off) ~ 0.0
        zr ~ ifelse(t > t_trim, ifelse(ftp > 0.5, recover * T_rated - T_req, -T_rated), -T_rated)
        ztd ~ ifelse(off > 0.5, -1.0, -h_pad)
        zfuel ~ ifelse(off > 0.5, -1.0, prop_eps - prop)
        T_cmd ~ (1 - off) * ifelse(t < t_trim, lo * T_rated, ifelse(ftp > 0.5, T_ftp, clamp(T_req, lo * T_rated, hi * T_rated)))
        throttle ~ T_cmd / T_rated
    end
    @events begin
        zr > 0 => begin
            reinit(ftp, 0.0)
        end
        ztd > 0 => begin
            reinit(off, 1.0)
        end
        zfuel > 0 => begin
            reinit(off, 1.0)
        end
    end
end
