@block Add2 begin
    # y = u1 + u2 (the IR sensor adds its noise voltage to the ideal reading).
    @inputs begin
        u1::Real
        u2::Real
    end
    @outputs y::Real
    @equations y ~ u1 + u2
end
