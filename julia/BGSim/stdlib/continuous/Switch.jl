@block Switch begin
    @inputs begin
        u1::Real
        u2::Real
        ctrl::Real
    end
    @outputs y::Real
    @parameters threshold::Real = 0.0, [tunable = true, description = "Control threshold"]
    @equations y ~ ifelse(ctrl > threshold, u1, u2)
end
