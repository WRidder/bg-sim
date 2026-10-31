@block DAC begin
    # Digital-to-analog converter with a zero-order hold: at every tick the input becomes
    # one of the 2^bits levels y_min + code*lsb, lsb = (y_max - y_min)/(2^bits - 1), held
    # until the next tick. With input = 0 (value) the input is a value in output units,
    # clipped to [y_min, y_max] and rounded to the nearest level; with input = 1 (code) it
    # is the code itself, rounded to a whole number and clipped to 0 .. 2^bits - 1 (the
    # inverse of the ADC). Ties round away from zero (the language's `round`).
    @constants sample_period::Real = 1.0e-3, [unit = "s", min = 1.0e-12, description = "Sample period of the clock"]
    @inputs u::Real, [description = "Value to convert (input = value) or code (input = code)"]
    @outputs y::Real = 0.0, [description = "Analog output, held between ticks"]
    @parameters begin
        bits::Int = 12, [min = 1, max = 52, description = "Resolution in bits"]
        y_min::Real = -10.0, [description = "Output at code 0"]
        y_max::Real = 10.0, [description = "Output at the largest code"]
        input::Int = 0, [options = ["value", "code"], description = "Meaning of the input: 0 = a value, quantized to the nearest level; 1 = the code"]
    end
    @discrete Ts = sample_period begin
        top = 2.0^bits - 1.0
        lsb = (y_max - y_min) / top
        if input == 1
            n = min(max(round(u), 0.0), top)
        else
            n = min(max(round((u - y_min) / lsb), 0.0), top)
        end
        y = y_min + n * lsb
    end
end
