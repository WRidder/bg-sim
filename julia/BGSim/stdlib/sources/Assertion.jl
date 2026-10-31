@block Assertion begin
    # Fails the run when its condition no longer holds (Simulink's Assertion). The condition
    # holds while the input is at least threshold (a Bool-like 1/0 signal with the default
    # 0.5); the moment it falls below is an exact event, and the run stops there with status
    # "failed" and an E902 error that names the block and the time. Name the block after
    # what it checks: its path is the message. An input already below threshold at the start
    # fails the run at once. The block is recognised by its library reference, so a copy of
    # it is an ordinary block that never fails a run.
    #
    # In the exported C code the condition is checked after every internal step: bg_step
    # returns BG_STEP_ASSERT, and fmi2DoStep logs the block path and returns fmi2Error.
    @inputs u::Real
    @parameters threshold::Real = 0.5, [description = "The condition holds while u is at least this value"]
    @variables begin
        failed::Real = 0.0, [description = "1 once u has fallen below threshold (set by the event)"]
        z::Real, [description = "threshold - u: the assertion fails when it is positive"]
    end
    @equations begin
        ddt(failed) ~ 0.0   # held: only the event changes it
        z ~ threshold - u
    end
    @events begin
        u < threshold => begin
            reinit(failed, 1.0)
        end
    end
end
