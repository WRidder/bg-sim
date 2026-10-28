# Work package J-MB5: the full planar vector primitive set (plan 6, row J-MB5).
#
# Every planar element of the plan's element list has a block in `stdlib/multibond/`:
#
#   existing (J-MB4): IPlanar, SePlanar, SfPlanar, GroundPlanar, TFAd, ScrewTF,
#                     FixedTransform2D, CoriolisPlanar, ComposePose2D, DePlanar, DfPlanar,
#                     GravityPlanar, Revolute2D
#   added here:       CPlanar, RPlanar, MSePlanar, MSfPlanar, TFPlanar, GYPlanar,
#                     MTFPlanar, MGYPlanar, ExternalWrenchPlanar, JointTransform2D
#
# The suffixed name is the plan's element: `stdlib:multibond/XPlanar` is the planar `X`
# (`C`, `R`, `MSe`, `MSf`, `TF`, `GY`, `MTF`, `MGY`, `Se`, `Sf`, `De`, `Df`, `I`). The
# `Planar` suffix avoids a catalog-name collision with the scalar `stdlib:bondgraph/X` (a
# block name may not repeat in the catalog). `Gravity`/`Ground`/`De`/`Df` are **not**
# aliased: `Ground` already exists in `stdlib:electrical` and `De`/`Df` in
# `stdlib:bondgraph`, so a second block with those names would collide; the suffixed names
# (`GravityPlanar`, `GroundPlanar`, `DePlanar`, `DfPlanar`) are the plan's elements.
# `ComposePose2D` is the plan's `ComposePose` and `JointTransform2D` its `JointTransform`.
#
# Every element gets the plan 9.1 four checks: a constitutive relation against a hand
# calculation, a power-continuity identity, a per-component unit check (torque N*m vs force
# N, angular rate rad/s vs linear m/s) and a causality check. Two-port elements are driven
# with random twists/wrenches; the residuals are printed. The last testset is a closed
# bond graph (source, C, R, transformer, gyrator, sink) whose power ledger is conserved.
#
# All helpers are `_mb5_`-prefixed: the test files share `Main`.
using Test
using BGSim
import BGSim.IR
import BGSim.Compile
import BGSim.Library
import BGSim.Units
import JSON3
using LinearAlgebra

const _MB5_E_UNITS = ["N*m", "N", "N"]
const _MB5_F_UNITS = ["rad/s", "m/s", "m/s"]

const _MB5_NEW_REFS = [
    "stdlib:multibond/CPlanar",
    "stdlib:multibond/ExternalWrenchPlanar",
    "stdlib:multibond/GYPlanar",
    "stdlib:multibond/JointTransform2D",
    "stdlib:multibond/MGYPlanar",
    "stdlib:multibond/MSePlanar",
    "stdlib:multibond/MSfPlanar",
    "stdlib:multibond/MTFPlanar",
    "stdlib:multibond/RPlanar",
    "stdlib:multibond/TFPlanar",
]

# FIX-MB-4 additions: the matrix transformer pair (`a.f = M b.f`, `b.e = -M^T a.e`) and the
# frame-neutral adjoint that makes the rigid joint's parent side legal on a body 1-junction.
const _MB5_FIX_REFS = [
    "stdlib:multibond/MTFPlanarMat",
    "stdlib:multibond/TFAdNeutral",
    "stdlib:multibond/TFPlanarMat",
]

# ---------------------------------------------------------------------------------------
# Inline signal sources (parameterised, so a value sweep is a compile-cache hit: parameter
# values are not in the structural key, D4).
# ---------------------------------------------------------------------------------------

const _MB5_VEC_CONST = """
@block VecConst begin
    @parameters begin
        c1::Real = 0.0, [description = "Component 1"]
        c2::Real = 0.0, [description = "Component 2"]
        c3::Real = 0.0, [description = "Component 3"]
    end
    @outputs y::Vec{3}
    @equations begin
        y[1] ~ c1
        y[2] ~ c2
        y[3] ~ c3
    end
end
"""

const _MB5_VEC_SINE = """
@block VecSine begin
    @parameters begin
        a1::Real = 1.0, [description = "Amplitude 1"]
        a2::Real = 1.0, [description = "Amplitude 2"]
        a3::Real = 1.0, [description = "Amplitude 3"]
        w::Real = 1.0, [unit = "rad/s", description = "Angular frequency"]
    end
    @outputs y::Vec{3}
    @equations begin
        y[1] ~ a1 * sin(w * t)
        y[2] ~ a2 * sin(w * t)
        y[3] ~ a3 * sin(w * t)
    end
end
"""

const _MB5_SCALAR_CONST = """
@block ScalarConst begin
    @parameters v::Real = 0.0, [description = "Value"]
    @outputs y::Real
    @equations y ~ v
end
"""

const _MB5_MAT_CONST = """
@block MatConst begin
    @parameters begin
        g11::Real = 1.0, [description = "Entry 1,1"]
        g12::Real = 0.0, [description = "Entry 1,2"]
        g13::Real = 0.0, [description = "Entry 1,3"]
        g21::Real = 0.0, [description = "Entry 2,1"]
        g22::Real = 1.0, [description = "Entry 2,2"]
        g23::Real = 0.0, [description = "Entry 2,3"]
        g31::Real = 0.0, [description = "Entry 3,1"]
        g32::Real = 0.0, [description = "Entry 3,2"]
        g33::Real = 1.0, [description = "Entry 3,3"]
    end
    @outputs G::Mat{3,3}
    @equations begin
        G[1, 1] ~ g11
        G[1, 2] ~ g12
        G[1, 3] ~ g13
        G[2, 1] ~ g21
        G[2, 2] ~ g22
        G[2, 3] ~ g23
        G[3, 1] ~ g31
        G[3, 2] ~ g32
        G[3, 3] ~ g33
    end
end
"""

# A time-varying 3x3 matrix signal: `G[i,j] = gij + dij*sin(w t)`. The base `gij` keeps it
# invertible at t = 0 (a gyrator needs that), and the modulation is not a constant, so a
# latched input fails the constitutive relation at every later sample (FIX-MB-4).
const _MB5_MAT_SINE = """
@block MatSine begin
    @parameters begin
        g11::Real = 1.0, [description = "Base 1,1"]
        g12::Real = 0.0, [description = "Base 1,2"]
        g13::Real = 0.0, [description = "Base 1,3"]
        g21::Real = 0.0, [description = "Base 2,1"]
        g22::Real = 1.0, [description = "Base 2,2"]
        g23::Real = 0.0, [description = "Base 2,3"]
        g31::Real = 0.0, [description = "Base 3,1"]
        g32::Real = 0.0, [description = "Base 3,2"]
        g33::Real = 1.0, [description = "Base 3,3"]
        d11::Real = 0.0, [description = "Amplitude 1,1"]
        d12::Real = 0.0, [description = "Amplitude 1,2"]
        d13::Real = 0.0, [description = "Amplitude 1,3"]
        d21::Real = 0.0, [description = "Amplitude 2,1"]
        d22::Real = 0.0, [description = "Amplitude 2,2"]
        d23::Real = 0.0, [description = "Amplitude 2,3"]
        d31::Real = 0.0, [description = "Amplitude 3,1"]
        d32::Real = 0.0, [description = "Amplitude 3,2"]
        d33::Real = 0.0, [description = "Amplitude 3,3"]
        w::Real = 1.0, [unit = "rad/s", description = "Angular frequency"]
    end
    @outputs G::Mat{3,3}
    @equations begin
        G[1, 1] ~ g11 + d11 * sin(w * t)
        G[1, 2] ~ g12 + d12 * sin(w * t)
        G[1, 3] ~ g13 + d13 * sin(w * t)
        G[2, 1] ~ g21 + d21 * sin(w * t)
        G[2, 2] ~ g22 + d22 * sin(w * t)
        G[2, 3] ~ g23 + d23 * sin(w * t)
        G[3, 1] ~ g31 + d31 * sin(w * t)
        G[3, 2] ~ g32 + d32 * sin(w * t)
        G[3, 3] ~ g33 + d33 * sin(w * t)
    end
end
"""


# ---------------------------------------------------------------------------------------
# Model-document builders (the same shape as test_multibond_slice.jl)
# ---------------------------------------------------------------------------------------

function _mb5_settings(; t_end = 0.01, points = 2, reltol = 1.0e-10, abstol = 1.0e-12)
    return BGSim.RunSettings(
        t_start = 0.0, t_end = t_end, solver = "auto", reltol = reltol, abstol = abstol,
        output = Dict{String,Any}("mode" => "points", "points" => points),
    )
end

function _mb5_node(id, name, block; params = Dict{String,Any}(),
    starts = Dict{String,Any}())
    return Dict{String,Any}(
        "id" => id, "name" => name, "block" => block,
        "position" => Dict{String,Any}("x" => 0.0, "y" => 0.0),
        "params" => params, "constants" => Dict{String,Any}(), "starts" => starts,
    )
end

_mb5_ref(ref) = Dict{String,Any}("ref" => ref)
_mb5_inline(source) = Dict{String,Any}("inline" => Dict{String,Any}("source" => source))

function _mb5_conn(id, kind, from_node, from_port, to_node, to_port = nothing)
    function ep(node, port)
        port === nothing && return Dict{String,Any}("node" => node)
        return Dict{String,Any}("node" => node, "port" => port)
    end
    return Dict{String,Any}("id" => id, "kind" => kind,
        "from" => ep(from_node, from_port), "to" => ep(to_node, to_port))
end

function _mb5_doc(name, nodes, connections; t_end = 0.01, points = 2)
    return Dict{String,Any}(
        "format" => "bgsim.model", "language" => "0.1.0", "name" => name,
        "diagram" => Dict{String,Any}(
            "nodes" => Any[nodes...], "connections" => Any[connections...],
            "subsystemPorts" => Any[], "annotations" => Any[],
        ),
        "settings" => Dict{String,Any}(
            "t_start" => 0.0, "t_end" => t_end, "solver" => "auto",
            "reltol" => 1.0e-10, "abstol" => 1.0e-12, "max_step" => nothing,
            "output" => Dict{String,Any}("mode" => "points", "points" => points),
            "event_limit" => 10000,
        ),
        "plots" => Any[], "scene" => nothing, "bindings" => Any[],
    )
end

_mb5_flat(doc) = Compile.flatten(IR.parse_model(doc))
_mb5_check(doc) = Compile.model_check(IR.parse_model(doc))
_mb5_errors(result) = [d for d in result.diagnostics if d.severity == "error"]
_mb5_has(result, code) = any(d -> d.code == code, result.diagnostics)

function _mb5_run(doc; t_end = 0.01, points = 2, reltol = 1.0e-10, abstol = 1.0e-12)
    flat = _mb5_flat(doc)
    dir = mktempdir()
    result = simulate(flat; run_dir = dir,
        settings = _mb5_settings(t_end = t_end, points = points, reltol = reltol,
            abstol = abstol))
    return result, dir
