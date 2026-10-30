# J1.1 — parser, whitelist and block-level checks.
#
# Everything here runs against the public front-end API (`parse_block`, `check_block`,
# `block_interface`, `block_equations` and the accessors). The golden sources are the spec's
# own blocks; the catalog test parses the source text of all 36 M1 blocks from
# `contracts/fixtures/catalog/valid/catalog.min.json`; the negative tests assert the exact
# line and column of every E-code.
using Test
using JSON3
import BGSim
using BGSim:
    parse_block,
    parse_blocks,
    check_block,
    block_interface,
    block_equations,
    block_name,
    block_ref,
    block_source,
    block_balance,
    block_filename,
    scopes,
    declarations,
    equations,
    causality,
    ports,
    decl_name,
    decl_type,
    decl_default,
    decl_attrs,
    decl_range,
    expr_range,
    type_kind,
    type_name,
    type_size,
    type_element,
    type_domain,
    ParsedBlock,
    Decl,
    TypeSpec,
    CausalityDecl,
    Diagnostic,
    SourceRange,
    SourceRef,
    Related,
    severity_of,
    diag,
    to_namedtuple,
    to_dict,
    from_dict,
    sort_diagnostics
using BGSim:
    Lit,
    Name,
    Call,
    BinOp,
    UnOp,
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
    EqBranch

const ROOT = normpath(joinpath(@__DIR__, "..", "..", ".."))
const CATALOG_FIXTURE =
    joinpath(ROOT, "contracts", "fixtures", "catalog", "valid", "catalog.min.json")
const DIAGNOSTIC_FIXTURE =
    joinpath(ROOT, "contracts", "fixtures", "diagnostic", "valid", "diagnostics.sample.json")

# The spec's blocks, verbatim (spec "Block structure and scopes" and "Worked example:
# gear with backlash and efficiency").
const SPEC_C = """
@block C begin
    @ports p::Power{Generic}
    @parameters c::Real = 1.0, [min = 0]
    @variables q::Real = 0.0, [state = :prefer]
    @equations begin
        ddt(q) ~ p.f
        p.e ~ q / c
    end
    @causality p => :effort_out   # preferred: integral causality
end
"""

const SPEC_PI = """
@block PIController begin
    @parameters begin
        Kp::Real = 1.0, [tunable = true]
        Ti::Real = 0.1, [unit = "s", min = 0]
    end
    @inputs  e::Real
    @outputs u::Real
    @variables x::Real = 0.0
    @equations begin
        ddt(x) ~ e / Ti
        u ~ Kp * (e + x)
    end
end
"""

const SPEC_GEARBACKLASH = """
@block GearBacklash begin
    @ports begin
        a::Power{Rotation}
        b::Power{Rotation}
    end
    @parameters begin
        k::Real   = 1e4,  [unit = "N*m/rad", min = 0]    # tooth contact stiffness
        d::Real   = 5.0,  [unit = "N*m*s/rad", min = 0]  # contact damping
        gap::Real = 0.01, [unit = "rad", min = 0]        # total backlash
    end
    @variables begin
        phi::Real = 0.0, [unit = "rad"]     # relative angle a minus b
        w::Real,         [unit = "rad/s"]
        T::Real,         [unit = "N*m"]
    end
    @equations begin
        w ~ a.f - b.f
        ddt(phi) ~ w
        # damping acts only in contact and never pulls the teeth together
        T ~ ifelse(phi >  gap/2, max(k*(phi - gap/2) + d*w, 0.0),
            ifelse(phi < -gap/2, min(k*(phi + gap/2) + d*w, 0.0), 0.0))
        a.e ~ T
        b.e ~ -T
    end
end
"""

const SPEC_LOSSYGEAR = """
@block LossyGear begin
    @ports begin
        a::Power{Rotation}    # input shaft (fast)
        b::Power{Rotation}    # output shaft (slow)
    end
    @parameters begin
        n::Real   = 10.0                    # a.f = n * b.f
        eta::Real = 0.9, [min = 0, max = 1] # efficiency
    end
    @equations begin
        a.f ~ n * b.f
        # efficiency depends on power direction: driven from a, or back-driven from b
        b.e ~ -n * a.e * ifelse(a.e * a.f > 0, eta, 1/eta)
    end
end
"""

# `I`, `R` and `Se` in the spec's style (the spec gives C in full and lists these in the
# element table; these are their natural one-port forms).
const SPEC_I = """
@block I begin
    @ports p::Power{Generic}
    @parameters i::Real = 1.0, [unit = "effort*s/flow", min = 0]
    @variables P::Real = 0.0, [unit = "effort*s", state = :prefer]
    @equations begin
        ddt(P) ~ p.e
        p.f ~ P / i
    end
    @causality p => :flow_out   # preferred: integral causality
end
"""

const SPEC_R = """
@block R begin
    @ports p::Power{Generic}
    @parameters r::Real = 1.0, [unit = "effort/flow", min = 0]
    @equations p.e ~ r * p.f
end
"""

const SPEC_SE = """
@block Se begin
    @ports p::Power{Generic}
    @parameters e::Real = 1.0, [unit = "effort"]
    @equations p.e ~ e
    @causality p => (:effort_out, :fixed)
end
"""

# ---------------------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------------------

"""The source position of a diagnostic as `(line, col)`, or `nothing`."""
function at(d::Diagnostic)
    d.source === nothing && return nothing
    r = d.source.range
    r === nothing && return nothing
    return (r.line, r.col)
end

