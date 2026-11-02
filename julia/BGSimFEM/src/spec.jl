# The part spec (JSON) and the end-to-end driver: mesh -> interfaces -> assemble -> Craig–Bampton
# -> validation -> reduced-model file + GLB.
#
#   {
#     "name": "bracket",
#     "geometry": { ... see geometry.jl ... },
#     "material": {"E": 70e9, "nu": 0.33, "rho": 2700},
#     "mesh": {"size": 0.004, "order": 2},
#     "interfaces": [ { "name": "A", "position": [...], "quaternion": [...], "select": {...} }, ... ],
#     "modes": {"fixed_interface": 6, "drop_above_hz": null},
#     "stiffening": true,
#     "visual": {"size": 0.006, "color": [0.75, 0.77, 0.8, 1]},
#     "validate": 6,
#     "output": {"model": "data/bracket.modal.json", "glb": "meshes/bracket.glb", "glb_ref": "bracket.glb"}
#   }
#
# Relative paths are relative to the spec file's directory (`base_dir`).

"""
    visual_for(fe, r; visual_grid = nothing) -> VisualMesh

The surface to draw and the mode shapes on it. Without `visual_grid` the FE boundary surface at
the corner nodes; with a (coarser, linear) grid of the same part in R coordinates, its surface,
the mode shapes interpolated from the FE solution at its vertices."""
function visual_for(fe::FEModel, r::ReducedModel; visual_grid::Union{Nothing,Grid} = nothing)
    if visual_grid === nothing
        tris = boundary_triangles(fe.grid; subdivide = false)
        modes = [dofs_to_nodal(fe, view(r.modes, :, k)) for k in 1:r.nm]
        return visual_mesh(fe.X, tris, modes; stress = r.stress_modes)
    end
    tris = boundary_triangles(visual_grid; subdivide = false)
    Pv = node_coordinates(visual_grid)
    used = sort!(unique(reduce(vcat, [collect(t) for t in tris])))
    pts = [Vec{3}((Pv[1, i], Pv[2, i], Pv[3, i])) for i in used]
    ph = PointEvalHandler(fe.grid, pts; warn = false)
    modes = Matrix{Float64}[]
    # nodes the point search misses (curved boundary of the fine mesh) take the nearest FE node
    nearest = Dict{Int,Int}()
    for k in 1:r.nm
        vals = evaluate_at_points(ph, fe.dh, r.modes[:, k], :u)
        U = zeros(3, size(Pv, 2))
        for (j, i) in enumerate(used)
            v = vals[j]
            if any(isnan, v)
                n = get!(nearest, i) do
                    argmin([sum(abs2, fe.X[:, m] .- Pv[:, i]) for m in axes(fe.X, 2)])
                end
                U[:, i] = r.modes[fe.nodedofs[:, n], k]
            else
                U[:, i] = collect(v)
            end
        end
        push!(modes, U)
    end
    # the averaged nodal stress is a nodal field like u: interpolate it with the same shape
    # functions, three components at a time (packed as a displacement-like dof vector)
    stress = Matrix{Float64}[]
    for S in r.stress_modes
        V = zeros(6, size(Pv, 2))
        for (h, rows) in enumerate((1:3, 4:6))
            vals = evaluate_at_points(ph, fe.dh, nodal_to_dofs(fe, S[rows, :]), :u)
            for (j, i) in enumerate(used)
                v = vals[j]
                V[rows, i] = any(isnan, v) ? S[rows, nearest[i]] : collect(v)
            end
        end
        push!(stress, V)
    end
    return visual_mesh(Pv, tris, modes; stress)
end

_get(d, k, default) = (d === nothing || !haskey(d, k) || d[k] === nothing) ? default : d[k]

