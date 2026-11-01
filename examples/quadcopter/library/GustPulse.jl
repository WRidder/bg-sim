@block GustPulse begin
    # A discrete gust on top of the turbulent wind: the "1 - cos" shape of the gust load standards,
    # g(t) = A/2 (1 - cos(2 pi (t - t0)/T)) for t0 < t < t0 + T, else 0, horizontal, blowing towards the
    # world heading `dir_deg` (0: +x, 90: +y). The shape is smooth in value and slope, so it needs no event.
    # A = 0 (the default) passes the wind through unchanged. Also gives the wind's speed and heading
    # (for the dashboard and the wind vane of the scene).
    @inputs u::Vec{3}
    @outputs begin
        y::Vec{3}
        g::Real, [unit = "m/s", description = "Gust speed"]
        speed::Real, [unit = "m/s", description = "Horizontal wind speed"]
        heading::Real, [unit = "rad", description = "Direction the wind blows towards (world, from +x)"]
    end
    @parameters begin
        A::Real = 0.0, [unit = "m/s", description = "Peak gust speed (0: off)"]
        dir_deg::Real = 0.0, [unit = "deg", description = "Direction the gust blows towards (world, from +x)"]
        t0::Real = 6.0, [unit = "s", description = "Start of the gust"]
        T::Real = 2.0, [unit = "s", min = 1.0e-3, description = "Duration of the gust"]
    end
    @equations begin
        g ~ ifelse(t > t0, ifelse(t < t0 + T, 0.5 * A * (1.0 - cos(6.283185307179586 * (t - t0) / T)), 0.0), 0.0)
        y[1] ~ u[1] + g * cos(0.017453292519943295 * dir_deg)
        y[2] ~ u[2] + g * sin(0.017453292519943295 * dir_deg)
        y[3] ~ u[3]
        speed ~ sqrt(y[1]^2 + y[2]^2 + 1.0e-12)
        heading ~ atan(y[2], y[1])
    end
end
