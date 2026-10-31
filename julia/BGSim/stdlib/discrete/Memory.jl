@block Memory begin
    # The input value from the previous tick (Simulink's Memory on a fixed clock): at each
    # tick the output becomes previous(u), the value u had before this tick, and holds until
    # the next one; `initial` at the first tick. For an input on the same clock the values are
    # those of UnitDelay, but the input is read through previous(), so the block does not depend
    # on its upstream block at the same tick: it breaks a cycle between discrete blocks (E105),
    # as Simulink's Memory breaks an algebraic loop. For a held (discrete) input previous(u) is
    # its value just before this tick (an input on a faster clock: its latest value before it);
    # for a continuous input it is the value at the model's previous tick of any clock.
    @constants sample_period::Real = 1.0e-3, [unit = "s", min = 1.0e-12, description = "Sample period of the clock"]
    @inputs u::Real
    @outputs y::Real = 0.0, [description = "Input value before this tick, or initial at the first tick"]
    @parameters initial::Real = 0.0, [tunable = true, description = "Output value at the first tick (the state before it)"]
    @variables started::Int = 0, [description = "0 before the first tick, 1 afterwards"]
    @discrete Ts = sample_period begin
        y = ifelse(started == 0, initial, previous(u))
        started = 1
    end
end
