@block ADC begin
    # Analog-to-digital converter: at every tick the input is clipped to [u_min, u_max] and
    # rounded to the nearest of the 2^bits levels u_min + code*lsb, lsb = (u_max - u_min)/
    # (2^bits - 1), so both ends of the range are exact levels; the code and the level are
    # held until the next tick. Ties round away from zero (the language's `round`).
    @constants sample_period::Real = 1.0e-3, [unit = "s", min = 1.0e-12, description = "Sample period of the clock"]
    @inputs u::Real, [description = "Analog input"]
    @outputs begin
        y::Real = 0.0, [description = "Quantized value: u_min + code*lsb, held between ticks"]
        code::Real = 0.0, [description = "Digital code, a whole number 0 .. 2^bits - 1"]
    end
    @parameters begin
        bits::Int = 12, [min = 1, max = 52, description = "Resolution in bits"]
        u_min::Real = -10.0, [description = "Input at code 0; lower inputs clip"]
        u_max::Real = 10.0, [description = "Input at the largest code; higher inputs clip"]
    end
    @discrete Ts = sample_period begin
        top = 2.0^bits - 1.0
        lsb = (u_max - u_min) / top
        n = min(max(round((u - u_min) / lsb), 0.0), top)
        code = n
        y = u_min + n * lsb
    end
end
