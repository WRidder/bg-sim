@block ExportOutput begin
    @inputs u::Real
    @variables sink::Real = 0.0, [description = "Held exported value, so the input is used in simulation"]
    @equations sink ~ u
end
