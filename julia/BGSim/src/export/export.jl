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
# Scope: ODE systems and index-1 DAEs with a constant diagonal mass matrix, Euler/RK4 (ODEs
# only) and the Rosenbrock methods ROS2/ROS34PW2/Rodas4P (D-EX6), the integrator and step
# chosen by cost (D-EX7), frozen switching conditions with W203, `@events` with `reinit` of
# states checked after every step with W203 (J-EX6, `emit_events.jl`), multi-rate
# `@discrete`, start values computed at export. Everything else is refused with E110/E111
# naming the construct. The Jacobian of the Rosenbrock step is symbolic with common
# subexpressions (`jacobian_c`) or coloured finite differences (D-EX12); its pattern and the
# linear solver (static sparse LU or dense LU, J-EX4) are chosen in `sparse.jl`.

module Export

using ..BGSim
import ..BGSim: Flat, Compile, IR, Diagnostic, diag, sort_diagnostics, LowerError
using ModelingToolkit
using SymbolicIndexingInterface: getname, getu, getp
import SymbolicIndexingInterface
import Symbolics
const SymbolicUtils = Symbolics.SymbolicUtils
import JSON3
import SHA
using OrdinaryDiffEqTsit5: Tsit5
using OrdinaryDiffEqRosenbrock: Rodas5P

const MTK = ModelingToolkit

"""The hand-written C runtime copied into every export; bump `RUNTIME_VERSION` on any change."""
const RUNTIME_DIR = normpath(joinpath(@__DIR__, "..", "..", "export", "runtime"))
const RUNTIME_VERSION = "0.2.0"
const RUNTIME_FILES = ["bg_runtime.h", "bg_solver.c", "fmi2_cs.c",
    "fmi2Functions.h", "fmi2FunctionTypes.h", "fmi2TypesPlatform.h",
    "bg_intrinsics.h", "bg_intrinsics.c", "bg_mech.h", "bg_mech.c"]

const MARKER_INPUT = "stdlib:converters/ExportInput"
const MARKER_OUTPUT = "stdlib:converters/ExportOutput"
const MARKER_PARAMETER = "stdlib:converters/ExportParameter"
const CSV_SOURCES = ("stdlib:sources/CsvSource", "stdlib:sources/CsvSourceSampled")

include("emit_c.jl")
include("emit_intrinsics.jl")
include("emit_discrete.jl")
include("emit_events.jl")
include("analysis.jl")
include("sparse.jl")
include("fmi2.jl")
include("scope.jl")

"""
    ExportSettings(; kwargs...)

| field | default | meaning |
| --- | --- | --- |
| `step` | `1e-3` | communication step (FMI `DefaultExperiment/stepSize`); `doStep` sizes are multiples of `dt` |
| `dt` | `nothing` | internal step in seconds; `nothing` chooses it from the spectrum (D-EX7) |
| `method` | `:auto` | `:auto` (the cheapest method that meets the step rule; a Rosenbrock method for a DAE), `:euler`, `:rk4`, `:ros2`, `:ros34pw2`, `:rodas4p` |
| `t_end` | `1.0` | `DefaultExperiment/stopTime` and the start-value horizon |
| `margin` | `0.5` | fraction of the stability bound the step may use (explicit methods) |
| `accuracy` | `0.3` | largest `h·|λ|` allowed for any eigenvalue (RK4); Rosenbrock methods meet the same per-step error |
| `damping` | `0.05` | a Rosenbrock step may leave a fast mode unresolved when both the method and the exact flow shrink it below this in one step |
| `stiff_ratio` | `10` | a Rosenbrock step may also damp a mode the exact flow keeps (W213) when `h·|λ|` is at least this and the method shrinks it below `damping` |
| `max_substeps` | `1000` | above this W207 is reported |
| `fold_parameters` | `true` | fold non-tunable parameters into literals |
| `expose_all` | `false` | publish every recorded signal as a `local` variable |
| `jacobian` | `:auto` | Rosenbrock only: `:symbolic` (`jacobian_c`, chain rule through the observed equations), `:fd` (coloured finite differences in C), `:auto` (symbolic within its guard, else `:fd`) |
| `symbolic_jacobian_limit` | `2e5` | the guard of `:auto`: the largest number of derivative terms the symbolic Jacobian may build (counted while it is built, W212 above it); a 120 s time limit applies as well |
| `linear_solver` | `:auto` | Rosenbrock only: `:dense` (LU with partial pivoting), `:sparse` (static sparse LU), `:auto` (sparse above `sparse_threshold` states) |
| `sparse_threshold` | `40` | `:auto` uses the sparse LU when the model has more states than this |
"""
Base.@kwdef struct ExportSettings
    step::Float64 = 1.0e-3
    dt::Union{Nothing,Float64} = nothing
    method::Symbol = :auto
    t_end::Float64 = 1.0
    margin::Float64 = 0.5
    accuracy::Float64 = 0.3
    damping::Float64 = 0.05
    stiff_ratio::Float64 = 10.0
    max_substeps::Int = 1000
    fold_parameters::Bool = true
    expose_all::Bool = false
    jacobian::Symbol = :auto
    symbolic_jacobian_limit::Float64 = 2.0e5
    linear_solver::Symbol = :auto
    sparse_threshold::Int = 40