"""Assert that a diagnostic with `code` (and an optional message fragment) exists at exactly
`(line, col)`. Returns the diagnostic so callers can assert on hint or severity."""
function expect_at(pb::ParsedBlock, code::String, line::Int, col::Int; contains = nothing)
    ds = check_block(pb)
    hits = [
        d for d in ds if
        d.code == code && (contains === nothing || occursin(contains, d.message))
    ]
    @test !isempty(hits)
    isempty(hits) && return nothing
    d = hits[1]
    @test at(d) == (line, col)
    return d
end

function codes(pb::ParsedBlock)
    return [d.code for d in check_block(pb)]
end

"""Build a block whose `@equations` call one whitelisted function, for the per-row
whitelist tests. `decl` is the declaration scope for the arguments (parameters, or variables
for `ddt`)."""
function row_source(
    fname::String;
    nargs::Int = 1,
    argtypes::Vector{String} = fill("Real", nargs),
    argnames::Vector{String} = ["a", "b", "c", "d"][1:nargs],
    callargs::Vector{String} = argnames,
    rettype::String = "Real",
    decl::String = "parameters",
    ref::String = "inline:row",
)
    decls = join(["        $(argnames[i])::$(argtypes[i])" for i in 1:nargs], "\n")
    return """
    @block RowTest begin
        @$(decl) begin
    $(decls)
        end
        @variables r::$(rettype)
        @equations r ~ $(fname)($(join(callargs, ", ")))
    end
    """
end

const ROW_OVERRIDES = Dict{Symbol,NamedTuple}(
    :dot => (nargs = 2, argtypes = ["Vec{3}", "Vec{3}"], rettype = "Real"),
    :norm => (nargs = 1, argtypes = ["Vec{3}"], rettype = "Real"),
    :cross => (nargs = 2, argtypes = ["Vec{3}", "Vec{3}"], rettype = "Vec{3}"),
    :transpose => (nargs = 1, argtypes = ["Mat{2,2}"], rettype = "Mat{2,2}"),
    :ddt => (nargs = 1, argtypes = ["Real"], rettype = "Real", decl = "variables"),
    :int => (nargs = 2, argtypes = ["Real", "Real"], rettype = "Real"),
    :delay => (nargs = 2, argtypes = ["Real", "Real"], callargs = ["a", "1.0"]),
    :deadzone => (nargs = 3, argtypes = ["Real", "Real", "Real"]),
    :saturate => (nargs = 3, argtypes = ["Real", "Real", "Real"]),
    :interp1 => (nargs = 3, argtypes = ["Real", "Vec{3}", "Vec{3}"]),
    :interp2 => (
        nargs = 4,
        argtypes = ["Real", "Vec{3}", "Vec{3}", "Mat{3,3}"],
    ),
)

# ---------------------------------------------------------------------------------------
# The suite
# ---------------------------------------------------------------------------------------

