# C/FMU export (plan/EXPORT_PLAN.md, work package J-EX1).
#
# `export_model(flat, out_dir; settings)` turns a flattened model into
#
#   <out_dir>/sources/model.h, model.c    generated: derivatives, Jacobian, frozen switching
#                                         conditions, outputs, discrete partitions, constants
#   <out_dir>/sources/<runtime files>     hand-written, versioned (julia/BGSim/export/runtime)
#   <out_dir>/modelDescription.xml        FMI 2.0 Co-Simulation
#   <out_dir>/export.json                 the export report (interface, step choice, W203)
#
# Compiling and zipping the FMU is the backend's job (backend/src/bgsim_server/fmu_build.py);
# this module never calls a C compiler.
#
# The interface is what the user declares (D-EX9), never "the whole model":
#
#   ExportInput      its `value` parameter becomes an FMU input (constant source in simulation)
#   ExportOutput     the signal wired to its input `u` becomes an FMU output
#   ExportParameter  its `value` becomes a tunable FMU parameter
#   tunable = true   any parameter declared tunable is a tunable FMU parameter too
#
# Every other parameter is folded into a literal (D-EX10, `fold_parameters`). The debug option
# `expose_all` publishes every recorded signal as a read-only `local` variable; it is what the
# example harness uses to compare the computation with simulation, and it does not change the
# interface.
#
# Phase A scope: ODE systems (identity mass matrix), Euler/RK4 (ROS2 on request), frozen
# switching conditions with W203, multi-rate `@discrete`, start values computed at export.
# Everything else is refused with E110/E111 naming the construct.

module Export

using ..BGSim
import ..BGSim: Flat, Compile, IR, Diagnostic, diag, sort_diagnostics, LowerError
using ModelingToolkit
using SymbolicIndexingInterface: getname, getu, getp
import Symbolics
const SymbolicUtils = Symbolics.SymbolicUtils
import JSON3
import SHA
using OrdinaryDiffEqTsit5: Tsit5

const MTK = ModelingToolkit

"""The hand-written C runtime copied into every export; bump `RUNTIME_VERSION` on any change."""
const RUNTIME_DIR = normpath(joinpath(@__DIR__, "..", "..", "export", "runtime"))
const RUNTIME_VERSION = "0.1.0"
const RUNTIME_FILES = ["bg_runtime.h", "bg_solver.c", "fmi2_cs.c",
    "fmi2Functions.h", "fmi2FunctionTypes.h", "fmi2TypesPlatform.h"]

const MARKER_INPUT = "stdlib:converters/ExportInput"
const MARKER_OUTPUT = "stdlib:converters/ExportOutput"
const MARKER_PARAMETER = "stdlib:converters/ExportParameter"

include("emit_c.jl")
include("emit_discrete.jl")
include("analysis.jl")
include("fmi2.jl")

"""
    ExportSettings(; kwargs...)

| field | default | meaning |
| --- | --- | --- |
| `step` | `1e-3` | communication step (FMI `DefaultExperiment/stepSize`); `doStep` sizes are multiples of `dt` |
| `dt` | `nothing` | internal step in seconds; `nothing` chooses it from the spectrum (D-EX7) |
| `method` | `:auto` | `:auto` (RK4 in phase A), `:euler`, `:rk4`, `:ros2` |
| `t_end` | `1.0` | `DefaultExperiment/stopTime` and the start-value horizon |
| `margin` | `0.5` | fraction of the stability bound the step may use |
| `accuracy` | `0.3` | largest `h·|λ|` allowed for any eigenvalue |
| `max_substeps` | `1000` | above this W207 is reported |
| `fold_parameters` | `true` | fold non-tunable parameters into literals |
| `expose_all` | `false` | publish every recorded signal as a `local` variable |
"""
Base.@kwdef struct ExportSettings
    step::Float64 = 1.0e-3
    dt::Union{Nothing,Float64} = nothing
    method::Symbol = :auto
    t_end::Float64 = 1.0
    margin::Float64 = 0.5
    accuracy::Float64 = 0.3
    max_substeps::Int = 1000
    fold_parameters::Bool = true
    expose_all::Bool = false