end

"""The time guard of the symbolic Jacobian (`jacobian = :auto`); the size guard is
`symbolic_jacobian_limit` (terms)."""
const JACOBIAN_MAX_SECONDS = 120.0

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
        damping = Float64(get_("damping", 0.05)),
        stiff_ratio = Float64(get_("stiff_ratio", 10.0)),
        max_substeps = Int(get_("max_substeps", 1000)),
        fold_parameters = Bool(get_("fold_parameters", true)),
        expose_all = Bool(get_("expose_all", false)),
        jacobian = Symbol(lowercase(String(get_("jacobian", "auto")))),
        symbolic_jacobian_limit = Float64(get_("symbolic_jacobian_limit", 2.0e5)),
        linear_solver = Symbol(lowercase(String(get_("linear_solver", "auto")))),
        sparse_threshold = Int(get_("sparse_threshold", 40)),
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
    settings.method in (:auto, EXPORT_METHODS...) ||
        return _fail([diag("E110", "unknown export method `$(settings.method)`";
            hint = "use auto, euler, rk4, ros2, ros34pw2 or rodas4p")], out_dir)
    settings.jacobian in (:auto, :symbolic, :fd) ||
        return _fail([diag("E110", "unknown Jacobian setting `$(settings.jacobian)`";
            hint = "use auto, symbolic or fd")], out_dir)
    settings.linear_solver in (:auto, :dense, :sparse) ||
        return _fail([diag("E110", "unknown linear solver `$(settings.linear_solver)`";
            hint = "use auto, dense or sparse")], out_dir)
    # A CSV source is simulation data (stimulus or comparison); the host supplies such a
    # signal through an ExportInput, so the export refuses it at the block (J-EX5).
    csv_nodes = [i.path for i in flat.instances if i.ref in CSV_SOURCES]
    if !isempty(csv_nodes)
        return _fail([diag("E110", "`$p` reads a CSV file, which is not exported"; path = p,
            hint = CSV_EXPORT_HINT) for p in csv_nodes], out_dir)
    end

    lowered = try
        BGSim.lower_model(flat; t_start = 0.0, t_end = max(settings.t_end, settings.step))
    catch err
        err isa LowerError || rethrow()
        return _fail([diag("E110", "the model uses a construct that is not exported yet";
            hint = sprint(showerror, err))], out_dir)
    end
    algebraic = lowered.model.algebraic
    if algebraic && settings.method in EXPLICIT_METHODS
        return _fail([diag("E111",
            "the compiled system keeps algebraic equations (a mass-matrix DAE); Euler and RK4 cannot step it";
            hint = "use method auto or a Rosenbrock method (ros2, ros34pw2, rodas4p)")], out_dir)
    end
    if algebraic && _mass_diagonal(lowered.problem.f.mass_matrix) === nothing
        return _fail([diag("E111",
            "the mass matrix of the compiled system is not a constant diagonal";
            hint = "only index-1 DAEs with a diagonal mass matrix are exported")], out_dir)
    end
    integ = try
        # The consistent start of a DAE comes from MTK's initialization, run by `init`.
        MTK.SciMLBase.init(lowered.problem, algebraic ? Rodas5P() : Tsit5())
    catch err
        return _fail([diag("E111", "the initial values could not be computed for the export";
            hint = sprint(showerror, err))], out_dir)
    end

    try
        # One intrinsics context for the whole export: the symbolic Jacobian is built before
        # model.c is emitted and registers its tables in the same place (emit_intrinsics.jl).
        return task_local_storage(_INTRINSIC_KEY, IntrinsicContext()) do
            _export(flat, lowered, integ, String(out_dir), settings, reference_dir,
                String(name), diags)
        end
    catch err
        if err isa EventExportError
            o = err.origin
            return _fail(push!(diags, diag("E110", err.message; path = o.path, block = o.block,
                node = o.node, source = BGSim._origin_source(o), scope = "@events")), out_dir)
        end
        err isa ExportError || rethrow()
        return _fail(push!(diags, diag("E110", "the model uses a construct that is not exported yet";
            hint = err.message)), out_dir)
    end
end

