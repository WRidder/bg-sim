@block Constant begin
    @outputs y::Real
    @parameters value::Real = 1.0, [description = "Output value"]
    @equations y ~ value
end
