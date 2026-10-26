@block Lookup2D begin
    @constants N::Int = 3
    @inputs begin
        u::Real
        v::Real
    end
    @outputs y::Real
    @parameters begin
        breaks::Mat{2,N} = [0.0 1.0 2.0; 0.0 1.0 2.0], [description = "Row 1: x breakpoints; row 2: y breakpoints"]
        table::Mat{N,N} = [0.0 1.0 2.0; 1.0 2.0 3.0; 2.0 3.0 4.0], [description = "Value at (x = breaks[1,j], y = breaks[2,i]) in row i, column j"]
    end
    @equations y ~ interp2(u, v, breaks, table)
end
