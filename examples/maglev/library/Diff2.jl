@block Diff2 begin
    # y = u1 - u2 (the gap difference between the nonlinear and the frozen linear loop).
    @inputs begin
        u1::Real, [unit = "m"]
        u2::Real, [unit = "m"]
    end
    @outputs y::Real, [unit = "m"]
    @equations y ~ u1 - u2
end
