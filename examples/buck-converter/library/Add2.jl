@block Add2 begin
    # y = u1 + u2: the scalar two-input sum used by the JSON signal graph.
    @inputs begin
        u1::Real
        u2::Real
    end
    @outputs y::Real
    @equations y ~ u1 + u2
end
