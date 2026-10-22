@block Gain begin
    @inputs u::Real
    @outputs y::Real
    @parameters k::Real = 1.0, [description = "Gain"]
    @equations y ~ k * u
end