"""The diagonal of a constant diagonal mass matrix, or `nothing`."""
function _mass_diagonal(mm)
    mm === nothing && return nothing
    mm isa LinearAlgebra.UniformScaling && return nothing
    mm isa AbstractMatrix || return nothing
    n = size(mm, 1)
    size(mm, 2) == n || return nothing
    for i in 1:n, j in 1:n
        i == j && continue
        v = mm[i, j]
        v isa Number && iszero(v) || return nothing
    end
    d = Float64[]
    for i in 1:n
        v = mm[i, i]
        v isa Number || return nothing
        push!(d, Float64(v))
    end
    return d
end

function _export(flat, lowered, integ, out_dir, settings, reference_dir, name, diags)
    sys = lowered.model.system
    algebraic = lowered.model.algebraic
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

    # ---- the continuous right-hand side `M x' = f(t, x)`
    # Row i of a differential equation is its state's index (mass 1); the algebraic
    # equations `0 = g` fill the rows of the unknowns no equation differentiates (mass 0).
    rhs = Vector{Any}(undef, nx)
    mass = zeros(nx)
    algebraic_eqs = Any[]
    alg_eq_rows = Int[]            # the compiled problem's row of each algebraic equation
    rowmap = zeros(Int, nx)        # rowmap[r]: the C row of the compiled problem's row r
    for (r, e) in enumerate(MTK.equations(sys))
        lhs = Symbolics.unwrap(e.lhs)
        if SymbolicUtils.iscall(lhs) && SymbolicUtils.operation(lhs) isa Symbolics.Differential
            x = Symbolics.unwrap(SymbolicUtils.arguments(lhs)[1])
            i = findfirst(y -> isequal(y, x), xs)
            (i === nothing || mass[i] != 0) &&
                throw(ExportError("the compiled system has an unexpected differential equation `$e`"))
            rhs[i] = Symbolics.unwrap(e.rhs)
            mass[i] = 1.0
            r <= nx && (rowmap[r] = i)
        else
            c = _try_const(lhs)
            push!(algebraic_eqs, c !== nothing && iszero(c) ? Symbolics.unwrap(e.rhs) :
                Symbolics.unwrap(e.rhs - e.lhs))
            push!(alg_eq_rows, r)
        end
    end
    free_rows = findall(iszero, mass)
    length(free_rows) == length(algebraic_eqs) ||
        throw(ExportError("the compiled system has $(length(algebraic_eqs)) algebraic equations for $(length(free_rows)) algebraic unknowns"))
    for (k, (i, g)) in enumerate(zip(free_rows, algebraic_eqs))
        rhs[i] = g
        alg_eq_rows[k] <= nx && (rowmap[alg_eq_rows[k]] = i)
    end
    nalg = length(free_rows)
    sort(rowmap) == collect(1:nx) ||
        throw(ExportError("internal: the compiled system's equations do not map one-to-one to its unknowns"))
    # A numeric Jacobian of the compiled problem in the rows of the C code.
    c_rows(J) = (Jc = similar(J); for r in 1:nx; Jc[rowmap[r], :] = J[r, :]; end; Jc)
    # The right-hand side reads t outside the frozen conditions: Rosenbrock needs df/dt.
    iv_used = e -> any(v -> isequal(v, iv), Symbolics.get_variables(e))
    rhs_need = needed_observed(rhs, obs)
    has_t = any(iv_used, rhs) || any(k -> rhs_need[k] && iv_used(obs.rhs[k]), eachindex(obs.rhs))
    f_ops = op_count(rhs, obs)
    events = lower_events(flat, lowered.model, xs)

    # ---- the step
    # The analysis uses a numeric Jacobian of the compiled right-hand side, which is cheap at
    # any size; the C Jacobian (symbolic or finite differences) is built only for a
    # Rosenbrock export.
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
    jac_fn = _numeric_jacobian(lowered.problem, integ, sys, ps, p0)
    # Runtime-settable values move the eigenvalues: scan their declared ranges too (D-EX16).
    # Only values the Jacobian depends on can move the integrator's eigenvalues; a gain that
    # only discrete code reads changes the closed loop, which simulation shows as well.
    in_rhs = _rhs_dependencies(rhs, obs)
    J0 = nx == 0 ? zeros(0, 0) : jac_fn(x0, p0, 0.0)
    # The structural pattern of J (D-EX12), for the Rosenbrock methods' cost and linear
    # algebra. It must cover every numeric non-zero; a miss would be a bug in the dependency
    # walk, so it is added and counted rather than lost.
    pattern = nothing
    pattern_stats = Dict{String,Any}()
    if nx > 0 && !(settings.method in EXPLICIT_METHODS)
        t0 = time()
        pattern = jacobian_pattern(rhs, obs, xs)
        pattern_stats["patternS"] = time() - t0
        miss = (c_rows(J0) .!= 0) .& .!pattern
        pattern .|= miss
        pattern_stats["patternAddedFromNumeric"] = count(miss)
    end
    # A value the right-hand side reads only linearly (an input added to a derivative) does
    # not move the Jacobian: perturb it and look.
    function moves_jacobian(k)
        nx == 0 && return false
        p = copy(p0)
        p[k] = p0[k] == 0 ? 1.0 : 1.5 * p0[k]
        J = jac_fn(x0, p, 0.0)
        scale = max(1.0, maximum(abs, J0))
        return maximum(abs, J .- J0) > 1e-6 * scale
    end
    ranged = Tuple{Int,Float64,Float64}[]
    for v in vcat(params, inputs)
        v.variability == "fixed" && continue
        v.id in in_rhs || continue
        k = findfirst(==(v.id), names_p)
        moves_jacobian(k) || continue
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
    # A DAE's spectrum is that of the pencil (J, M) in the compiled problem's row order; an
    # algebraic block that is singular at the start is not index 1.
    mass_an = algebraic ? _mass_diagonal(lowered.problem.f.mass_matrix) : nothing
    if mass_an !== nothing && nx > 0
        try
            pencil_eigvals(J0, mass_an)
        catch err
            err isa LinearAlgebra.SingularException || rethrow()
            return _fail(push!(diags, diag("E111",
                "the algebraic equations cannot be solved for the algebraic unknowns at the start (index > 1, or a singular algebraic block)";
                hint = "the Rosenbrock methods step index-1 DAEs only")), out_dir)
        end
    end
    points = spectrum_scan(jac_fn, x0, p0, names_x, names_p, 0.0; reference_dir = reference_dir,
        ranges = ranged, mass = mass_an)

    # ---- the method and the step (D-EX7): the cheapest candidate that meets the step rule
    modes = Any[]
    jac_info = Ref{Any}(nothing)
    build_jacobian() = (jac_info[] === nothing &&
        (jac_info[] = _jacobian(rhs, xs, obs, env, modes, settings)); jac_info[])
    step_kw = (margin = settings.margin, accuracy = settings.accuracy,
        max_substeps = settings.max_substeps, damping = settings.damping,
        stiff_ratio = settings.stiff_ratio)
    candidates = if settings.method !== :auto
        (settings.method,)
    elseif algebraic
        ROSENBROCK_METHODS
    elseif settings.dt !== nothing
        (:rk4,)                     # a fixed step on an ODE keeps the explicit default
    else
        (:rk4, ROSENBROCK_METHODS...)
    end
    # The Rosenbrock step's linear algebra and finite-difference Jacobian are priced from the
    # pattern (the symbolic factorization and the colouring take milliseconds); the symbolic
    # Jacobian by its terms once it is built.
    sparse_lu = pattern !== nothing && _use_sparse(settings, nx)
    lu_kw = if sparse_lu
        slu0 = static_lu(pattern)
        (lu_ops = lu_flops(slu0), solve_ops = lu_solve_flops(slu0))
    else
        (lu_ops = nx^2 + nx^3 / 3, solve_ops = 2nx^2)
    end
    ncolour = pattern === nothing ? 0 : maximum(colour_columns(pattern); init = 0)
    fd_ops = pattern === nothing ? 0.0 :
        (ncolour + 1) * derivative_call_cost(f_ops, nx) + 3 * count(pattern)
    jac_ops(m) = !is_rosenbrock(m) ? 0.0 :
        settings.jacobian === :fd ? fd_ops :
        jac_info[] === nothing ? 0.0 :
        jac_info[].kind === :fd ? fd_ops : f_ops + 3 * jac_info[].terms
    choice, table = choose_method(candidates, points, base_ns, nx; f_ops, jac_ops, has_t,
        lu_kw..., step_kw...)
    if is_rosenbrock(choice.method) && length(candidates) > 1 && settings.jacobian !== :fd
        # The first pass priced the symbolic Jacobian at zero; with its real cost RK4 may win
        # again.
        build_jacobian()
        choice, table = choose_method(candidates, points, base_ns, nx; f_ops, jac_ops, has_t,
            lu_kw..., step_kw...)
    end
    dt_ns = settings.dt === nothing ? choice.dt_ns : round(Int64, settings.dt * 1e9)
    clock_errors = _dt_clock_errors(settings.dt, dt_ns, step_ns, sched, base_ns)
    isempty(clock_errors) || return _fail(append!(diags, clock_errors), out_dir)
    if settings.dt !== nothing && length(candidates) > 1
        # A fixed step on a DAE: the cheapest Rosenbrock method that meets the rule at it.
        # ROS2 is not suggested when it would damp a mode numerically (`ros2_ok`).
        met = [r for r in table if step_rule_met(r.method, points, dt_ns / 1e9; step_kw...) &&
               (r.method !== :ros2 || numerically_damped(:ros2, points, dt_ns / 1e9; step_kw...)[1] == 0)]
        pick = isempty(met) ? :rodas4p :
            met[argmin([step_cost(r.method, nx; f_ops, jac_ops = jac_ops(r.method), has_t,
                lu_kw...) for r in met])].method
        choice = first(r.choice for r in table if r.method === pick)
    end
    method = choice.method
    dt = dt_ns / 1e9
    if !is_rosenbrock(method) && dt > choice.stable_step
        push!(diags, diag("W207",
            "the internal step $(dt) s is above the $(uppercase(String(method))) stability limit $(round(choice.stable_step; sigdigits = 3)) s; the export will diverge";
            hint = "use dt <= $(round(choice.dt_ns / 1e9; sigdigits = 3)) s or a Rosenbrock method (ros2, ros34pw2, rodas4p)"))
    elseif choice.over_budget && settings.dt === nothing
        push!(diags, diag("W207",
            "the step needs $(choice.substeps) substeps per $(base_ns / 1e9) s, above the budget of $(settings.max_substeps)";
            hint = is_rosenbrock(method) ?
                "a fast mode (|λ| up to $(round(choice.max_abs_lambda; sigdigits = 3)) 1/s) is neither resolved nor damped at a larger step" :
                "a stiff mode (|λ| = $(round(choice.max_abs_lambda; sigdigits = 3)) 1/s) limits the step; a Rosenbrock method avoids it"))
    end
    # Stiff modes the model keeps but the Rosenbrock step kills (D-EX7, the step rule's third
    # case).
    n_num, f_num = numerically_damped(method, points, dt; step_kw...)
    if n_num > 0
        f3 = round(f_num; sigdigits = 3)
        f_txt = f3 >= 100 ? string(round(Int, f3)) : string(f3)
        push!(diags, diag("W213",
            "$(n_num) stiff undamped mode$(n_num == 1 ? "" : "s") at or above $(f_txt) Hz $(n_num == 1 ? "is" : "are") damped numerically by $(uppercase(String(method))); force rk4 to resolve them";
            hint = "the step h = $(dt) s is at least $(settings.stiff_ratio)/|λ| for them; method = rk4 follows them, at a smaller step"))
    end

    # ---- the Jacobian and the linear algebra of the Rosenbrock step (D-EX12, D-EX13)
    jac = is_rosenbrock(method) ? build_jacobian() : nothing
    la = nothing
    if jac !== nothing
        if jac.reason !== nothing
            push!(diags, diag("W212",
                "the symbolic Jacobian is replaced by coloured finite differences ($(ncolour + 1) derivative calls per step): $(jac.reason)";
                hint = "jacobian = fd skips the attempt; symbolic_jacobian_limit raises the size guard"))
        end
        S = copy(pattern)
        stats = copy(pattern_stats)
        if jac.kind === :symbolic
            # The symbolic entries are structural too; one outside the pattern is added.
            added = 0
            for (i, j, _) in jac.jc.jentries
                S[i, j] || (S[i, j] = true; added += 1)
            end
            stats["patternAddedFromSymbolic"] = added
            stats["symbolicTerms"] = jac.terms
        end
        hg = ROSENBROCK_TABLEAUS[method].gamma * dt
        Js = [c_rows(J) for J in _check_jacobians(jac_fn, x0, p0, names_x, names_p, reference_dir)]
        la = _plan_linear_algebra((pattern = S, kind = jac.kind, stats = stats), settings, nx,
            hg, mass, Js, diags)
    end

    # ---- emit
    ident = c_identifier(name)
    guid = _guid(lowered.key, settings, dt_ns, method, vars, params, inputs)
    cbuf = IOBuffer()
    # The intrinsics' context is the one `export_model` opened: the symbolic Jacobian above
    # already registered its tables there.
    intrinsics = _intrinsic_context()
    _emit_model_c(cbuf, name, xs, x0, names_x, rhs, mass, jac, la, env, obs, modes, vars,
        params, inputs, held_ids, dvals, sched, ps, names_p, flat_params, events)
    block_of = Dict(i.path => i.ref for i in flat.instances)
    for cond in modes
        path = _condition_path(cond)
        push!(diags, diag("W203",
            "switching condition `$(cond)` is evaluated once per step, so its switch is not located between steps";
            path, block = path === nothing ? nothing : get(block_of, path, nothing),
            hint = "a smaller dt moves the switch closer to the simulated instant"))
    end
    for ev in events
        o = ev.origin
        push!(diags, diag("W203",
            "event `$(ev.label)` is checked once per step, so its reinit applies at the end of the step in which the condition crosses zero (up to one dt late)";
            path = o.path, block = o.block, node = o.node, source = BGSim._origin_source(o),
            scope = "@events",
            hint = "a smaller dt moves the event closer to the simulated instant"))
    end
    mkpath(joinpath(out_dir, "sources"))
    _write_model_h(joinpath(out_dir, "sources", "model.h"), name, ident, guid, nx,
        length(params), length(held_ids), has_disc ? length(sched.input_ids) : 0, length(vars),
        length(inputs), has_disc ? length(sched.partitions) : 0, length(modes), dt, dt_ns, method;
        nalg, has_t, la, ne = length(events),
        ner = maximum((length(ev.targets) for ev in events); init = 0))
    write(joinpath(out_dir, "sources", "model.c"), splice_intrinsics(String(take!(cbuf)), intrinsics))
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
        "states" => nx, "algebraic" => nalg, "dependsOnTime" => has_t,
        "modes" => length(modes), "events" => length(events), "folded" => folded,
        "jacobian" => jac === nothing ? nothing : Dict("kind" => String(jac.kind),
            "terms" => jac.terms,
            "entries" => jac.kind === :symbolic ? jac.entries : count(la.pattern),
            "fallbackReason" => jac.reason),
        # D-EX7c: every candidate with its step and estimated cost per communication step
        # (flops; derivative calls, Jacobian, LU and solves).
        "selection" => [Dict("method" => String(r.method), "substeps" => r.choice.substeps,
            "dt" => r.choice.dt_ns / 1e9, "cost" => r.cost,
            "withinBudget" => !r.choice.over_budget,
            "numericallyDamped" => r.numerical) for r in table],
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
            "analysisMethod" => String(method),
            "proposedDt" => choice.dt_ns / 1e9,
            # W213: modes the exact flow keeps that the Rosenbrock step damps.
            "numericallyDamped" => Dict("modes" => n_num,
                "minHz" => isfinite(f_num) ? f_num : nothing)),
        "linearAlgebra" => la === nothing ? nothing : la.report,
        "tables" => intrinsics_report(intrinsics),
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

