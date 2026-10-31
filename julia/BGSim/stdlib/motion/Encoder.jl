@block Encoder begin
    # Incremental rotary encoder read by a counter on a clock: at every tick the shaft angle
    # u is converted to whole counts, counts = floor(u*cpr/(2*pi)) with cpr the counts per
    # revolution after decoding (4x the line count of a quadrature encoder), and held until
    # the next tick. `y` is the angle those counts stand for, counts*2*pi/cpr: the angle
    # quantized down to the encoder resolution. Zero counts is angle 0; negative angles give
    # negative counts. `index` is the once-per-revolution index (zero) pulse: true while the
    # count is a whole multiple of cpr, i.e. during the first count of every revolution.
    @constants sample_period::Real = 1.0e-3, [unit = "s", min = 1.0e-12, description = "Sample period of the clock"]
    @inputs u::Real, [unit = "rad", description = "Shaft angle"]
    @outputs begin
        counts::Real = 0.0, [description = "Counter value: whole counts since angle 0 (a whole number)"]
        y::Real = 0.0, [unit = "rad", description = "Measured angle: counts*2*pi/cpr"]
        index::Bool = false, [description = "Index pulse: true during the first count of every revolution"]
    end
    @parameters cpr::Int = 4096, [min = 1, description = "Counts per revolution (after quadrature decoding)"]
    @discrete Ts = sample_period begin
        n = floor(u * cpr / 6.283185307179586)
        counts = n
        y = n * 6.283185307179586 / cpr
        index = mod(n, cpr) == 0
    end
end
