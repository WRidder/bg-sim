# Work package J2.4: causality (SCAP) and W201/W202/E106.
#
# The four acceptance cases:
#   * the RLC bond graph contract fixture (the real fixture and the real flattener): integral
#     causality on both storage elements, no W201, and the strokes on the expected ends;
#   * two compliances in series with no inertia between them: W201 on one C;
#   * an Se-Se conflict on a 0-junction: E106;
#   * an R-R loop: W202 naming both resistors.
#
# The DC motor bond graph (a contract fixture too) pins the gyrator half of the propagation
# rules, `tf_chain.json` the transformer half, and the last test pins the post-mtkcompile
# W201 hook of plan 5.7 (iconic models).

using Test
using BGSim
import BGSim.IR
import BGSim.Compile
import JSON3
using ModelingToolkit
using ModelingToolkit: t_nounits as t, D_nounits as D

const _CZ_REPO = normpath(joinpath(@__DIR__, "..", "..", ".."))
const _CZ_MODEL_FIXTURES = joinpath(_CZ_REPO, "contracts", "fixtures", "model", "valid")
const _CZ_FIXTURES = joinpath(@__DIR__, "fixtures", "causality")

_cz_doc(path) = IR.parse_model(JSON3.read(read(path, String)))
_cz_contract(name) = _cz_doc(joinpath(_CZ_MODEL_FIXTURES, name))
_cz_fixture(name) = _cz_doc(joinpath(_CZ_FIXTURES, name))

_cz_with_code(diagnostics, code) = [d for d in diagnostics if d.code == code]

