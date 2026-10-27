@block TimeTable begin
    # A uniformly sampled table with a hold or linear output (plan section 8, M2 row).
    #
    # Every switching condition is written **in `t`** (`t >= t_start + k*sample_time` and
    # `clamp(t - (t_start + k*sample_time), 0, sample_time)`), not as a normalised table
    # coordinate `(t - t_start)/sample_time - k`. That is the fix for plan/STATUS.md NOTE-6:
    # the normalised form has no representable Float64 root when a sample instant lands on
    # an output-grid time (0.07/0.01 is 6.999999999999999, not 7), so the condition-only
    # callback could never consume its crossing and the solver re-fired at every step until
    # W206. The `t` form puts the root at the sampled instants themselves, where the
    # condition is exactly zero and the callback machinery's zero-sign guard advances it.
    #
    # Only sign-changing kinks are used: no `floor` staircase and no `max(0, 1-|...|)`
    # tangent, whose zero sets also confuse root finding. Hold is a difference of `t`
    # comparisons; linear is a difference of saturating ramps `clamp(t-a, 0, Ts)/Ts`, i.e.
    # a tent basis. The hold/linear choice is the weighted sum `(1-method)*hold +
    # method*linear`, so `method == 0` never becomes a parameter-only ifelse condition.
    @constants N::Int = 8
    @outputs y::Real
    @parameters begin
        t_start::Real = 0.0, [unit = "s", description = "Time of the first table value"]
        sample_time::Real = 1.0, [unit = "s", min = 1.0e-12, description = "Spacing of the table samples"]
        values::Vec{N} = [0.0, 1.0, 0.0, 1.0, 0.0, 1.0, 0.0, 1.0], [description = "Output value at each sample"]
        method::Int = 1, [options = ["hold", "linear"], description = "Interpolation: 0 = hold, 1 = linear"]
    end
    @variables w::Vec{N}
    @equations begin
        for i in 1:N
            w[i] ~ (1 - method) * (
                ifelse(t >= t_start + (i - 1) * sample_time, 1.0, 0.0) -
                ifelse(t >= t_start + i * sample_time, 1.0, 0.0)
            ) + method * (
                clamp(t - (t_start + (i - 2) * sample_time), 0.0, sample_time) / sample_time -
                clamp(t - (t_start + (i - 1) * sample_time), 0.0, sample_time) / sample_time
            )
        end
        y ~ ifelse(
            t < t_start,
            values[1],
            ifelse(t > t_start + (N - 1) * sample_time, values[N], dot(w, values)),
        )
    end
end
