# Command line front end of BGSimFEM.
#
#   julia --project=julia/BGSimFEM julia/BGSimFEM/bin/bgsim-fem.jl PART.json [--no-write] [--quiet]
#
# Reads the part spec (see julia/BGSimFEM/src/spec.jl and the manual page "Flexible bodies"),
# meshes the part, reduces it (Craig–Bampton, interface 1 = reference frame), validates the
# reduction against the full FE model and writes the reduced-model JSON and the GLB with the mode
# shapes to the paths in the spec's `output` (relative to the spec file).
using BGSimFEM

function main(args)
    files = [a for a in args if !startswith(a, "--")]
    if isempty(files) || "--help" in args
        println("usage: bgsim-fem.jl PART.json [--no-write] [--quiet]")
        return 1
    end
    for f in files
        BGSimFEM.reduce_part(f; write = !("--no-write" in args), verbose = !("--quiet" in args))
    end
    return 0
end

exit(main(ARGS))
