# Golden test for `stdlib:converters/DCMotor` as a textual composite (J2.6b/CONTRACT-6).
#
# The old flat block is kept as a test fixture and used here as the equivalence oracle: the
# composite must reproduce the flat motor's current and relative speed (and every signal the
# consumers read) for the plan 9.1 iconic drive. Its parameters stay live at the composite
# path (`Motor1/R`), and the flat block's recorded names `Motor1/i` / `Motor1/w_rel` remain.
if !isdefined(@__MODULE__, :BondGraphGolden)
    include(joinpath(@__DIR__, "..", "bondgraph", "golden_helpers.jl"))
end
using Test
using BGSim
import BGSim.IR
import BGSim.Compile
using JSON3
using .BondGraphGolden

const DCM_FLAT_SOURCE = read(
    joinpath(@__DIR__, "..", "..", "fixtures", "components", "library", "DCMotorFlat.jl"),
    String,
)

"""The plan 9.1 iconic DC-motor model: `motor` is the block field of the motor node."""
function dcm_model(name, motor)
    return bg_model(
        name,
        [
            bg_node("n1", "Step1", bg_ref("stdlib:sources/Step");
                params = Dict{String,Any}("t_step" => "0.01", "initial" => "0.0",
                    "final" => "12.0")),
            bg_node("n2", "V1", bg_ref("stdlib:electrical/VoltageSource");
                params = Dict{String,Any}("V" => "1.0")),
            bg_node("n3", "Motor1", motor;
                params = Dict{String,Any}("R" => "2.0", "L" => "5e-4", "k_t" => "0.05",
                    "J" => "1e-5", "d" => "0.0")),
            bg_node("n4", "Ground1", bg_ref("stdlib:electrical/Ground")),
            bg_node("n5", "FixHousing", bg_ref("stdlib:rotation/FixedShaft")),
            bg_node("n6", "Damp1", bg_ref("stdlib:rotation/RotationalDamper");
                params = Dict{String,Any}("d" => "1e-6")),
            bg_node("n7", "FixShaft", bg_ref("stdlib:rotation/FixedShaft")),
        ],
        [
            bg_conn("c1", "signal", "n1", "y", "n2", "u"),
            bg_conn("c2", "wire", "n2", "p", "n3", "p"),
            bg_conn("c3", "wire", "n3", "n", "n4", "p"),
            bg_conn("c4", "wire", "n3", "housing", "n5", "a"),
            bg_conn("c5", "wire", "n3", "shaft", "n6", "a"),
            bg_conn("c6", "wire", "n6", "b", "n7", "a"),
            bg_conn("c7", "wire", "n2", "n", "n4", "p"),
        ];
        t_end = 1.0, points = 1001, reltol = 1.0e-10, abstol = 1.0e-12,
    )
end

