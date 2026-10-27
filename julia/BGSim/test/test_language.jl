# J2.1 — language completion: Vec/Mat, indexing, `for` unrolling, `if` equations, `ifelse`,
# the complete function whitelist and the `@initial`, `@discrete` and `@events` scopes.
#
# The golden blocks are the spec's `SpeedMonitor`, plan 9.2's `Ball` and plan 9.5's
# `LQGController` (with the literal matrices the plan says `design.py` writes into the model
# JSON). Everything runs against the frozen J1.1 front-end API plus the J2.1 additions:
# `initial_equations`, `discrete_scopes`, `events`, `block_initial_equations`, and the
# `DiscreteScope` / `EventDecl` / `Assign` / `IfStatement` / `ForStatement` /
# `CallStatement` AST nodes.
using Test
import BGSim
using BGSim:
    parse_block,
    check_block,
    block_interface,
    block_equations,
    block_balance,
    block_name,
    block_ref,
    scopes,
    declarations,
    equations,
    initial_equations,
    discrete_scopes,
    events,
    ports,
    decl_name,
    decl_type,
    decl_default,
    decl_attrs,
    type_name,
    type_size,
    type_domain,
    constant_env,
    Diagnostic,
    ParsedBlock,
    Lit,
    Name,
    Call,
    BinOp,
    Index,
    VectorLit,
    MatrixLit,
    IfElse,
    Comparison,
    BoolOp,
    Field,
    Equation,
    IfEquation,
    ForEquation,
    Assign,
    IfStatement,
    ForStatement,
    CallStatement,
    EventDecl,
    DiscreteScope,
    block_initial_equations,
    discrete_period,
    discrete_offset,
    event_condition,
    event_body,
    event_zero_crossing,
    assign_target,
    assign_value,
    assign_op

# ---------------------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------------------

function lang_at(d::Diagnostic)
    d.source === nothing && return nothing
    r = d.source.range
    r === nothing && return nothing
    return (r.line, r.col)
end

function lang_expect(pb::ParsedBlock, code::String, line::Int, col::Int; contains = nothing)
    ds = check_block(pb)
    hits = [d for d in ds if d.code == code && (contains === nothing || occursin(contains, d.message))]
    @test !isempty(hits)
    isempty(hits) && return nothing
    d = hits[1]
    # The diagnostic must point at the offending line; J1.1's suite pins exact columns for
    # the parser-stage codes, and this suite pins the line plus the message.
    @test lang_at(d)[1] == line
    return d
end

lang_codes(pb::ParsedBlock) = [d.code for d in check_block(pb)]

"Errors of a block, ignoring warnings such as W204 and the block-level E103."
lang_errors(pb::ParsedBlock) = [d for d in check_block(pb) if d.severity == "error"]

# ---------------------------------------------------------------------------------------
# Per-row whitelist sources
# ---------------------------------------------------------------------------------------

const LANG_ROW_OVERRIDES = Dict{Symbol,NamedTuple}(
    :dot => (nargs = 2, argtypes = ["Vec{3}", "Vec{3}"], rettype = "Real"),
    :norm => (nargs = 1, argtypes = ["Vec{3}"], rettype = "Real"),
    :cross => (nargs = 2, argtypes = ["Vec{3}", "Vec{3}"], rettype = "Vec{3}"),
    :transpose => (nargs = 1, argtypes = ["Mat{2,2}"], rettype = "Mat{2,2}"),
    :ddt => (nargs = 1, argtypes = ["Real"], rettype = "Real", decl = "variables"),
    :int => (nargs = 2, argtypes = ["Real", "Real"], rettype = "Real"),
    :delay => (nargs = 2, argtypes = ["Real", "Real"], callargs = ["a", "1.0"]),
    :deadzone => (nargs = 3, argtypes = ["Real", "Real", "Real"]),
    :saturate => (nargs = 3, argtypes = ["Real", "Real", "Real"]),
    :interp1 => (nargs = 3, argtypes = ["Real", "Vec{3}", "Vec{3}"], rettype = "Real"),
    :interp2 => (
        nargs = 4,
        argtypes = ["Real", "Vec{3}", "Vec{3}", "Mat{3,3}"],
        rettype = "Real",
    ),
    :noise_normal => (nargs = 2, argtypes = ["Int", "Int"], rettype = "Real"),
    :reinit => (nargs = 2, argtypes = ["Real", "Real"], rettype = "Real", decl = "variables"),
)

function lang_row_spec(rule, name::Symbol)
    ov = get(LANG_ROW_OVERRIDES, name, NamedTuple())
    nargs = get(ov, :nargs, rule.min_args)
    return (
        nargs = nargs,
        argtypes = get(ov, :argtypes, fill("Real", nargs)),
        argnames = get(ov, :argnames, ["a", "b", "c", "d"][1:nargs]),
        callargs = get(ov, :callargs, ["a", "b", "c", "d"][1:nargs]),
        rettype = get(ov, :rettype, "Real"),
        decl = get(ov, :decl, "parameters"),
    )
end

function lang_row_source(ctx::Symbol, fname::Symbol, spec)
    decls = join(
        ["        $(spec.argnames[i])::$(spec.argtypes[i])" for i in 1:spec.nargs], "\n"
    )
    call = string(fname, "(", join(spec.callargs, ", "), ")")
    if ctx === :equation
        return """
        @block RowTest begin
            @$(spec.decl) begin
        $(decls)
            end
            @variables r::$(spec.rettype)
            @equations r ~ $call
        end
        """
    elseif ctx === :discrete
        body = fname === :reinit ? call : "r = $call"
        return """
        @block RowTest begin
            @$(spec.decl) begin
        $(decls)
            end
            @outputs r::$(spec.rettype)
            @discrete Ts = 1e-3 begin
                $body
            end
        end
        """
    else
        body = fname === :reinit ? call : "r = $call"
        return """
        @block RowTest begin
            @$(spec.decl) begin
        $(decls)
            end
            @outputs r::$(spec.rettype)
            @events t > 0.0 => begin
                $body
            end
        end
        """
    end
