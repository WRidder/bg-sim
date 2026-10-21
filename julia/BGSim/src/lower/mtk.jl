"""
    mtk_variable(name::AbstractString) -> Num

Create a ModelingToolkit unknown `name(t)` from a string, for example
`mtk_variable("motor.omega")`.

This is the documented equivalent of `only(@variables \$(Symbol(name))(t))`. It is how the
lowering stage (plan section 5.8) turns a bg-sim signal ID into a symbolic variable; the
caller keeps the `Dict{String, Num}` from signal ID to variable and never parses MTK's
generated names.

The name is used verbatim, so a bg-sim signal ID such as `"motor.omega"` survives the
round trip (verified: it prints as `var"motor.omega"(t)` and `signal_name` gives it back).
Two calls with the same string produce the same symbolic variable (`isequal` is `true`).

Note: symbolic variables must never be compared with `==`; in Symbolics `==` builds an
`Equation`. Use `isequal`.
"""
function mtk_variable(name::AbstractString)::Num
    isempty(name) &&
        throw(ArgumentError("a signal name must not be empty"))
    sym = Symbol(name)
    return only(@variables $(sym)(t))
end

"""
    mtk_parameter(name::AbstractString) -> Num

Create a ModelingToolkit parameter from a string, for example `mtk_parameter("motor.R")`.

Parameters are time independent (`@parameters`), so they are not called with `t`. Every
bg-sim parameter stays a runtime MTK parameter (plan decision D4), which is what makes a
parameter-only re-run possible through `remake` (see `julia/BGSim/NOTES.md`).
"""
function mtk_parameter(name::AbstractString)::Num
    isempty(name) &&
        throw(ArgumentError("a parameter name must not be empty"))
    sym = Symbol(name)
    return only(@parameters $(sym))
end

"""
    mtk_discrete(name::AbstractString) -> Num

Create a ModelingToolkit discrete variable from a string, for example
`mtk_discrete("motor.mode")`.

This is the documented equivalent of `only(@discretes \$(Symbol(name))(t))`. A discrete is a
*time-dependent parameter* (`isparameter` is `true`), which is what events are allowed to
write to: it must be passed in the parameter list of the `System`, not in the unknown list,
and an affect that writes it must list it in the callback's `discrete_parameters`.
"""
function mtk_discrete(name::AbstractString)::Num
    isempty(name) &&
        throw(ArgumentError("a discrete name must not be empty"))
    sym = Symbol(name)
    return only(@discretes $(sym)(t))
end

"""
    signal_name(x) -> String

Return the plain name of a symbolic variable, parameter or observed quantity as a
`String`, for example `signal_name(mtk_variable("motor.omega")) == "motor.omega"`.

This is the inverse of [`mtk_variable`](@ref)/[`mtk_parameter`](@ref) and is what the
recorder uses to map an MTK quantity back to a bg-sim signal ID. It never parses a
generated name: it reads the `VariableSource` metadata through
`SymbolicIndexingInterface.getname`.
"""
signal_name(x) = String(getname(x))
