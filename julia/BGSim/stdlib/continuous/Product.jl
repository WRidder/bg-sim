@block Product begin
    @inputs begin
        u1::Real
        u2::Real
    end
    @outputs y::Real
    @equations y ~ u1 * u2
end
