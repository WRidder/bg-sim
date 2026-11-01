# Golden tests of `stdlib:contact/TerrainSurface` (the hills of the `cars` buggy).
#
# A query point moves over the terrain at a constant velocity (a PoseIntegrator3D on a
# constant twist); at every sample the block's height, tangent-plane frame and slope are the
# closed form of the height field h(x, y) = h0 + sx x + sy y + sum a cos(kx x + ky y + ph):
# n = (-h_x, -h_y, 1)/|.|, t1 = (1, 0, h_x)/|.|, t2 = n x t1 (an orthonormal frame).
# The wheel tests on a TerrainSurface plane are in test_Tyre.jl.
using Test
using BGSim
using LinearAlgebra

if !isdefined(@__MODULE__, :_ty_kinematic)
    include(joinpath(@__DIR__, "tyre_rig.jl"))
end

const _TS_TERRAIN = (h0 = 0.4, sx = 0.05, sy = -0.02, a = [1.5, 0.6, 0.2], kx = [0.08, -0.15, 0.4],
    ky = [0.03, 0.12, -0.25], ph = [0.3, 1.9, 4.0])

function _ts_model(; vx = 3.0, vy = 1.2, t_end = 10.0, points = 201)
    T = _TS_TERRAIN
    nodes = Any[
        bg_node("v", "Twist", _ty_d("inline" => _ty_d("source" => _TY_VEC6));
            params = _ty_d("c4" => string(vx), "c5" => string(vy))),
        bg_node("pose", "Pose", bg_ref("stdlib:multibond/PoseIntegrator3D");
            starts = _ty_d("qw" => "1.0", "qx" => "0.0", "qy" => "0.0", "qz" => "0.0",
                "px" => "-5.0", "py" => "2.0", "pz" => "0.0")),
        bg_node("s", "Terrain", bg_ref("stdlib:contact/TerrainSurface");
            params = _ty_d("h0" => string(T.h0), "sx" => string(T.sx), "sy" => string(T.sy),
                "a" => _ty_vec(T.a), "kx" => _ty_vec(T.kx), "ky" => _ty_vec(T.ky), "ph" => _ty_vec(T.ph))),
    ]
    nodes[end]["constants"] = _ty_d("N" => "3")
    conns = Any[
        bg_conn("c1", "signal", "v", "y", "pose", "tw"),
        bg_conn("c2", "signal", "pose", "g", "s", "g"),
    ]
    return bg_model("TerrainRig", nodes, conns; t_end = t_end, points = points, reltol = 1.0e-10, abstol = 1.0e-12)
end

function _ts_h(x, y)
    T = _TS_TERRAIN
    h = T.h0 + T.sx * x + T.sy * y
    hx, hy = T.sx, T.sy
    for i in eachindex(T.a)
        ph = T.kx[i] * x + T.ky[i] * y + T.ph[i]
        h += T.a[i] * cos(ph)
        hx -= T.a[i] * T.kx[i] * sin(ph)
        hy -= T.a[i] * T.ky[i] * sin(ph)
    end
    return h, hx, hy
end

@testset "TerrainSurface (golden)" begin
    cols, res, _ = bg_run(_ts_model())
    @test res.status == "done"
    @test isempty([d for d in res.diagnostics if d.severity == "error"])
    errs = Float64[]
    for i in eachindex(cols["time"])
        x, y = cols["Pose/px"][i], cols["Pose/py"][i]
        h, hx, hy = _ts_h(x, y)
        n = [-hx, -hy, 1.0] / sqrt(1 + hx^2 + hy^2)
        t1 = [1.0, 0.0, hx] / sqrt(1 + hx^2)
        t2 = cross(n, t1)
        fr = [cols["Terrain/fr[$k]"][i] for k in 1:9]
        push!(errs, abs(cols["Terrain/hq"][i] - h))
        push!(errs, abs(cols["Terrain/o[3]"][i] - h))
        push!(errs, abs(cols["Terrain/o[1]"][i] - x) + abs(cols["Terrain/o[2]"][i] - y))
        push!(errs, norm(fr[1:3] - n), norm(fr[4:6] - t1), norm(fr[7:9] - t2))
        push!(errs, abs(cols["Terrain/slope"][i] - atan(sqrt(hx^2 + hy^2))))
        # the frame is orthonormal
        F = reshape(fr, 3, 3)
        push!(errs, opnorm(F' * F - I))
    end
    @test maximum(errs) < 1.0e-9
    # the query point really crossed hills and valleys
    @test maximum(cols["Terrain/hq"]) - minimum(cols["Terrain/hq"]) > 0.5
end
