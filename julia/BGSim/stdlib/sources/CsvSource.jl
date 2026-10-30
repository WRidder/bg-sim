@block CsvSource begin
    # Columns of a project CSV file as continuous signals (work package F5.1).
    #
    # The file is *not* unrolled into equations (unlike `TimeTable`): the compiler reads it
    # while it instantiates the node and registers the parsed table; the equation below calls
    # the intrinsic `csv_value(table, k, t)`, an opaque function that binary-searches the data
    # at run time and has registered time derivatives (so ModelingToolkit can differentiate a
    # CSV signal, e.g. a velocity that prescribes an inertia in derivative causality).
    #
    # The data settings are entries of the node's `constants`, consumed by the compiler:
    #   file          project-relative path, e.g. "data/trajectory.csv" (required)
    #   time_column   header name of the time column (default: the first column)
    #   columns       comma separated header names of the outputs (default: every other column)
    #   method        0 hold, 1 linear, 2 cubic (default; a C2 not-a-knot spline)
    #   extrapolation 0 hold the end values (default), 1 error past the data
    #   time_offset   seconds added to the file's time column (default 0)
    #   scale         factor applied to every value (default 1)
    # The two constants declared here are filled in by the compiler from those settings:
    # `N` is the number of selected columns (the size of `y`) and `table` the id of the loaded
    # table, a hash of the file content and the settings, so editing the file recompiles.
    @constants begin
        N::Int = 1
        table::Int = 0
    end
    @outputs y::Vec{N}
    @equations begin
        for i in 1:N
            y[i] ~ csv_value(table, i, t)
        end
    end
end