end

# ---------------------------------------------------------------------------------------
# The golden blocks
# ---------------------------------------------------------------------------------------

# The spec's SpeedMonitor, verbatim (spec "Block structure and scopes").
const SPEEDMONITOR = """
@block SpeedMonitor begin
    @parameters wmax::Real = 300.0, [unit = "rad/s"]
    @inputs  w::Real
    @outputs fault::Bool = false
    @discrete Ts = 1e-3 begin
        if abs(w) > wmax
            fault = true
        end
    end
end
"""

# Plan 9.2's bouncing ball, verbatim.
const BALL = """
@block Ball begin
    @parameters begin
        g::Real = 9.81, [unit = "m/s^2"]
        e::Real = 0.8, [min = 0, max = 1, description = "restitution"]
    end
    @variables begin
        h::Real = 1.0, [unit = "m"]
        v::Real = 0.0, [unit = "m/s"]
    end
    @outputs height::Real
    @equations begin
        ddt(h) ~ v
        ddt(v) ~ -g
        height ~ h
    end
    @events begin
        h < 0 => begin
            reinit(v, -e * v)
        end
    end
end
"""

# Plan 9.5's LQGController. The plan writes `...` where `design.py` would put literal gains;
# the matrices below are those literals. `nu` and `ny` are the plan's structural constants and
# are used as the bounds of the one-iteration loops around the single input and the single
# measurement (the language has no Mat{1,4} -> scalar product).
const LQG = """
@block LQGController begin
    @constants begin
        nx::Int = 4
        nu::Int = 1
        ny::Int = 1
    end
    @parameters begin
        Ad::Mat{nx,nx} = [1.0 1e-3 0.0 0.0; -0.02 0.998 0.01 0.0; 0.0 0.0 1.0 1e-3; 0.0 0.0 -0.02 0.998]
        Bd::Vec{nx} = [0.0, 0.001, 0.0, 0.0]
        Cd::Vec{nx} = [1.0, 0.0, 0.0, 0.0]
        L::Vec{nx} = [0.5, 0.1, 0.05, 0.01]
        K::Vec{nx} = [1.0, 0.2, 0.3, 0.1]
        Ki::Real = 2.0
        umax::Real = 24.0, [unit = "V"]
    end
    @inputs begin
        theta_m::Real
        w_ref::Real
    end
    @outputs begin
        u::Real = 0.0
        w_load_hat::Real = 0.0
    end
    @variables begin
        xhat::Vec{nx} = [0.0, 0.0, 0.0, 0.0]
        z::Real = 0.0
    end
    @discrete Ts = 1e-3 begin
        for j in 1:ny
            y = theta_m
        end
        xhat = xhat + L * (y - dot(Cd, xhat))
        z += Ts * (w_ref - xhat[4])
        v = -dot(K, xhat) + Ki * z
        for j in 1:nu
            u = clamp(v, -umax, umax)
        end
        if abs(v) > umax
            z -= Ts * (w_ref - xhat[4])
        end
        xhat = Ad * xhat + Bd * u
        w_load_hat = xhat[nx]
    end
end
"""

# ---------------------------------------------------------------------------------------
# The suite
# ---------------------------------------------------------------------------------------

