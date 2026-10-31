@block LimitSwitch begin
    # An end-of-travel switch wired into the drive enable (not through the controller
    # software): when the cart position x rises past x_limit, an event latches `tripped`
    # to 1 and the force passed on to the drive drops to zero for the rest of the run.
    @parameters begin
        x_limit::Real = 1.2, [description = "Switch position (m)"]
        leak::Real = 0.0, [min = 0, description = "Latch leak rate (0 holds the latch exactly, as in stdlib Relay)"]
    end
    @inputs begin
        x::Real
        F_cmd::Real
    end
    @outputs begin
        F::Real = 0.0
        tripped::Real = 0.0
    end
    @variables latch::Real = 0.0, [description = "1 after the switch has tripped"]
    @equations begin
        ddt(latch) ~ -leak * latch
        tripped ~ latch
        F ~ (1.0 - latch) * F_cmd
    end
    @events begin
        x > x_limit => begin
            reinit(latch, 1.0)
        end
    end
end