"""    _dt_clock_errors(dt_setting, dt_ns, step_ns, sched, base_ns) -> Vector{Diagnostic}

E104 against `dt` (D-EX5): one diagnostic for each clock the internal step does not divide,
the communication step and every discrete period and offset, the latter at the partition's
block. Empty when `dt` is valid."""
function _dt_clock_errors(dt_setting, dt_ns, step_ns, sched, base_ns)
    hint = "use a step that divides $(base_ns / 1e9) s"
    dt = dt_ns / 1e9
    if dt_ns <= 0 || (dt_setting !== nothing && abs(dt - dt_setting) > 1e-15 * max(1.0, dt_setting))
        return [diag("E104", "the internal step $(something(dt_setting, dt)) s is not a positive whole number of nanoseconds";
            hint)]
    end
    out = Diagnostic[]
    step_ns % dt_ns == 0 || push!(out, diag("E104",
        "the internal step $dt s does not divide the communication step $(step_ns / 1e9) s"; hint))
    if sched !== nothing
        for sp in sched.partitions
            p = sp.partition
            for (what, ns) in (("period", p.period_ns), ("offset", p.offset_ns))
                ns > 0 && ns % dt_ns != 0 || continue
                push!(out, diag("E104",
                    "the internal step $dt s does not divide the $what $(ns / 1e9) s of the discrete clock in `$(p.path)`";
                    hint, path = p.path, node = p.node, block = p.ref))
            end
        end
    end
    return out
