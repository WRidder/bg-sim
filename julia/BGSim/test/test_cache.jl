# Work package J2.8: the compile cache and remake (plan 5.12).
#
# The acceptance of the work package:
#   * a repeated run of the same structural model (the same `compile_key`) reuses the
#     `mtkcompile`d `System` and only remakes the `ODEProblem`, through the recorder path as
#     well as the direct API, and a parameter-only re-run reaches first data in under 300 ms
#     once warm (plan 5.12);
#   * a structural edit misses the cache and compiles a new `System`: topology, block
#     references, a `@constants` value folded into an equation or a static size, an equation,
#     an `@events` threshold/body and a `@discrete` clock/body all invalidate it, while
#     parameter values, start values, comments and editor metadata do not;
#   * no stale systems and no parameter leakage: after an edit and after reverting, every run
#     produces its own numbers, and a parameter-only change really reaches the integrator;
#   * the cache is bounded (LRU) and `clear_compile_cache!` (the worker's `cache.clear`)
#     empties it, so the next run is a real compile.
#
# The J1.5 timing test in `test_simulate.jl` keeps its own 300 ms assertion; this file adds
# the cache-policy and invalidation regressions on a two-node model so it stays fast.

using Test
using BGSim
import BGSim.IR
import BGSim.Compile
import JSON3

# ---------------------------------------------------------------------------------------
# Model-document helpers (the `_comp_`/`_sim_` pattern: one prefix per test file)
# ---------------------------------------------------------------------------------------

function _cache_node(id, name, block; params = Dict{String,Any}(),
    starts = Dict{String,Any}())
    return Dict{String,Any}(
        "id" => id,
        "name" => name,
        "block" => block,
        "position" => Dict{String,Any}("x" => 0.0, "y" => 0.0),
        "params" => params,
        "constants" => Dict{String,Any}(),
        "starts" => starts,
    )
end

_cache_ref(ref) = Dict{String,Any}("ref" => ref)
_cache_inline(source) = Dict{String,Any}("inline" => Dict{String,Any}("source" => source))

function _cache_conn(id, from_node, from_port, to_node, to_port)
    return Dict{String,Any}(
        "id" => id,
        "kind" => "signal",
        "from" => Dict{String,Any}("node" => from_node, "port" => from_port),
        "to" => Dict{String,Any}("node" => to_node, "port" => to_port),
    )
end

function _cache_model(name, nodes, connections; t_end = 1.0, points = 11)
    return Dict{String,Any}(
        "format" => "bgsim.model",
        "language" => "0.1.0",
        "name" => name,
        "diagram" => Dict{String,Any}(
            "nodes" => Any[nodes...],
            "connections" => Any[connections...],
            "subsystemPorts" => Any[],
            "annotations" => Any[],
        ),
        "settings" => Dict{String,Any}(
            "t_start" => 0.0,
            "t_end" => t_end,
            "solver" => "Tsit5",
            "reltol" => 1.0e-9,
            "abstol" => 1.0e-11,
            "max_step" => nothing,
            "output" => Dict{String,Any}("mode" => "points", "points" => points),
            "event_limit" => 10000,
        ),
        "plots" => Any[],
        "scene" => nothing,
        "bindings" => Any[],
    )
end

_cache_flat(doc) = Compile.flatten(IR.parse_model(doc))
_cache_errors(fm) = [d for d in fm.diagnostics if d.severity == "error"]

function _cache_manifest(dir)
    return JSON3.read(read(joinpath(dir, "manifest.json"), String))
end

"""The columns file as `id => Vector{Float64}`, plus `"time"`."""
function _cache_columns(dir)
    m = _cache_manifest(dir)
    n = Int(m.time.n)
    nsig = length(m.signals)
    raw = read(joinpath(dir, "columns.f64"))
    @test length(raw) == 8 * n * (nsig + 1)
    columns = reshape(reinterpret(Float64, raw), (n, nsig + 1))
    out = Dict{String,Vector{Float64}}("time" => collect(columns[:, 1]))
    for (j, signal) in enumerate(m.signals)
        out[String(signal.id)] = collect(columns[:, j + 1])
    end
    return out
end

# ---------------------------------------------------------------------------------------
# Blocks
# ---------------------------------------------------------------------------------------

