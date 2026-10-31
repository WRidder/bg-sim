@block WrapToPi begin
    # An angle wrapped into (-pi, pi]: y = u - 2*pi*k with the integer k that puts y in the
    # interval, k = ceil((u - pi) / (2*pi)), so pi stays pi and -pi becomes pi (MATLAB's
    # wrapToPi). The output jumps by 2*pi when u crosses an odd multiple of pi; each jump is
    # an exact event. Unwrap a continuous angle by integrating its rate instead.
    @inputs u::Real, [unit = "rad"]
    @outputs y::Real, [unit = "rad"]
    @equations begin
        y ~ u - 6.283185307179586 * ceil((u - 3.141592653589793) / 6.283185307179586)
    end
end