end

"""The columns file as `id => Vector{Float64}`, plus `"time"`."""
function _mb5_columns(dir)
    m = JSON3.read(read(joinpath(dir, "manifest.json"), String))
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

"""The three components of `prefix` (`node/port.field`) at sample `i`."""
_mb5_at(data, prefix, i = 1) = [data["$prefix[$k]"][i] for k in 1:3]

"""Cumulative integral of `y` on the uniform grid `t`: composite Simpson on every even
prefix, plus one trapezoid step onto the next sample. Fourth-order accurate, so the
`ddt(q) = p.f` and energy identities can be asserted at the solver's own accuracy."""
function _mb5_cumint(t, y)
    n = length(t)
    out = zeros(Float64, n)
    h = t[2] - t[1]
    @test n >= 3
    out[2] = h / 2 * (y[1] + y[2])
    for i in 3:n
        if isodd(i)
            out[i] = out[i - 2] + h / 3 * (y[i - 2] + 4 * y[i - 1] + y[i])
        else
            out[i] = out[i - 1] + h / 2 * (y[i - 1] + y[i])
        end
    end
    return out
end

"""Simpson integration of `y` over the uniform grid `t` (odd number of samples)."""
function _mb5_simpson(t, y)
    n = length(t)
    @test n >= 3
    @test isodd(n)
    h = t[2] - t[1]
    s = y[1] + y[end]
    for i in 2:2:(n - 1)
        s += 4 * y[i]
    end
    for i in 3:2:(n - 2)
        s += 2 * y[i]
    end
    return s * h / 3
end

"""A deterministic uniform generator in `[lo, hi)`; the tests are reproducible and need no
`Random` dependency (the toolbox must not add packages for a test)."""
function _mb5_rng(seed::Integer, lo::Float64 = -1.0, hi::Float64 = 1.0)
    state = Ref{UInt64}(UInt64(seed) * 0x9e3779b97f4a7c15 + 0x1234_5678)
    return function ()
        state[] = state[] * 6364136223846793005 + 1442695040888963407
        u = Float64((state[] >> 11) & 0x1fffffffffffff) / 9.007199254740992e15
        return lo + (hi - lo) * u
    end
end

"""`node.port.e`/`.f` series of one port as a 3-vector at every sample."""
_mb5_port_matrix(data, prefix) =
    [data["$prefix[$k]"] for k in 1:3]

"""Relative power residual `|a.e.a.f + b.e.b.f| / max(1, |a.e.a.f|, |b.e.b.f|)` at sample i."""
function _mb5_power_residual(data, pa, pb, i)
    ae, af = _mb5_at(data, "$pa.e", i), _mb5_at(data, "$pa.f", i)
    be, bf = _mb5_at(data, "$pb.e", i), _mb5_at(data, "$pb.f", i)
    lhs = sum(ae[k] * af[k] for k in 1:3)
    rhs = sum(be[k] * bf[k] for k in 1:3)
    return abs(lhs + rhs) / max(1.0, abs(lhs), abs(rhs))
end

_mb5_unit(b, scope::Symbol, name::AbstractString) =
    only([d for d in getproperty(b.interface, scope) if d.name == name]).unit

