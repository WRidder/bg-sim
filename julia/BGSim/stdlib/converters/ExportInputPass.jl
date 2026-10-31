@block ExportInputPass begin
    @inputs u::Real
    @outputs y::Real
    @parameters value::Real = 0.0, [description = "Start value of the exported input; in simulation the block passes u through"]
    @variables start_value::Real = 0.0, [description = "Held start value, so the parameter is part of the system"]
    @equations begin
        y ~ u
        start_value ~ value
    end
end