end

function ExportSettings(d::AbstractDict)
    get_(k, default) = haskey(d, k) ? d[k] : haskey(d, Symbol(k)) ? d[Symbol(k)] : default
    dt = get_("dt", nothing)
    return ExportSettings(
        step = Float64(get_("step", 1.0e-3)),
        dt = dt === nothing ? nothing : Float64(dt),
        method = Symbol(lowercase(String(get_("method", "auto")))),
        t_end = Float64(get_("t_end", 1.0)),
        margin = Float64(get_("margin", 0.5)),
        accuracy = Float64(get_("accuracy", 0.3)),
        max_substeps = Int(get_("max_substeps", 1000)),
        fold_parameters = Bool(get_("fold_parameters", true)),
        expose_all = Bool(get_("expose_all", false)),
    )
end

"""    ExportResult(ok, diagnostics, dir, report)

`ok` is false when an error diagnostic stopped the export (no sources are written then).
`report` is the content of `export.json`."""
struct ExportResult
    ok::Bool
    diagnostics::Vector{Diagnostic}
    dir::String
    report::Dict{String,Any}
end

"""One variable of the exported interface."""
struct ExportVar
    name::String          # the FMI name
    id::String            # the bg-sim signal or parameter id
    kind::Symbol          # :output, :local, :parameter, :input
    variability::String   # FMI variability
    start::Float64        # parameters and inputs
    expr::Any             # outputs and locals: the symbolic value
    lo::Float64           # parameters and inputs: the declared range (D-EX16)
    hi::Float64
end

ExportVar(name, id, kind, variability, start, expr) =
    ExportVar(name, id, kind, variability, start, expr, -Inf, Inf)

function _range(fp)
    fp === nothing && return (-Inf, Inf)
    lo = get(fp.attrs, :min, nothing)
    hi = get(fp.attrs, :max, nothing)
    return (lo isa Real ? Float64(lo) : -Inf, hi isa Real ? Float64(hi) : Inf)
end

c_identifier(name) = (s = replace(String(name), r"[^A-Za-z0-9_]" => "_");
    isempty(s) || isdigit(s[1]) ? "m_" * s : s)

_fail(diags, dir) = ExportResult(false, sort_diagnostics(diags), String(dir), Dict{String,Any}())

"""
    export_model(flat, out_dir; settings = ExportSettings(), reference_dir = nothing,
                 name = flat.name) -> ExportResult

Generate the C sources and the FMI 2.0 description of `flat` into `out_dir` (see the file
header). `reference_dir` is an optional run folder of the same model (`stream.f64` and
`manifest.json`); its trajectory widens the spectrum scan that chooses `dt`.
"""
function export_model(flat::Flat.FlatModel, out_dir::AbstractString;
    settings::ExportSettings = ExportSettings(), reference_dir = nothing,
    name::AbstractString = flat.name)
    diags = Diagnostic[]
    if any(d -> d.severity == "error", flat.diagnostics)
        return _fail(collect(Diagnostic, flat.diagnostics), out_dir)
    end
    settings.method in (:auto, :euler, :rk4, :ros2) ||
        return _fail([diag("E110", "unknown export method `$(settings.method)`";
            hint = "use auto, euler, rk4 or ros2")], out_dir)
    if !isempty(flat.events)
        return _fail([diag("E110", "`@events` with `reinit` are not exported yet (plan J-EX6)";
            hint = "the model has $(length(flat.events)) event(s)")], out_dir)
    end

    lowered = try
        BGSim.lower_model(flat; t_start = 0.0, t_end = max(settings.t_end, settings.step))
    catch err
        err isa LowerError || rethrow()
        return _fail([diag("E110", "the model uses a construct that is not exported yet";
            hint = sprint(showerror, err))], out_dir)
    end
    if lowered.model.algebraic
        return _fail([diag("E111",
            "the compiled system keeps algebraic equations (a mass-matrix DAE); Euler and RK4 cannot step it";
            hint = "DAE export arrives with the Rosenbrock integrator (plan J-EX3)")], out_dir)
    end
    integ = try
        MTK.SciMLBase.init(lowered.problem, Tsit5())
    catch err
        return _fail([diag("E111", "the initial values could not be computed for the export";
            hint = sprint(showerror, err))], out_dir)
    end

    try
        return _export(flat, lowered, integ, String(out_dir), settings, reference_dir,
            String(name), diags)
    catch err
        err isa ExportError || rethrow()
        return _fail(push!(diags, diag("E110", "the model uses a construct that is not exported yet";
            hint = err.message)), out_dir)
    end
