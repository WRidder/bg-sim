@block CsvSourceSampled begin
    # `CsvSource` on a clock (work package F5.1): the columns are sampled at every tick of
    # `sample_period` and held in between, so a CSV drives discrete controllers
    # deterministically and the output is a discrete partition like any other sampled block.
    # The data settings are the same node `constants` as for `CsvSource` (see there); the
    # tick at time `t_k` outputs the table value at `t_k`.
    @constants begin
        N::Int = 1
        table::Int = 0
        sample_period::Real = 1.0e-3, [unit = "s", min = 1.0e-12, description = "Sample period of the clock"]
    end
    @outputs y::Vec{N}
    @discrete Ts = sample_period begin
        for i in 1:N
            y[i] = csv_value(table, i, t)
        end
    end
end