@testset "J2.4 causality (SCAP) and W201/W202/E106" begin
    @testset "RLC contract fixture: integral causality and strokes" begin
        result = Compile.model_check(_cz_contract("model.rlc.bondgraph.json"))
        @test result.causality == Dict(
            "c1" => (strokeAt = "to",),
            "c2" => (strokeAt = "from",),
            "c3" => (strokeAt = "to",),
            "c4" => (strokeAt = "from",),
        )
        # Both storage elements keep integral causality; there is no loop and no conflict.
        @test isempty(_cz_with_code(result.diagnostics, "W201"))
        @test isempty(_cz_with_code(result.diagnostics, "W202"))
        @test isempty(_cz_with_code(result.diagnostics, "E106"))
        @test isempty([d for d in result.diagnostics if d.severity == "error"])
        # W205 is the only diagnostic of the pure Generic island (plan 5.6).
        @test [d.code for d in result.diagnostics] == ["W205"]

        flat = Compile.flatten(_cz_contract("model.rlc.bondgraph.json"))
        @test count(v -> v.kind === :state, flat.variables) == 2
    end

    @testset "DC motor bond graph: gyrator propagation" begin
        result = Compile.model_check(_cz_contract("model.dcmotor.bondgraph.json"))
        # The Se fixes J1, the two I elements keep their preferred stroke at their port, so
        # the GY sees effort out on p1 and must put effort out on p2 as well.
        @test result.causality == Dict(
            "c1" => (strokeAt = "to",),
            "c2" => (strokeAt = "from",),
            "c3" => (strokeAt = "to",),
            "c4" => (strokeAt = "from",),
            "c5" => (strokeAt = "to",),
            "c6" => (strokeAt = "to",),
            "c7" => (strokeAt = "from",),
        )
        @test isempty(_cz_with_code(result.diagnostics, "W201"))
        @test isempty(_cz_with_code(result.diagnostics, "E106"))
        @test isempty(_cz_with_code(result.diagnostics, "W202"))
    end

    @testset "two springs in series: W201 on one C" begin
        doc = _cz_fixture("two_c_series.json")
        flat = Compile.flatten(doc)
        @test (flat.stats.unknowns, flat.stats.equations) == (6, 6)

        warnings = _cz_with_code(flat.diagnostics, "W201")
        @test length(warnings) == 1
        warning = only(warnings)
        @test warning.severity == "warning"
        @test warning.path == "C2"
        @test warning.connection == "c2"
        @test occursin("derivative causality", warning.message)
        @test isempty(_cz_with_code(flat.diagnostics, "E106"))
        @test isempty(_cz_with_code(flat.diagnostics, "W202"))

        causality = Compile.model_check(doc).causality
        @test causality["c1"].strokeAt == "to"     # C1: effort out, integral
        @test causality["c2"].strokeAt == "from"   # C2: effort in at its port, derivative
    end

    @testset "Se-Se conflict on a 0-junction: E106" begin
        doc = _cz_fixture("se_se_conflict.json")
        flat = Compile.flatten(doc)
        errors = _cz_with_code(flat.diagnostics, "E106")
        @test length(errors) == 1
        conflict = only(errors)
        @test conflict.severity == "error"
        @test conflict.path == "Se2"
        @test conflict.connection == "c2"
        @test occursin("Se1 and Se2 both impose the effort", conflict.message)
        @test occursin("0-junction", conflict.message)

        # SCAP still returns a complete stroke map (best effort) for the editor.
        causality = Compile.model_check(doc).causality
        @test Set(keys(causality)) == Set(["c1", "c2"])
        @test causality["c1"].strokeAt == "to"
    end

    @testset "R-R loop: W202 naming both resistors" begin
        doc = _cz_fixture("r_r_loop.json")
        flat = Compile.flatten(doc)
        warnings = _cz_with_code(flat.diagnostics, "W202")
        @test length(warnings) == 1
        warning = only(warnings)
        @test warning.severity == "warning"
        @test warning.path == "R1"
        @test warning.connection == "c1"
        @test occursin("algebraic loop through R1, R2", warning.message)
        @test isempty(_cz_with_code(flat.diagnostics, "W201"))
        @test isempty(_cz_with_code(flat.diagnostics, "E106"))

        # The arbitrary choice still produces one stroke for the bond.
        @test Compile.model_check(doc).causality["c1"].strokeAt in ("from", "to")
    end

    @testset "transformer propagation" begin
        doc = _cz_fixture("tf_chain.json")
        result = Compile.model_check(doc)
        # Se -> J1 (stroke at J1), J1 forces the TF bond's stroke to the TF p1 end; effort in
        # on p1 means effort out on p2, so the R bond is stroked at the R port.
        @test result.causality == Dict(
            "c1" => (strokeAt = "to",),
            "c2" => (strokeAt = "to",),
            "c3" => (strokeAt = "to",),
        )
        @test isempty(_cz_with_code(result.diagnostics, "W201"))
        @test isempty(_cz_with_code(result.diagnostics, "E106"))
        @test isempty(_cz_with_code(result.diagnostics, "W202"))
    end

    @testset "after mtkcompile: ddt variables that are not states" begin
        flat = Compile.flatten(_cz_contract("model.rlc.bondgraph.json"))
        lowered = BGSim.lower_model(flat)
        # The real RLC keeps both ddt variables as differential states: no warning.
        @test isempty(Compile.post_compile_warnings(flat, lowered.model.system))

        # The same flat model with C1/q algebraically constrained: `mtkcompile` eliminates it,
        # so it is no longer a differential state and the hook reports W201 with its path.
        vars = BGSim.lower_flat(flat).vars
        current = vars["IL/P"]
        charge = vars["C1/q"]
        system = mtkcompile(System(
            [D(current) ~ 1.0, charge ~ 0.0], t, [current, charge], [];
            name = :j24_post_compile,
        ))
        warnings = Compile.post_compile_warnings(flat, system)
        @test length(warnings) == 1
        @test warnings[1].code == "W201"
        @test warnings[1].severity == "warning"
        @test warnings[1].path == "C1"
        @test occursin("C1/q", warnings[1].message)
    end
end