end

function _export(flat, lowered, integ, out_dir, settings, reference_dir, name, diags)
    sys = lowered.model.system
    iv = Symbolics.unwrap(MTK.get_iv(sys))
    xs = Any[Symbolics.unwrap(x) for x in MTK.unknowns(sys)]
    nx = length(xs)
    x0 = Float64[getu(integ, x)(integ) for x in xs]
    names_x = String[String(getname(x)) for x in xs]

    has_disc = !isempty(flat.discrete)
    sched = has_disc ? BGSim.discrete_schedule(flat; t_start = 0.0,
        t_end = max(settings.t_end, settings.step)) : nothing
    held_ids = has_disc ? sched.held_ids : String[]

    # ---- the interface from the markers
    markers_in = String[i.path for i in flat.instances if i.ref == MARKER_INPUT]
    markers_out = String[i.path for i in flat.instances if i.ref == MARKER_OUTPUT]
    markers_par = String[i.path for i in flat.instances if i.ref == MARKER_PARAMETER]
    input_param = Dict(p * "/value" => p for p in markers_in)
    export_param = Dict(p * "/value" => p for p in markers_par)
    flat_params = Dict(p.id => p for p in flat.parameters)

    ps = Any[Symbolics.unwrap(p) for p in MTK.parameters(sys)]
    names_p = String[String(getname(p)) for p in ps]
    p0 = Float64[Float64(getp(integ, p)(integ)) for p in ps]

    env = Dict{Any,String}(iv => "t")
    for (i, x) in enumerate(xs)
        env[x] = "x[$(i - 1)]"
    end
    vars = ExportVar[]
    params = ExportVar[]
    inputs = ExportVar[]
    dvals = zeros(length(held_ids))
    folded = 0
    for (i, p) in enumerate(ps)
        id = names_p[i]
        k = findfirst(==(id), held_ids)
        if k !== nothing
            env[p] = "m->d[$(k - 1)]"
            dvals[k] = p0[i]
            continue
        end
        fp = get(flat_params, id, nothing)
        fp !== nothing && get(fp.attrs, :kind, nothing) === :discrete &&
            throw(ExportError("the held value `$id` is not written by any discrete partition"))
        if haskey(input_param, id)
            push!(inputs, ExportVar(input_param[id], id, :input, "continuous", p0[i], nothing,
                _range(fp)...))
            env[p] = "m->u[$(length(inputs) - 1)]"
        elseif haskey(export_param, id) || (fp !== nothing && get(fp.attrs, :tunable, false) === true)
            push!(params, ExportVar(get(export_param, id, id), id, :parameter, "tunable", p0[i],
                nothing, _range(fp)...))
            env[p] = "m->p[$(length(params) - 1)]"
        elseif settings.fold_parameters
            env[p] = clit(p0[i])
            folded += 1
        else
            push!(params, ExportVar(id, id, :parameter, "fixed", p0[i], nothing, _range(fp)...))
            env[p] = "m->p[$(length(params) - 1)]"
        end
    end

    obs_eqs = MTK.observed(sys)
    obs = (
        lhs = Any[Symbolics.unwrap(e.lhs) for e in obs_eqs],
        rhs = Any[Symbolics.unwrap(e.rhs) for e in obs_eqs],
        names = String[String(getname(e.lhs)) for e in obs_eqs],
        index = Dict{Any,Int}(),
    )
    for (k, l) in enumerate(obs.lhs)
        obs.index[l] = k
    end
    known = Dict{String,Any}()
    for (i, x) in enumerate(xs); known[names_x[i]] = x; end
    for (k, l) in enumerate(obs.lhs); known[obs.names[k]] = l; end
    for (i, p) in enumerate(ps); known[names_p[i]] = p; end

    taken = Set{String}(v.name for v in vcat(params, inputs))
    for path in markers_out
        sym = get(known, path * "/u", nothing)
        sym === nothing && throw(ExportError("the export output `$path` has no value in the compiled system"))
        push!(vars, ExportVar(path, path * "/u", :output,
            path * "/u" in held_ids ? "discrete" : "continuous", 0.0, sym))
        push!(taken, path)
    end
    if settings.expose_all
        for s in flat.signals
            id = String(s.id)
            (id in taken || haskey(input_param, id) || haskey(export_param, id)) && continue
            sym = get(known, id, nothing)
            sym === nothing && continue
            haskey(flat_params, id) && !(id in held_ids) && continue
            push!(vars, ExportVar(id, id, :local, id in held_ids ? "discrete" : "continuous", 0.0, sym))
            push!(taken, id)
        end
    end
    if isempty(markers_in) && isempty(markers_out)
        push!(diags, diag("W209", "the model has no ExportInput or ExportOutput markers, so the FMU has no inputs or outputs";
            hint = "place ExportInput blocks where the controller supplies a signal and ExportOutput blocks on the signals to publish"))
    end

    # ---- the continuous right-hand side and its Jacobian
    rhs = Vector{Any}(undef, nx)
    for e in MTK.equations(sys)
        lhs = Symbolics.unwrap(e.lhs)
        (SymbolicUtils.iscall(lhs) && SymbolicUtils.operation(lhs) isa Symbolics.Differential) ||
            throw(ExportError("the compiled system has a non-differential equation `$e`"))
        x = Symbolics.unwrap(SymbolicUtils.arguments(lhs)[1])
        rhs[findfirst(y -> isequal(y, x), xs)] = Symbolics.unwrap(e.rhs)
    end
    jac = nx == 0 ? Matrix{Any}(undef, 0, 0) : MTK.calculate_jacobian(sys)

    # ---- the step
    step_ns = round(Int64, settings.step * 1e9)
    abs(step_ns / 1e9 - settings.step) < 1e-15 * max(1.0, settings.step) && step_ns > 0 ||
        throw(ExportError("the communication step must be a positive whole number of nanoseconds"))
    base_ns = step_ns
    if has_disc
        for sp in sched.partitions
            base_ns = gcd(base_ns, sp.partition.period_ns)
            sp.partition.offset_ns > 0 && (base_ns = gcd(base_ns, sp.partition.offset_ns))
        end
    end
    method = settings.method === :auto ? :rk4 : settings.method
    jac_fn = _jacobian_function(jac, xs, ps, iv)
    # Runtime-settable values move the eigenvalues: scan their declared ranges too (D-EX16).
    # Only values the Jacobian depends on can move the integrator's eigenvalues; a gain that
    # only discrete code reads changes the closed loop, which simulation shows as well.
    in_jac = Set{String}()
    for e in jac
        for v in Symbolics.get_variables(Symbolics.unwrap(e))
            push!(in_jac, String(getname(v)))
        end
    end
    ranged = Tuple{Int,Float64,Float64}[]
    for v in vcat(params, inputs)
        v.variability == "fixed" && continue
        v.id in in_jac || continue
        k = findfirst(==(v.id), names_p)
        if isfinite(v.lo) && isfinite(v.hi)
            push!(ranged, (k, v.lo, v.hi))
        else
            isfinite(v.lo) && push!(ranged, (k, v.lo, v.lo))
            isfinite(v.hi) && push!(ranged, (k, v.hi, v.hi))
            push!(diags, diag("W210",
                "`$(v.name)` can change at runtime but has no complete range, so the step is only proven stable for the values scanned";
                hint = "declare min and max on `$(v.id)`; the FMU then refuses values outside them"))
        end
    end
    points = spectrum_scan(jac_fn, x0, p0, names_x, names_p, 0.0; reference_dir = reference_dir,
        ranges = ranged)
    analysis_method = method === :ros2 ? :rk4 : method
    choice = choose_step(analysis_method, points, base_ns; margin = settings.margin,
        accuracy = settings.accuracy, max_substeps = settings.max_substeps)
    dt_ns = if settings.dt === nothing
        method === :ros2 ? base_ns : choice.dt_ns
    else
        round(Int64, settings.dt * 1e9)
    end
    dt_ns > 0 && base_ns % dt_ns == 0 || return _fail(push!(diags, diag("E104",
        "the internal step $(dt_ns / 1e9) s does not divide the communication step and every discrete period";
        hint = "use a step that divides $(base_ns / 1e9) s")), out_dir)
    dt = dt_ns / 1e9
    if method !== :ros2 && dt > choice.stable_step
        push!(diags, diag("W207",
            "the internal step $(dt) s is above the $(uppercase(String(method))) stability limit $(round(choice.stable_step; sigdigits = 3)) s; the export will diverge";
            hint = "use dt <= $(round(choice.dt_ns / 1e9; sigdigits = 3)) s or method ros2"))
    elseif choice.over_budget && settings.dt === nothing
        push!(diags, diag("W207",
            "the step needs $(choice.substeps) substeps per $(base_ns / 1e9) s, above the budget of $(settings.max_substeps)";
            hint = "a stiff mode (|λ| = $(round(choice.max_abs_lambda; sigdigits = 3)) 1/s) limits the step; a Rosenbrock export (plan J-EX3) avoids it"))
    end

    # ---- emit
    ident = c_identifier(name)
    guid = _guid(lowered.key, settings, dt_ns, method, vars, params, inputs)
    modes = Any[]
    cbuf = IOBuffer()
    _emit_model_c(cbuf, name, xs, x0, names_x, rhs, jac, env, obs, modes, vars, params,
        inputs, held_ids, dvals, sched, ps, names_p, flat_params)
    for cond in modes
        push!(diags, diag("W203",
            "switching condition `$(cond)` is evaluated once per step, so its switch is not located between steps";
            path = _condition_path(cond), hint = "a smaller dt moves the switch closer to the simulated instant"))
    end
    mkpath(joinpath(out_dir, "sources"))
    _write_model_h(joinpath(out_dir, "sources", "model.h"), name, ident, guid, nx,
        length(params), length(held_ids), has_disc ? length(sched.input_ids) : 0, length(vars),
        length(inputs), has_disc ? length(sched.partitions) : 0, length(modes), dt, dt_ns, method)
    write(joinpath(out_dir, "sources", "model.c"), take!(cbuf))
    for f in RUNTIME_FILES
        cp(joinpath(RUNTIME_DIR, f), joinpath(out_dir, "sources", f); force = true)
    end
    write_fmi2_description(joinpath(out_dir, "modelDescription.xml"); name, ident, guid,
        vars, params, inputs, t_end = settings.t_end, step = settings.step)

    report = Dict{String,Any}(
        "name" => name, "identifier" => ident, "guid" => guid,
        "runtimeVersion" => RUNTIME_VERSION, "fmiVersion" => "2.0",
        "method" => String(method), "dt" => dt, "step" => settings.step,
        "tEnd" => settings.t_end, "substeps" => base_ns ÷ dt_ns,
        "states" => nx, "modes" => length(modes), "folded" => folded,
        "heldValues" => length(held_ids), "partitions" => has_disc ? length(sched.partitions) : 0,
        "inputs" => [Dict("name" => v.name, "id" => v.id, "start" => v.start) for v in inputs],
        "outputs" => [Dict("name" => v.name, "id" => v.id) for v in vars if v.kind === :output],
        "parameters" => [Dict("name" => v.name, "id" => v.id, "start" => v.start,
            "variability" => v.variability) for v in params],
        "locals" => [v.name for v in vars if v.kind === :local],
        "spectrum" => Dict(
            "maxAbsLambda" => choice.max_abs_lambda, "atT" => choice.at_t,
            "points" => length(points), "rangedValues" => length(ranged),
            "stableStep" => isfinite(choice.stable_step) ? choice.stable_step : nothing,
            "accurateStep" => isfinite(choice.accurate_step) ? choice.accurate_step : nothing,
            "analysisMethod" => String(analysis_method),
            "proposedDt" => choice.dt_ns / 1e9),
        "diagnostics" => [BGSim.to_namedtuple(d) for d in sort_diagnostics(diags)],
    )
    open(joinpath(out_dir, "export.json"), "w") do io
        JSON3.pretty(io, JSON3.write(report))
    end
    return ExportResult(true, sort_diagnostics(diags), out_dir, report)
