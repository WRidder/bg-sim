@block Diff2 begin
    # y = u1 - u2: the scalar error used by the voltage loop.
    @inputs begin
        u1::Real
        u2::Real
    end
    @outputs y::Real
    @equations y ~ u1 - u2
end