end

"""    _numeric_jacobian(prob, integ, sys, ps, p0) -> (x, p, t) -> Matrix

A central-difference Jacobian of the compiled right-hand side `prob.f`, for the step analysis.
`p` is a full value vector in the order of `ps`; only the entries that differ from `p0` are
written into a copy of the integrator's parameter object."""
function _numeric_jacobian(prob, integ, sys, ps, p0)
    f = prob.f
    base = deepcopy(integ.p)
    setters = Dict{Int,Any}()
    return function (x, p, t)
        n = length(x)
        n == 0 && return zeros(0, 0)
        pobj = deepcopy(base)
        for k in eachindex(p)
            p[k] == p0[k] && continue
            setter = get!(() -> SymbolicIndexingInterface.setp(sys, ps[k]), setters, k)
            setter(pobj, p[k])
        end
        J = zeros(n, n)
        fp = zeros(n)
        fm = zeros(n)
        xp = copy(x)
        for j in 1:n
            h = 6.0e-6 * max(1.0, abs(x[j]))
            xp[j] = x[j] + h
            f(fp, xp, pobj, t)
            xp[j] = x[j] - h
            f(fm, xp, pobj, t)
            xp[j] = x[j]
            for i in 1:n
                J[i, j] = (fp[i] - fm[i]) / (2h)
            end
        end
        return J
    end
