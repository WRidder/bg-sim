@block MultiportSwitch begin
    # y = u[k]: the control input selects one of the N data inputs (Simulink's Multiport
    # Switch, one-based). k is `index` rounded to the nearest integer, halves up, and clamped
    # to 1..N: index 2.4 selects u[2], 2.5 selects u[3], 0 selects u[1]. Each switch at a
    # half-integer of index is an exact event. Feed the data inputs through a Mux.
    # s[i] is the selected input among u[1..i], so s[N] is the output.
    @constants N::Int = 3, [min = 1, description = "Number of data inputs"]
    @inputs begin
        index::Real, [description = "Selects u[index], one-based"]
        u::Vec{N}, [description = "Data inputs"]
    end
    @outputs y::Real
    @variables s::Vec{N}, [description = "s[i]: the input selected among u[1] to u[i]"]
    @equations begin
        s[1] ~ u[1]
        for i in 2:N
            s[i] ~ ifelse(index >= i - 0.5, u[i], s[i - 1])
        end
        y ~ s[N]
    end
end