# One state, one runtime parameter whose default folds a `@constants` value. Everything the
# cache has to distinguish is reachable from this block: an equation edit, a constant folded
# into an equation, a constant that only reaches a parameter value, and a parameter change
# (D4). `y = g * x` with `x = 3 t`, so `y(1) = 3 g`.
const _CACHE_GAIN_BLOCK = """
@block CacheGain begin
    @constants c::Real = 2.0
    @inputs u::Real
    @outputs y::Real
    @parameters g::Real = c * 1.0
    @variables x::Real = 0.0, [state = :prefer]
    @equations begin
        ddt(x) ~ u
        y ~ g * x
    end
end
"""

# An event whose threshold and body are structural (D19).
const _CACHE_EVENT_BLOCK = """
@block CacheEvent begin
    @inputs u::Real
    @outputs y::Real
    @variables x::Real = 0.0, [state = :prefer]
    @events begin
        x > 1.0 => begin
            reinit(x, 0.5)
        end
    end
    @equations begin
        ddt(x) ~ u
        y ~ x
    end
end
"""

# A discrete partition (plan 5.9); its clock and body are structural.
const _CACHE_DISCRETE_BLOCK = """
@block CacheTick begin
    @outputs n::Real = 0.0
    @discrete Ts = 1e-3 begin
        n = n + 1
    end
end
"""

# A static array size taken from a structural constant (D13): changing `N` adds parameter
# elements, the "structural parameter" case of plan 5.2.2.
const _CACHE_VEC_BLOCK = """
@block CacheVec begin
    @constants N::Int = 2
    @inputs u::Real
    @outputs y::Real
    @parameters begin
        p::Vec{N} = [1.0, 1.0]
    end
    @equations y ~ p[1] * u + p[2] * u * u
end
"""

# ---------------------------------------------------------------------------------------
# Model builders
# ---------------------------------------------------------------------------------------

function _cache_gain_model(; source = _CACHE_GAIN_BLOCK, constants = Dict{String,Any}(),
    name = "CacheGain")
    node = _cache_node("n2", "G1", _cache_inline(source))
    node["constants"] = constants
    return _cache_model(
        name,
        [
            _cache_node("n1", "C1", _cache_ref("stdlib:sources/Constant");
                params = Dict("value" => "3.0")),
            node,
        ],
        [_cache_conn("c1", "n1", "y", "n2", "u")],
    )
end

# A two-stage signal chain; swapping the two connections is a pure topology edit that keeps
# the model valid (both blocks take the same kind of input).
function _cache_chain_model(; swapped = false)
    connections = swapped ?
                  [
                      _cache_conn("c1", "n1", "y", "n3", "u"),
                      _cache_conn("c2", "n3", "y", "n2", "u"),
                  ] :
                  [
                      _cache_conn("c1", "n1", "y", "n2", "u"),
                      _cache_conn("c2", "n2", "y", "n3", "u"),
                  ]
    return _cache_model(
        "CacheChain",
        [
            _cache_node("n1", "C1", _cache_ref("stdlib:sources/Constant");
                params = Dict("value" => "3.0")),
            _cache_node("n2", "G1", _cache_inline(_CACHE_GAIN_BLOCK)),
            _cache_node("n3", "G2", _cache_inline(_CACHE_GAIN_BLOCK)),
        ],
        connections,
    )
end

function _cache_event_model(; threshold = "1.0", reset = "0.5")
    source = replace(_CACHE_EVENT_BLOCK, "x > 1.0" => "x > " * threshold)
    source = replace(source, "reinit(x, 0.5)" => "reinit(x, " * reset * ")")
    return _cache_model(
        "CacheEvent",
        [
            _cache_node("n1", "C1", _cache_ref("stdlib:sources/Constant");
                params = Dict("value" => "3.0")),
            _cache_node("n2", "E1", _cache_inline(source)),
        ],
        [_cache_conn("c1", "n1", "y", "n2", "u")],
    )
end

function _cache_discrete_model(; step = "1")
    source = replace(_CACHE_DISCRETE_BLOCK, "n = n + 1" => "n = n + " * step)
    return _cache_model(
        "CacheTick",
        [_cache_node("n1", "T1", _cache_inline(source))],
        Any[],
    )
end

function _cache_vec_model(; constants = Dict{String,Any}(), params = Dict{String,Any}())
    node = _cache_node("n2", "V1", _cache_inline(_CACHE_VEC_BLOCK); params = params)
    node["constants"] = constants
    return _cache_model(
        "CacheVec",
        [
            _cache_node("n1", "C1", _cache_ref("stdlib:sources/Constant");
                params = Dict("value" => "3.0")),
            node,
        ],
        [_cache_conn("c1", "n1", "y", "n2", "u")],
    )
