@block ExportInput begin
    @outputs y::Real
    @parameters value::Real = 0.0, [description = "Value the exported input supplies in simulation"]
    @equations y ~ value
end
