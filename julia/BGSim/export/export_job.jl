# One export job of the backend (backend/src/bgsim_server/exports.py, plan P-EX1):
#
#     julia --project=julia/BGSim julia/BGSim/export/export_job.jl <job_dir>
#
# Reads <job_dir>/request.json (the ExportRequest contract plus projectDir), runs
# `BGSim.Export.export_job` and writes <job_dir>/result.json. Progress goes to stdout as
# lines `@@bgsim {"phase": ...}`; everything else on stdout/stderr is log text.

const T_START = time()
using BGSim
import JSON3

phase(name) = (println(stdout, "@@bgsim ", JSON3.write(Dict("phase" => name))); flush(stdout))

function main(job_dir)
    load_s = time() - T_START
    phase("loaded")
    request = JSON3.read(read(joinpath(job_dir, "request.json"), String))
    result = try
        BGSim.Export.export_job(request, job_dir; progress = phase)
    catch err
        Dict{String,Any}("status" => "failed", "diagnostics" => Any[], "notes" => String[],
            "timings" => Dict{String,Any}(),
            "error" => first(sprint(showerror, err, catch_backtrace()), 4000))
    end
    result["timings"]["loadS"] = load_s
    open(joinpath(job_dir, "result.json"), "w") do io
        JSON3.write(io, result)
    end
    phase("written")
    return result["status"] == "failed" ? 1 : 0
end

exit(main(abspath(ARGS[1])))