end

# A condition's location for W203: the instance path of its first variable.
function _condition_path(cond)
    for v in Symbolics.get_variables(cond)
        n = try
            String(getname(v))
        catch
            continue
        end
        i = findlast('/', n)
        i === nothing || return n[1:i - 1]
    end
    return nothing
end

function _jacobian_function(jac, xs, ps, iv)
    isempty(xs) && return (x, p, t) -> zeros(0, 0)
    f = Symbolics.build_function(jac, xs, ps, iv; expression = Val{false})[1]
    return (x, p, t) -> Float64.(f(x, p, t))
end

function _guid(key, settings, dt_ns, method, vars, params, inputs)
    h = bytes2hex(SHA.sha256(string(key, "|", RUNTIME_VERSION, "|", dt_ns, "|", method, "|",
        settings.fold_parameters, "|", join([v.name for v in vcat(vars, params, inputs)], ","))))
    return "{" * h[1:8] * "-" * h[9:12] * "-" * h[13:16] * "-" * h[17:20] * "-" * h[21:32] * "}"
end

function _emit_model_c(io, name, xs, x0, names_x, rhs, jac, env, obs, modes, vars, params,
    inputs, held_ids, dvals, sched, ps, names_p, flat_params)
    nx = length(xs)
    println(io, "/* Generated by bg-sim (C/FMU export, runtime $(RUNTIME_VERSION)) from model `$(ccomment(name))`. Do not edit. */")
    println(io, "#include <math.h>\n#include \"model.h\"\n#include \"bg_runtime.h\"\n")
    arr(cname, vals) = println(io, "const double $cname[BG_SZ($(length(vals)))] = {",
        isempty(vals) ? "0.0" : join(clit.(vals), ", "), "};")
    arr("bg_x0", x0)
    arr("bg_p0", Float64[v.start for v in params])
    arr("bg_u0", Float64[v.start for v in inputs])
    arr("bg_d0", dvals)
    arr("bg_p_min", Float64[v.lo for v in params])
    arr("bg_p_max", Float64[v.hi for v in params])
    arr("bg_u_min", Float64[v.lo for v in inputs])
    arr("bg_u_max", Float64[v.hi for v in inputs])
    println(io, "const unsigned char bg_p_tunable[BG_SZ($(length(params)))] = {",
        isempty(params) ? "0" : join([v.variability == "tunable" ? 1 : 0 for v in params], ", "), "};\n")
    for (i, n) in enumerate(names_x)
        println(io, "/* x[$(i - 1)] = $(ccomment(n)) */")
    end
    for (i, v) in enumerate(params)
        println(io, "/* p[$(i - 1)] = $(ccomment(v.id)) ($(v.variability)) */")
    end
    for (i, v) in enumerate(inputs)
        println(io, "/* u[$(i - 1)] = $(ccomment(v.name)) */")
    end
    for (i, n) in enumerate(held_ids)
        println(io, "/* d[$(i - 1)] = $(ccomment(n)) */")
    end
    println(io)

    emit_function(io, "void bg_derivatives(const bg_model *m, double t, const double *x, double *dx)",
        [("dx[$(i - 1)]", rhs[i], "d/dt " * names_x[i]) for i in 1:nx], env, obs; modes = modes)
    jt = Tuple{String,Any,Any}[]
    for i in 1:nx, j in 1:nx
        e = Symbolics.unwrap(jac[i, j])
        c = _try_const(e)
        c !== nothing && iszero(c) && continue
        push!(jt, ("J[$((i - 1) * nx + (j - 1))]", e, nothing))
    end
    println(io, "/* Row-major; the caller zeroes J, so only the structural non-zeros are written. */")
    emit_function(io, "void bg_jacobian(const bg_model *m, double t, const double *x, double *J)",
        jt, env, obs; modes = modes)
    emit_function(io, "void bg_modes(const bg_model *m, double t, const double *x, double *c)",
        [("c[$(k - 1)]", modes[k], string(modes[k])) for k in eachindex(modes)], env, obs)
    emit_function(io, "void bg_outputs(const bg_model *m, double t, const double *x, double *y)",
        [("y[$(k - 1)]", v.expr, v.name) for (k, v) in enumerate(vars)], env, obs)

    sample = Tuple{String,Any,Any}[]
    if sched !== nothing
        known = Dict{String,Any}()
        for (i, x) in enumerate(xs); known[names_x[i]] = x; end
        for (k, l) in enumerate(obs.lhs); known[obs.names[k]] = l; end
        for (j, id) in enumerate(sched.input_ids)
            sym = get(known, id, nothing)
            sym === nothing && throw(ExportError("the discrete code samples `$id`, which is not in the compiled system"))
            push!(sample, ("din[$(j - 1)]", sym, id))
        end
    end
    emit_function(io, "void bg_sample(const bg_model *m, double t, const double *x, double *din)",
        sample, env, obs)

    if sched === nothing || isempty(sched.partitions)
        println(io, "const bg_partition bg_partitions[1] = {{0, 0, 0}};")
        return
    end
    param = Dict{Int,String}()
    sym_by_name = Dict(names_p[i] => ps[i] for i in eachindex(ps))
    for (k, id) in enumerate(sched.param_ids)
        sym = get(sym_by_name, id, nothing)
        sym === nothing && throw(ExportError("the discrete code reads `$id`, which is not a parameter of the compiled system"))
        param[k] = env[sym]
    end
    for (k, sp) in enumerate(sched.partitions)
        emit_partition(io, k - 1, sp.partition, sched, param)
    end
    println(io, "const bg_partition bg_partitions[$(length(sched.partitions))] = {")
    for (k, sp) in enumerate(sched.partitions)
        println(io, "    {INT64_C($(sp.partition.period_ns)), INT64_C($(sp.partition.offset_ns)), bg_part_$(k - 1)},")
    end
    println(io, "};")