end

"""    _jacobian(rhs, xs, obs, env, modes, settings) -> NamedTuple

The Jacobian of a Rosenbrock export (D-EX12): symbolic with common subexpressions
(`jacobian_c`), or coloured finite differences (`kind = :fd`, emitted from the pattern by
`emit_fd_jacobian`) when asked (`jacobian = :fd`) or when the symbolic one exceeds its guard
(`symbolic_jacobian_limit` terms, `JACOBIAN_MAX_SECONDS`) or meets a partial without a C
form, such as an intrinsic without a symbolic derivative (`reason` says which; W212). A
forced `jacobian = :symbolic` has no guard and fails instead of falling back."""
function _jacobian(rhs, xs, obs, env, modes, settings)
    option = settings.jacobian
    fd(reason) = (kind = :fd, jc = nothing, terms = 0, entries = 0, reason = reason)
    option === :fd && return fd(nothing)
    n0 = length(modes)
    try
        jc = jacobian_c(rhs, xs, obs, env, modes;
            max_terms = option === :symbolic ? Inf : settings.symbolic_jacobian_limit,
            max_seconds = option === :symbolic ? Inf : JACOBIAN_MAX_SECONDS)
        return (kind = :symbolic, jc = jc, terms = jc.terms, entries = jc.entries,
            reason = nothing)
    catch err
        err isa InterruptException && rethrow()
        option === :symbolic && rethrow()
        resize!(modes, n0)       # conditions met only in the abandoned Jacobian
        reason = err isa JacobianTooBig ? err.reason :
            err isa ExportError ? err.message : sprint(showerror, err)
        return fd(first(reason, 300))
    end
