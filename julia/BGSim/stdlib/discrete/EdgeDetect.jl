@block EdgeDetect begin
    @constants sample_period::Real = 1.0e-3, [unit = "s", min = 1.0e-12, description = "Sample period of the clock"]
    @inputs u::Bool, [description = "Signal whose edges are detected"]
    @outputs y::Bool = false, [description = "True on a tick where the selected edge is present"]
    @parameters mode::Int = 0, [options = ["rising", "falling", "both"], description = "Which edges are reported"]
    @variables up::Bool = false, [description = "Input sample from the previous tick"]
    @discrete Ts = sample_period begin
        if mode == 0
            y = ifelse(u, !up, false)
        elseif mode == 1
            y = ifelse(u, false, up)
        else
            y = u != up
        end
        up = u
    end
end
