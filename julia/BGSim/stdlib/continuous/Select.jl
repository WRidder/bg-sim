@block Select begin
    # One element of a vector signal (for example a column of `CsvSource`) as a scalar.
    @constants begin
        N::Int = 2
        index::Int = 1
    end
    @inputs u::Vec{N}
    @outputs y::Real
    @equations y ~ u[index]
end