end

"""    _rhs_dependencies(rhs, obs) -> Set{String}

The names every derivative depends on, through the observed equations, without substituting
them (the cheap stand-in for "the Jacobian depends on it")."""
function _rhs_dependencies(rhs, obs)
    need = needed_observed(rhs, obs)
    names = Set{String}()
    add(e) = for v in Symbolics.get_variables(e)
        n = try
            String(getname(v))
        catch
            continue
        end
        push!(names, n)
    end
    foreach(add, rhs)
    for k in eachindex(obs.rhs)
        need[k] && add(obs.rhs[k])
    end
    return names
end

function _guid(key, settings, dt_ns, method, vars, params, inputs)
    h = bytes2hex(SHA.sha256(string(key, "|", RUNTIME_VERSION, "|", dt_ns, "|", method, "|",
        settings.fold_parameters, "|", join([v.name for v in vcat(vars, params, inputs)], ","))))
    return "{" * h[1:8] * "-" * h[9:12] * "-" * h[13:16] * "-" * h[17:20] * "-" * h[21:32] * "}"
end

function _emit_model_c(io, name, xs, x0, names_x, rhs, mass, jac, la, env, obs, modes, vars,
    params, inputs, held_ids, dvals, sched, ps, names_p, flat_params, events)
    nx = length(xs)
    println(io, "/* Generated by bg-sim (C/FMU export, runtime $(RUNTIME_VERSION)) from model `$(ccomment(name))`. Do not edit. */")
    println(io, "#include <math.h>\n#include \"model.h\"\n#include \"bg_runtime.h\"\n")
    arr(cname, vals) = println(io, "const double $cname[BG_SZ($(length(vals)))] = {",
        isempty(vals) ? "0.0" : join(clit.(vals), ", "), "};")
    arr("bg_x0", x0)
    arr("bg_mass", mass)
    alg = [i - 1 for i in eachindex(mass) if mass[i] == 0]
    println(io, "const int bg_alg[BG_SZ($(length(alg)))] = {", isempty(alg) ? "0" : join(alg, ", "), "};")
    # Where dg/dz of the algebraic block sits in m->jac (-1: structurally zero), for the
    # re-solve after a tick or an event.
    jpos = la === nothing ? Int[] : [la.targets[i + 1, j + 1] for i in alg for j in alg]
    println(io, "const int bg_alg_jpos[BG_SZ($(length(jpos)))] = {", isempty(jpos) ? "0" : join(jpos, ", "), "};")
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

    println(io, "/* M x' = f(t, x) with M = diag(bg_mass): row i is d/dt x[i] (mass 1) or an algebraic")
    println(io, "   residual 0 = g (mass 0). */")
    emit_function(io, "void bg_derivatives(const bg_model *m, double t, const double *x, double *dx)",
        [("dx[$(i - 1)]", rhs[i], mass[i] != 0 ? "d/dt " * names_x[i] : "0 = residual (algebraic, solves " * names_x[i] * ")")
         for i in 1:nx], env, obs; modes = modes)
    emit_jacobian(io, la, jac === nothing ? nothing : jac.jc)
    la === nothing || la.lu === nothing || emit_sparse_lu(io, la.lu)
    emit_function(io, "void bg_modes(const bg_model *m, double t, const double *x, double *c)",
        [("c[$(k - 1)]", modes[k], string(modes[k])) for k in eachindex(modes)], env, obs)
    emit_function(io, "void bg_outputs(const bg_model *m, double t, const double *x, double *y)",
        [("y[$(k - 1)]", v.expr, v.name) for (k, v) in enumerate(vars)], env, obs)
    emit_events(io, events, env, obs, names_x)

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

