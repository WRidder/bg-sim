@block TimeTable begin
    @constants N::Int = 8
    @outputs y::Real
    @parameters begin
        t_start::Real = 0.0, [unit = "s", description = "Time of the first table value"]
        sample_time::Real = 1.0, [unit = "s", min = 1.0e-12, description = "Spacing of the table samples"]
        values::Vec{N} = [0.0, 1.0, 0.0, 1.0, 0.0, 1.0, 0.0, 1.0], [description = "Output value at each sample"]
        method::Int = 1, [options = ["hold", "linear"], description = "Interpolation: 0 = hold, 1 = linear"]
    end
    @variables w::Vec{N}
    @equations begin
        for i in 1:N
            w[i] ~ ifelse(
                method == 0,
                ifelse(
                    floor(clamp((t - t_start) / sample_time, 0.0, N - 1.0)) == i - 1,
                    1.0,
                    0.0,
                ),
                max(
                    0.0,
                    1.0 - abs(
                        clamp((t - t_start) / sample_time, 0.0, N - 1.0) - (i - 1),
                    ),
                ),
            )
        end
        y ~ dot(w, values)
    end
end
