@block Max begin
    @inputs begin
        u1::Real
        u2::Real
    end
    @outputs y::Real
    @equations y ~ max(u1, u2)
end