@testset "J1.1 parser and whitelist" begin
    # -----------------------------------------------------------------------------------
    @testset "diagnostic contract (plan 3.4)" begin
        items = JSON3.read(read(DIAGNOSTIC_FIXTURE, String))
        @test items isa JSON3.Array
        @test length(items) >= 20

        allowed = Set([
            "code", "severity", "message", "hint", "path", "block", "scope", "source",
            "node", "connection", "related",
        ])
        for item in items
            # Every key the fixture uses is representable by our type.
            @test all(k -> String(k) in allowed, keys(item))
            d = from_dict(item)
            @test d.code == String(item.code)
            @test d.severity == String(item.severity)
            @test d.severity == severity_of(d.code)
            @test d.message == String(item.message)
            dict = to_dict(d)
            @test Set(keys(dict)) ⊆ allowed
            @test dict["severity"] == String(item.severity)
            @test haskey(dict, "source") == haskey(item, :source)
            # A JSON round trip through the worker's shape is lossless.
            back = from_dict(JSON3.read(JSON3.write(to_namedtuple(d))))
            @test to_dict(back) == dict
        end

        @test severity_of("E000") == "error"
        @test severity_of("W204") == "warning"
        @test severity_of("I100") == "info"

        # The block-level E103 precheck is the one documented severity override.
        pb = parse_block("""
        @block A begin
            @variables x::Real = 0.0
            @outputs y::Real
            @equations y ~ 1.0
        end
        """)
        d = expect_at(pb, "E103", 1, 1)
        @test d !== nothing && d.severity == "warning"
        @test d !== nothing && d.scope === nothing
    end

    # -----------------------------------------------------------------------------------
    @testset "golden parse: C (spec)" begin
        pb = parse_block(SPEC_C; filename = "C.jl", ref = "stdlib:bondgraph/C")
        @test block_name(pb) == :C
        @test block_ref(pb) == "stdlib:bondgraph/C"
        @test block_filename(pb) == "C.jl"
        @test scopes(pb) == [:ports, :parameters, :variables, :equations, :causality]
        @test length(ports(pb)) == 1
        @test decl_name(ports(pb)[1]) == :p
        @test type_kind(decl_type(ports(pb)[1])) == :Power
        @test type_domain(decl_type(ports(pb)[1])) == :Generic
        @test length(declarations(pb, :parameters)) == 1
        @test decl_name(declarations(pb, :parameters)[1]) == :c
        @test decl_attrs(declarations(pb, :parameters)[1])[:min] == 0
        @test decl_attrs(declarations(pb, :variables)[1])[:state] == :prefer
        @test decl_default(declarations(pb, :variables)[1]) isa Lit
        @test length(equations(pb)) == 2
        @test equations(pb)[1] isa Equation
        @test equations(pb)[1].lhs isa Call
        @test equations(pb)[1].lhs.fn.name == :ddt
        @test block_balance(pb) == (unknowns = 2, equations = 2)
        @test isempty(check_block(pb))
        @test codes(pb) == String[]

        iface = block_interface(pb)
        @test length(iface.parameters) == 1
        @test iface.parameters[1].name == "c"
        @test iface.parameters[1].type == "Real"
        @test iface.parameters[1].default == "1.0"
        @test iface.parameters[1].unit === nothing
        @test iface.parameters[1].min == 0
        @test iface.parameters[1].tunable == false
        @test iface.parameters[1].options === nothing
        @test iface.variables[1].name == "q"
        @test iface.variables[1].size == Int[]
        @test iface.variables[1].start == "0.0"
        @test iface.variables[1].state == "prefer"
        @test iface.ports == [(name = "p", domain = "Generic", size = Int[], frame = nothing)]
        @test iface.causality[1].ports == ["p"]
        @test iface.causality[1].kind == "preferred"
        @test iface.causality[1].value == "effort_out"
        @test length(block_equations(pb)) == 2
    end

    # -----------------------------------------------------------------------------------
    @testset "accessors and helpers" begin
        pb = parse_block(SPEC_C; filename = "C.jl", ref = "project:C")
        @test block_filename(pb) == "C.jl"
        @test block_range(pb).line == 1
        @test block_range(pb).endLine == 10
        @test block_diagnostics(pb) isa Vector{Diagnostic}
        @test isempty(block_diagnostics(pb))
        c = declarations(pb, :parameters)[1]
        @test decl_scope(c) == :parameters
        @test decl_default_text(c) == "1.0"
        @test decl_range(c).line == 3
        q = declarations(pb, :variables)[1]
        @test decl_default_text(q) == "0.0"
        @test decl_default(q) isa Lit
        @test expr_range(equations(pb)[1].lhs) == SourceRange("C.jl", 6, 9, 6, 14)
        @test expr_range(equations(pb)[1].rhs).line == 6
        @test scope_string(:equations) == "@equations"
        @test source_kind("stdlib:bondgraph/C") == "stdlib"
        @test source_kind("project:MyBlock") == "project"
        @test source_kind("inline:n7") == "inline"
        @test domain_size(:Generic) == 1
        @test domain_size(:Planar) == 3
        @test domain_size(:Spatial) == 6
        @test type_args(TypeSpec(:Mat, (2, 3))) == (2, 3)
        @test type_domain(TypeSpec(:Power, (:Rotation,))) == :Rotation
        @test type_size(TypeSpec(:Power, (:Generic,))) == Int[]
        @test type_size(TypeSpec(:Vec, (:N,)), Dict(:N => 4)) == [4]
        @test resolve_type(TypeSpec(:Vec, (:N,)), Dict(:N => 4)) == TypeSpec(:Vec, (4,))
        @test resolve_type(TypeSpec(:Vec, (:N,)), Dict{Symbol,Any}()) == TypeSpec(:Vec, (:N,))
        @test BGSim.type_scalar_count(TypeSpec(:Mat, (2, 3))) == 6
        @test BGSim.domain_size(:Rotation) == 1
    end

    # -----------------------------------------------------------------------------------
    @testset "golden parse: PIController (spec)" begin
        pb = parse_block(SPEC_PI)
        @test block_name(pb) == :PIController
        @test scopes(pb) == [:parameters, :inputs, :outputs, :variables, :equations]
        @test length(declarations(pb, :parameters)) == 2
        @test decl_name(declarations(pb, :parameters)[1]) == :Kp
        @test decl_attrs(declarations(pb, :parameters)[1])[:tunable] == true
        @test decl_name(declarations(pb, :inputs)[1]) == :e
        @test decl_name(declarations(pb, :outputs)[1]) == :u
        @test length(equations(pb)) == 2
        @test block_balance(pb) == (unknowns = 2, equations = 2)
        @test isempty(check_block(pb))
        iface = block_interface(pb)
        @test iface.parameters[2].unit == "s"
        @test iface.parameters[2].min == 0
        @test iface.parameters[1].tunable == true
        @test iface.inputs == [(name = "e", type = "Real", size = Int[], unit = nothing)]
        @test iface.outputs == [(name = "u", type = "Real", size = Int[], unit = nothing)]
        @test iface.variables[1].state === nothing  # no state attribute in the spec block
        @test length(block_equations(pb)) == 2
    end

    # -----------------------------------------------------------------------------------
    @testset "golden parse: GearBacklash (spec)" begin
        pb = parse_block(SPEC_GEARBACKLASH; ref = "project:GearBacklash")
        @test block_name(pb) == :GearBacklash
        @test block_ref(pb) == "project:GearBacklash"
        @test length(ports(pb)) == 2
        @test [decl_name(d) for d in ports(pb)] == [:a, :b]
        @test all(d -> type_domain(decl_type(d)) == :Rotation, ports(pb))
        @test length(declarations(pb, :parameters)) == 3
        @test length(declarations(pb, :variables)) == 3
        @test decl_attrs(declarations(pb, :variables)[2])[:unit] == "rad/s"
        @test decl_default(declarations(pb, :variables)[2]) === nothing
        @test length(equations(pb)) == 5
        @test equations(pb)[3].rhs isa IfElse
        @test equations(pb)[3].rhs.otherwise isa IfElse
        @test equations(pb)[4].rhs isa Name  # a.e ~ T
        @test equations(pb)[5].rhs isa UnOp  # b.e ~ -T
        @test block_balance(pb) == (unknowns = 5, equations = 5)
        @test isempty(check_block(pb))
        iface = block_interface(pb)
        @test iface.variables[2].unit == "rad/s"
        @test iface.variables[2].start == ""
        @test iface.parameters[1].unit == "N*m/rad"
        @test length(block_equations(pb)) == 5
    end

    # -----------------------------------------------------------------------------------
    @testset "golden parse: LossyGear (spec)" begin
        pb = parse_block(SPEC_LOSSYGEAR)
        @test block_name(pb) == :LossyGear
        @test length(ports(pb)) == 2
        @test length(equations(pb)) == 2
        @test block_balance(pb) == (unknowns = 2, equations = 2)
        @test isempty(check_block(pb))
        # `-n * a.e * ifelse(...)` is one left-associative chain.
        rhs = equations(pb)[2].rhs
        @test rhs isa BinOp && rhs.op == :*
        @test rhs.rhs isa IfElse
        @test decl_attrs(declarations(pb, :parameters)[2])[:max] == 1
        @test length(block_equations(pb)) == 2
    end

    # -----------------------------------------------------------------------------------
    @testset "golden parse: I, R, Se" begin
        for (src, name, bal) in
            ((SPEC_I, :I, (unknowns = 2, equations = 2)), (SPEC_R, :R, (unknowns = 1, equations = 1)),
                (SPEC_SE, :Se, (unknowns = 1, equations = 1)))
            pb = parse_block(src; ref = "stdlib:bondgraph/$name")
            @test block_name(pb) == name
            @test block_source(pb) == strip(src)
            @test block_balance(pb) == bal
            @test isempty(check_block(pb))
            @test length(block_equations(pb)) == bal.equations
        end
        # Fixed causality (D6) is stored as the catalog reports it.
        se = parse_block(SPEC_SE)
        @test length(causality(se)) == 1
        @test BGSim.causality_kind(causality(se)[1]) == :fixed
        @test BGSim.causality_value(causality(se)[1]) == :effort_out
        # Preferred causality for a storage element.
        i = parse_block(SPEC_I)
        @test BGSim.causality_kind(causality(i)[1]) == :preferred
        @test BGSim.causality_value(causality(i)[1]) == :flow_out
    end

    # -----------------------------------------------------------------------------------
    @testset "all 36 catalog blocks parse, check and match the fixture interface" begin
        catalog = JSON3.read(read(CATALOG_FIXTURE, String))
        @test length(catalog.blocks) == 36
        # The metadata must equal what the source text says: `source` is normative, so a
        # disagreement is a fixture bug, not something to skip. CONTRACT-2 aligned the
        # fixture with the source (Sum description, VoltageSource/ForceSource/TorqueSource
        # causality), and this test now compares every field.
        skip = Set{Tuple{String,String,Symbol}}()
        for blk in catalog.blocks
            ref = String(blk.ref)
            pb = parse_block(String(blk.source); ref = ref, filename = String(blk.path))
            @test block_name(pb) == Symbol(blk.name)
            @test block_source(pb) == String(blk.source)
            ds = check_block(pb)
            @test isempty([d for d in ds if d.severity != "info"])
            bal = block_balance(pb)
            # A textual composite has no equations of its own; its balance is the sum of
            # its components' and is checked after instantiation (J2.6/J2.6b).
            isempty(components(pb)) && @test bal.unknowns == bal.equations
            iface = block_interface(pb)
            for field in
                ("constants", "parameters", "inputs", "outputs", "ports", "variables")
                got = getproperty(iface, Symbol(field))
                expected = getproperty(blk, Symbol(field))
                @test length(got) == length(expected)
                length(got) == length(expected) || continue
                for (g, e) in zip(got, expected)
                    for k in keys(e)
                        (ref, field, Symbol(k)) in skip && continue
                        gv =
                            g[k] === nothing ? nothing :
                            g[k] isa AbstractVector ? collect(g[k]) : g[k]
                        ev =
                            e[k] === nothing ? nothing :
                            e[k] isa JSON3.Array ? collect(e[k]) : e[k]
                        if gv != ev
                            @info "catalog mismatch" ref field k gv ev
                        end
                        @test gv == ev
                    end
                end
            end
            (ref, "causality", :all) in skip && continue
            @test length(iface.causality) == length(blk.causality)
        end
    end

    # -----------------------------------------------------------------------------------
    @testset "declarations, types and attributes" begin
        src = """
        @block Arrays begin
            @constants begin
                N::Int = 2
                M::Int = 3
            end
            @parameters begin
                A::Mat{M,N} = [1.0 2.0; 3.0 4.0; 5.0 6.0]
                b::Vec{M} = [1.0, 2.0, 3.0]
            end
            @variables x::Vec{N} = [0.0, 0.0]
            @outputs y::Vec{M}
            @equations begin
                x ~ [b[1], b[2]]
                y ~ A * x
            end
        end
        """
        pb = parse_block(src)
        env = BGSim.constant_env(pb)
        params = declarations(pb, :parameters)
        @test type_kind(decl_type(params[1])) == :Mat
        @test type_name(decl_type(params[1])) == "Mat{M,N}"
        @test type_size(decl_type(params[1]), env) == [3, 2]
        @test type_kind(decl_type(params[2])) == :Vec
        @test type_size(decl_type(params[2]), env) == [3]
        @test decl_default(params[1]) isa MatrixLit
        @test length(decl_default(params[1]).rows) == 3
        # `N` and `M` are structural constants: they set a size.
        consts = declarations(pb, :constants)
        @test decl_attrs(consts[1])[:structural] == true
        @test decl_attrs(consts[2])[:structural] == true
        @test block_balance(pb) == (unknowns = 5, equations = 5)
        @test isempty(check_block(pb))
        iface = block_interface(pb)
        @test iface.constants[1] ==
              (name = "N", type = "Int", default = 2, structural = true)
        @test iface.inputs == NamedTuple[]
        @test iface.outputs[1].size == [3]
        @test iface.outputs[1].type == "Real"
        @test iface.parameters[1].type == "Real"  # element type, per the catalog schema
        @test type_element(decl_type(params[1])) == :Real
    end

    @testset "declaration forms and attributes" begin
        src = """
        @block Forms begin
            @constants N::Int = 4
            @parameters begin
                a::Real = 2 * N, [unit = "m", min = -1, max = 10, description = "an a"]
                b = 1.0
                c::Int = 1, [options = ["hold", "linear"]]
            end
            @inputs u::Vec{N}, [unit = "m/s"]
            @outputs y::Bool = false
            @variables v::Real = 0.0, [state = :avoid, nominal = 1e-3]
            @equations begin
                v ~ a + b + c
                y ~ ifelse(u[1] > 0.0, true, false)
            end
        end
        """
        pb = parse_block(src)
        @test isempty(check_block(pb))
        params = declarations(pb, :parameters)
        @test decl_attrs(params[1])[:unit] == "m"
        @test decl_attrs(params[1])[:min] == -1
        @test decl_attrs(params[1])[:max] == 10
        @test decl_attrs(params[1])[:description] == "an a"
        @test decl_attrs(declarations(pb, :variables)[1])[:nominal] == 1e-3
        @test decl_attrs(params[3])[:options] == ["hold", "linear"]
        @test decl_attrs(declarations(pb, :inputs)[1])[:unit] == "m/s"
        @test decl_attrs(declarations(pb, :variables)[1])[:state] == :avoid
        iface = block_interface(pb)
        @test iface.parameters[3].options == ["hold", "linear"]
        @test iface.inputs[1].size == [4]
        @test iface.outputs[1].type == "Bool"
        @test iface.variables[1].state == "avoid"
    end

    # -----------------------------------------------------------------------------------
    @testset "causality syntax (D6)" begin
        src = """
        @block Caus begin
            @ports begin
                p::Power{Generic}
                q::Power{Generic}
            end
            @equations begin
                p.e ~ 0.0
                q.e ~ 0.0
            end
            @causality begin
                p => :effort_out
                p => (:flow_out, :fixed)
                (p, q) => :transformer
                (p, q) => :gyrator
            end
        end
        """
        pb = parse_block(src)
        @test isempty(check_block(pb))
        cs = causality(pb)
        @test length(cs) == 4
        @test [BGSim.causality_kind(c) for c in cs] ==
              [:preferred, :fixed, :transformer, :gyrator]
        @test [BGSim.causality_value(c) for c in cs] ==
              [:effort_out, :flow_out, nothing, nothing]
        @test [BGSim.causality_ports(c) for c in cs] ==
              [[:p], [:p], [:p, :q], [:p, :q]]
        iface = block_interface(pb)
        @test iface.causality[1] ==
              (ports = ["p"], kind = "preferred", value = "effort_out")
        @test iface.causality[2] == (ports = ["p"], kind = "fixed", value = "flow_out")
        @test iface.causality[3] ==
              (ports = ["p", "q"], kind = "transformer", value = nothing)
        @test iface.causality[4] == (ports = ["p", "q"], kind = "gyrator", value = nothing)
    end

    # -----------------------------------------------------------------------------------
    @testset "for loops and if equations count for the balance precheck" begin
        src = """
        @block Loops begin
            @constants N::Int = 3
            @variables begin
                v::Vec{N} = [0.0, 0.0, 0.0]
                w::Real = 0.0
            end
            @outputs y::Real
            @equations begin
                for i in 1:N
                    v[i] ~ 0.0
                end
                w ~ v[1]
                if w > 0
                    y ~ w
                else
                    y ~ -w
                end
            end
        end
        """
        pb = parse_block(src)
        @test isempty(check_block(pb))
        @test block_balance(pb) == (unknowns = 5, equations = 5)
        items = equations(pb)
        @test items[1] isa ForEquation
        @test items[1].var == :i
        @test length(items[1].body) == 1
        @test items[3] isa IfEquation
        @test length(items[3].branches) == 2
        @test items[3].branches[2].cond === nothing
        # A branch-count mismatch is rejected (the spec requires equal counts).
        bad = replace(src, "y ~ -w" => "y ~ -w\n                    w ~ 0.0")
        pb2 = parse_block(bad)
        @test "E001" in codes(pb2)
    end

    # -----------------------------------------------------------------------------------
    @testset "negative: E000 syntax error" begin
        pb = parse_block("@block Broken begin\n    @equations x ~ 1.0\n"; filename = "b.jl")
        d = expect_at(pb, "E000", 2, 24)
        @test d !== nothing && occursin("expected `end`", d.message)
        @test d !== nothing && d.hint == "add `end` to close the block or scope"
        @test block_equations(pb) == Any[]
    end

    @testset "negative: E001 not allowed in this scope" begin
        pb = parse_block("""
        @block A begin
            @equations begin
                while x > 0
                    x ~ 1.0
                end
            end
        end
        """)
        d = expect_at(pb, "E001", 3, 9; contains = "while")
        @test d !== nothing && occursin("not allowed in @equations", d.message)
        @test d !== nothing && occursin("for i in 1:N", d.hint)

        # `=` in @equations is the D1 case: E001 with the exact hint text.
        pb = parse_block("""
        @block A begin
            @outputs y::Real
            @equations begin
                y = 1.0
            end
        end
        """)
        d = expect_at(pb, "E001", 4, 9; contains = "`=`")
        @test d !== nothing && d.hint == "use `~` for equations"

        # `previous` is a @discrete function.
        pb = parse_block("""
        @block A begin
            @inputs e::Real
            @outputs u::Real
            @equations u ~ previous(e)
        end
        """)
        d = expect_at(pb, "E001", 4, 20; contains = "previous")
        @test d !== nothing && occursin("@discrete", d.hint)

        # A comparison outside `ifelse`.
        pb = parse_block("""
        @block A begin
            @inputs e::Real
            @outputs u::Real
            @equations u ~ (e < 1.0)
        end
        """)
        expect_at(pb, "E001", 4, 21; contains = "comparisons")

        # A string literal in an expression.
        pb = parse_block("""
        @block A begin
            @outputs u::Real
            @equations u ~ "hello"
        end
        """)
        expect_at(pb, "E001", 3, 20; contains = "string literals")

        # An unknown attribute.
        pb = parse_block("""
        @block A begin
            @parameters p::Real = 1.0, [colour = "red"]
            @outputs y::Real
            @equations y ~ p
        end
        """)
        expect_at(pb, "E001", 2, 33; contains = "colour")

        # A bad causality value.
        pb = parse_block("""
        @block A begin
            @ports p::Power{Generic}
            @equations p.e ~ 0.0
            @causality p => :flying
        end
        """)
        expect_at(pb, "E001", 4, 21; contains = "flying")
    end

    @testset "the J2.6 textual subsystem scopes are no longer rejected" begin
        for (scope, kind) in (("@components g = LossyGear()", :components),
                              ("@connections connect(a, b)", :connections))
            src = "@block A begin\n    $scope\nend\n"
            pb = parse_block(src)
            @test isempty(block_diagnostics(pb))
            @test kind in scopes(pb)
        end
        # A malformed entry still has the usual E001 shape.
        bad = parse_block("@block A begin\n    @components g\nend\n")
        d = expect_at(bad, "E001", 2, 17)
        @test d !== nothing && occursin("`name = BlockName", d.message)
        composite = parse_block("""
        @block Composite begin
            @ports a::Power{Rotation}
            @components g = LossyGear(n = 1.0)
            @connections connect(a, g.a)
        end
        """)
        @test scopes(composite) == [:ports, :components, :connections]
        @test length(components(composite)) == 1
        @test length(connections(composite)) == 1
    end

    @testset "the J2.1 scopes are no longer rejected" begin
        for scope in ("@initial x ~ 0.0", "@discrete Ts = 1e-3 begin y = 1.0 end",
                      "@events x > 0.0 => begin y = 1.0 end")
            src = "@block A begin\n    @variables x::Real = 0.0\n    @outputs y::Real = 0.0\n    $scope\nend\n"
            pb = parse_block(src)
            @test !any(d -> occursin("not supported yet", d.message), check_block(pb))
        end
    end

    @testset "negative: E002 function not on the whitelist" begin
        pb = parse_block("""
        @block A begin
            @inputs e::Real
            @outputs u::Real
            @equations u ~ rand(e)
        end
        """)
        d = expect_at(pb, "E002", 4, 20; contains = "rand")
        @test d !== nothing && occursin("noise_normal", d.hint)

        pb = parse_block("""
        @block A begin
            @inputs e::Real
            @outputs u::Real
            @equations u ~ e % 2.0
        end
        """)
        d = expect_at(pb, "E002", 4, 22; contains = "%")
        @test d !== nothing && occursin("mod", d.hint)
    end

    @testset "negative: E003 undeclared and shadowed names" begin
        pb = parse_block("""
        @block A begin
            @inputs e::Real
            @outputs u::Real
            @equations u ~ Kp * e
        end
        """)
        d = expect_at(pb, "E003", 4, 20; contains = "Kp")
        @test d !== nothing && occursin("not declared", d.message)

        pb = parse_block("""
        @block A begin
            @parameters sin::Real = 1.0
            @outputs u::Real
            @equations u ~ sin
        end
        """)
        d = expect_at(pb, "E003", 2, 16; contains = "sin")
        @test d !== nothing && occursin("shadows built-in", d.message)

        # A port used without `.e`/`.f`, and a wrong field.
        pb = parse_block("""
        @block A begin
            @ports p::Power{Generic}
            @equations 0.0 ~ p
        end
        """)
        expect_at(pb, "E003", 3, 22; contains = "port")
        pb = parse_block("""
        @block A begin
            @ports p::Power{Generic}
            @equations 0.0 ~ p.g
        end
        """)
        expect_at(pb, "E003", 3, 22; contains = "has fields")
    end

    @testset "negative: E004 type mismatch" begin
        pb = parse_block("""
        @block A begin
            @inputs flag::Bool
            @outputs y::Real
            @equations y ~ flag + 1.0
        end
        """)
        d = expect_at(pb, "E004", 4, 20; contains = "Bool value used in arithmetic")
        @test d !== nothing && occursin("Type conversion", d.hint)

        pb = parse_block("""
        @block A begin
            @variables n::Int = 0
            @outputs y::Real
            @equations y ~ n
        end
        """)
        expect_at(pb, "E004", 2, 15; contains = "Int")

        # A Bool state.
        pb = parse_block("""
        @block A begin
            @variables flag::Bool = false
            @outputs y::Real
            @equations y ~ ifelse(flag, 1.0, 0.0)
        end
        """)
        expect_at(pb, "E004", 2, 15; contains = "continuous state")

        # A parameter on the left side of an equation.
        pb = parse_block("""
        @block A begin
            @parameters k::Real = 1.0
            @outputs y::Real
            @equations k ~ y
        end
        """)
        expect_at(pb, "E004", 4, 16; contains = "cannot be the left side")
    end

    @testset "negative: E005 size and index" begin
        pb = parse_block("""
        @block A begin
            @variables v::Vec{M}
            @outputs y::Real
            @equations y ~ v[1]
        end
        """)
        d = expect_at(pb, "E005", 2, 16; contains = "not static")
        @test d !== nothing && occursin("@constants", d.hint)

        pb = parse_block("""
        @block A begin
            @variables v::Vec{3} = [1.0, 2.0, 3.0]
            @outputs y::Real
            @equations y ~ v[4]
        end
        """)
        d = expect_at(pb, "E005", 4, 20; contains = "index out of range")
        @test d !== nothing && occursin("Vec{3}", d.message)

        pb = parse_block("""
        @block A begin
            @variables x::Real = 0.0
            @outputs y::Real
            @equations y ~ x[1]
        end
        """)
        expect_at(pb, "E005", 4, 20; contains = "not an array")

        pb = parse_block("""
        @block A begin
            @variables x::Vec{3} = [0.0, 0.0, 0.0]
            @outputs y::Real
            @equations begin
                for i in 1:M
                    x[i] ~ 0.0
                end
                y ~ x[1]
            end
        end
        """)
        d = expect_at(pb, "E005", 5, 20; contains = "for")
        @test d !== nothing && occursin("@constants", d.hint)

        # A size that comes from a @parameter is not structural.
        pb = parse_block("""
        @block A begin
            @parameters M::Int = 3
            @variables v::Vec{M}
            @outputs y::Real
            @equations y ~ v[1]
        end
        """)
        expect_at(pb, "E005", 3, 16; contains = "not static")

        # A size of zero.
        pb = parse_block("""
        @block A begin
            @variables v::Vec{0}
            @outputs y::Real
            @equations y ~ 1.0
        end
        """)
        expect_at(pb, "E005", 2, 23; contains = "at least 1")
    end

    @testset "negative: W204 unused declaration" begin
        pb = parse_block("""
        @block A begin
            @parameters unused::Real = 1.0
            @outputs y::Real
            @equations y ~ 1.0
        end
        """)
        d = expect_at(pb, "W204", 2, 16; contains = "unused")
        @test d !== nothing && d.severity == "warning"
        @test d !== nothing && d.scope == "@parameters"
    end

    # -----------------------------------------------------------------------------------
    @testset "whitelist: every function row" begin
        # (names, allowed source-level case, expected rejection code)
        for rule in BGSim.FUNCTION_RULES
            name = rule.names[1]
            @test BGSim.function_rule(name) === rule
            for alias in rule.names
                @test BGSim.function_rule(alias) === rule
            end

            nargs = rule.min_args
            ov = get(ROW_OVERRIDES, name, NamedTuple())
            kw = Dict{Symbol,Any}()
            for k in (:nargs, :argtypes, :argnames, :callargs, :rettype, :decl)
                haskey(ov, k) && (kw[k] = ov[k])
            end
            haskey(kw, :nargs) || (kw[:nargs] = nargs)

            # The allowed case exists only for rows that a J1.1 expression scope accepts.
            if :equation in rule.contexts
                ref = rule.stdlib_only ? "stdlib:test/RowTest" : "inline:row"
                src = row_source(String(name); kw...)
                pb = parse_block(src; ref = ref)
                ds = check_block(pb)
                whitelist_errors = [
                    d for d in ds if
                    d.code in ("E001", "E002") && occursin(String(name), d.message)
                ]
                @test isempty(whitelist_errors)
            end

            # A rejection at source level: out of scope, wrong arity, or stdlib-only.
            if !(:equation in rule.contexts)
                src = row_source(String(name); kw...)
                pb = parse_block(src)
                ds = check_block(pb)
                hits = [d for d in ds if d.code == "E001" && occursin(String(name), d.message)]
                @test !isempty(hits)
            elseif rule.stdlib_only
                src = row_source(String(name); kw...)
                pb = parse_block(src; ref = "inline:row")
                ds = check_block(pb)
                @test any(
                    d -> d.code == "E002" && occursin("stdlib", d.message) &&
                         occursin(String(name), d.message),
                    ds,
                )
            else
                # One argument too many. Arity is checked before the argument types, so
                # plain Real parameters are enough here.
                extra = (rule.max_args < 0 ? rule.min_args : rule.max_args) + 1
                names = ["a", "b", "c", "d", "e"][1:extra]
                bad = row_source(
                    String(name);
                    nargs = extra,
                    argnames = names,
                    callargs = names,
                )
                pb = parse_block(bad)
                ds = check_block(pb)
                @test any(
                    d -> d.code == "E001" && occursin(String(name), d.message) &&
                         occursin("takes", d.message),
                    ds,
                )
            end
        end
        # The table has one row per spec line (24 rows including the D12 intrinsics and the
        # F5.1 `csv_value`). The
        # spatial-mechanics additions of J-MB3 live in their own table
        # (`MECH_FUNCTION_RULES`), mirroring the spec's separate table.
        @test length(BGSim.FUNCTION_RULES) == 24
        @test length(BGSim.MECH_FUNCTION_RULES) == 18
        @test BGSim.function_rule(:rand) === nothing
        @test BGSim.function_rule(:jacobian) === nothing
    end

    @testset "whitelist: every operator and statement row" begin
        # Every row of the spec's operator table is present, with its scope contexts.
        expected = Dict(
            :arith => BGSim.ALL_CONTEXTS,
            :pow_int => BGSim.ALL_CONTEXTS,
            :pow_real => BGSim.ALL_CONTEXTS,
            :compare => [:discrete],
            :logic => [:discrete],
            :equation => [:equation],
            :assign => [:discrete],
            :opassign => [:discrete],
            :ifelse => BGSim.ALL_CONTEXTS,
            :if => [:equation, :discrete],
            :for => [:equation, :discrete],
            :while => Symbol[],
            :array => BGSim.ALL_CONTEXTS,
            :derivative => [:equation],
            :integral => [:equation],
            :previous => [:discrete],
            :hold => [:discrete],
            :reinit => [:events],
            :funcdef => Symbol[],
            :macro => Symbol[],
            :string => Symbol[],
            :ternary => Symbol[],
            :broadcast => Symbol[],
        )
        for (key, contexts) in expected
            @test BGSim.syntax_rule(key).contexts == contexts
        end
        @test length(BGSim.SYNTAX_RULES) == 23
        # "Inside `ifelse` only" for comparisons and logic in equations and defaults.
        @test !BGSim.syntax_allowed(:compare, :equation)
        @test BGSim.syntax_allowed(:compare, :equation; in_ifelse = true)
        @test BGSim.syntax_allowed(:compare, :discrete)
        @test !BGSim.syntax_allowed(:logic, :default)
        @test BGSim.syntax_allowed(:logic, :default; in_ifelse = true)

        allowed_cases = [
            "x ~ a + b", "x ~ -a", "x ~ a * b / c", "x ~ a ^ 2", "x ~ a ^ 2.5",
            "x ~ a ^ -1", "x ~ ifelse(a > b, 1.0, 2.0)",
            "x ~ ifelse(a > b && !(a < 0), 1.0, 2.0)", "x ~ [a, b][1]",
        ]
        for body in allowed_cases
            src = """
            @block A begin
                @parameters begin
                    a::Real = 1.0
                    b::Real = 2.0
                    c::Real = 3.0
                end
                @variables x::Real = 0.0
                @equations $body
            end
            """
            pb = parse_block(src)
            @test isempty([d for d in check_block(pb) if d.code in ("E001", "E002")])
        end

        rejected = [
            ("while a > 0\n x ~ 1.0\n end", "while"),
            ("function f(a)\n a\n end", "function definitions"),
            ("@foo x", "macros"),
            ("x ~ (a > 0 ? 1.0 : 2.0)", "ternary"),
            ("x ~ sin.(a)", "broadcasting"),
        ]
        for (body, needle) in rejected
            src = """
            @block A begin
                @parameters a::Real = 1.0
                @variables x::Real = 0.0
                @equations begin
                    $body
                end
            end
            """
            pb = parse_block(src)
            @test any(
                d -> d.code == "E001" && occursin(needle, d.message), check_block(pb)
            )
        end
    end

    # -----------------------------------------------------------------------------------
    @testset "block_equations and error paths" begin
        pb = parse_block(SPEC_C)
        @test block_equations(pb) isa Vector{Any}
        @test length(block_equations(pb)) == 2
        bad = parse_block("""
        @block A begin
            @outputs y::Real
            @equations y = 1.0
        end
        """)
        @test block_equations(bad) == Any[]
        # An unbalanced block is only a warning, so its equations are still available.
        unbal = parse_block("""
        @block A begin
            @outputs y::Real
            @variables x::Real = 0.0
            @equations y ~ 1.0
        end
        """)
        @test any(d -> d.code == "E103" && d.severity == "warning", check_block(unbal))
        @test length(block_equations(unbal)) == 1
    end

    @testset "parse_blocks and block source text" begin
        text = """
        @block A begin
            @outputs y::Real
            @equations y ~ 1.0
        end
        @block B begin
            @outputs z::Real
            @equations z ~ 2.0
        end
        """
        bs = parse_blocks(text; filename = "two.jl")
        @test length(bs) == 2
        @test [block_name(b) for b in bs] == [:A, :B]
        @test block_ref(bs[2]) == "inline:b"
        @test startswith(block_source(bs[1]), "@block A begin")
        @test endswith(block_source(bs[1]), "end")
        @test isempty(check_block(bs[1]))
        @test isempty(check_block(bs[2]))
        # A single-block source must contain exactly one block.
        pb = parse_block(text)
        @test block_name(pb) == :A
        @test any(d -> d.code == "E001" && occursin("exactly one", d.message), check_block(pb))
        # A statement outside a block is rejected.
        pb = parse_block("x = 1\n@block A begin\n @outputs y::Real\n @equations y ~ 1.0\nend")
        @test any(d -> d.code == "E001" && occursin("top level", d.message), check_block(pb))
    end

    @testset "sort_diagnostics is deterministic" begin
        ds = Diagnostic[
            diag("E001", "b"; path = "B"),
            diag("W204", "a"; path = "A"),
            diag(
                "E002",
                "c";
                path = "A",
                source = SourceRef("inline", "x", SourceRange("x", 3, 1, 3, 2)),
            ),
        ]
        sorted = sort_diagnostics(ds)
        @test [d.code for d in sorted] == ["W204", "E002", "E001"]
        @test sort_diagnostics(sorted) == sorted
        # Same input, same output.
        @test sort_diagnostics(ds) == sorted
    end

    @testset "totality: bad input never throws" begin
        nasty = [
            "",
            "   ",
            "@block",
            "@block A",
            "@block A begin",
            "@block A begin\n    @equations\nend",
            "@block A begin\n    @bogus x\nend",
            "@block A begin\n    @parameters x::\nend",
            "@block A begin\n    @parameters x::Real = \nend",
            "@block A begin\n    @equations x ~\nend",
            "@block A begin\n    @parameters a::Real = 1.0, [unit = ]\nend",
            "@block A begin\n    @causality => :effort_out\nend",
            "@block A begin\n    @equations if x\nend",
            "@block A begin\n    @equations for i in 1:3\nend",
            "@block A begin\n    @equations for i\nend",
            "x = 1",
        ]
        for src in nasty
            pb = parse_block(src)
            @test pb isa ParsedBlock
            ds = check_block(pb)
            @test ds isa Vector{Diagnostic}
            @test all(d -> d.code isa String && d.severity in ("error", "warning", "info"), ds)
            @test block_interface(pb) isa NamedTuple
            @test block_equations(pb) isa Vector{Any}
        end
        # Parsing and checking are deterministic.
        src = SPEC_GEARBACKLASH
        a = [to_dict(d) for d in check_block(parse_block(src))]
        b = [to_dict(d) for d in check_block(parse_block(src))]
        @test a == b
    end
end