"""
    reduce_part(spec; base_dir = pwd(), write = true, verbose = true) -> (r, fe, vm, files)

Run the whole tool chain for a part spec (`Dict`, see the file comment)."""
function reduce_part(spec::AbstractDict; base_dir::AbstractString = pwd(), write::Bool = true, verbose::Bool = true)
    log(msg) = verbose && println("[BGSimFEM] ", msg)
    name = String(_get(spec, "name", "part"))
    msh = _get(spec, "mesh", Dict{String,Any}())
    h = Float64(_get(msh, "size", 0.005))
    order = Int(_get(msh, "order", 2))
    t0 = time()
    part = mesh_part(spec["geometry"]; size = h, order = order, base_dir = base_dir)
    log("mesh: $(getncells(part.grid)) tetrahedra (order $order), $(getnnodes(part.grid)) nodes, size $h m ($(round(time() - t0; digits = 1)) s)")
    ifs = make_interfaces(part.grid, spec["interfaces"])
    for f in ifs
        log("interface $(f.name): $(length(f.nodes)) nodes at $(f.position)")
    end
    gridR, ifsR, p1, R1 = to_reference_frame(part.grid, ifs)
    m = spec["material"]
    mat = Material(Float64(m["E"]), Float64(m["nu"]), Float64(m["rho"]))
    t1 = time()
    fe = assemble(gridR, mat)
    log("assembled K, M: $(ndofs_fe(fe)) dofs ($(round(time() - t1; digits = 1)) s)")
    md = _get(spec, "modes", Dict{String,Any}())
    nf = Int(_get(md, "fixed_interface", 6))
    drop = Float64(something(_get(md, "drop_above_hz", nothing), Inf))
    stiff = Bool(_get(spec, "stiffening", true))
    rs = _get(spec, "rail", nothing)
    rail = rs === nothing ? nothing : make_rail(part.grid, rs, p1, R1)
    extra = zeros(0, 0)
    if rail !== nothing
        log("rail $(rail.name): $(round(rail.length; sigdigits = 5)) m, $(length(rail.s)) stations, footprint $(minimum(length.(rail.nodes)))..$(maximum(length.(rail.nodes))) nodes")
        lm = _get(rs, "load_modes", Any[])
        isempty(lm) || (extra = reduce(hcat, [rail_unit_loads(fe, rail, Float64(f))[1] for f in lm]))
    end
    r, aux = craig_bampton(fe, ifsR; nf = nf, stiffening = stiff, name = name, drop_above_hz = drop,
        extra_loads = extra)
    r.frame_position = p1
    r.frame_rotation = R1
    nlm = r.validation["cb"]["load_modes"]
    log("Craig-Bampton: $(r.nf) fixed-interface + $(6 * (length(ifs) - 1)) constraint" *
        (nlm > 0 ? " + $nlm rail load" : "") * " modes -> $(r.nm) modes ($(round(r.timings["total"]; digits = 1)) s)")
    if rail !== nothing
        rd = rail_tables!(r, fe, rail)
        log("rail tables: $(rail.nc) Chebyshev terms, fit error $(round(rd["fit_error"]["translation"]; sigdigits = 3)) (translation), $(round(rd["fit_error"]["rotation"]; sigdigits = 3)) (rotation)")
        vr = validate_rail!(r, fe, aux, rail)
        log("rail statics, full vs reduced deflection under unit loads: max rel. error forces $(round(vr["max_rel_error_force"]; sigdigits = 3)), torsion $(round(vr["max_rel_error_torsion"]; sigdigits = 3)); against the largest deflection $(round(vr["max_error_of_largest"]; sigdigits = 3))")
        for c in vr["cases"]
            log("  s = $(rpad(round(c["station"]; digits = 4), 7)) $(rpad(c["load"], 9)) full $(round(c["full_compliance"]; sigdigits = 5)), reduced $(round(c["reduced_compliance"]; sigdigits = 5)) ($(round(100 * c["rel_error"]; sigdigits = 3)) %, $(round(100 * c["error_of_largest"]; sigdigits = 3)) % of the largest)")
        end
    end
    log("mass $(r.mass) kg, CoM $(r.S0 ./ r.mass) m (in R)")
    log("modal frequencies (clamped at $(ifs[1].name)) [Hz]: $(round.(frequencies_hz(r); sigdigits = 5))")
    nval = Int(_get(spec, "validate", 6))
    if nval > 0
        t2 = time()
        v = validate!(r, aux; nmodes = nval)
        for cfg in ("clamped", "free")
            log("validation $cfg: full $(round.(v[cfg]["full_hz"]; sigdigits = 6)) Hz, reduced $(round.(v[cfg]["reduced_hz"]; sigdigits = 6)) Hz, max rel. error below $(round(v["band_hz"]; sigdigits = 4)) Hz: $(round(v[cfg]["max_rel_error_in_band"]; sigdigits = 3))")
        end
        att = _get(spec, "validate_attached", nothing)
        if att !== nothing && !isempty(att)
            names = [f.name for f in ifs]
            list = map(att) do a
                j = findfirst(==(String(a["interface"])), names)
                j === nothing && throw(ArgumentError("validate_attached: no interface `$(a["interface"])`"))
                Jv = Float64.(reduce(vcat, _get(a, "inertia", [0.0, 0.0, 0.0])))
                J = length(Jv) == 3 ? Matrix(Diagonal(Jv)) : permutedims(reshape(Jv, 3, 3))
                # given in part coordinates: turn into R
                (interface = j, mass = Float64(a["mass"]), inertia = R1' * J * R1,
                    com = R1' * Float64.(collect(_get(a, "com", [0.0, 0.0, 0.0]))))
            end
            va = validate_attached!(r, aux, list; nmodes = min(nval, 4))
            log("validation clamped at $(ifs[1].name) with attached bodies: full $(round.(va["full_hz"]; sigdigits = 6)) Hz, reduced $(round.(va["reduced_hz"]; sigdigits = 6)) Hz, max rel. error below $(round(v["band_hz"]; sigdigits = 4)) Hz: $(round(va["max_rel_error_in_band"]; sigdigits = 3))")
        end
        r.validation["seconds"] = time() - t2
    end
    st = _get(spec, "stress", Dict{String,Any}())
    if st !== false
        st isa AbstractDict || (st = Dict{String,Any}())
        hot = [(String(_get(p, "name", "hotspot $k")), R1' * (Float64.(collect(p["position"])) .- p1))
               for (k, p) in enumerate(_get(st, "hotspots", Any[]))]
        sv = modal_stress!(r, fe, aux; hotspots = hot, peak_points = Int(_get(st, "peak_points", 24)),
            exclude_interfaces = (x -> x isa Bool ? x : Float64(x))(_get(st, "exclude_interfaces", true)))
        log("stress: $(length(r.stress_points)) points ($(length(hot)) hotspots), static load cases full vs reduced peak von Mises: " *
            "interface loads $(round(sv["max_peak_rel_error_interface_loads"]; sigdigits = 3)), self weight $(round(sv["max_peak_rel_error_self_weight"]; sigdigits = 3)); " *
            "points find $(round(100 * sv["peak_coverage"]["min_ratio"]; digits = 1)) % (worst) / $(round(100 * sv["peak_coverage"]["mean_ratio"]; digits = 1)) % (mean) of the surface peak ($(round(sv["seconds"]; digits = 1)) s)")
        for c in sv["cases"]
            log("  $(rpad(c["name"], 34)) peak full $(round(c["full_peak"]; sigdigits = 5)) Pa, reduced $(round(c["reduced_peak"]; sigdigits = 5)) Pa ($(round(100 * c["peak_rel_error"]; sigdigits = 3)) %)" *
                join([", $(h["name"]) $(round(100 * h["rel_error"]; sigdigits = 3)) %" for h in c["hotspots"]]))
        end
    end
    vis = _get(spec, "visual", Dict{String,Any}())
    vsize = _get(vis, "size", nothing)
    vgrid = nothing
    if vsize !== nothing
        vp = mesh_part(spec["geometry"]; size = Float64(vsize), order = 1, base_dir = base_dir)
        vgrid = Grid(getcells(vp.grid), [Node(Vec{3}(Tuple(R1' * (collect(n.x) .- p1)))) for n in getnodes(vp.grid)])
    end
    vm = visual_for(fe, r; visual_grid = vgrid)
    log("visual mesh: $(size(vm.positions, 2)) vertices, $(length(vm.triangles)) triangles")
    files = String[]
    if write
        out = _get(spec, "output", Dict{String,Any}())
        glbpath = _get(out, "glb", nothing)
        glbref = _get(out, "glb_ref", glbpath === nothing ? nothing : basename(glbpath))
        if glbpath !== nothing
            p = isabspath(glbpath) ? glbpath : joinpath(base_dir, glbpath)
            color = Tuple(Float64.(_get(vis, "color", [0.75, 0.77, 0.8, 1.0])))
            write_glb(p, vm; color = color, frequencies = frequencies_hz(r), name = name)
            push!(files, p)
        end
        mp = _get(out, "model", "$name.modal.json")
        p = isabspath(mp) ? mp : joinpath(base_dir, mp)
        info = Dict{String,Any}("element" => order == 2 ? "tet10" : "tet4", "size" => h,
            "cells" => getncells(part.grid), "nodes" => getnnodes(part.grid), "dofs" => ndofs_fe(fe))
        write_modal_body(p, r; glb = glbref, mesh_info = info,
            visual = Dict{String,Any}("vertices" => size(vm.positions, 2), "triangles" => length(vm.triangles)))
        push!(files, p)
        for f in files
            log("wrote $f")
        end
    end
    log("done in $(round(time() - t0; digits = 1)) s")
    return r, fe, vm, files
end

"""Read a part spec file and run `reduce_part` with paths relative to the spec's folder."""
function reduce_part(path::AbstractString; kwargs...)
    spec = JSON3.read(read(path, String), Dict{String,Any})
    return reduce_part(spec; base_dir = dirname(abspath(path)), kwargs...)
end