end

function _write_model_h(path, name, ident, guid, nx, np, nd, ni, ny, nu, npart, nc, dt, dt_ns, method)
    open(path, "w") do io
        print(io, """
        /* Generated by bg-sim (C/FMU export, runtime $(RUNTIME_VERSION)) from model `$(ccomment(name))`. Do not edit. */
        #ifndef BG_MODEL_H
        #define BG_MODEL_H

        #include <stdint.h>

        #define BG_MODEL_IDENTIFIER "$(ident)"
        #define BG_GUID "$(guid)"
        #define BG_NX $(nx)        /* continuous states */
        #define BG_NP $(np)        /* runtime parameters (tunable, or all unfolded ones) */
        #define BG_NU $(nu)        /* inputs (ExportInput) */
        #define BG_ND $(nd)        /* held discrete values */
        #define BG_NI $(ni)        /* continuous values sampled by discrete code */
        #define BG_NY $(ny)        /* outputs, then locals */
        #define BG_NC $(nc)        /* switching conditions, frozen during a step */
        #define BG_NPART $(npart)  /* discrete partitions */
        #define BG_DT $(repr(dt))
        #define BG_DT_NS INT64_C($(dt_ns))
        #define BG_METHOD_EULER 1
        #define BG_METHOD_RK4 2
        #define BG_METHOD_ROS2 3
        #define BG_METHOD BG_METHOD_$(uppercase(String(method)))

        /* Value references: y [0, BG_NY), p [BG_VR_P0, +BG_NP), u [BG_VR_U0, +BG_NU). */
        #define BG_VR_P0 $(ny)
        #define BG_VR_U0 $(ny + np)

        /* Arrays are never zero-length (C99), so every size is at least 1. */
        #define BG_SZ(n) ((n) > 0 ? (n) : 1)

        /* One model instance. Everything the hot path touches lives here and its size is fixed
           at generation time, so a step never allocates. */
        typedef struct {
            double t;                      /* current time */
            double t_start;
            int64_t n;                     /* steps taken since t_start */
            int64_t t_start_ns;
            double x[BG_SZ(BG_NX)];
            double p[BG_SZ(BG_NP)];
            double u[BG_SZ(BG_NU)];
            double d[BG_SZ(BG_ND)];
            double dprev[BG_SZ(BG_ND)];    /* held values before this tick (previous(x)) */
            double din[BG_SZ(BG_NI)];
            double dinprev[BG_SZ(BG_NI)];
            double dprev_t;
            double c[BG_SZ(BG_NC)];
            double y[BG_SZ(BG_NY)];        /* valid when y_valid */
            int y_valid;
            /* solver workspace */
            double k1[BG_SZ(BG_NX)], k2[BG_SZ(BG_NX)], k3[BG_SZ(BG_NX)], k4[BG_SZ(BG_NX)];
            double xs[BG_SZ(BG_NX)];
            double w[BG_SZ(BG_NX * BG_NX)];
            int piv[BG_SZ(BG_NX)];
        } bg_model;

        typedef struct {
            int64_t period_ns;
            int64_t offset_ns;
            void (*run)(bg_model *m, double t);
        } bg_partition;

        extern const double bg_x0[BG_SZ(BG_NX)];
        extern const double bg_p0[BG_SZ(BG_NP)];
        extern const double bg_u0[BG_SZ(BG_NU)];
        extern const double bg_d0[BG_SZ(BG_ND)];
        extern const unsigned char bg_p_tunable[BG_SZ(BG_NP)];
        /* Declared ranges; the FMI wrapper refuses values outside them, which keeps the step
           inside the range the export proved stable (D-EX16). */
        extern const double bg_p_min[BG_SZ(BG_NP)], bg_p_max[BG_SZ(BG_NP)];
        extern const double bg_u_min[BG_SZ(BG_NU)], bg_u_max[BG_SZ(BG_NU)];
        extern const bg_partition bg_partitions[BG_SZ(BG_NPART)];

        /* model.c (generated) */
        void bg_derivatives(const bg_model *m, double t, const double *x, double *dx);
        void bg_jacobian(const bg_model *m, double t, const double *x, double *J);
        void bg_modes(const bg_model *m, double t, const double *x, double *c);
        void bg_outputs(const bg_model *m, double t, const double *x, double *y);
        void bg_sample(const bg_model *m, double t, const double *x, double *din);

        /* bg_solver.c (runtime) */
        void bg_reset(bg_model *m, double t_start);
        int bg_step(bg_model *m);           /* advance one BG_DT; 0 ok, nonzero error */
        void bg_update_outputs(bg_model *m);

        #endif
        """)
    end
end

export ExportSettings, ExportResult, export_model

end # module Export
