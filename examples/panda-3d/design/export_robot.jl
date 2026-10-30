# Export the `Robot` subsystem of `panda` alone as a plant FMU (BGSim.Export.scope_document).
#
#     julia --project=julia/BGSim examples/panda-3d/design/export_robot.jl <out_dir> [t_end] [method]
#
# `method` is an `ExportSettings` method (`auto` = RK4, or `ros2`: the linearly implicit
# Rosenbrock export with a sparse LU, which the stiff held directions need for a 1 ms step).
#
# The scope keeps the Robot subsystem (mechanics, drives, sensors) and turns its signal ports
# into the FMU interface: inputs tau1..tau7 [N*m], outputs q1..q7, dq1..dq7, tauJ1..tauJ7. The
# inputs start at the gravity torque of the ready pose (the drive preload), so the exported
# plant holds the arm at rest when the host leaves them alone. The script writes the export
# twice, like examples/export_examples.jl: once to check the plant is accepted, then against a
# reference run of the same scoped model (the accuracy report of the export), and prints the
# timings and the report summary.

using BGSim
using JSON3

const ROOT = normpath(joinpath(@__DIR__, ".."))
todict(x::AbstractDict) = Dict{String,Any}(String(k) => todict(v) for (k, v) in pairs(x))
todict(x::AbstractVector) = Any[todict(v) for v in x]
todict(x) = x

function main(args)
    out = abspath(args[1])
    t_end = length(args) >= 2 ? parse(Float64, args[2]) : 1.0
    method = length(args) >= 3 ? args[3] : "auto"
    doc = todict(JSON3.read(read(joinpath(ROOT, "models", "panda.bgmodel.json"), String)))
    # the link-side command that holds the ready pose: the gravity torque, which is also the
    # start value of the PD outputs u<k> in library/PandaPD.jl (generated from the Gaz model)
    pd = read(joinpath(ROOT, "library", "PandaPD.jl"), String)
    values = Dict{String,Any}()
    for k in 1:7
        m = match(Regex("\\bu$(k)::Real = ([-0-9.eE+]+), \\[unit = \"N\\*m\"\\]"), pd)
        m === nothing && error("no start value of u$k in PandaPD.jl")
        values["tau$k"] = parse(Float64, m.captures[1])
    end
    println("inputs at     ", values)
    scoped, diags = BGSim.Export.scope_document(doc, "Robot"; input_values = values)
    scoped === nothing && error("scope refused: " * join((d.message for d in diags), "; "))
    scoped["settings"]["t_end"] = t_end
    rm(out; force = true, recursive = true)
    mkpath(out)
    t0 = time()
    flat = BGSim.Compile.flatten(BGSim.IR.parse_model(scoped); project_dir = ROOT)
    println("flatten        ", round(time() - t0; digits = 2), " s")
    errs = filter(d -> d.severity == "error", flat.diagnostics)
    isempty(errs) || error("flatten: " * join((d.code * " " * d.message for d in errs), "; "))
    es = BGSim.Export.ExportSettings(Dict{String,Any}("t_end" => t_end, "step" => 1.0e-3,
        "method" => method, "linear_solver" => method == "ros2" ? "sparse" : "auto"))
    t0 = time()
    first = BGSim.Export.export_model(flat, joinpath(out, "export"); settings = es, name = "panda_robot")
    println("first export   ", round(time() - t0; digits = 2), " s  ok=", first.ok)
    for d in first.diagnostics
        println("  ", d.code, " ", d.message)
    end
    first.ok || return 1
    ref = joinpath(out, "reference")
    t0 = time()
    BGSim.simulate(flat; run_dir = ref, settings = Dict{String,Any}(
        "t_end" => t_end, "solver" => "Rodas5P", "reltol" => 1e-6, "abstol" => 1e-8,
        "output" => Dict("mode" => "interval", "interval" => 1.0e-3)))
    println("reference      ", round(time() - t0; digits = 2), " s")
    t0 = time()
    result = BGSim.Export.export_model(flat, joinpath(out, "export"); settings = es,
        reference_dir = ref, name = "panda_robot")
    println("export         ", round(time() - t0; digits = 2), " s  ok=", result.ok)
    for d in result.diagnostics
        println("  ", d.code, " ", d.message)
    end
    rep = result.report
    if rep !== nothing
        println("inputs  ", join((i["name"] for i in rep["inputs"]), " "))
        println("outputs ", join((o["name"] for o in rep["outputs"]), " "))
        for key in sort(collect(keys(rep)))
            key in ("inputs", "outputs", "parameters", "variables") && continue
            v = rep[key]
            s = v isa AbstractDict || v isa AbstractVector ? JSON3.write(v) : string(v)
            println(rpad(key, 16), length(s) > 300 ? s[1:300] * " ..." : s)
        end
    end
    return result.ok ? 0 : 1
end

exit(main(ARGS))