@testset "golden: DCMotor composite" begin
    R0, k, d_ext = 2.0, 0.05, 1.0e-6
    target = k * 12.0 / (R0 * d_ext + k^2)
    @test isapprox(target, 239.80815347721824; rtol = 1e-12)

    composite = Compile.flatten(IR.parse_model(dcm_model("DCMotorComposite",
        bg_ref("stdlib:converters/DCMotor"))))
    flat = Compile.flatten(IR.parse_model(dcm_model("DCMotorFlat",
        Dict{String,Any}("inline" => Dict{String,Any}("source" => DCM_FLAT_SOURCE)))))
    @test isempty([x for x in composite.diagnostics if x.severity == "error"])
    @test isempty([x for x in flat.diagnostics if x.severity == "error"])

    # The flat oracle's two states plus the rotor angle the Inertia block introduces.
    @test flat.stats.states == 2
    @test composite.stats.states == 3

    # J2.6b: the composite's parameters are the flat block's, at the composite path, and the
    # component parameters are aliases (there is no `Motor1/resistor/R` parameter).
    @test [p.id for p in composite.parameters] == [p.id for p in flat.parameters]
    @test [p.value for p in composite.parameters] == [p.value for p in flat.parameters]
    @test !any(p -> p.id == "Motor1/resistor/R", composite.parameters)
    @test any(e -> occursin("Motor1/R", sprint(show, e)), composite.equations)

    cols_c, res_c, fm_c = bg_run(dcm_model("DCMotorComposite",
        bg_ref("stdlib:converters/DCMotor")))
    cols_f, res_f, _ = bg_run(dcm_model("DCMotorFlat",
        Dict{String,Any}("inline" => Dict{String,Any}("source" => DCM_FLAT_SOURCE))))
    @test res_c.status == "done"
    @test res_f.status == "done"

    # The flat block's recorded signal names survive the rewrite as composite observables.
    for id in ("Motor1/i", "Motor1/w_rel", "Motor1/p.e", "Motor1/p.f", "Motor1/p.P",
        "Motor1/shaft.f", "Motor1/housing.f")
        @test haskey(cols_c, id)
    end
    signal = Dict(String(s.id) => s for s in fm_c.signals)
    @test signal["Motor1/i"].kind == "observed"
    @test signal["Motor1/w_rel"].kind == "observed"
    @test signal["Motor1/i"].unit == "A"
    @test signal["Motor1/w_rel"].unit == "1/s"

    # Equivalence on every signal the consumers read. The composite's shaft/housing *effort*
    # is the effort at the exposed rotor port, not the flat block's lumped motor equation, so
    # those two aliases (and their powers) are deliberately excluded. The housing's reaction
    # torque reaches the fixed support too (`FixHousing/a.e`): the EMConverter block has no
    # stator port, while the flat block folds the reaction into `housing.e = -shaft.e`.
    exclude = Set(["time", "Motor1/shaft.e", "Motor1/housing.e", "Motor1/shaft.P",
        "Motor1/housing.P", "FixHousing/a.e"])
    common = sort([id for id in keys(cols_f) if haskey(cols_c, id) && !(id in exclude)])
    @test "Motor1/i" in common
    @test "Motor1/w_rel" in common
    @test "Motor1/shaft.f" in common
    @test "Motor1/p.P" in common
    # The composite and the flat oracle share the same solver grid (both have the Step kink).
    @test cols_c["time"] == cols_f["time"]
    for id in common
        @test all(isapprox.(cols_c[id], cols_f[id]; rtol = 1.0e-8, atol = 1.0e-10))
    end

    # Steady state and current, exactly the plan 9.1 checks.
    @test isapprox(cols_c["Motor1/shaft.f"][end], target; rtol = 1e-4)
    @test isapprox(cols_c["Motor1/i"][end], d_ext * target / k; rtol = 1e-4)
    @test isapprox(cols_c["Motor1/w_rel"][end], target; rtol = 1e-6)

    # Parameter tuning at the composite path: R is a real MTK parameter, the structural key
    # does not change, and the next run remakes the problem without recompiling.
    tuned = BGSim.set_parameter_values(composite, Dict("Motor1/R" => 20.0))
    @test BGSim.compile_key(tuned) == BGSim.compile_key(composite)
    dir_tuned = mktempdir()
    settings = BGSim.RunSettings(IR.parse_model(
        dcm_model("DCMotorComposite", bg_ref("stdlib:converters/DCMotor"))).settings)
    run_tuned = simulate(tuned; run_dir = dir_tuned, settings = settings)
    @test run_tuned.status == "done"
    @test run_tuned.cache_hit
    raw = read(joinpath(dir_tuned, "manifest.json"), String)
    manifest = BGSim.JSON3.read(raw)
    n = Int(manifest.time.n)
    nsignals = length(manifest.signals)
    table = reshape(reinterpret(Float64, read(joinpath(dir_tuned, "columns.f64"))),
        (n, nsignals + 1))
    ids = [String(s.id) for s in manifest.signals]
    speed_tuned = collect(table[:, 1 + findfirst(==("Motor1/shaft.f"), ids)])
    target_tuned = k * 12.0 / (20.0 * d_ext + k^2)
    @test isapprox(speed_tuned[end], target_tuned; rtol = 1e-4)
    @test abs(speed_tuned[end] - cols_c["Motor1/shaft.f"][end]) > 0.05
end
