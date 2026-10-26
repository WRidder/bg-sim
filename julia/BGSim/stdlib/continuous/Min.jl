@block Min begin
    @inputs begin
        u1::Real
        u2::Real
    end
    @outputs y::Real
    @equations y ~ min(u1, u2)
end
