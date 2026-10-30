@block AirMass begin
    # The air: a constant world-frame wind velocity (m/s, z up), used by the aerodynamic blocks. Zero
    # for the nominal runs; the `wind` parameter is the knob for disturbance experiments.
    @outputs w::Vec{3}
    @parameters wind::Vec{3} = [0.0, 0.0, 0.0], [unit = "m/s", description = "Wind velocity in the world frame"]
    @equations begin
        w[1] ~ wind[1]
        w[2] ~ wind[2]
        w[3] ~ wind[3]
    end
end
