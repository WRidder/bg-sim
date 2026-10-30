@block AngleError begin
    # Joint angle of the bond-graph arm against the angle column of the CSV file.
    # `offset` is the initial joint angle when the joint output excludes it.
    @inputs begin
        q::Real, [unit = "rad", description = "Joint angle of the model"]
        ref::Real, [unit = "rad", description = "Joint angle of the CSV file"]
    end
    @outputs e::Real, [unit = "rad", description = "q + offset - ref"]
    @parameters offset::Real = 0.0, [unit = "rad", description = "Added to q"]
    @equations e ~ q + offset - ref
end