@testset "J2.1 language completion" begin
    # -----------------------------------------------------------------------------------
    @testset "golden: SpeedMonitor (spec)" begin
        pb = parse_block(SPEEDMONITOR; ref = "project:SpeedMonitor", filename = "speed.jl")
        @test block_name(pb) == :SpeedMonitor
        @test scopes(pb) == [:parameters, :inputs, :outputs, :discrete]
        @test isempty(check_block(pb))
        @test block_balance(pb) == (unknowns = 0, equations = 0)

        iface = block_interface(pb)
        @test [p.name for p in iface.parameters] == ["wmax"]
        @test iface.parameters[1].unit == "rad/s"
        @test [i.name for i in iface.inputs] == ["w"]
        @test [o.name for o in iface.outputs] == ["fault"]
        @test iface.outputs[1].type == "Bool"
        @test isempty(iface.variables)

        ds = discrete_scopes(pb)
        @test length(ds) == 1
        @test discrete_period(ds[1]) == 1e-3
        @test discrete_offset(ds[1]) === nothing
        body = ds[1].body
        @test length(body) == 1
        @test body[1] isa IfStatement
        stmt = body[1]
        @test length(stmt.branches) == 1          # no else: legal for an if *statement*
        @test stmt.branches[1].cond isa Comparison
        @test stmt.branches[1].cond.op === :>
        @test length(stmt.branches[1].body) == 1
        @test stmt.branches[1].body[1] isa Assign
        @test assign_target(stmt.branches[1].body[1]) isa Name
        @test assign_op(stmt.branches[1].body[1]) === :assign
    end

    # -----------------------------------------------------------------------------------
    @testset "golden: Ball (plan 9.2)" begin
        pb = parse_block(BALL; ref = "project:Ball", filename = "ball.jl")
        @test scopes(pb) == [:parameters, :variables, :outputs, :equations, :events]
        @test isempty(check_block(pb))
        @test block_balance(pb) == (unknowns = 3, equations = 3)
        @test length(block_equations(pb)) == 3
        @test isempty(block_initial_equations(pb))

        iface = block_interface(pb)
        @test [p.name for p in iface.parameters] == ["g", "e"]
        @test iface.parameters[2].description == "restitution"
        @test iface.parameters[2].min == 0
        @test iface.parameters[2].max == 1
        @test [v.name for v in iface.variables] == ["h", "v"]
        @test iface.variables[1].unit == "m"
        @test [o.name for o in iface.outputs] == ["height"]

        evs = events(pb)
        @test length(evs) == 1
        ev = evs[1]
        cond = event_condition(ev)
        @test cond isa Comparison
        @test cond.op === :<
        @test cond.lhs isa Name && cond.lhs.name === :h
        @test cond.rhs isa Lit && cond.rhs.value == 0
        body = event_body(ev)
        @test length(body) == 1
        @test body[1] isa CallStatement
        @test body[1].call.fn.name === :reinit
        @test length(body[1].call.args) == 2
        @test body[1].call.args[1] isa Name && body[1].call.args[1].name === :v
        # D19: `h < 0` fires on the upward crossing of `0 - h`.
        crossing = event_zero_crossing(ev)
        @test crossing isa BinOp && crossing.op === :-
        @test crossing.lhs isa Lit && crossing.lhs.value == 0
        @test crossing.rhs isa Name && crossing.rhs.name === :h
    end

    # -----------------------------------------------------------------------------------
    @testset "golden: LQGController (plan 9.5)" begin
        pb = parse_block(LQG; ref = "project:LQGController", filename = "lqg.jl")
        @test scopes(pb) == [:constants, :parameters, :inputs, :outputs, :variables, :discrete]
        @test isempty(check_block(pb))
        @test block_balance(pb) == (unknowns = 0, equations = 0)
        @test block_equations(pb) == Any[]
        @test block_initial_equations(pb) == Any[]

        consts = constant_env(pb)
        @test consts[:nx] == 4
        @test consts[:nu] == 1
        @test consts[:ny] == 1
        iface = block_interface(pb)
        @test [c.name for c in iface.constants] == ["nx", "nu", "ny"]
        @test all(c -> c.structural, iface.constants)
        @test [p.name for p in iface.parameters] ==
              ["Ad", "Bd", "Cd", "L", "K", "Ki", "umax"]
        @test iface.parameters[1].type == "Real"    # catalog type is the element type
        @test iface.parameters[1].default ==
              "[1.0 1e-3 0.0 0.0; -0.02 0.998 0.01 0.0; 0.0 0.0 1.0 1e-3; 0.0 0.0 -0.02 0.998]"
        @test iface.parameters[7].unit == "V"
        @test [i.name for i in iface.inputs] == ["theta_m", "w_ref"]
        @test [o.name for o in iface.outputs] == ["u", "w_load_hat"]
        @test [v.name for v in iface.variables] == ["xhat", "z"]
        @test iface.variables[1].size == [4]
        @test iface.variables[2].size == Int[]

        ds = only(discrete_scopes(pb))
        @test discrete_period(ds) == 1e-3
        @test length(ds.body) == 8
        # D18: `y` and `v` are undeclared temporaries, created by assignment; check_block
        # above is the assertion that they type-check.
        vars = Dict(decl_name(d) => d for d in declarations(pb, :variables))
        @test !haskey(vars, :y)
        @test !haskey(vars, :v)
    end

    # -----------------------------------------------------------------------------------
    @testset "@initial, @discrete and @events are no longer rejected" begin
        src = """
        @block AllScopes begin
            @parameters a::Real = 1.0
            @variables x::Real = 0.0
            @outputs y::Real = 0.0
            @initial x ~ a
            @equations ddt(x) ~ 0.0
            @discrete Ts = 1e-3 begin
                y = x
            end
            @events x < -1.0 => begin
                reinit(x, 0.0)
            end
        end
        """
        pb = parse_block(src)
        ds = check_block(pb)
        @test !any(d -> occursin("not supported yet", d.message), ds)
        @test scopes(pb) == [:parameters, :variables, :outputs, :initial, :equations,
                             :discrete, :events]
        @test length(initial_equations(pb)) == 1
        @test length(discrete_scopes(pb)) == 1
        @test length(events(pb)) == 1
        # The textual subsystem scopes are parsed since J2.6 (decision D5).
        composite = parse_block("""
        @block Composite begin
            @ports a::Power{Rotation}
            @components g = LossyGear(n = 1.0)
            @connections connect(a, g.a)
        end
        """)
        @test !any(d -> occursin("not supported yet", d.message), check_block(composite))
        @test scopes(composite) == [:ports, :components, :connections]
        @test length(components(composite)) == 1
        @test only(components(composite)).block === :LossyGear
        @test length(connections(composite)) == 1
    end

    # -----------------------------------------------------------------------------------
    @testset "@initial: parsing and checking" begin
        src = """
        @block Init begin
            @constants N::Int = 2
            @parameters a::Real = 1.0
            @variables begin
                x::Real = 0.0
                v::Vec{N} = [0.0, 0.0]
            end
            @outputs y::Real
            @initial begin
                x ~ a
                for i in 1:N
                    v[i] ~ a
                end
                if a > 0.0
                    y ~ a
                else
                    y ~ -a
                end
            end
            @equations begin
                ddt(x) ~ 0.0
                y ~ x
                for i in 1:N
                    v[i] ~ 0.0
                end
            end
        end
        """
        pb = parse_block(src)
        @test isempty(check_block(pb))
        items = initial_equations(pb)
        @test length(items) == 3
        @test items[1] isa Equation && items[1].scope === :initial
        @test items[2] isa ForEquation
        @test items[3] isa IfEquation
        @test length(block_initial_equations(pb)) == 3
        # Initial equations do not count towards the balance count.
        @test block_balance(pb) == (unknowns = 4, equations = 4)

        # `ddt` has no meaning in an initial equation.
        bad = parse_block("""
        @block Init2 begin
            @variables x::Real = 0.0
            @outputs y::Real
            @initial ddt(x) ~ 0.0
            @equations begin
                ddt(x) ~ 0.0
                y ~ x
            end
        end
        """)
        d = lang_expect(bad, "E001", 4, 14; contains = "ddt")
        @test d !== nothing && occursin("@initial", d.message)
        @test block_initial_equations(bad) == Any[]

        # `=` is still not an equation.
        bad = parse_block("""
        @block Init3 begin
            @variables x::Real = 0.0
            @outputs y::Real
            @initial x = 0.0
            @equations begin
                ddt(x) ~ 0.0
                y ~ x
            end
        end
        """)
        d = lang_expect(bad, "E001", 4, 13; contains = "`=`")
        @test d !== nothing && occursin("use `~`", d.hint)

        # An initial `if` needs an else and equal branch counts, like @equations.
        bad = parse_block("""
        @block Init4 begin
            @variables x::Real = 0.0
            @initial begin
                if x > 0.0
                    x ~ 1.0
                end
            end
        end
        """)
        @test any(d -> d.code == "E001" && occursin("else", d.message), check_block(bad))
    end

    # -----------------------------------------------------------------------------------
    @testset "ifelse in a declaration default" begin
        pb = parse_block("""
        @block IfDefault begin
            @parameters p::Real = ifelse(1 > 0, 1.0, 2.0)
            @outputs y::Real
            @equations y ~ p
        end
        """)
        @test isempty(check_block(pb))
        @test decl_default(declarations(pb, :parameters)[1]) isa IfElse
        # A condition that is not Bool is E004.
        bad = parse_block("""
        @block BadIfDefault begin
            @parameters p::Real = ifelse(1.0, 1.0, 2.0)
            @outputs y::Real
            @equations y ~ p
        end
        """)
        @test any(d -> d.code == "E004" && occursin("condition", d.message), check_block(bad))
    end

    # -----------------------------------------------------------------------------------
    @testset "@discrete: header forms and period checking" begin
        # `Ts = <period>` (the spec's form).
        pb = parse_block("""
        @block D begin
            @outputs y::Real = 0.0
            @discrete Ts = 1e-3 begin
                y = 1.0
            end
        end
        """)
        @test isempty(check_block(pb))
        @test discrete_period(only(discrete_scopes(pb))) == 1e-3

        # The bare form, and a period that is a constant expression.
        pb = parse_block("""
        @block D begin
            @constants T::Real = 2.0
            @outputs y::Real = 0.0
            @discrete 1e-3 / T begin
                y = Ts
            end
        end
        """)
        @test isempty(check_block(pb))
        @test discrete_period(only(discrete_scopes(pb))) == 5e-4

        # `offset` is the one attribute, in the plan's `Ts = ..., [offset = ...]` form.
        pb = parse_block("""
        @block D begin
            @outputs y::Real = 0.0
            @discrete Ts = 1e-3, [offset = 1e-4] begin
                y = Ts
            end
        end
        """)
        @test isempty(check_block(pb))
        ds = only(discrete_scopes(pb))
        @test discrete_period(ds) == 1e-3
        @test discrete_offset(ds) == 1e-4

        # A zero offset is legal.
        pb = parse_block("""
        @block D begin
            @outputs y::Real = 0.0
            @discrete Ts = 1e-3, [offset = 0.0] begin
                y = 0.0
            end
        end
        """)
        @test isempty(check_block(pb))

        # The plan's `@discrete Ts = … [offset = …]` spelling (no comma).
        pb = parse_block("""
        @block D begin
            @outputs y::Real = 0.0
            @discrete Ts = 1e-3 [offset = 1e-4] begin
                y = 0.0
            end
        end
        """)
        @test isempty(check_block(pb))
        @test discrete_offset(only(discrete_scopes(pb))) == 1e-4

        # Errors: no period, wrong header name, a non-constant period, a bad offset.
        bad = parse_block("""
        @block D begin
            @outputs y::Real = 0.0
            @discrete begin
                y = 1.0
            end
        end
        """)
        d = lang_expect(bad, "E001", 3, 5; contains = "period")
        @test d !== nothing && occursin("Ts = <period>", d.hint)

        bad = parse_block("""
        @block D begin
            @parameters T::Real = 1e-3
            @outputs y::Real = 0.0
            @discrete T = 1e-3 begin
                y = 1.0
            end
        end
        """)
        lang_expect(bad, "E001", 4, 15; contains = "Ts")

        bad = parse_block("""
        @block D begin
            @parameters T::Real = 1e-3
            @outputs y::Real = 0.0
            @discrete Ts = T begin
                y = 1.0
            end
        end
        """)
        @test any(d -> d.code == "E004" && occursin("constant", d.message), check_block(bad))

        bad = parse_block("""
        @block D begin
            @outputs y::Real = 0.0
            @discrete Ts = -1e-3 begin
                y = 1.0
            end
        end
        """)
        @test any(d -> d.code == "E004" && occursin("positive", d.message), check_block(bad))

        bad = parse_block("""
        @block D begin
            @outputs y::Real = 0.0
            @discrete Ts = 1e-3, [offset = 2e-3] begin
                y = 1.0
            end
        end
        """)
        @test any(d -> d.code == "E004" && occursin("offset", d.message), check_block(bad))

        bad = parse_block("""
        @block D begin
            @outputs y::Real = 0.0
            @discrete Ts = 1e-3, [phase = 0.0] begin
                y = 1.0
            end
        end
        """)
        @test any(d -> d.code == "E001" && occursin("phase", d.message), check_block(bad))

        bad = parse_block("""
        @block D begin
            @outputs y::Real = 0.0
            @discrete Ts = 1e-3 begin
            end
        end
        """)
        @test any(d -> d.code == "E001" && occursin("empty", d.message), check_block(bad))
    end

    # -----------------------------------------------------------------------------------
    @testset "@discrete: statements, types and D18 temporaries" begin
        src = """
        @block D begin
            @constants N::Int = 3
            @inputs u::Real
            @outputs out::Real = 0.0
            @variables begin
                x::Vec{N} = [0.0, 0.0, 0.0]
                c::Real = 0.0
            end
            @discrete Ts = 1e-3 begin
                n = 0
                y = u + c
                n = n + 1
                n += 1
                out = y * Ts
                x[1] += out
                x[2] = clamp(x[1], -1.0, 1.0)
                if abs(y) > 2.0
                    out = 1.0
                elseif n > 2
                    out = 2.0
                    n = 0
                else
                    out = 3.0
                end
                for i in 1:N
                    x[i] = x[i] * Ts
                end
                flag = y > 0.0
                if flag && !(n < 0)
                    out = x[N]
                end
                holdval = previous(out)
                sampled = hold(u)
                out = holdval + sampled
            end
            @equations begin
                ddt(c) ~ 0.0
            end
        end
        """
        pb = parse_block(src)
        @test isempty(check_block(pb))
        @test block_balance(pb) == (unknowns = 1, equations = 1)  # only c is continuous
        ds = only(discrete_scopes(pb))
        @test any(s -> s isa IfStatement, ds.body)
        @test any(s -> s isa ForStatement, ds.body)
        assigns = [s for s in ds.body if s isa Assign]
        @test any(s -> assign_op(s) === :assign, assigns)
        @test any(s -> assign_op(s) === :+, assigns)

        # D18: a local is created by its first assignment and is not visible in @equations.
        bad = parse_block("""
        @block D2 begin
            @outputs out::Real = 0.0
            @discrete Ts = 1e-3 begin
                out = localvalue
            end
        end
        """)
        d = lang_expect(bad, "E003", 4, 19; contains = "localvalue")
        @test d !== nothing && occursin("temporary", d.hint)

        # A local that a later statement sets with a different type is E004.
        bad = parse_block("""
        @block D3 begin
            @outputs out::Real = 0.0
            @discrete Ts = 1e-3 begin
                tmp = 1.0
                tmp = true
                out = tmp
            end
        end
        """)
        @test any(d -> d.code == "E004" && occursin("Bool", d.message), check_block(bad))

        # A compound assignment to an undeclared name is a read of an undeclared name.
        bad = parse_block("""
        @block D4 begin
            @outputs out::Real = 0.0
            @discrete Ts = 1e-3 begin
                tmp += 1
                out = tmp
            end
        end
        """)
        d = lang_expect(bad, "E003", 4, 9; contains = "tmp")
        @test d !== nothing && occursin("tmp = ...", d.hint)

        # Inputs, parameters, constants and ports are read-only.
        for (decl, name) in (("@inputs u::Real", "u"),
                             ("@parameters p::Real = 1.0", "p"),
                             ("@constants K::Int = 1", "K"))
            bad = parse_block("""
            @block D5 begin
                $decl
                @outputs out::Real = 0.0
                @discrete Ts = 1e-3 begin
                    $name = 1.0
                    out = 1.0
                end
            end
            """)
            @test any(d -> d.code == "E004" && occursin("cannot be assigned", d.message),
                      check_block(bad))
        end

        # Predefined names and built-in functions cannot be shadowed by D18 temporaries or
        # loop variables.
        for (body, name) in (("t = 1.0\n out = 1.0", "t"),
                             ("Ts = 1.0\n out = 1.0", "Ts"),
                             ("sin = 1.0\n out = 1.0", "sin"),
                             ("for sin in 1:2\n out = 1.0\n end", "sin"))
            bad = parse_block("""
            @block D5b begin
                @outputs out::Real = 0.0
                @discrete Ts = 1e-3 begin
                    $body
                end
            end
            """)
            @test any(d -> d.code == "E003" && occursin("`$name`", d.message),
                      check_block(bad))
        end

        # `Ts` is readable inside the body and nowhere else.
        pb = parse_block("""
        @block D6 begin
            @inputs u::Real
            @outputs out::Real = 0.0
            @equations out ~ Ts
        end
        """)
        d = lang_expect(pb, "E001", 4, 19; contains = "Ts")
        @test d !== nothing && occursin("@discrete", d.message)

        # Int is the natural type of a counter local, and Real -> Int never happens.
        pb = parse_block("""
        @block D7 begin
            @outputs out::Real = 0.0
            @discrete Ts = 1e-3 begin
                n = 0
                n += 1
                out = n
            end
        end
        """)
        @test isempty(check_block(pb))

        # A D18 temporary takes its size from the assigned array literal.
        pb = parse_block("""
        @block D7c begin
            @outputs out::Real = 0.0
            @discrete Ts = 1e-3 begin
                tmp = [1.0, 2.0]
                out = tmp[2]
            end
        end
        """)
        @test isempty(check_block(pb))
        # An element of a D18 temporary beyond its size is E005.
        bad = parse_block("""
        @block D7d begin
            @outputs out::Real = 0.0
            @discrete Ts = 1e-3 begin
                tmp = [1.0, 2.0]
                out = tmp[3]
            end
        end
        """)
        @test any(d -> d.code == "E005" && occursin("index out of range", d.message),
                  check_block(bad))

        # A *held* discrete counter may be declared Int: it lives in discrete code only.
        pb = parse_block("""
        @block Counter begin
            @variables n::Int = 0
            @outputs y::Int = 0
            @discrete Ts = 1e-3 begin
                n += 1
                y = n
            end
        end
        """)
        @test isempty(check_block(pb))
        @test block_balance(pb) == (unknowns = 0, equations = 0)
        @test decl_type(declarations(pb, :variables)[1]).kind === :Int

        # A held Bool variable is a discrete state, not a continuous one.
        pb = parse_block("""
        @block Flip begin
            @variables q::Bool = false
            @outputs y::Bool = false
            @discrete Ts = 1e-3 begin
                q = !q
                y = q
            end
        end
        """)
        @test isempty(check_block(pb))
        @test block_balance(pb) == (unknowns = 0, equations = 0)

        # An Int that is not discrete is still rejected.
        bad = parse_block("""
        @block D7b begin
            @variables n::Int = 0
            @outputs out::Real
            @equations out ~ n
        end
        """)
        @test any(d -> d.code == "E004" && occursin("Int", d.message), check_block(bad))

        bad = parse_block("""
        @block D8 begin
            @outputs out::Real = 0.0
            @discrete Ts = 1e-3 begin
                n = 0
                n = 1.5
                out = n
            end
        end
        """)
        @test any(d -> d.code == "E004" && occursin("Int", d.message), check_block(bad))

        # Statements that are not discrete code.
        for (body, needle) in (
            ("while out > 0.0\n out = 0.0\n end", "while"),
            ("function f(a)\n a\n end", "function"),
            ("out ~ 1.0", "`~`"),
            ("reinit(out, 0.0)", "reinit"),
            ("sin(out)", "not a statement"),
        )
            bad = parse_block("""
            @block D9 begin
                @outputs out::Real = 0.0
                @discrete Ts = 1e-3 begin
                    $body
                end
            end
            """)
            @test any(d -> d.code == "E001" && occursin(needle, d.message), check_block(bad))
        end

        # A for bound must be static, and a loop index must fit the array it indexes.
        bad = parse_block("""
        @block D10 begin
            @parameters P::Int = 3
            @outputs out::Real = 0.0
            @discrete Ts = 1e-3 begin
                for i in 1:P
                    out = 1.0
                end
            end
        end
        """)
        @test any(d -> d.code == "E005" && occursin("constant", d.message), check_block(bad))
    end

    # -----------------------------------------------------------------------------------
    @testset "@events: conditions, bodies and reinit" begin
        src = """
        @block E begin
            @parameters e::Real = 0.8
            @variables begin
                h::Real = 1.0
                v::Real = 0.0
            end
            @outputs hit::Real = 0.0
            @events begin
                h < 0.0 => begin
                    reinit(v, -e * v)
                    hit = 1.0
                end
                v > 2.0 => begin
                    t_local = v
                    hit = t_local
                end
                h + 1.0 => begin
                    hit = 0.0
                end
            end
            @equations begin
                ddt(h) ~ v
                ddt(v) ~ 0.0
            end
        end
        """
        pb = parse_block(src)
        @test isempty(check_block(pb))
        evs = events(pb)
        @test length(evs) == 3
        @test event_condition(evs[1]) isa Comparison
        @test event_condition(evs[2]).op === :>
        @test event_condition(evs[3]) isa BinOp
        @test length(event_body(evs[1])) == 2
        @test event_body(evs[1])[1] isa CallStatement
        @test event_body(evs[1])[2] isa Assign
        # `v > 2.0` normalizes to `v - 2.0`.
        crossing = event_zero_crossing(evs[2])
        @test crossing isa BinOp && crossing.op === :-
        @test crossing.lhs isa Name && crossing.lhs.name === :v
        @test crossing.rhs isa Lit && crossing.rhs.value == 2.0

        # Only `<` and `>` comparisons have an upward zero crossing (D19).
        for op in ("<=", ">=", "==", "!=")
            bad = parse_block("""
            @block E2 begin
                @variables x::Real = 0.0
                @events x $op 0.0 => begin
                    reinit(x, 0.0)
                end
            end
            """)
            @test any(d -> d.code == "E001" && occursin("`$op`", d.message), check_block(bad))
        end

        # A Bool condition is not a real expression.
        bad = parse_block("""
        @block E3 begin
            @outputs flag::Bool = false
            @events flag => begin
                flag = false
            end
        end
        """)
        @test any(d -> d.code == "E004" && occursin("real expression", d.message), check_block(bad))

        # `&&` in an event condition is rejected: the trigger is one crossing.
        bad = parse_block("""
        @block E4 begin
            @variables x::Real = 0.0
            @events x > 0.0 && x < 1.0 => begin
                reinit(x, 0.0)
            end
        end
        """)
        @test any(d -> d.code == "E004" && occursin("real expression", d.message), check_block(bad))

        # `reinit` needs a continuous state, not an output, parameter or temporary.
        for (decl, name) in (("@outputs y::Real = 0.0", "y"),
                             ("@parameters p::Real = 1.0", "p"))
            bad = parse_block("""
            @block E5 begin
                $decl
                @events t > 0.0 => begin
                    reinit($name, 0.0)
                end
            end
            """)
            @test any(d -> d.code == "E004" && occursin("reinit", d.message),
                      check_block(bad))
        end
        bad = parse_block("""
        @block E6 begin
            @events t > 0.0 => begin
                tmp = 1.0
                reinit(tmp, 0.0)
            end
        end
        """)
        @test any(d -> d.code == "E004" && occursin("temporary", d.message), check_block(bad))

        # An entry must be `cond => begin ... end`.
        bad = parse_block("""
        @block E7 begin
            @variables x::Real = 0.0
            @events begin
                x > 0.0
            end
        end
        """)
        @test any(d -> d.code == "E001" && occursin("cond =>", d.message), check_block(bad))

        # `@discrete` and `@events` are separate: reinit is events-only.
        bad = parse_block("""
        @block E8 begin
            @variables x::Real = 0.0
            @discrete Ts = 1e-3 begin
                reinit(x, 0.0)
            end
        end
        """)
        d = lang_expect(bad, "E001", 4, 9; contains = "reinit")
        @test d !== nothing && occursin("@events", d.hint)
    end

    # -----------------------------------------------------------------------------------
    @testset "Vec/Mat: literals, sizes, indexing and linear algebra" begin
        pb = parse_block("""
        @block Arrays begin
            @constants N::Int = 3
            @parameters begin
                A::Mat{2,2} = [1.0 2.0; 3.0 4.0]
                b::Vec{2} = [1.0, 2.0]
            end
            @variables begin
                v::Vec{N} = [1.0, 2.0, 3.0]
                w::Vec{2}
                M::Mat{N,N}
                s::Real = 0.0
            end
            @outputs y::Real
            @equations begin
                w ~ A * b
                y ~ dot(b, w)
                M[1, 1] ~ 1.0
                for i in 1:N
                    v[i] ~ 0.0
                end
                s ~ v[N]
                y ~ M[2, 2]
            end
        end
        """)
        # The block is unbalanced (M is an array of 9 unknowns with one equation); only
        # errors matter here.
        @test isempty(lang_errors(pb))
        items = equations(pb)
        @test items[1].rhs isa BinOp && items[1].rhs.op === :*
        @test items[2].rhs isa Call && items[2].rhs.fn.name === :dot
        @test items[3].lhs isa Index
        @test items[4] isa ForEquation

        # `A \\ b` is the fixed-size linear solve.
        pb = parse_block("""
        @block Solve begin
            @parameters A::Mat{2,2} = [2.0 0.0; 0.0 4.0]
            @parameters b::Vec{2} = [2.0, 8.0]
            @outputs x::Vec{2}
            @equations x ~ A \\ b
        end
        """)
        @test isempty(check_block(pb))
        @test equations(pb)[1].rhs isa BinOp && equations(pb)[1].rhs.op === Symbol("\\")

        # Indexing errors: literal, constant and loop indices.
        cases = [
            ("v[0]", "out ~ v[0]", "index out of range"),
            ("v[4] with Vec{3}", "out ~ v[4]", "index out of range"),
            ("M[3,1]", "out ~ M[3, 1]", "index out of range"),
            ("v[1,2]", "out ~ v[1, 2]", "one index"),
            ("M[1]", "out ~ M[1]", "two indices"),
        ]
        for (label, body, needle) in cases
            bad = parse_block("""
            @block BadIndex begin
                @variables begin
                    v::Vec{3} = [0.0, 0.0, 0.0]
                    M::Mat{2,2} = [0.0 0.0; 0.0 0.0]
                end
                @outputs out::Real
                @equations $body
            end
            """)
            @test any(d -> d.code == "E005" && occursin(needle, d.message), check_block(bad))
        end

        # A `for` index that runs past the array is E005 (the J2.1 unrolled index check).
        bad = parse_block("""
        @block BadLoop begin
            @constants N::Int = 5
            @variables v::Vec{3} = [0.0, 0.0, 0.0]
            @outputs out::Real
            @equations begin
                for i in 1:N
                    v[i] ~ 0.0
                end
                out ~ 0.0
            end
        end
        """)
        d = lang_expect(bad, "E005", 7, 13; contains = "loop index")
        @test d !== nothing && occursin("1:5", d.message)

        # A constant index is checked as well.
        bad = parse_block("""
        @block BadConstant begin
            @constants N::Int = 4
            @variables v::Vec{3} = [0.0, 0.0, 0.0]
            @outputs out::Real
            @equations out ~ v[N]
        end
        """)
        lang_expect(bad, "E005", 5, 22; contains = "index out of range")

        # An equation index must be static; discrete code may use a runtime index.
        bad = parse_block("""
        @block BadDynamic begin
            @parameters j::Int = 1
            @variables v::Vec{3} = [0.0, 0.0, 0.0]
            @outputs out::Real
            @equations out ~ v[j]
        end
        """)
        @test any(d -> d.code == "E005" && occursin("not static", d.message), check_block(bad))
        ok = parse_block("""
        @block DynamicOk begin
            @variables v::Vec{3} = [0.0, 0.0, 0.0]
            @outputs out::Real = 0.0
            @discrete Ts = 1e-3 begin
                j = 2
                out = v[j]
            end
        end
        """)
        @test isempty([d for d in check_block(ok) if d.code == "E005"])

        # Sizes are static: a Vec sized by a parameter is E005.
        bad = parse_block("""
        @block BadSize begin
            @parameters P::Int = 3
            @variables v::Vec{P} = [0.0, 0.0, 0.0]
            @outputs out::Real
            @equations out ~ v[1]
        end
        """)
        lang_expect(bad, "E005", 3, 23; contains = "not static")

        # `ifelse` in a size is folded from the constants (spec: defaults and sizes).
        pb = parse_block("""
        @block IfSize begin
            @constants N::Int = 2
            @variables v::Vec{ifelse(N > 1, 3, 2)} = [0.0, 0.0, 0.0]
        end
        """)
        @test isempty(lang_errors(pb))
        v = declarations(pb, :variables)[1]
        @test type_size(decl_type(v), constant_env(pb)) == [3]
        @test !any(d -> d.code == "W204" && occursin("`N`", d.message), check_block(pb))
        pb = parse_block("""
        @block IfSize2 begin
            @constants N::Int = 2
            @variables v::Vec{ifelse(N > 2, 3, 2)} = [0.0, 0.0]
        end
        """)
        @test isempty(lang_errors(pb))
        @test type_size(decl_type(declarations(pb, :variables)[1]), constant_env(pb)) == [2]

        # A size that does not fold is still E005.
        bad = parse_block("""
        @block BadIfSize begin
            @parameters P::Int = 2
            @variables v::Vec{ifelse(P > 1, 3, 2)} = [0.0, 0.0, 0.0]
        end
        """)
        @test any(d -> d.code == "E005" && occursin("not static", d.message), check_block(bad))

        # Matrix literals need rectangular rows.
        bad = parse_block("""
        @block BadMatrix begin
            @parameters A::Mat{2,2} = [1.0 2.0; 3.0]
            @variables x::Real = 0.0
            @outputs out::Real
            @equations out ~ x
        end
        """)
        @test any(d -> d.code == "E005" && occursin("same length", d.message), check_block(bad))

        # `*` on two vectors is not the dot product.
        bad = parse_block("""
        @block BadMul begin
            @variables begin
                a::Vec{3} = [1.0, 1.0, 1.0]
                b::Vec{3} = [1.0, 1.0, 1.0]
            end
            @outputs out::Real
            @equations out ~ a * b
        end
        """)
        @test any(d -> d.code == "E004" && occursin("dot", d.hint), check_block(bad))
    end

    # -----------------------------------------------------------------------------------
    @testset "units in @initial, @discrete and @events" begin
        bad = parse_block("""
        @block U1 begin
            @variables x::Real = 0.0, [unit = "s"]
            @outputs y::Real = 0.0, [unit = "m"]
            @discrete Ts = 1e-3 begin
                y = x
            end
            @equations y ~ 0.0
        end
        """)
        d = lang_expect(bad, "E006", 5, 13; contains = "assign")
        @test d !== nothing && occursin("[m]", d.message) && occursin("[s]", d.message)

        bad = parse_block("""
        @block U2 begin
            @variables begin
                x::Real = 0.0, [unit = "s"]
                y::Real = 0.0, [unit = "m"]
            end
            @outputs out::Real
            @initial x ~ y
            @equations begin
                ddt(x) ~ 0.0
                out ~ x
            end
        end
        """)
        @test any(d -> d.code == "E006" && occursin("[m]", d.message), check_block(bad))

        # A literal is legal in any unit, and an un-unit-ed value is a wildcard.
        ok = parse_block("""
        @block U3 begin
            @variables x::Real = 0.0, [unit = "s"]
            @inputs u::Real
            @outputs y::Real = 0.0, [unit = "s"]
            @discrete Ts = 1e-3 begin
                y = u
                y = 1.0
            end
        end
        """)
        @test isempty([d for d in check_block(ok) if d.code == "E006"])
    end

    # -----------------------------------------------------------------------------------
    @testset "balance: discrete values are excluded, @initial does not count" begin
        pb = parse_block("""
        @block Balance begin
            @inputs u::Real
            @outputs held::Real = 0.0
            @variables begin
                c::Real = 0.0
                x::Real = 0.0
            end
            @initial c ~ 0.0
            @equations begin
                ddt(c) ~ u
                x ~ c
            end
            @discrete Ts = 1e-3 begin
                held = x
            end
        end
        """)
        @test isempty(check_block(pb))
        @test block_balance(pb) == (unknowns = 2, equations = 2)

        # An if equation counts one branch, with for loops unrolled.
        pb = parse_block("""
        @block Branches begin
            @constants N::Int = 3
            @variables v::Vec{N} = [0.0, 0.0, 0.0]
            @outputs y::Real
            @inputs u::Real
            @equations begin
                for i in 1:N
                    v[i] ~ 0.0
                end
                if u > 0.0
                    y ~ v[1]
                else
                    for i in 1:N
                        y ~ v[i]
                    end
                end
            end
        end
        """)
        # The two branches have 1 and 3 scalar equations: E001 names both counts.
        d = lang_expect(pb, "E001", 10, 9; contains = "same number")
        @test d !== nothing && occursin("1, 3", d.message)
    end

    # -----------------------------------------------------------------------------------
    # Every row of the function whitelist, allowed and rejected, in the same testset.
    # -----------------------------------------------------------------------------------

    @testset "whitelist: every function row (allowed and E002)" begin
        expected = Set([
            :sin, :cos, :tan, :asin, :acos, :atan, :sinh, :cosh, :tanh, :exp, :log,
            :log10, :sqrt, :abs, :sign, :min, :max, :clamp, :floor, :ceil, :round, :mod,
            :rem, :hypot, :dot, :norm, :cross, :transpose, :ddt, :int, :deadzone,
            :saturate, :delay, :previous, :hold, :reinit, :interp1, :interp2,
            :noise_normal,
        ])
        @test Set(keys(BGSim.FUNCTION_LOOKUP)) == expected
        @test length(BGSim.FUNCTION_RULES) == 23
        @test length(BGSim.INTRINSIC_RULES) == 4

        for rule in BGSim.FUNCTION_RULES
            name = rule.names[1]
            spec = lang_row_spec(rule, name)

            # Allowed: every context the row offers.
            for ctx in (:equation, :discrete, :events)
                allows = ctx in rule.contexts || (ctx === :events && :discrete in rule.contexts)
                allows || continue
                ref = rule.stdlib_only ? "stdlib:test/Row" : "inline:row"
                src = lang_row_source(ctx, name, spec)
                ds = check_block(parse_block(src; ref = ref))
                bad = [
                    d for d in ds if d.code in ("E001", "E002", "E003", "E004") &&
                                     occursin(String(name), d.message)
                ]
                @test isempty(bad)
            end

            # Rejected with E002: the whitelist is closed, so a near-miss is not a function.
            miss = Symbol(name, "_x")
            src = lang_row_source(:equation, miss, spec)
            ds = check_block(parse_block(src))
            @test any(
                d -> d.code == "E002" && occursin(String(name), d.message) &&
                     occursin(String(miss), d.message),
                ds,
            )

            # Rejected in a scope the row does not offer (E001), and stdlib-only in user
            # blocks (E002). Together with the near-miss above that is an allowed and a
            # rejected test for every row.
            if !(:equation in rule.contexts)
                src = lang_row_source(:equation, name, spec)
                ds = check_block(parse_block(src; ref = "stdlib:test/Row"))
                @test any(d -> d.code == "E001" && occursin(String(name), d.message), ds)
            end
            if rule.stdlib_only
                ctx = :discrete in rule.contexts ? :discrete : :equation
                src = lang_row_source(ctx, name, spec)
                ds = check_block(parse_block(src; ref = "inline:row"))
                @test any(
                    d -> d.code == "E002" && occursin("stdlib", d.message) &&
                         occursin(String(name), d.message),
                    ds,
                )
            end
        end

        # Names outside the whitelist are E002 with a helpful hint.
        pb = parse_block("""
        @block Unknown begin
            @inputs e::Real
            @outputs u::Real
            @equations u ~ rand(e)
        end
        """)
        d = lang_expect(pb, "E002", 4, 20; contains = "rand")
        @test d !== nothing && occursin("noise_normal", d.hint)
        @test BGSim.function_rule(:inv) === nothing
        @test BGSim.function_rule(:randn) === nothing

        # The D12 intrinsics table is the same single source as FUNCTION_RULES.
        names = [r.name for r in BGSim.INTRINSIC_RULES]
        @test names == [:interp1, :interp2, :noise_normal, :delay]
        @test [r.stdlib_only for r in BGSim.INTRINSIC_RULES] == [false, false, true, true]
        for r in BGSim.INTRINSIC_RULES
            fr = BGSim.function_rule(r.name)
            @test fr !== nothing
            @test fr.contexts == r.contexts
            @test fr.stdlib_only == r.stdlib_only
            @test fr.min_args == r.min_args && fr.max_args == r.max_args
            @test BGSim.intrinsic_rule(r.name) === r
        end
        @test BGSim.intrinsic_rule(:sin) === nothing

        # The operator table still covers every spec row (J1.1's table, unchanged).
        @test length(BGSim.SYNTAX_RULES) == 23
        for key in (:arith, :pow_int, :pow_real, :compare, :logic, :equation, :assign,
                    :opassign, :ifelse, :if, :for, :while, :array, :derivative, :integral,
                    :previous, :hold, :reinit, :funcdef, :macro, :string, :ternary,
                    :broadcast)
            @test BGSim.syntax_rule(key) isa BGSim.SyntaxRule
        end
    end
end