end

# A model whose node references one of two project blocks with identical interface and
# equations; only the block reference differs.
function _cache_ref_model(ref)
    return _cache_model(
        "CacheRef",
        [
            _cache_node("n1", "C1", _cache_ref("stdlib:sources/Constant");
                params = Dict("value" => "3.0")),
            _cache_node("n2", "B1", _cache_ref(ref)),
        ],
        [_cache_conn("c1", "n1", "y", "n2", "u")],
    )
end

@testset "J2.8 compile cache and remake" begin
    @testset "the structural key: structure invalidates, values do not" begin
        base = _cache_flat(_cache_gain_model())
        @test isempty(_cache_errors(base))
        key0 = BGSim.compile_key(base)
        @test occursin(r"^[0-9a-f]{64}$", key0)
        # The same document flattens to the same key (the key is deterministic).
        @test BGSim.compile_key(_cache_flat(_cache_gain_model())) == key0

        # D4: parameter values and start values are not structure.
        @test BGSim.compile_key(
            BGSim.set_parameter_values(base, Dict("G1/g" => 4.0))
        ) == key0
        @test BGSim.compile_key(
            BGSim.set_start_values(base, Dict("G1/x" => 1.0))
        ) == key0

        # A constant that only feeds a parameter *value* folds at flattening time: the
        # structure is unchanged and `remake` applies the new value (see the run tests).
        c3 = _cache_flat(_cache_gain_model(constants = Dict{String,Any}("c" => "3.0")))
        @test isempty(_cache_errors(c3))
        @test BGSim.compile_key(c3) == key0
        @test only(p for p in c3.parameters if p.id == "G1/g").value == 3.0
        @test only(p for p in base.parameters if p.id == "G1/g").value == 2.0

        # A constant folded into an equation *is* structure.
        folded = _cache_flat(_cache_gain_model(
            source = replace(_CACHE_GAIN_BLOCK, "y ~ g * x" => "y ~ c * g * x"),
        ))
        @test isempty(_cache_errors(folded))
        @test BGSim.compile_key(folded) != key0

        # An equation edit is structure.
        edited = _cache_flat(_cache_gain_model(
            source = replace(_CACHE_GAIN_BLOCK, "y ~ g * x" => "y ~ 2.0 * g * x"),
        ))
        @test BGSim.compile_key(edited) != key0

        # A comment edit is not structure (the AST is unchanged).
        commented = _cache_flat(_cache_gain_model(
            source = replace(_CACHE_GAIN_BLOCK, "@inputs u::Real" =>
                "# the drive signal\n    @inputs u::Real"),
        ))
        @test isempty(_cache_errors(commented))
        @test BGSim.compile_key(commented) == key0

        # Topology: the same nodes, a different signal chain.
        chain = _cache_flat(_cache_chain_model())
        chain_swapped = _cache_flat(_cache_chain_model(swapped = true))
        @test isempty(_cache_errors(chain))
        @test isempty(_cache_errors(chain_swapped))
        @test BGSim.compile_key(chain) != BGSim.compile_key(chain_swapped)

        # Block references: two project blocks with identical interface and equations. The
        # equations are equal, so only the reference can tell the models apart.
        project = mktempdir()
        mkpath(joinpath(project, "library"))
        for name in ("RefA", "RefB")
            write(
                joinpath(project, "library", name * ".jl"),
                "@block $name begin\n    @inputs u::Real\n    @outputs y::Real\n" *
                "    @equations y ~ u\nend\n",
            )
        end
        ref_a = Compile.flatten(
            IR.parse_model(_cache_ref_model("project:RefA")); project_dir = project
        )
        ref_b = Compile.flatten(
            IR.parse_model(_cache_ref_model("project:RefB")); project_dir = project
        )
        @test isempty(_cache_errors(ref_a))
        @test isempty(_cache_errors(ref_b))
        @test [v.id for v in ref_a.variables] == [v.id for v in ref_b.variables]
        @test [(sprint(show, e.lhs), sprint(show, e.rhs)) for e in ref_a.equations] ==
              [(sprint(show, e.lhs), sprint(show, e.rhs)) for e in ref_b.equations]
        @test [i.ref for i in ref_a.instances] != [i.ref for i in ref_b.instances]
        @test BGSim.compile_key(ref_a) != BGSim.compile_key(ref_b)

        # `@events` structure: the threshold and the body both change the key.
        event = _cache_flat(_cache_event_model())
        @test isempty(_cache_errors(event))
        @test !isempty(event.events)
        @test BGSim.compile_key(_cache_flat(_cache_event_model(threshold = "2.0"))) !=
              BGSim.compile_key(event)
        @test BGSim.compile_key(_cache_flat(_cache_event_model(reset = "0.25"))) !=
              BGSim.compile_key(event)

        # `@discrete` structure: the clock and the body are structural.
        discrete = _cache_flat(_cache_discrete_model())
        @test isempty(_cache_errors(discrete))
        @test !isempty(discrete.discrete)
        @test BGSim.compile_key(_cache_flat(_cache_discrete_model(step = "2"))) !=
              BGSim.compile_key(discrete)

        # A structural constant that fixes an array size changes the flat parameter list
        # (plan 5.2.2 / D13), so it is structure. (A *parameter* may not do this: E005.)
        vec2 = _cache_flat(_cache_vec_model())
        vec3 = _cache_flat(_cache_vec_model(
            constants = Dict{String,Any}("N" => "3"),
            params = Dict{String,Any}("p" => "[1.0, 2.0, 3.0]"),
        ))
        @test isempty(_cache_errors(vec2))
        @test isempty(_cache_errors(vec3))
        @test count(p -> startswith(p.id, "V1/p["), vec2.parameters) == 2
        @test count(p -> startswith(p.id, "V1/p["), vec3.parameters) == 3
        @test BGSim.compile_key(vec3) != BGSim.compile_key(vec2)
    end

    @testset "reuse, parameter-only remake and structural invalidation" begin
        flat = _cache_flat(_cache_gain_model())
        @test isempty(_cache_errors(flat))
        key = BGSim.compile_key(flat)
        @test BGSim.compile_key(_cache_flat(_cache_gain_model())) == key
        settings = BGSim.RunSettings(
            t_start = 0.0, t_end = 1.0, solver = "Tsit5", reltol = 1.0e-9,
            abstol = 1.0e-11,
            output = Dict{String,Any}("mode" => "points", "points" => 11),
        )

        BGSim.clear_compile_cache!()
        @test BGSim.cache_size() == 0
        @test isempty(BGSim.compile_cache_keys())
        builds = BGSim.compile_build_count()

        # 1. Fresh compile through the run path. `y = g * x = 2 * 3 t`, so y(1) = 6.
        cold_dir = mktempdir()
        cold = simulate(flat; run_dir = cold_dir, settings = settings)
        @test cold.status == "done"
        @test !cold.cache_hit
        @test BGSim.compile_build_count() == builds + 1
        @test BGSim.cache_size() == 1
        @test String(_cache_manifest(cold_dir).modelHash) == key
        @test isapprox(_cache_columns(cold_dir)["G1/y"][end], 6.0; rtol = 1.0e-8)

        # 2. An identical model (same key) reuses the compiled system and its recorder path.
        warm_dir = mktempdir()
        warm = simulate(flat; run_dir = warm_dir, settings = settings)
        @test warm.status == "done"
        @test warm.cache_hit
        @test BGSim.compile_build_count() == builds + 1
        @test isapprox(_cache_columns(warm_dir)["G1/y"][end], 6.0; rtol = 1.0e-8)

        # 3. The direct API hands out the *same* compiled model: no stale copy, no rebuild.
        l1 = BGSim.lower_model(flat; t_start = 0.0, t_end = 1.0)
        l2 = BGSim.lower_model(flat; t_start = 0.0, t_end = 1.0)
        @test l1.cache_hit && l2.cache_hit
        @test l1.key == key && l2.key == key
        @test l2.model === l1.model
        @test l2.model.system === l1.model.system
        @test BGSim.compile_build_count() == builds + 1

        # 4. A parameter-only change keeps the key, hits the cache and applies the new value.
        flat_p = BGSim.set_parameter_values(flat, Dict("G1/g" => 4.0))
        @test BGSim.compile_key(flat_p) == key
        # NOTES.md: the first re-run after a parameter change pays JIT; measure the second.
        p_warm_dir = mktempdir()
        p_warm = simulate(flat_p; run_dir = p_warm_dir, settings = settings)
        @test p_warm.cache_hit
        @test BGSim.compile_build_count() == builds + 1
        @test isapprox(_cache_columns(p_warm_dir)["G1/y"][end], 12.0; rtol = 1.0e-8)
        p_dir = mktempdir()
        parameter_only = simulate(flat_p; run_dir = p_dir, settings = settings)
        @test parameter_only.cache_hit
        @test parameter_only.status == "done"
        @test parameter_only.first_data_s < 0.3          # plan 5.12, measured warm
        @test BGSim.compile_build_count() == builds + 1
        @test isapprox(_cache_columns(p_dir)["G1/y"][end], 12.0; rtol = 1.0e-8)

        # 5. No parameter leakage: going back to the original value is a hit with y = 6.
        back_dir = mktempdir()
        back = simulate(flat; run_dir = back_dir, settings = settings)
        @test back.cache_hit
        @test BGSim.compile_build_count() == builds + 1
        @test isapprox(_cache_columns(back_dir)["G1/y"][end], 6.0; rtol = 1.0e-8)

        # 6. A structural edit misses the cache, compiles once and produces the new numbers.
        edited = _cache_flat(_cache_gain_model(
            source = replace(_CACHE_GAIN_BLOCK, "y ~ g * x" => "y ~ 2.0 * g * x"),
        ))
        @test BGSim.compile_key(edited) != key
        edited_dir = mktempdir()
        edited_run = simulate(edited; run_dir = edited_dir, settings = settings)
        @test edited_run.status == "done"
        @test !edited_run.cache_hit
        @test BGSim.compile_build_count() == builds + 2
        @test BGSim.cache_size() == 2
        @test isapprox(_cache_columns(edited_dir)["G1/y"][end], 12.0; rtol = 1.0e-8)

        # The edited model is cached too, and reverting still hits the original entry (the
        # cache is keyed by structure, so both compiled models coexist without leaking).
        @test simulate(edited; run_dir = mktempdir(), settings = settings).cache_hit
        back2_dir = mktempdir()
        back2 = simulate(flat; run_dir = back2_dir, settings = settings)
        @test back2.cache_hit
        @test BGSim.compile_build_count() == builds + 2
        @test isapprox(_cache_columns(back2_dir)["G1/y"][end], 6.0; rtol = 1.0e-8)

        # 7. `cache.clear` empties the cache; the next run recompiles.
        BGSim.clear_compile_cache!()
        @test BGSim.cache_size() == 0
        @test isempty(BGSim.compile_cache_keys())
        cleared_dir = mktempdir()
        cleared = simulate(flat; run_dir = cleared_dir, settings = settings)
        @test !cleared.cache_hit
        @test BGSim.compile_build_count() == builds + 3
        @test BGSim.cache_size() == 1
        @test isapprox(_cache_columns(cleared_dir)["G1/y"][end], 6.0; rtol = 1.0e-8)

        # 8. The cache is bounded and evicts least-recently-used entries. Store placeholder
        #    keys with a real `CompiledModel` so the policy is tested without compiling.
        @test BGSim.compile_cache_limit() >= 1
        model = l1.model
        limit = BGSim.compile_cache_limit()
        for k in 1:(limit + 2)
            BGSim._cache_store!("J2.8-placeholder-$k", model)
        end
        @test BGSim.cache_size() == limit
        keys_in_order = BGSim.compile_cache_keys()
        @test length(keys_in_order) == limit
        @test keys_in_order[end] == "J2.8-placeholder-$(limit + 2)"
        @test !("J2.8-placeholder-1" in keys_in_order)
        BGSim._cache_touch!("J2.8-placeholder-3")
        @test BGSim.compile_cache_keys()[end] == "J2.8-placeholder-3"
        BGSim.clear_compile_cache!()
        @test BGSim.cache_size() == 0

        println(
            "J2.8 timings: fresh compile+problem = ",
            round(1000 * cold.stats.compile_s; digits = 1),
            " ms, fresh run to first data = ", round(1000 * cold.first_data_s; digits = 1),
            " ms; parameter-only rerun (warm) = ",
            round(1000 * parameter_only.first_data_s; digits = 1),
            " ms (target < 300 ms; first after the change ",
            round(1000 * p_warm.first_data_s; digits = 1),
            " ms); structural edit (cache miss) = ",
            round(1000 * edited_run.first_data_s; digits = 1), " ms",
        )
    end
end
