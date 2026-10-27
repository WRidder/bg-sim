@block SRFlipFlop begin
    @constants sample_period::Real = 1.0e-3, [unit = "s", min = 1.0e-12, description = "Sample period of the clock"]
    @inputs begin
        set::Bool, [description = "Sets the output while high"]
        reset::Bool, [description = "Resets the output while high"]
    end
    @outputs q::Bool = false, [description = "Latch state; the start value is the initial state"]
    @parameters dominant::Int = 0, [options = ["set", "reset"], description = "Which input wins when both are high"]
    @discrete Ts = sample_period begin
        if set
            if reset
                q = dominant == 0
            else
                q = true
            end
        else
            if reset
                q = false
            end
        end
    end
end
