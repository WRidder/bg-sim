@block GustEOG begin
    # The extreme operating gust of IEC 61400-1 (ed. 3, 6.3.2.2) as a wind-speed increment
    # (signal only): a dip of 0.27 v_gust, a rise of 0.74 v_gust above the mean and a second
    # dip, over T seconds from t0,
    #
    #   dv(t) = -0.37 v_gust sin(3 pi s / T) (1 - cos(2 pi s / T)),  s = t - t0 in [0, T]
    #
    # and 0 outside. Add it to the mean wind with a stdlib Sum.
    @outputs dv::Real, [unit = "m/s", description = "Gust increment"]
    @parameters begin
        t0::Real = 20.0, [unit = "s", description = "Start of the gust"]
        v_gust::Real = 5.6, [unit = "m/s", min = 0, description = "Gust magnitude V_gust (dip to peak: 1.01 V_gust)"]
        T::Real = 10.5, [unit = "s", min = 1.0e-3, description = "Gust duration (10.5 s in IEC 61400-1)"]
    end
    @variables s::Real = 0.0, [unit = "s"]
    @equations begin
        s ~ clamp(t - t0, 0.0, T)
        dv ~ -0.37 * v_gust * sin(3.0 * 3.141592653589793 * s / T) * (1.0 - cos(2.0 * 3.141592653589793 * s / T))
    end
end
