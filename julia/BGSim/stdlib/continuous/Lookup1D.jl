@block Lookup1D begin
    @constants N::Int = 3
    @inputs u::Real
    @outputs y::Real
    @parameters begin
        x::Vec{N} = [0.0, 1.0, 2.0], [description = "Breakpoints, strictly increasing"]
        table::Vec{N} = [0.0, 1.0, 4.0], [description = "Value at every breakpoint"]
    end
    @equations y ~ interp1(u, x, table)
end
