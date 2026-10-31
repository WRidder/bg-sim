@block Rounding begin
    # Rounds the input to an integer value (Simulink's Rounding Function): floor (towards
    # -Inf), ceil (towards +Inf), round (to the nearest, halves away from zero) or fix
    # (towards zero). The output jumps at the integer (or half-integer) crossings; each jump
    # is an exact event.
    @inputs u::Real
    @outputs y::Real
    @parameters mode::Int = 2, [options = ["floor", "ceil", "round", "fix"], description = "Rounding: 0 floor, 1 ceil, 2 round (halves away from zero), 3 fix (towards zero)"]
    @equations begin
        y ~ ifelse(
            mode == 0,
            floor(u),
            ifelse(mode == 1, ceil(u), ifelse(mode == 2, round(u), ifelse(u >= 0.0, floor(u), ceil(u)))),
        )
    end
end