@testset "J-MB5 planar vector primitives" begin
    # -----------------------------------------------------------------------------------
    # Catalog contract
    # -----------------------------------------------------------------------------------
    @testset "catalog: clean, dimension 2, per-component units, frames" begin
        blocks = Dict(b.ref => b for b in Library.load_stdlib())
        for ref in vcat(_MB5_NEW_REFS, _MB5_FIX_REFS)
            b = blocks[ref]
            @test b.group == "Multibond"
            @test b.interface.dimension == 2
            @test isempty(check_block(b.ast))          # 0 errors and 0 warnings (no W204)
            bal = block_balance(b.ast)
            @test bal.unknowns == bal.equations
            @test !isempty(b.description)
            @test !isempty(b.icon)
            # Every parameter and input has a description (plan section 8).
            for d in b.interface.parameters
                @test !isempty(d.description)
            end
            # Every Planar port carries the authoritative per-component units (D-MB2/D-MB10)
            # and a `frame` field (null = frame-neutral, D-MB5).
            env = Units.unit_env(b.ast)
            @test any(p -> p.domain == "Planar", b.interface.ports)
            for p in b.interface.ports
                @test haskey(p, :frame)
                p.domain == "Planar" || continue
                @test p.size == [3]
                for k in 1:3
                    @test env.labels[Symbol(p.name, ".e[", string(k), "]")] ==
                          _MB5_E_UNITS[k]
                    @test env.labels[Symbol(p.name, ".f[", string(k), "]")] ==
                          _MB5_F_UNITS[k]
                end
            end
            @test isempty([d for d in check_block(b.ast) if d.code == "E006"])
        end

        # The constitutive parameters carry the per-component stiffness/damping units.
        c = blocks["stdlib:multibond/CPlanar"]
        @test _mb5_unit(c, :parameters, "kr") == "N*m/rad"
        @test _mb5_unit(c, :parameters, "kx") == "N/m"
        @test _mb5_unit(c, :parameters, "ky") == "N/m"
        @test _mb5_unit(c, :variables, "qr") == "rad"
        @test _mb5_unit(c, :variables, "qx") == "m"
        @test _mb5_unit(c, :variables, "qy") == "m"
        @test c.interface.causality == [(ports = ["p"], kind = "preferred", value = "effort_out")]
        r = blocks["stdlib:multibond/RPlanar"]
        @test _mb5_unit(r, :parameters, "br") == "N*m*s/rad"
        @test _mb5_unit(r, :parameters, "bx") == "N*s/m"
        @test _mb5_unit(r, :parameters, "by") == "N*s/m"
        @test isempty(r.interface.causality)          # free, exactly like the scalar R

        mse = blocks["stdlib:multibond/MSePlanar"]
        @test [_mb5_unit(mse, :inputs, n) for n in ("ur", "ux", "uy")] ==
              ["N*m", "N", "N"]
        @test mse.interface.causality ==
              [(ports = ["p"], kind = "fixed", value = "effort_out")]
        msf = blocks["stdlib:multibond/MSfPlanar"]
        @test [_mb5_unit(msf, :inputs, n) for n in ("vr", "vx", "vy")] ==
              ["rad/s", "m/s", "m/s"]
        @test msf.interface.causality ==
              [(ports = ["p"], kind = "fixed", value = "flow_out")]
        ew = blocks["stdlib:multibond/ExternalWrenchPlanar"]
        @test [_mb5_unit(ew, :inputs, n) for n in ("wr", "wx", "wy")] ==
              ["N*m", "N", "N"]
        @test ew.interface.causality ==
              [(ports = ["p"], kind = "fixed", value = "effort_out")]
        @test [(d.name, d.size) for d in ew.interface.inputs] ==
              [("wr", Int[]), ("wx", Int[]), ("wy", Int[])]

        # The diagonal modulus is dimensionless (so the checker still proves each port keeps
        # its own component unit through the transformer).
        tf = blocks["stdlib:multibond/TFPlanar"]
        @test _mb5_unit(tf, :parameters, "n") == "1"
        @test length(tf.interface.variables) == 0
        @test tf.interface.causality ==
              [(ports = ["a", "b"], kind = "transformer", value = nothing)]
        mtf = blocks["stdlib:multibond/MTFPlanar"]
        @test _mb5_unit(mtf, :inputs, "u") == "1"
        @test [(d.name, d.size) for d in mtf.interface.inputs] == [("u", [3])]

        # The matrix gyrators: a general planar gyrator matrix is not unit-homogeneous (a
        # torque next to two forces), so the nine entries carry no single unit and the block
        # documents that; the port components still carry their own units (asserted above).
        gy = blocks["stdlib:multibond/GYPlanar"]
        @test _mb5_unit(gy, :parameters, "G") === nothing
        @test gy.interface.parameters[1].type == "Real"
        @test count(==(';'), gy.interface.parameters[1].default) == 2    # three rows
        @test gy.interface.causality ==
              [(ports = ["a", "b"], kind = "gyrator", value = nothing)]
        mgy = blocks["stdlib:multibond/MGYPlanar"]
        @test _mb5_unit(mgy, :inputs, "G") === nothing
        @test [(d.name, d.size) for d in mgy.interface.inputs] == [("G", [3, 3])]

        # FIX-MB-4: the general matrix transformer (no inverse needed) and the frame-neutral
        # adjoint. A Mat carries one unit slot, so the matrix has no unit; the port components
        # above still carry their own.
        tfm = blocks["stdlib:multibond/TFPlanarMat"]
        @test _mb5_unit(tfm, :parameters, "M") === nothing
        @test count(==(';'), tfm.interface.parameters[1].default) == 2
        @test tfm.interface.causality ==
              [(ports = ["a", "b"], kind = "transformer", value = nothing)]
        mtfm = blocks["stdlib:multibond/MTFPlanarMat"]
        @test _mb5_unit(mtfm, :inputs, "M") === nothing
        @test [(d.name, d.size) for d in mtfm.interface.inputs] == [("M", [3, 3])]
        @test mtfm.interface.causality ==
              [(ports = ["a", "b"], kind = "transformer", value = nothing)]
        tfn = blocks["stdlib:multibond/TFAdNeutral"]
        @test all(p -> p.frame === nothing, tfn.interface.ports)
        @test [(d.name, d.size) for d in tfn.interface.inputs] == [("g", [3])]
        @test tfn.interface.causality ==
              [(ports = ["a", "b"], kind = "transformer", value = nothing)]

        # The joint transform is the joint-role frame bridge: two *different* named frames.
        jt = blocks["stdlib:multibond/JointTransform2D"]
        @test [p.frame for p in jt.interface.ports] == ["parent", "child"]
        @test [(d.name, d.size) for d in jt.interface.inputs] == [("g", [3])]
        @test jt.interface.causality ==
              [(ports = ["a", "b"], kind = "transformer", value = nothing)]
    end

    # -----------------------------------------------------------------------------------
    # One-port storage and dissipation
    # -----------------------------------------------------------------------------------
    @testset "CPlanar: ddt(q) = p.f, the spring law, the stored energy, causality" begin
        doc = _mb5_doc(
            "CPlanarEnergy",
            Any[
                _mb5_node("n1", "U", _mb5_inline(_MB5_VEC_SINE);
                    params = Dict{String,Any}("a1" => "0.4", "a2" => "-0.25",
                        "a3" => "0.3", "w" => "1.3")),
                _mb5_node("n2", "F", _mb5_ref("stdlib:multibond/SfPlanar")),
                _mb5_node("n3", "C", _mb5_ref("stdlib:multibond/CPlanar");
                    params = Dict{String,Any}("kr" => "220.0", "kx" => "90.0",
                        "ky" => "140.0"),
                    starts = Dict{String,Any}("qr" => "0.02", "qx" => "-0.01",
                        "qy" => "0.015")),
            ],
            Any[
                _mb5_conn("c1", "signal", "n1", "y", "n2", "u"),
                _mb5_conn("c2", "bond", "n2", "p", "n3", "p"),
            ];
            t_end = 2.0, points = 2001,
        )
        @test isempty(_mb5_errors(_mb5_check(doc)))
        # Integral (effort-out) causality: the C imposes the effort, so the stroke sits on
        # the source end where the effort is the input to the source. No derivative causal
        # storage (W201) and no arbitrary choice (W202).
        causality = _mb5_check(doc).causality
        @test causality["c2"].strokeAt == "from"
        result, dir = _mb5_run(doc; t_end = 2.0, points = 2001)
        @test result.status == "done"
        @test !_mb5_has(result, "W201")
        @test !_mb5_has(result, "W202")
        data = _mb5_columns(dir)
        t = data["time"]
        q0 = [0.02, -0.01, 0.015]
        k = [220.0, 90.0, 140.0]
        scales = ["qr", "qx", "qy"]
        for (j, name) in enumerate(scales)
            q = data["C/$name"]
            f = data["C/p.f[$j]"]
            e = data["C/p.e[$j]"]
            # ddt(q) = p.f[k]: the state is the integral of its own port flow.
            @test isapprox(q .- q0[j], _mb5_cumint(t, f); atol = 1e-8)
            # The spring law with a zero rest deflection.
            @test all(isapprox.(e, k[j] .* q; rtol = 1e-12, atol = 1e-12))
        end
        # The stored energy 1/2 k q^2 changes by exactly the port power integral.
        energy = 0.5 .* (k[1] .* data["C/qr"] .^ 2 .+ k[2] .* data["C/qx"] .^ 2 .+
                         k[3] .* data["C/qy"] .^ 2)
        port_power = [sum(data["C/p.e[$jj]"][i] * data["C/p.f[$jj]"][i] for jj in 1:3)
                      for i in eachindex(t)]
        stored = _mb5_simpson(t, port_power)
        @test isapprox(energy[end] - energy[1], stored; rtol = 1e-7, atol = 1e-10)
        @test maximum(abs.(energy)) > 1e-3          # the test is not vacuous
        println("J-MB5 CPlanar energy balance: |dE - int P| = ",
            abs(energy[end] - energy[1] - stored), " J of ", maximum(abs.(energy)), " J")
    end

    @testset "FIX-MB-4: CPlanar with a nonzero rest: e = k(q - q0), E = 1/2 k (q - q0)^2" begin
        # The J-MB5 test drove the C from a zero rest, where `q - q0` and `q` are the same
        # expression. A nonzero rest makes the reference load-bearing in both the effort law
        # and the stored energy.
        k = [220.0, 90.0, 140.0]
        q0 = [0.03, -0.02, 0.05]
        qstart = [0.05, -0.05, 0.07]
        doc = _mb5_doc(
            "CPlanarRest",
            Any[
                _mb5_node("n1", "U", _mb5_inline(_MB5_VEC_SINE);
                    params = Dict{String,Any}("a1" => "0.4", "a2" => "-0.25",
                        "a3" => "0.3", "w" => "1.3")),
                _mb5_node("n2", "F", _mb5_ref("stdlib:multibond/SfPlanar")),
                _mb5_node("n3", "C", _mb5_ref("stdlib:multibond/CPlanar");
                    params = Dict{String,Any}("kr" => string(k[1]), "kx" => string(k[2]),
                        "ky" => string(k[3]), "qr0" => string(q0[1]),
                        "qx0" => string(q0[2]), "qy0" => string(q0[3])),
                    starts = Dict{String,Any}("qr" => string(qstart[1]),
                        "qx" => string(qstart[2]), "qy" => string(qstart[3]))),
            ],
            Any[
                _mb5_conn("c1", "signal", "n1", "y", "n2", "u"),
                _mb5_conn("c2", "bond", "n2", "p", "n3", "p"),
            ];
            t_end = 2.0, points = 2001,
        )
        @test isempty(_mb5_errors(_mb5_check(doc)))
        result, dir = _mb5_run(doc; t_end = 2.0, points = 2001)
        @test result.status == "done"
        @test !_mb5_has(result, "W201")
        data = _mb5_columns(dir)
        t = data["time"]
        states = [data["C/qr"], data["C/qx"], data["C/qy"]]
        for j in 1:3
            q = states[j]
            @test isapprox(q[1], qstart[j]; atol = 1e-12)
            # e = k (q - q0): the rest offset is inside the spring law.
            @test all(isapprox.(data["C/p.e[$j]"], k[j] .* (q .- q0[j]);
                rtol = 1e-12, atol = 1e-12))
            # ... and the stored energy is measured from the rest, not from zero.
            @test isapprox(data["C/p.e[$j]"][1], k[j] * (qstart[j] - q0[j]); rtol = 1e-12)
        end
        energy = 0.5 .* (k[1] .* (states[1] .- q0[1]) .^ 2 .+
                         k[2] .* (states[2] .- q0[2]) .^ 2 .+
                         k[3] .* (states[3] .- q0[3]) .^ 2)
        port_power = [sum(data["C/p.e[$jj]"][i] * data["C/p.f[$jj]"][i] for jj in 1:3)
                      for i in eachindex(t)]
        stored = _mb5_simpson(t, port_power)
        @test isapprox(energy[end] - energy[1], stored; rtol = 1e-7, atol = 1e-10)
        # The rest is load-bearing: E(0) is not zero and the q0 = 0 formula would be wrong.
        @test energy[1] > 1e-3
        zero_rest = 0.5 .* (k[1] .* states[1][1]^2 + k[2] .* states[2][1]^2 +
                            k[3] .* states[3][1]^2)
        @test abs(zero_rest - energy[1]) > 1e-3
        println("CPlanar nonzero rest: E0 = ", energy[1], " J, |dE - int P| = ",
            abs(energy[end] - energy[1] - stored), " J")
    end


    @testset "RPlanar: p.e = b.p.f, positive dissipation, free causality" begin
        b = [0.6, 0.35, 0.45]
        v = [0.8, -0.6, 0.5]
        doc = _mb5_doc(
            "RPlanarConstitutive",
            Any[
                _mb5_node("n1", "U", _mb5_inline(_MB5_VEC_CONST);
                    params = Dict{String,Any}("c1" => string(v[1]), "c2" => string(v[2]),
                        "c3" => string(v[3]))),
                _mb5_node("n2", "F", _mb5_ref("stdlib:multibond/SfPlanar")),
                _mb5_node("n3", "R", _mb5_ref("stdlib:multibond/RPlanar");
                    params = Dict{String,Any}("br" => string(b[1]), "bx" => string(b[2]),
                        "by" => string(b[3]))),
            ],
            Any[
                _mb5_conn("c1", "signal", "n1", "y", "n2", "u"),
                _mb5_conn("c2", "bond", "n2", "p", "n3", "p"),
            ],
        )
        @test isempty(_mb5_errors(_mb5_check(doc)))
        result, dir = _mb5_run(doc)
        @test result.status == "done"
        data = _mb5_columns(dir)
        e = _mb5_at(data, "R/p.e")
        f = _mb5_at(data, "R/p.f")
        @test isapprox(f, -v; atol = 1e-12)          # the source bond flips the flow
        @test isapprox(e, b .* f; atol = 1e-12)
        power = sum(e[j] * f[j] for j in 1:3)
        @test power ≈ sum(b[j] * f[j]^2 for j in 1:3) atol = 1e-14
        @test power > 0                               # dissipated, never generated
        @test data["R/p.P"][1] ≈ power atol = 1e-14
        println("J-MB5 RPlanar dissipation residual = ",
            abs(power - sum(b[j] * f[j]^2 for j in 1:3)), " W of ", power, " W")
    end

    # -----------------------------------------------------------------------------------
    # Sources
    # -----------------------------------------------------------------------------------
    @testset "MSePlanar and MSfPlanar: three scalar inputs with their own units" begin
        u = (1.7, -2.4, 0.9)
        doc = _mb5_doc(
            "MSePlanarSource",
            Any[
                _mb5_node("n1", "Ur", _mb5_inline(_MB5_SCALAR_CONST);
                    params = Dict{String,Any}("v" => string(u[1]))),
                _mb5_node("n2", "Ux", _mb5_inline(_MB5_SCALAR_CONST);
                    params = Dict{String,Any}("v" => string(u[2]))),
                _mb5_node("n3", "Uy", _mb5_inline(_MB5_SCALAR_CONST);
                    params = Dict{String,Any}("v" => string(u[3]))),
                _mb5_node("n4", "S", _mb5_ref("stdlib:multibond/MSePlanar")),
                _mb5_node("n5", "D", _mb5_ref("stdlib:multibond/DePlanar")),
            ],
            Any[
                _mb5_conn("c1", "signal", "n1", "y", "n4", "ur"),
                _mb5_conn("c2", "signal", "n2", "y", "n4", "ux"),
                _mb5_conn("c3", "signal", "n3", "y", "n4", "uy"),
                _mb5_conn("c4", "bond", "n4", "p", "n5", "p"),
            ],
        )
        @test isempty(_mb5_errors(_mb5_check(doc)))
        causality = _mb5_check(doc).causality
        @test causality["c4"].strokeAt == "to"      # the effort enters at the source end
        result, dir = _mb5_run(doc)
        @test result.status == "done"
        data = _mb5_columns(dir)
        @test isapprox(_mb5_at(data, "S/p.e"), collect(u); atol = 1e-13)
        @test isapprox(_mb5_at(data, "D/y"), collect(u); atol = 1e-13)
        @test all(_mb5_at(data, "S/p.f") .== 0.0)   # the De imposes zero twist

        v = (0.55, -0.35, 0.25)
        docf = _mb5_doc(
            "MSfPlanarSource",
            Any[
                _mb5_node("n1", "Vr", _mb5_inline(_MB5_SCALAR_CONST);
                    params = Dict{String,Any}("v" => string(v[1]))),
                _mb5_node("n2", "Vx", _mb5_inline(_MB5_SCALAR_CONST);
                    params = Dict{String,Any}("v" => string(v[2]))),
                _mb5_node("n3", "Vy", _mb5_inline(_MB5_SCALAR_CONST);
                    params = Dict{String,Any}("v" => string(v[3]))),
                _mb5_node("n4", "S", _mb5_ref("stdlib:multibond/MSfPlanar")),
                _mb5_node("n5", "D", _mb5_ref("stdlib:multibond/DfPlanar")),
            ],
            Any[
                _mb5_conn("c1", "signal", "n1", "y", "n4", "vr"),
                _mb5_conn("c2", "signal", "n2", "y", "n4", "vx"),
                _mb5_conn("c3", "signal", "n3", "y", "n4", "vy"),
                _mb5_conn("c4", "bond", "n4", "p", "n5", "p"),
            ],
        )
        @test isempty(_mb5_errors(_mb5_check(docf)))
        @test _mb5_check(docf).causality["c4"].strokeAt == "from"
        resultf, dirf = _mb5_run(docf)
        @test resultf.status == "done"
        dataf = _mb5_columns(dirf)
        @test isapprox(_mb5_at(dataf, "S/p.f"), collect(v); atol = 1e-13)
        @test isapprox(_mb5_at(dataf, "D/y"), -collect(v); atol = 1e-13)
        @test all(_mb5_at(dataf, "S/p.e") .== 0.0)
    end

    @testset "ExternalWrenchPlanar: the wrench source and its 1-junction sign" begin
        w = (2.5, -1.5, 0.8)
        doc = _mb5_doc(
            "ExternalWrenchSource",
            Any[
                _mb5_node("n1", "Wr", _mb5_inline(_MB5_SCALAR_CONST);
                    params = Dict{String,Any}("v" => string(w[1]))),
                _mb5_node("n2", "Wx", _mb5_inline(_MB5_SCALAR_CONST);
                    params = Dict{String,Any}("v" => string(w[2]))),
                _mb5_node("n3", "Wy", _mb5_inline(_MB5_SCALAR_CONST);
                    params = Dict{String,Any}("v" => string(w[3]))),
                _mb5_node("n4", "E", _mb5_ref("stdlib:multibond/ExternalWrenchPlanar")),
                _mb5_node("n5", "D", _mb5_ref("stdlib:multibond/DePlanar")),
            ],
            Any[
                _mb5_conn("c1", "signal", "n1", "y", "n4", "wr"),
                _mb5_conn("c2", "signal", "n2", "y", "n4", "wx"),
                _mb5_conn("c3", "signal", "n3", "y", "n4", "wy"),
                _mb5_conn("c4", "bond", "n4", "p", "n5", "p"),
            ],
        )
        @test isempty(_mb5_errors(_mb5_check(doc)))
        @test _mb5_check(doc).causality["c4"].strokeAt == "to"
        result, dir = _mb5_run(doc)
        @test result.status == "done"
        data = _mb5_columns(dir)
        # FIX-MB-4: the inputs are the **physical external wrench** `W_ext`; the element is an
        # effort source, so its port effort is `-W_ext` (the wrench it supplies to the
        # junction). The detector therefore reads `-w`.
        @test isapprox(_mb5_at(data, "E/p.e"), -collect(w); atol = 1e-13)
        @test isapprox(_mb5_at(data, "D/y"), -collect(w); atol = 1e-14)
        @test all(_mb5_at(data, "E/p.f") .== 0.0)

        # The sign convention: the body on the 1-junction feels the physical wrench, so
        # dP/dt = +w and a constant external wrench ramps the momentum exactly as +w*t.
        P0 = [0.02, -0.03, 0.04]
        sign_doc = _mb5_doc(
            "ExternalWrenchSign",
            Any[
                _mb5_node("n1", "Wr", _mb5_inline(_MB5_SCALAR_CONST);
                    params = Dict{String,Any}("v" => string(w[1]))),
                _mb5_node("n2", "Wx", _mb5_inline(_MB5_SCALAR_CONST);
                    params = Dict{String,Any}("v" => string(w[2]))),
                _mb5_node("n3", "Wy", _mb5_inline(_MB5_SCALAR_CONST);
                    params = Dict{String,Any}("v" => string(w[3]))),
                _mb5_node("n4", "E", _mb5_ref("stdlib:multibond/ExternalWrenchPlanar")),
                _mb5_node("n5", "J", Dict{String,Any}("junction" => "1")),
                _mb5_node("n6", "B", _mb5_ref("stdlib:multibond/IPlanar");
                    params = Dict{String,Any}("J" => "0.05", "m" => "1.5"),
                    starts = Dict{String,Any}("P" => "[$(P0[1]), $(P0[2]), $(P0[3])]")),
            ],
            Any[
                _mb5_conn("c1", "signal", "n1", "y", "n4", "wr"),
                _mb5_conn("c2", "signal", "n2", "y", "n4", "wx"),
                _mb5_conn("c3", "signal", "n3", "y", "n4", "wy"),
                _mb5_conn("c4", "bond", "n4", "p", "n5"),
                _mb5_conn("c5", "bond", "n6", "p", "n5"),
            ];
            t_end = 0.1, points = 11,
        )
        @test isempty(_mb5_errors(_mb5_check(sign_doc)))
        @test !_mb5_has(_mb5_check(sign_doc), "W201")
        results, dirs = _mb5_run(sign_doc; t_end = 0.1, points = 11)
        @test results.status == "done"
        datas = _mb5_columns(dirs)
        for k in 1:3
            @test all(isapprox.(datas["B/P[$k]"], P0[k] .+ w[k] .* datas["time"];
                atol = 1e-10))
        end
    end

    # -----------------------------------------------------------------------------------
    # Transformers and gyrators
    # -----------------------------------------------------------------------------------
    @testset "TFPlanar: the diagonal modulus and power continuity" begin
        rng = _mb5_rng(20261028)
        worst = 0.0
        for case in 1:4
            n = [1.0 + 0.9 * (case - 1) / 3, -1.4 + 0.3 * case, 0.6 + 0.2 * case]
            E = [rng(), rng(), rng()]
            F = [rng(), rng(), rng()]
            doc = _mb5_doc(
                "TFPlanarPower$case",
                Any[
                    _mb5_node("n1", "Ue", _mb5_inline(_MB5_VEC_CONST);
                        params = Dict{String,Any}("c1" => string(E[1]),
                            "c2" => string(E[2]), "c3" => string(E[3]))),
                    _mb5_node("n2", "Uf", _mb5_inline(_MB5_VEC_CONST);
                        params = Dict{String,Any}("c1" => string(F[1]),
                            "c2" => string(F[2]), "c3" => string(F[3]))),
                    _mb5_node("n3", "A", _mb5_ref("stdlib:multibond/SePlanar")),
                    _mb5_node("n4", "B", _mb5_ref("stdlib:multibond/SfPlanar")),
                    _mb5_node("n5", "T", _mb5_ref("stdlib:multibond/TFPlanar");
                        params = Dict{String,Any}("n" => "[$(n[1]), $(n[2]), $(n[3])]")),
                ],
                Any[
                    _mb5_conn("c1", "signal", "n1", "y", "n3", "u"),
                    _mb5_conn("c2", "signal", "n2", "y", "n4", "u"),
                    _mb5_conn("c3", "bond", "n3", "p", "n5", "a"),
                    _mb5_conn("c4", "bond", "n5", "b", "n4", "p"),
                ],
            )
            @test isempty(_mb5_errors(_mb5_check(doc)))
            result, dir = _mb5_run(doc)
            @test result.status == "done"
            data = _mb5_columns(dir)
            ae, af = _mb5_at(data, "T/a.e"), _mb5_at(data, "T/a.f")
            be, bf = _mb5_at(data, "T/b.e"), _mb5_at(data, "T/b.f")
            @test isapprox(ae, E; atol = 1e-12)
            @test isapprox(bf, -F; atol = 1e-12)
            @test isapprox(af, n .* bf; atol = 1e-12)
            @test isapprox(be, -n .* ae; atol = 1e-12)
            res = _mb5_power_residual(data, "T/a", "T/b", 1)
            worst = max(worst, res)
            @test res <= 1e-12
            # The derived port powers agree with the element's own sum.
            @test data["T/a.P"][1] ≈ sum(ae[k] * af[k] for k in 1:3) atol = 1e-12
            @test data["T/b.P"][1] ≈ -data["T/a.P"][1] atol = 1e-12
        end
        println("J-MB5 TFPlanar worst power residual = ", worst)
    end

    @testset "GYPlanar: random matrix, Se + R load, power continuity" begin
        rng = _mb5_rng(424242)
        worst = 0.0
        for case in 1:4
            # A well-conditioned random matrix (the load-terminated test needs G invertible
            # to give the port a finite flow; the element itself never inverts G).
            G = [2.0+rng() 0.5*rng() 0.4*rng()
                 0.6*rng() 1.5+rng() 0.3*rng()
                 0.5*rng() 0.4*rng() 1.2+rng()]
            r = [0.7 + abs(rng()), 0.9 + abs(rng()), 1.1 + abs(rng())]
            E = [rng(), rng(), rng()]
            doc = _mb5_doc(
                "GYPlanarPower$case",
                Any[
                    _mb5_node("n1", "Ue", _mb5_inline(_MB5_VEC_CONST);
                        params = Dict{String,Any}("c1" => string(E[1]),
                            "c2" => string(E[2]), "c3" => string(E[3]))),
                    _mb5_node("n2", "A", _mb5_ref("stdlib:multibond/SePlanar")),
                    _mb5_node("n3", "G", _mb5_ref("stdlib:multibond/GYPlanar");
                        params = Dict{String,Any}("G" =>
                            "[$(G[1,1]) $(G[1,2]) $(G[1,3]); $(G[2,1]) $(G[2,2]) $(G[2,3]); $(G[3,1]) $(G[3,2]) $(G[3,3])]")),
                    _mb5_node("n4", "R", _mb5_ref("stdlib:multibond/RPlanar");
                        params = Dict{String,Any}("br" => string(r[1]),
                            "bx" => string(r[2]), "by" => string(r[3]))),
                ],
                Any[
                    _mb5_conn("c1", "signal", "n1", "y", "n2", "u"),
                    _mb5_conn("c2", "bond", "n2", "p", "n3", "a"),
                    _mb5_conn("c3", "bond", "n4", "p", "n3", "b"),
                ],
            )
            @test isempty(_mb5_errors(_mb5_check(doc)))
            result, dir = _mb5_run(doc)
            @test result.status == "done"
            data = _mb5_columns(dir)
            ae, af = _mb5_at(data, "G/a.e"), _mb5_at(data, "G/a.f")
            be, bf = _mb5_at(data, "G/b.e"), _mb5_at(data, "G/b.f")
            @test isapprox(ae, E; atol = 1e-11)
            # a.e = G b.f and b.e = -G^T a.f, component-wise.
            @test isapprox(ae, G * bf; atol = 1e-11)
            @test isapprox(be, -transpose(G) * af; atol = 1e-11)
            # The R load: GY.b.e = -r .* GY.b.f, so b.f = (G^T a.f) ./ r and a.f solves
            # (G diag(1/r) G^T) a.f = E. This pins the transpose ordering.
            @test isapprox(bf, (transpose(G) * af) ./ r; atol = 1e-11)
            expected_af = inv(G * Diagonal(1.0 ./ r) * transpose(G)) * E
            @test isapprox(af, expected_af; atol = 1e-10)
            @test norm(af) > 1e-3
            res = _mb5_power_residual(data, "G/a", "G/b", 1)
            worst = max(worst, res)
            @test res <= 1e-12
        end
        println("J-MB5 GYPlanar worst power residual (random G) = ", worst)
    end

    @testset "MTFPlanar: the modulated diagonal modulus" begin
        worst = 0.0
        for (case, u) in enumerate(([1.5, 0.4, -2.0], [-0.75, 1.25, 0.5]))
            E = [0.9, -1.1, 0.6]
            F = [-0.4, 0.7, 0.35]
            doc = _mb5_doc(
                "MTFPlanarPower$case",
                Any[
                    _mb5_node("n1", "Ue", _mb5_inline(_MB5_VEC_CONST);
                        params = Dict{String,Any}("c1" => string(E[1]),
                            "c2" => string(E[2]), "c3" => string(E[3]))),
                    _mb5_node("n2", "Uf", _mb5_inline(_MB5_VEC_CONST);
                        params = Dict{String,Any}("c1" => string(F[1]),
                            "c2" => string(F[2]), "c3" => string(F[3]))),
                    _mb5_node("n3", "Uu", _mb5_inline(_MB5_VEC_CONST);
                        params = Dict{String,Any}("c1" => string(u[1]),
                            "c2" => string(u[2]), "c3" => string(u[3]))),
                    _mb5_node("n4", "A", _mb5_ref("stdlib:multibond/SePlanar")),
                    _mb5_node("n5", "B", _mb5_ref("stdlib:multibond/SfPlanar")),
                    _mb5_node("n6", "T", _mb5_ref("stdlib:multibond/MTFPlanar")),
                ],
                Any[
                    _mb5_conn("c1", "signal", "n1", "y", "n4", "u"),
                    _mb5_conn("c2", "signal", "n2", "y", "n5", "u"),
                    _mb5_conn("c3", "signal", "n3", "y", "n6", "u"),
                    _mb5_conn("c4", "bond", "n4", "p", "n6", "a"),
                    _mb5_conn("c5", "bond", "n6", "b", "n5", "p"),
                ],
            )
            @test isempty(_mb5_errors(_mb5_check(doc)))
            result, dir = _mb5_run(doc)
            @test result.status == "done"
            data = _mb5_columns(dir)
            ae, af = _mb5_at(data, "T/a.e"), _mb5_at(data, "T/a.f")
            be, bf = _mb5_at(data, "T/b.e"), _mb5_at(data, "T/b.f")
            @test isapprox(ae, E; atol = 1e-12)
            @test isapprox(bf, -F; atol = 1e-12)
            @test isapprox(af, u .* bf; atol = 1e-12)
            @test isapprox(be, -u .* ae; atol = 1e-12)
            res = _mb5_power_residual(data, "T/a", "T/b", 1)
            worst = max(worst, res)
            @test res <= 1e-12
        end
        println("J-MB5 MTFPlanar worst power residual = ", worst)
    end

    @testset "MGYPlanar: the matrix signal input" begin
        G = [1.4 -0.3 0.2
             0.5 2.1 -0.4
             -0.25 0.35 1.7]
        r = [1.2, 0.8, 1.5]
        E = [1.1, -0.9, 0.6]
        params = Dict{String,Any}()
        for i in 1:3, j in 1:3
            params["g$i$j"] = string(G[i, j])
        end
        doc = _mb5_doc(
            "MGYPlanarPower",
            Any[
                _mb5_node("n1", "Ue", _mb5_inline(_MB5_VEC_CONST);
                    params = Dict{String,Any}("c1" => string(E[1]),
                        "c2" => string(E[2]), "c3" => string(E[3]))),
                _mb5_node("n2", "Ug", _mb5_inline(_MB5_MAT_CONST); params = params),
                _mb5_node("n3", "A", _mb5_ref("stdlib:multibond/SePlanar")),
                _mb5_node("n4", "G", _mb5_ref("stdlib:multibond/MGYPlanar")),
                _mb5_node("n5", "R", _mb5_ref("stdlib:multibond/RPlanar");
                    params = Dict{String,Any}("br" => string(r[1]),
                        "bx" => string(r[2]), "by" => string(r[3]))),
            ],
            Any[
                _mb5_conn("c1", "signal", "n1", "y", "n3", "u"),
                _mb5_conn("c2", "signal", "n2", "G", "n4", "G"),
                _mb5_conn("c3", "bond", "n3", "p", "n4", "a"),
                _mb5_conn("c4", "bond", "n5", "p", "n4", "b"),
            ],
        )
        @test isempty(_mb5_errors(_mb5_check(doc)))
        result, dir = _mb5_run(doc)
        @test result.status == "done"
        data = _mb5_columns(dir)
        ae, af = _mb5_at(data, "G/a.e"), _mb5_at(data, "G/a.f")
        be, bf = _mb5_at(data, "G/b.e"), _mb5_at(data, "G/b.f")
        @test isapprox(ae, E; atol = 1e-11)
        @test isapprox(ae, G * bf; atol = 1e-11)
        @test isapprox(be, -transpose(G) * af; atol = 1e-11)
        expected_af = inv(G * Diagonal(1.0 ./ r) * transpose(G)) * E
        @test isapprox(af, expected_af; atol = 1e-10)
        @test _mb5_power_residual(data, "G/a", "G/b", 1) <= 1e-12
        println("J-MB5 MGYPlanar power residual = ",
            _mb5_power_residual(data, "G/a", "G/b", 1))
    end

    # -----------------------------------------------------------------------------------
    # FIX-MB-4: the matrix transformer, time-varying modulations and a varying-adjoint run
    # -----------------------------------------------------------------------------------
    @testset "FIX-MB-4: TFPlanarMat/MTFPlanarMat: random M, power zero, no inverse" begin
        rng = _mb5_rng(20261029)
        worst = 0.0
        for case in 1:4
            # A well-conditioned random matrix with rotational/translational coupling: the
            # matrix form is the general 3x3 TF (`a.f = M b.f`, `b.e = -M^T a.e`).
            M = [1.4 + 0.5 * abs(rng()) 0.3 * rng() -0.4 * rng()
                 0.25 * rng() 1.1 + 0.6 * abs(rng()) 0.35 * rng()
                 -0.3 * rng() 0.2 * rng() 1.6 + 0.4 * abs(rng())]
            E = [rng(), rng(), rng()]
            F = [rng(), rng(), rng()]
            mstr = "[$(M[1,1]) $(M[1,2]) $(M[1,3]); $(M[2,1]) $(M[2,2]) $(M[2,3]); " *
                   "$(M[3,1]) $(M[3,2]) $(M[3,3])]"
            for (label, block_ref, params, extra_nodes, extra_conns) in (
                ("TFPlanarMat", "stdlib:multibond/TFPlanarMat",
                    Dict{String,Any}("M" => mstr), Any[], Any[]),
                ("MTFPlanarMat", "stdlib:multibond/MTFPlanarMat", Dict{String,Any}(),
                    Any[_mb5_node("n7", "Ug", _mb5_inline(_MB5_MAT_CONST);
                        params = Dict{String,Any}(
                            "g11" => string(M[1, 1]), "g12" => string(M[1, 2]),
                            "g13" => string(M[1, 3]), "g21" => string(M[2, 1]),
                            "g22" => string(M[2, 2]), "g23" => string(M[2, 3]),
                            "g31" => string(M[3, 1]), "g32" => string(M[3, 2]),
                            "g33" => string(M[3, 3])))],
                    Any[_mb5_conn("c7", "signal", "n7", "G", "n5", "M")]),
            )
                doc = _mb5_doc(
                    "$label$case",
                    Any[
                        _mb5_node("n1", "Ue", _mb5_inline(_MB5_VEC_CONST);
                            params = Dict{String,Any}("c1" => string(E[1]),
                                "c2" => string(E[2]), "c3" => string(E[3]))),
                        _mb5_node("n2", "Uf", _mb5_inline(_MB5_VEC_CONST);
                            params = Dict{String,Any}("c1" => string(F[1]),
                                "c2" => string(F[2]), "c3" => string(F[3]))),
                        _mb5_node("n3", "A", _mb5_ref("stdlib:multibond/SePlanar")),
                        _mb5_node("n4", "B", _mb5_ref("stdlib:multibond/SfPlanar")),
                        _mb5_node("n5", "T", _mb5_ref(block_ref); params = params),
                        extra_nodes...,
                    ],
                    Any[
                        _mb5_conn("c1", "signal", "n1", "y", "n3", "u"),
                        _mb5_conn("c2", "signal", "n2", "y", "n4", "u"),
                        _mb5_conn("c3", "bond", "n3", "p", "n5", "a"),
                        _mb5_conn("c4", "bond", "n5", "b", "n4", "p"),
                        extra_conns...,
                    ],
                )
                @test isempty(_mb5_errors(_mb5_check(doc)))
                result, dir = _mb5_run(doc)
                @test result.status == "done"
                data = _mb5_columns(dir)
                ae, af = _mb5_at(data, "T/a.e"), _mb5_at(data, "T/a.f")
                be, bf = _mb5_at(data, "T/b.e"), _mb5_at(data, "T/b.f")
                @test isapprox(ae, E; atol = 1e-12)
                @test isapprox(bf, -F; atol = 1e-12)
                @test isapprox(af, M * bf; atol = 1e-12)
                @test isapprox(be, -transpose(M) * ae; atol = 1e-12)
                res = _mb5_power_residual(data, "T/a", "T/b", 1)
                worst = max(worst, res)
                @test res <= 1e-12
                @test maximum(abs.(af)) > 1e-2         # the test is not vacuous
            end
        end
        println("FIX-MB-4 matrix TF worst power residual (random M) = ", worst)
    end

    @testset "FIX-MB-4: MTFPlanar with a time-varying modulation" begin
        # A constant modulation cannot tell a live signal from a value latched at t = 0. The
        # source is `a[k]*sin(w t)`, so it starts at zero and changes every step.
        E = [0.9, -1.1, 0.6]
        F = [-0.4, 0.7, 0.35]
        a = [1.2, -0.8, 0.9]
        w = 2.1
        doc = _mb5_doc(
            "MTFPlanarTimeVarying",
            Any[
                _mb5_node("n1", "Ue", _mb5_inline(_MB5_VEC_CONST);
                    params = Dict{String,Any}("c1" => string(E[1]),
                        "c2" => string(E[2]), "c3" => string(E[3]))),
                _mb5_node("n2", "Uf", _mb5_inline(_MB5_VEC_CONST);
                    params = Dict{String,Any}("c1" => string(F[1]),
                        "c2" => string(F[2]), "c3" => string(F[3]))),
                _mb5_node("n3", "Uu", _mb5_inline(_MB5_VEC_SINE);
                    params = Dict{String,Any}("a1" => string(a[1]), "a2" => string(a[2]),
                        "a3" => string(a[3]), "w" => string(w))),
                _mb5_node("n4", "A", _mb5_ref("stdlib:multibond/SePlanar")),
                _mb5_node("n5", "B", _mb5_ref("stdlib:multibond/SfPlanar")),
                _mb5_node("n6", "T", _mb5_ref("stdlib:multibond/MTFPlanar")),
            ],
            Any[
                _mb5_conn("c1", "signal", "n1", "y", "n4", "u"),
                _mb5_conn("c2", "signal", "n2", "y", "n5", "u"),
                _mb5_conn("c3", "signal", "n3", "y", "n6", "u"),
                _mb5_conn("c4", "bond", "n4", "p", "n6", "a"),
                _mb5_conn("c5", "bond", "n6", "b", "n5", "p"),
            ];
            t_end = 1.0, points = 1001,
        )
        @test isempty(_mb5_errors(_mb5_check(doc)))
        result, dir = _mb5_run(doc; t_end = 1.0, points = 1001)
        @test result.status == "done"
        data = _mb5_columns(dir)
        t = data["time"]
        U = [[a[k] * sin(w * ti) for ti in t] for k in 1:3]
        @test maximum(maximum(abs, u) for u in U) > 0.5    # the modulation is live
        for i in (1, 250, 500, 1000)
            ae, af = _mb5_at(data, "T/a.e", i), _mb5_at(data, "T/a.f", i)
            be, bf = _mb5_at(data, "T/b.e", i), _mb5_at(data, "T/b.f", i)
            u = [U[k][i] for k in 1:3]
            @test isapprox(ae, E; atol = 1e-12)
            @test isapprox(bf, -F; atol = 1e-12)
            @test isapprox(af, u .* bf; atol = 1e-11)
            @test isapprox(be, -u .* ae; atol = 1e-11)
            @test _mb5_power_residual(data, "T/a", "T/b", i) <= 1e-11
        end
        # A latched input (u frozen at t = 0 = 0) would make a.f exactly zero: it is not.
        @test maximum(abs.(data["T/a.f[1]"])) > 1e-2
    end

    @testset "FIX-MB-4: MGYPlanar with a time-varying matrix input" begin
        G0 = [1.4 -0.3 0.2
              0.5 2.1 -0.4
              -0.25 0.35 1.7]
        D = [0.5 0.2 -0.3
             -0.4 0.6 0.25
             0.3 -0.2 0.4]
        w = 1.9
        r = [1.2, 0.8, 1.5]
        E = [1.1, -0.9, 0.6]
        params = Dict{String,Any}("w" => string(w))
        for i in 1:3, j in 1:3
            params["g$i$j"] = string(G0[i, j])
            params["d$i$j"] = string(D[i, j])
        end
        doc = _mb5_doc(
            "MGYPlanarTimeVarying",
            Any[
                _mb5_node("n1", "Ue", _mb5_inline(_MB5_VEC_CONST);
                    params = Dict{String,Any}("c1" => string(E[1]),
                        "c2" => string(E[2]), "c3" => string(E[3]))),
                _mb5_node("n2", "Ug", _mb5_inline(_MB5_MAT_SINE); params = params),
                _mb5_node("n3", "A", _mb5_ref("stdlib:multibond/SePlanar")),
                _mb5_node("n4", "G", _mb5_ref("stdlib:multibond/MGYPlanar")),
                _mb5_node("n5", "R", _mb5_ref("stdlib:multibond/RPlanar");
                    params = Dict{String,Any}("br" => string(r[1]),
                        "bx" => string(r[2]), "by" => string(r[3]))),
            ],
            Any[
                _mb5_conn("c1", "signal", "n1", "y", "n3", "u"),
                _mb5_conn("c2", "signal", "n2", "G", "n4", "G"),
                _mb5_conn("c3", "bond", "n3", "p", "n4", "a"),
                _mb5_conn("c4", "bond", "n5", "p", "n4", "b"),
            ];
            t_end = 1.5, points = 1501,
        )
        @test isempty(_mb5_errors(_mb5_check(doc)))
        result, dir = _mb5_run(doc; t_end = 1.5, points = 1501)
        @test result.status == "done"
        data = _mb5_columns(dir)
        t = data["time"]
        Gt(i) = G0 .+ D .* sin(w * t[i])
        @test maximum(abs.(Gt(1000) - G0)) > 0.2         # the matrix is live
        worst = 0.0
        for i in (1, 400, 800, 1500)
            G = Gt(i)
            ae, af = _mb5_at(data, "G/a.e", i), _mb5_at(data, "G/a.f", i)
            be, bf = _mb5_at(data, "G/b.e", i), _mb5_at(data, "G/b.f", i)
            @test isapprox(ae, E; atol = 1e-11)
            @test isapprox(ae, G * bf; atol = 1e-11)
            @test isapprox(be, -transpose(G) * af; atol = 1e-11)
            @test isapprox(be, -r .* bf; atol = 1e-10)    # the R load on the b side
            res = _mb5_power_residual(data, "G/a", "G/b", i)
            worst = max(worst, res)
            @test res <= 1e-11
        end
        println("FIX-MB-4 time-varying MGYPlanar worst power residual = ", worst)
    end

    @testset "FIX-MB-4: TFAd with a time-varying pose in a running model" begin
        # `g = (theta, x, y)` is a signal input, so the adjoint itself changes every step.
        # An inertia is driven through the transform: `dP/dt = -b.e = -Ad(g(t))^T E`, which is
        # integrated independently (RK4) from the analytic `g(t)` and compared to the run.
        g1, g2, g3, w = 0.6, 0.15, -0.2, 1.7
        E = [0.5, -0.8, 1.1]
        P0 = [0.03, -0.02, 0.05]
        J, m = 0.05, 1.5
        doc = _mb5_doc(
            "TFAdTimeVarying",
            Any[
                _mb5_node("n1", "G", _mb5_inline(_MB5_VEC_SINE);
                    params = Dict{String,Any}("a1" => string(g1), "a2" => string(g2),
                        "a3" => string(g3), "w" => string(w))),
                _mb5_node("n2", "Ue", _mb5_inline(_MB5_VEC_CONST);
                    params = Dict{String,Any}("c1" => string(E[1]),
                        "c2" => string(E[2]), "c3" => string(E[3]))),
                _mb5_node("n3", "Se", _mb5_ref("stdlib:multibond/SePlanar")),
                _mb5_node("n4", "T", _mb5_ref("stdlib:multibond/TFAd")),
                _mb5_node("n5", "J", Dict{String,Any}("junction" => "1")),
                _mb5_node("n6", "I", _mb5_ref("stdlib:multibond/IPlanar");
                    params = Dict{String,Any}("J" => string(J), "m" => string(m)),
                    starts = Dict{String,Any}("P" =>
                        "[$(P0[1]), $(P0[2]), $(P0[3])]")),
            ],
            Any[
                _mb5_conn("c1", "signal", "n1", "y", "n4", "g"),
                _mb5_conn("c2", "signal", "n2", "y", "n3", "u"),
                _mb5_conn("c3", "bond", "n3", "p", "n4", "a"),
                _mb5_conn("c4", "bond", "n4", "b", "n5"),
                _mb5_conn("c5", "bond", "n6", "p", "n5"),
            ];
            t_end = 1.0, points = 1001,
        )
        result = _mb5_check(doc)
        @test isempty(_mb5_errors(result))
        @test !_mb5_has(result, "W201")
        run, dir = _mb5_run(doc; t_end = 1.0, points = 1001, reltol = 1e-10,
            abstol = 1e-12)
        @test run.status == "done"
        data = _mb5_columns(dir)
        t = data["time"]
        P = [data["I/P[$k]"] for k in 1:3]
        worst = 0.0
        for i in (1, 250, 500, 1000)
            ti = t[i]
            gi = [g1 * sin(w * ti), g2 * sin(w * ti), g3 * sin(w * ti)]
            th = gi[1]
            A = [1.0 0.0 0.0; gi[3] cos(th) -sin(th); -gi[2] sin(th) cos(th)]
            ae, af = _mb5_at(data, "T/a.e", i), _mb5_at(data, "T/a.f", i)
            be, bf = _mb5_at(data, "T/b.e", i), _mb5_at(data, "T/b.f", i)
            @test isapprox(ae, E; atol = 1e-12)
            @test isapprox(bf, [P[1][i] / J, P[2][i] / m, P[3][i] / m]; atol = 1e-10)
            @test isapprox(af, -A * bf; atol = 1e-10)
            @test isapprox(be, transpose(A) * ae; atol = 1e-10)
            res = _mb5_power_residual(data, "T/a", "T/b", i)
            worst = max(worst, res)
            @test res <= 1e-9
        end
        @test maximum(abs.(data["T/a.f[1]"])) > 1e-3     # varying, not frozen at zero
        # Independent RK4 of dP/dt = -Ad(g(t))^T E with the analytic g(t).
        function rhs(Pv, ti)
            gi = [g1 * sin(w * ti), g2 * sin(w * ti), g3 * sin(w * ti)]
            th = gi[1]
            A = [1.0 0.0 0.0; gi[3] cos(th) -sin(th); -gi[2] sin(th) cos(th)]
            return -transpose(A) * E
        end
        dt = 1.0e-4
        Pv = collect(float.(P0))
        for k in 1:round(Int, 1.0 / dt)
            ti = (k - 1) * dt
            k1 = rhs(Pv, ti)
            k2 = rhs(Pv .+ (dt / 2) .* k1, ti + dt / 2)
            k3 = rhs(Pv .+ (dt / 2) .* k2, ti + dt / 2)
            k4 = rhs(Pv .+ dt .* k3, ti + dt)
            Pv = Pv .+ (dt / 6) .* (k1 .+ 2 .* k2 .+ 2 .* k3 .+ k4)
        end
        Pend = [P[j][end] for j in 1:3]
        @test maximum(abs.(Pend .- Pv)) / max(1.0, maximum(abs, Pv)) <= 1.0e-6
        println("FIX-MB-4 varying TFAd: worst power residual ", worst,
            ", momentum vs independent RK4 ", maximum(abs.(Pend .- Pv)) /
                                                 max(1.0, maximum(abs, Pv)))
    end

    # -----------------------------------------------------------------------------------
    # Joint transform (the legal frame bridge) and the frame contract
    # -----------------------------------------------------------------------------------
    @testset "JointTransform2D: component-wise Ad(g) and the frame bridge" begin
        # `a` is driven by an effort source and `b` by a flow source: a transformer's two
        # sides are complementary, so the transform takes the effort at `a` and supplies it
        # at `b`, and takes the flow at `b`. Each source block names its frame, so the pair
        # of blocks around the transform is a genuine two-frame bridge.
        function joint_frame_block(frame, name, flux)
            if flux
                return """
                @block $name begin
                    @ports p::Power{Planar}, [frame = "$frame"]
                    @parameters begin
                        f1::Real = 0.0, [unit = "rad/s", description = "Twist 1"]
                        f2::Real = 0.0, [unit = "m/s", description = "Twist 2"]
                        f3::Real = 0.0, [unit = "m/s", description = "Twist 3"]
                    end
                    @equations begin
                        p.f[1] ~ f1
                        p.f[2] ~ f2
                        p.f[3] ~ f3
                    end
                    @causality p => (:flow_out, :fixed)
                end
                """
            end
            return """
            @block $name begin
                @ports p::Power{Planar}, [frame = "$frame"]
                @parameters begin
                    e1::Real = 0.0, [unit = "N*m", description = "Wrench 1"]
                    e2::Real = 0.0, [unit = "N", description = "Wrench 2"]
                    e3::Real = 0.0, [unit = "N", description = "Wrench 3"]
                end
                @equations begin
                    p.e[1] ~ e1
                    p.e[2] ~ e2
                    p.e[3] ~ e3
                end
                @causality p => (:effort_out, :fixed)
            end
            """
        end
        parent_block = joint_frame_block("parent", "ParentPort", false)
        child_block = joint_frame_block("child", "ChildPort", true)
        rng = _mb5_rng(7007)
        worst = 0.0
        for case in 1:3
            g = case == 1 ? [0.37, 0.42, -0.28] :
                [1.5 * rng(), rng(), rng()]
            E = case == 1 ? [1.3, -0.8, 0.55] : [rng(), rng(), rng()]
            F = case == 1 ? [0.45, 0.3, -0.6] : [rng(), rng(), rng()]
            doc = _mb5_doc(
                "JointTransformBridge$case",
                Any[
                    _mb5_node("n1", "U", _mb5_inline(_MB5_VEC_CONST);
                        params = Dict{String,Any}("c1" => string(g[1]),
                            "c2" => string(g[2]), "c3" => string(g[3]))),
                    _mb5_node("n2", "P", _mb5_inline(parent_block);
                        params = Dict{String,Any}("e1" => string(E[1]),
                            "e2" => string(E[2]), "e3" => string(E[3]))),
                    _mb5_node("n3", "T",
                        _mb5_ref("stdlib:multibond/JointTransform2D")),
                    _mb5_node("n4", "C", _mb5_inline(child_block);
                        params = Dict{String,Any}("f1" => string(F[1]),
                            "f2" => string(F[2]), "f3" => string(F[3]))),
                ],
                Any[
                    _mb5_conn("c1", "signal", "n1", "y", "n3", "g"),
                    _mb5_conn("c2", "bond", "n2", "p", "n3", "a"),
                    _mb5_conn("c3", "bond", "n3", "b", "n4", "p"),
                ],
            )
            check = _mb5_check(doc)
            @test isempty(_mb5_errors(check))
            @test !_mb5_has(check, "E007")
            @test endswith(check.frames["c2"], "/parent")
            @test endswith(check.frames["c3"], "/child")
            result, dir = _mb5_run(doc)
            @test result.status == "done"
            data = _mb5_columns(dir)
            ae, af = _mb5_at(data, "T/a.e"), _mb5_at(data, "T/a.f")
            be, bf = _mb5_at(data, "T/b.e"), _mb5_at(data, "T/b.f")
            theta, x, y = g
            c, s = cos(theta), sin(theta)
            A = [1.0 0.0 0.0; y c -s; -x s c]
            @test isapprox(ae, E; atol = 1e-12)
            @test isapprox(bf, -F; atol = 1e-12)
            @test isapprox(af, -A * bf; atol = 1e-12)
            @test isapprox(ae, transpose(inv(A)) * be; atol = 1e-12)
            res = _mb5_power_residual(data, "T/a", "T/b", 1)
            worst = max(worst, res)
            @test res <= 1e-12
        end
        println("J-MB5 JointTransform2D worst power residual (random pose/twist/wrench) = ",
            worst)

        # The transform is the *only* legal bridge: a `parent`-frame port joins `a`, but a
        # `world`-frame port does not, and a direct parent-to-child bond is E007 too.
        wrong = _mb5_doc(
            "JointTransformWrongFrame",
            Any[
                _mb5_node("n1", "U", _mb5_inline(_MB5_VEC_CONST);
                    params = Dict{String,Any}("c1" => "0.1", "c2" => "0.0", "c3" => "0.0")),
                _mb5_node("n2", "W",
                    _mb5_inline(joint_frame_block("world", "WorldPort", false))),
                _mb5_node("n3", "T", _mb5_ref("stdlib:multibond/JointTransform2D")),
                _mb5_node("n4", "C", _mb5_inline(child_block)),
            ],
            Any[
                _mb5_conn("c1", "signal", "n1", "y", "n3", "g"),
                _mb5_conn("c2", "bond", "n2", "p", "n3", "a"),
                _mb5_conn("c3", "bond", "n3", "b", "n4", "p"),
            ],
        )
        @test _mb5_has(_mb5_check(wrong), "E007")

        direct = _mb5_doc(
            "JointTransformDirectBond",
            Any[
                _mb5_node("n2", "P", _mb5_inline(parent_block)),
                _mb5_node("n4", "C", _mb5_inline(child_block)),
            ],
            Any[_mb5_conn("c1", "bond", "n2", "p", "n4", "p")],
        )
        @test _mb5_has(_mb5_check(direct), "E007")
    end

    # -----------------------------------------------------------------------------------
    # Coriolis: the sign a C/R on the same 1-junction receives
    # -----------------------------------------------------------------------------------
    @testset "CoriolisPlanar: coupled free body with a C and an R on the 1-junction" begin
        J, m = 0.05, 2.0
        k = [30.0, 60.0, 45.0]
        b = [0.4, 0.35, 0.5]
        P0 = [0.05, 0.2, -0.15]
        q0 = [0.1, 0.05, -0.08]
        doc = _mb5_doc(
            "CoriolisWithCAndR",
            Any[
                _mb5_node("n1", "J", Dict{String,Any}("junction" => "1")),
                _mb5_node("n2", "B", _mb5_ref("stdlib:multibond/IPlanar");
                    params = Dict{String,Any}("J" => string(J), "m" => string(m)),
                    starts = Dict{String,Any}("P" =>
                        "[$(P0[1]), $(P0[2]), $(P0[3])]")),
                _mb5_node("n3", "C", _mb5_ref("stdlib:multibond/CoriolisPlanar")),
                _mb5_node("n4", "K", _mb5_ref("stdlib:multibond/CPlanar");
                    params = Dict{String,Any}("kr" => string(k[1]), "kx" => string(k[2]),
                        "ky" => string(k[3])),
                    starts = Dict{String,Any}("qr" => string(q0[1]),
                        "qx" => string(q0[2]), "qy" => string(q0[3]))),
                _mb5_node("n5", "R", _mb5_ref("stdlib:multibond/RPlanar");
                    params = Dict{String,Any}("br" => string(b[1]), "bx" => string(b[2]),
                        "by" => string(b[3]))),
            ],
            Any[
                _mb5_conn("c1", "bond", "n2", "p", "n1"),
                _mb5_conn("c2", "bond", "n3", "p", "n1"),
                _mb5_conn("c3", "bond", "n4", "p", "n1"),
                _mb5_conn("c4", "bond", "n5", "p", "n1"),
                _mb5_conn("c5", "signal", "n2", "Pm", "n3", "P"),
            ];
            t_end = 2.0, points = 2001,
        )
        check = _mb5_check(doc)
        @test isempty(_mb5_errors(check))
        @test !_mb5_has(check, "W201")
        result, dir = _mb5_run(doc; t_end = 2.0, points = 2001, reltol = 1.0e-9,
            abstol = 1.0e-11)
        @test result.status == "done"
        data = _mb5_columns(dir)

        # All four elements hang off the same 1-junction with a bond from the element to the
        # junction, so every port sees the inertia's twist V (the junction ties the bond
        # flows; the flip is the same for all four). The junction sums the efforts to zero:
        #   e_I = -(e_Coriolis + e_C + e_R) = ad(V)^T P - k q - b V,
        # because the block's effort is -ad(V)^T P. That is the free body with a spring and
        # a damper: an independent RK4 of exactly these equations is the reference.
        V = [data["B/P[1]"] ./ J, data["B/P[2]"] ./ m, data["B/P[3]"] ./ m]
        for i in eachindex(data["time"])
            @test isapprox(V[1][i], data["B/p.f[1]"][i]; atol = 1e-12)
            @test isapprox(V[2][i], data["B/p.f[2]"][i]; atol = 1e-12)
            @test isapprox(V[3][i], data["B/p.f[3]"][i]; atol = 1e-12)
            @test isapprox(data["C/p.f[1]"][i], V[1][i]; atol = 1e-12)
            @test isapprox(data["R/p.f[2]"][i], V[2][i]; atol = 1e-12)
        end
        function rhs(P, q)
            w = P[1] / J
            vx = P[2] / m
            vy = P[3] / m
            dP = [vy * P[2] - vx * P[3], w * P[3], -w * P[2]]
            return ([dP[1] - k[1] * q[1] - b[1] * w,
                     dP[2] - k[2] * q[2] - b[2] * vx,
                     dP[3] - k[3] * q[3] - b[3] * vy],
                [w, vx, vy])
        end
        function rk4(P0v, q0v, t_end, dt)
            P = collect(float.(P0v))
            q = collect(float.(q0v))
            n = round(Int, t_end / dt)
            for _ in 1:n
                k1p, k1q = rhs(P, q)
                k2p, k2q = rhs(P .+ (dt / 2) .* k1p, q .+ (dt / 2) .* k1q)
                k3p, k3q = rhs(P .+ (dt / 2) .* k2p, q .+ (dt / 2) .* k2q)
                k4p, k4q = rhs(P .+ dt .* k3p, q .+ dt .* k3q)
                P = P .+ (dt / 6) .* (k1p .+ 2 .* k2p .+ 2 .* k3p .+ k4p)
                q = q .+ (dt / 6) .* (k1q .+ 2 .* k2q .+ 2 .* k3q .+ k4q)
            end
            return P, q
        end
        Pref, qref = rk4(P0, q0, 2.0, 1.0e-5)
        Pend = [data["B/P[$j]"][end] for j in 1:3]
        qend = [data["K/qr"][end], data["K/qx"][end], data["K/qy"][end]]
        pscale = max(1.0, maximum(abs, Pref))
        @test maximum(abs.(Pend .- Pref)) / pscale <= 1.0e-6
        @test maximum(abs.(qend .- qref)) / max(1.0, maximum(abs, qref)) <= 1.0e-6
        println("J-MB5 Coriolis+C/R free-body rel error: P ",
            maximum(abs.(Pend .- Pref)) / pscale, ", q ",
            maximum(abs.(qend .- qref)) / max(1.0, maximum(abs, qref)))

        # The energy ledger with the C/R signs: dE/dt = -b . V^2 <= 0, so the energy lost is
        # exactly the damper integral (the Coriolis effort is power-neutral).
        t = data["time"]
        E = 0.5 .* (data["B/P[1]"] .^ 2 ./ J .+ data["B/P[2]"] .^ 2 ./ m .+
                    data["B/P[3]"] .^ 2 ./ m) .+
            0.5 .* (k[1] .* data["K/qr"] .^ 2 .+ k[2] .* data["K/qx"] .^ 2 .+
                    k[3] .* data["K/qy"] .^ 2)
        dissipated = [b[1] * V[1][i]^2 + b[2] * V[2][i]^2 + b[3] * V[3][i]^2
                      for i in eachindex(t)]
        @test isapprox(E[end] - E[1], -_mb5_simpson(t, dissipated);
            rtol = 1e-7, atol = 1e-12)
        @test E[end] < E[1]
        for i in eachindex(t)
            e = _mb5_at(data, "C/p.e", i)
            f = _mb5_at(data, "C/p.f", i)
            @test abs(sum(e[j] * f[j] for j in 1:3)) <=
                  1e-10 * max(1.0, maximum(abs, e))
        end
    end

    # -----------------------------------------------------------------------------------
    # A closed bond graph: source, C, R, TF, GY, sink
    # -----------------------------------------------------------------------------------
    @testset "closed bond graph: power is conserved" begin
        # All five junctions bonds run element -> 1-junction, so every port sees the body
        # twist V. The effort source supplies u, the inertia integrates, the C stores, the R
        # and the transformer branch dissipate. The chain is TF(n) -> GY(diag g) -> R2, so
        # the sink R2 is reflected as R_eff = g^2/(n^2 r) on the TF's primary port.
        J, m = 0.02, 1.5
        k = [40.0, 25.0, 30.0]
        b1 = [0.4, 0.3, 0.35]
        b2 = [0.6, 0.5, 0.45]
        n = [1.5, 0.5, 2.0]
        g = [2.0, 3.0, 4.0]
        u = [1.2, -0.7, 0.5]
        P0 = [0.03, -0.02, 0.04]
        q0 = [-0.01, 0.02, 0.005]
        doc = _mb5_doc(
            "ClosedPlanarBondGraph",
            Any[
                _mb5_node("n1", "Ur", _mb5_inline(_MB5_SCALAR_CONST);
                    params = Dict{String,Any}("v" => string(u[1]))),
                _mb5_node("n2", "Ux", _mb5_inline(_MB5_SCALAR_CONST);
                    params = Dict{String,Any}("v" => string(u[2]))),
                _mb5_node("n3", "Uy", _mb5_inline(_MB5_SCALAR_CONST);
                    params = Dict{String,Any}("v" => string(u[3]))),
                _mb5_node("n4", "S", _mb5_ref("stdlib:multibond/MSePlanar")),
                _mb5_node("n5", "J1", Dict{String,Any}("junction" => "1")),
                _mb5_node("n6", "B", _mb5_ref("stdlib:multibond/IPlanar");
                    params = Dict{String,Any}("J" => string(J), "m" => string(m)),
                    starts = Dict{String,Any}("P" =>
                        "[$(P0[1]), $(P0[2]), $(P0[3])]")),
                _mb5_node("n7", "C", _mb5_ref("stdlib:multibond/CPlanar");
                    params = Dict{String,Any}("kr" => string(k[1]), "kx" => string(k[2]),
                        "ky" => string(k[3])),
                    starts = Dict{String,Any}("qr" => string(q0[1]),
                        "qx" => string(q0[2]), "qy" => string(q0[3]))),
                _mb5_node("n8", "R", _mb5_ref("stdlib:multibond/RPlanar");
                    params = Dict{String,Any}("br" => string(b1[1]),
                        "bx" => string(b1[2]), "by" => string(b1[3]))),
                _mb5_node("n9", "T", _mb5_ref("stdlib:multibond/TFPlanar");
                    params = Dict{String,Any}("n" =>
                        "[$(n[1]), $(n[2]), $(n[3])]")),
                _mb5_node("n10", "G", _mb5_ref("stdlib:multibond/GYPlanar");
                    params = Dict{String,Any}("G" =>
                        "[$(g[1]) 0.0 0.0; 0.0 $(g[2]) 0.0; 0.0 0.0 $(g[3])]")),
                _mb5_node("n11", "L", _mb5_ref("stdlib:multibond/RPlanar");
                    params = Dict{String,Any}("br" => string(b2[1]),
                        "bx" => string(b2[2]), "by" => string(b2[3]))),
            ],
            Any[
                _mb5_conn("c1", "signal", "n1", "y", "n4", "ur"),
                _mb5_conn("c2", "signal", "n2", "y", "n4", "ux"),
                _mb5_conn("c3", "signal", "n3", "y", "n4", "uy"),
                _mb5_conn("c4", "bond", "n4", "p", "n5"),
                _mb5_conn("c5", "bond", "n6", "p", "n5"),
                _mb5_conn("c6", "bond", "n7", "p", "n5"),
                _mb5_conn("c7", "bond", "n8", "p", "n5"),
                _mb5_conn("c8", "bond", "n9", "a", "n5"),
                _mb5_conn("c9", "bond", "n9", "b", "n10", "a"),
                _mb5_conn("c10", "bond", "n11", "p", "n10", "b"),
            ];
            t_end = 2.0, points = 8001,
        )
        check = _mb5_check(doc)
        @test isempty(_mb5_errors(check))
        @test !_mb5_has(check, "W201")
        @test !_mb5_has(check, "W202")
        @test !_mb5_has(check, "E106")
        result, dir = _mb5_run(doc; t_end = 2.0, points = 8001, reltol = 1.0e-10,
            abstol = 1.0e-12)
        @test result.status == "done"
        data = _mb5_columns(dir)
        t = data["time"]

        # V = P/M and q' = f_C: the inertia and the capacitance are the two state blocks.
        V = [data["B/P[1]"] ./ J, data["B/P[2]"] ./ m, data["B/P[3]"] ./ m]
        for i in eachindex(t)
            for j in 1:3
                @test isapprox(data["C/p.f[$j]"][i], V[j][i]; atol = 1e-11)
                @test isapprox(data["R/p.f[$j]"][i], V[j][i]; atol = 1e-11)
                @test isapprox(data["T/a.f[$j]"][i], V[j][i]; atol = 1e-11)
            end
        end

        # The TF/GY chain: a.f = n b.f, b.e = -n a.e; GY a.e = g b.f, b.e = -g a.f (diagonal
        # g here); and the sink R2 terminates the GY's b side.
        ae, af = _mb5_port_matrix(data, "T/a.e"), _mb5_port_matrix(data, "T/a.f")
        be, bf = _mb5_port_matrix(data, "T/b.e"), _mb5_port_matrix(data, "T/b.f")
        gae, gaf = _mb5_port_matrix(data, "G/a.e"), _mb5_port_matrix(data, "G/a.f")
        gbe, gbf = _mb5_port_matrix(data, "G/b.e"), _mb5_port_matrix(data, "G/b.f")
        le = _mb5_port_matrix(data, "L/p.e")
        residuals = zeros(5)
        for i in eachindex(t)
            residuals[1] = max(residuals[1],
                maximum(abs.(af[j][i] - n[j] * bf[j][i]) for j in 1:3))
            residuals[2] = max(residuals[2],
                maximum(abs.(be[j][i] + n[j] * ae[j][i]) for j in 1:3))
            residuals[3] = max(residuals[3],
                maximum(abs.(gbe[j][i] + g[j] * gaf[j][i]) for j in 1:3))
            residuals[4] = max(residuals[4],
                maximum(abs.(gae[j][i] - g[j] * gbf[j][i]) for j in 1:3))
            residuals[5] = max(residuals[5],
                maximum(abs.(le[j][i] - b2[j] * (-gbf[j][i])) for j in 1:3))
        end
        @test maximum(residuals) <= 1e-10
        println("J-MB5 closed model chain residuals (TF flow, TF effort, GY effort, ",
            "GY flow, sink) = ", residuals)

        # Element constitutive relations on the run (every element, every sample).
        for i in eachindex(t)
            @test isapprox(_mb5_at(data, "C/p.e", i),
                [k[j] * [data["C/qr"][i], data["C/qx"][i], data["C/qy"][i]][j]
                 for j in 1:3]; atol = 1e-10)
            @test isapprox(_mb5_at(data, "R/p.e", i),
                [b1[j] * V[j][i] for j in 1:3]; atol = 1e-10)
            @test isapprox(_mb5_at(data, "S/p.e", i), u; atol = 1e-12)
            @test _mb5_power_residual(data, "T/a", "T/b", i) <= 1e-11
            @test _mb5_power_residual(data, "G/a", "G/b", i) <= 1e-11
        end

        # The 1-junction power sum is zero and the global ledger closes: the source power
        # supplied equals the stored energy plus the two dissipated powers.
        junction_power = [sum(_mb5_at(data, "S/p.e", i)[j] * V[j][i] +
                              _mb5_at(data, "B/p.e", i)[j] * V[j][i] +
                              _mb5_at(data, "C/p.e", i)[j] * V[j][i] +
                              _mb5_at(data, "R/p.e", i)[j] * V[j][i] +
                              _mb5_at(data, "T/a.e", i)[j] * V[j][i] for j in 1:3)
                          for i in eachindex(t)]
        scale = maximum(abs, junction_power) + 1.0
        @test maximum(abs, junction_power) <= 1e-9 * scale
        stored = 0.5 .* (data["B/P[1]"] .^ 2 ./ J .+ data["B/P[2]"] .^ 2 ./ m .+
                         data["B/P[3]"] .^ 2 ./ m) .+
                 0.5 .* (k[1] .* data["C/qr"] .^ 2 .+ k[2] .* data["C/qx"] .^ 2 .+
                         k[3] .* data["C/qy"] .^ 2)
        source_power = [sum(_mb5_at(data, "S/p.e", i)[j] * V[j][i] for j in 1:3)
                        for i in eachindex(t)]
        dissip = [sum(_mb5_at(data, "R/p.e", i)[j] * V[j][i] for j in 1:3) +
                  sum(_mb5_at(data, "L/p.e", i)[j] * (-_mb5_at(data, "G/b.f", i)[j])
                      for j in 1:3)
                  for i in eachindex(t)]
        supplied = -_mb5_simpson(t, source_power)
        stored_change = stored[end] - stored[1]
        used = _mb5_simpson(t, dissip)
        @test isapprox(supplied, stored_change + used; rtol = 1e-6, atol = 1e-9)
        @test used > 0.0
        println("J-MB5 closed model power ledger: supplied ", supplied,
            " J, stored ", stored_change, " J, dissipated ", used,
            " J, residual ", supplied - stored_change - used, " J",
            "; max |junction power| ", maximum(abs, junction_power), " W")
    end
end
