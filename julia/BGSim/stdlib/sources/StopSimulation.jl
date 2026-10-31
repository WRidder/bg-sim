@block StopSimulation begin
    # Ends the run when the input rises above threshold (Simulink's Stop Simulation). The
    # crossing is an exact event: the simulation stops at that instant with status "done"
    # and a W217 warning that names the block and the time; an input already above threshold
    # at the start stops the run at once. The block is recognised by its library reference,
    # so a copy of it is an ordinary block that never stops a run.
    #
    # In the exported C code the condition is checked after every internal step: bg_step
    # returns BG_STEP_STOP, and fmi2DoStep returns fmi2Discard with fmi2Terminated set in
    # fmi2GetBooleanStatus, so a co-simulation master ends the run (up to one dt late).
    #
    # Note: the latch is a state that only its event changes. A state whose derivative is
    # identically zero is removed by the symbolic reduction, so it carries a decay of 1e-300
    # per second, which leaves 1.0 unchanged in double precision.
    @inputs u::Real
    @parameters threshold::Real = 0.5, [description = "The run stops when u rises above this value"]
    @variables begin
        stopped::Real = 0.0, [description = "1 once u has risen above threshold (set by the event)"]
        z::Real, [description = "u - threshold: the run stops when it is positive"]
    end
    @equations begin
        ddt(stopped) ~ -1.0e-300 * stopped   # held (see the note above)
        z ~ u - threshold
    end
    @events begin
        u > threshold => begin
            reinit(stopped, 1.0)
        end
    end
end
