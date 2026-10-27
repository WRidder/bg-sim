@block ExportParameter begin
    @parameters value::Real = 0.0, [tunable = true, description = "Tunable parameter the export publishes"]
    @variables sink::Real = 0.0, [description = "Held parameter value, so the marker is part of the system"]
    @equations sink ~ value
end
