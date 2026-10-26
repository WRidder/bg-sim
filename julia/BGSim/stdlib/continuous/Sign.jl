@block Sign begin
    @inputs u::Real
    @outputs y::Real
    @equations y ~ sign(u)
end