function _write_model_h(path, name, ident, guid, nx, np, nd, ni, ny, nu, npart, nc, dt, dt_ns, method;
    nalg = 0, has_t = false, la = nothing, ne = 0, ner = 0)
    nstage = is_rosenbrock(method) ? method_stages(method) : 0
    sparse = la !== nothing && la.lu !== nothing
    lu_defs = sparse ? """
        #define BG_SPARSE_LU 1     /* the static sparse LU in model.c replaces the dense one */
        #define BG_LU_NNZ $(lu_nnz(la.lu))    /* non-zeros of the LU factors (pattern of W plus fill-in) */
        #define BG_LU_NUPD $(length(la.lu.upd))   /* multiply-adds of one factorization */
        #define BG_NJ BG_LU_NNZ    /* m->jac holds J on the static pattern */
        #define BG_NW 0
        """ : """
        #define BG_NJ $(nstage > 0 ? "(BG_NX * BG_NX)" : "0")   /* m->jac holds J row-major (dense LU) */
        #define BG_NW BG_NJ        /* the dense W */
        """
    w_fields = sparse ? """
            double lu[BG_LU_NNZ];          /* W = M - hg J, then its LU factors, on the static pattern */
            double lu_inv[BG_SZ(BG_NX)];   /* 1 / pivot */
            double lu_y[BG_SZ(BG_NX)];     /* solve workspace */
        """ : """
            double w[BG_SZ(BG_NW)];        /* W = M - hg J, factored in place */
            int piv[BG_SZ(BG_NX)];
        """
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
        #define BG_NE $(ne)        /* @events, checked after every step */
        #define BG_NER $(ner)       /* the most states one event writes */
        #define BG_DT $(repr(dt))
        #define BG_DT_NS INT64_C($(dt_ns))
        #define BG_METHOD_EULER 1
        #define BG_METHOD_RK4 2
        #define BG_METHOD_ROS2 3
        #define BG_METHOD_ROS34PW2 4
        #define BG_METHOD_RODAS4P 5
        #define BG_METHOD BG_METHOD_$(uppercase(String(method)))
        #define BG_NSTAGE $(nstage)    /* Rosenbrock stages (0: explicit method) */
        #define BG_NALG $(nalg)      /* algebraic equations: zero rows of the mass matrix */
        #define BG_HAS_T $(has_t ? 1 : 0)     /* the right-hand side reads t (Rosenbrock adds df/dt) */
        $(lu_defs)
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
            double ez0[BG_SZ(BG_NE)];      /* event conditions at the start of the step */
            double ez[BG_SZ(BG_NE)];       /* ... and at its end */
            double er[BG_SZ(BG_NER)];      /* the new values of the event being applied */
            double y[BG_SZ(BG_NY)];        /* valid when y_valid */
            int y_valid;
            /* solver workspace */
            double k1[BG_SZ(BG_NX)], k2[BG_SZ(BG_NX)], k3[BG_SZ(BG_NX)], k4[BG_SZ(BG_NX)];
            double xs[BG_SZ(BG_NX)];
            /* Rosenbrock workspace: the Jacobian (in the layout of the LU), the linear algebra,
               the stages, f and df/dt */
            double jac[BG_SZ(BG_NJ)];
        $(w_fields)    double ks[BG_SZ(BG_NSTAGE)][BG_SZ(BG_NX)];
            double fx[BG_SZ(BG_NX)], ft[BG_SZ(BG_NX)];
            /* re-solving the algebraic unknowns after a tick or an event: dg/dz and the Newton step */
            double wa[BG_SZ(BG_NALG * BG_NALG)], ga[BG_SZ(BG_NALG)];
        } bg_model;

        typedef struct {
            int64_t period_ns;
            int64_t offset_ns;
            void (*run)(bg_model *m, double t);
        } bg_partition;

        extern const double bg_x0[BG_SZ(BG_NX)];
        extern const double bg_mass[BG_SZ(BG_NX)];  /* the mass matrix diagonal */
        extern const int bg_alg[BG_SZ(BG_NALG)];    /* the algebraic rows (= their unknowns) */
        extern const int bg_alg_jpos[BG_SZ(BG_NALG * BG_NALG)];  /* dg/dz in m->jac, -1: zero */
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
        void bg_event_conditions(const bg_model *m, double t, const double *x, double *z);
        int bg_events(bg_model *m, double t);  /* after a step: apply the events that fired */

        /* The linear algebra of the Rosenbrock methods: W = M - hg J with M = diag(bg_mass) and
           J from m->jac (filled by bg_jacobian), factored in place (non-zero on a bad pivot),
           and an in-place solve with it. Dense in bg_solver.c, or the static sparse LU in
           model.c when BG_SPARSE_LU is defined. */
        int bg_w_factor(bg_model *m, double hg);
        void bg_w_solve(bg_model *m, double *b);

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
