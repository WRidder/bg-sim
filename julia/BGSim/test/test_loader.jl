# Work package J-MB15: the joint-chain record loader, `lumpInto`, inverse dynamics and gravity
# compensation, on the six-axis arm of J-MB10 (UR5-like geometry, `golden/spatial/jmb10_arm.jl`).
#
# The records are the J-MB10 arm **re-described with an arbitrary joint axis per joint** (a random
# rotation `Q_i` of every link frame, so the axis in the joint frame is `Q_i ez`, the link frame,
# CoM, principal axes and the child joint origins are rotated along). The physical arm and the joint
# coordinates are identical, so the independent Craig Newton-Euler and forward kinematics of
# `jmb10_arm.jl` are valid references for the loader placement transforms, its `N - c` bookkeeping
# and the spatial-vector inverse dynamics.
using Test
using BGSim
using LinearAlgebra
using Random

if !isdefined(@__MODULE__, :_ja_arm_model)
    include(joinpath(@__DIR__, "golden", "spatial", "jmb10_arm.jl"))
end

const _JL_QH = [0.4, 1.2, -0.6, -0.5, 0.8, 0.3]    # the stable hold pose of J-MB10

"""A random proper rotation matrix."""
function _jl_rot(rng)
    Q = Matrix(qr(randn(rng, 3, 3)).Q)
    det(Q) < 0 && (Q[:, 3] .*= -1)
    return Q
end

"""The J-MB10 arm as chain records with the link frame of link i rotated by `Qs[i]` (v_new = Q v_old)."""
function _jl_records(arm, Qs)
    links = LinkRecord[]
    joints = JointRecord[]
    for i in eachindex(arm)
        L, Q = arm[i], Qs[i]
        Qp = i == 1 ? Matrix(1.0I, 3, 3) : Qs[i - 1]
        push!(links, LinkRecord("l$i"; mass = L.m, com = Q * L.c, inertia = L.J, axes = Q))
        push!(joints, JointRecord("j$i"; parent = i == 1 ? "world" : "l$(i - 1)", child = "l$i",
            type = :revolute, axis = Q * [0.0, 0.0, 1.0], origin = (Qp * L.RN * Q', Qp * L.pN)))
    end
    return JointChain(links, joints)
end

"""Independent forward kinematics of the original arm: `(R, p)` of every body frame (link frame, CoM)."""
function _jl_fk(arm, q)
    Rw = Matrix(1.0I, 3, 3)
    pw = zeros(3)
    out = Tuple{Matrix{Float64},Vector{Float64}}[]
    for i in eachindex(arm)
        L = arm[i]
        pw = pw + Rw * L.pN
        Rw = Rw * L.RN * _ja_Rz(q[i])
        push!(out, (copy(Rw), pw + Rw * L.c))
    end
    return out
end

_jl_pe(arm, q) = _JA_G * sum(arm[i].m * c[2][3] for (i, c) in enumerate(_jl_fk(arm, q)))

@testset "J-MB15 joint-chain loader, lumpInto, inverse dynamics" begin
    t_total = @elapsed begin
        rng = MersenneTwister(15)
        arm = _ja_arm()
        Qs = [_jl_rot(rng) for _ in 1:6]
        chain = _jl_records(arm, Qs)
        e6 = Matrix(1.0I, 6, 6)

        @testset "record validation" begin
            @test_throws ArgumentError LinkRecord("x"; mass = -1.0, inertia = [1.0, 1.0, 1.0])
            @test_throws ArgumentError LinkRecord("x"; mass = 1.0)
            @test_throws ArgumentError JointRecord("j"; parent = "world", child = "x", type = :ball)
            l = LinkRecord("a"; mass = 1.0, inertia = [1.0, 1.0, 1.0])
            @test_throws ArgumentError JointChain([l], [JointRecord("j"; parent = "nowhere", child = "a")])
            @test_throws ArgumentError JointChain([l], [JointRecord("j"; parent = "world", child = "b")])
            # a tensor is diagonalised to a proper rotation and the moments
            T = [2.0 0.3 0.1; 0.3 3.0 -0.2; 0.1 -0.2 4.0]
            lt = LinkRecord("t"; mass = 1.0, tensor = T)
            @test lt.axes * Diagonal(lt.inertia) * lt.axes' ≈ T atol = 1e-12
            @test det(lt.axes) ≈ 1.0
            # SDF-style rpy and quaternion
            R1, _ = joint_pose(; rpy = (0.3, -0.4, 0.5))
            R2, _ = joint_pose(; quat = (cos(0.1), 0.0, 0.0, sin(0.1)))
            @test R2 ≈ [cos(0.2) -sin(0.2) 0; sin(0.2) cos(0.2) 0; 0 0 1] atol = 1e-14
            @test R1 * R1' ≈ I atol = 1e-14
            # fixed joints must be lumped before a model is loaded
            fixed = JointChain([l], [JointRecord("j"; parent = "world", child = "a", type = :fixed)])
            @test_throws ArgumentError load_chain(fixed)
        end

        @testset "inverse dynamics vs the independent Craig Newton-Euler (J-MB10)" begin
            worst = 0.0
            for _ in 1:20
                q, qd, qdd = 2 .* randn(rng, 6), 3 .* randn(rng, 6), 5 .* randn(rng, 6)
                tau = inverse_dynamics(chain, q, qd, qdd; g = _JA_G)
                ref = _ja_rne(arm, q, qd, qdd)[1]
                worst = max(worst, maximum(abs.(tau .- ref)) / maximum(abs.(ref)))
            end
            println("J-MB15 inverse dynamics vs J-MB10 reference, worst relative error over 20 random states: ", worst)
            @test worst <= 1e-10
            @test_throws ArgumentError inverse_dynamics(chain, zeros(5), zeros(6), zeros(6))
        end

        @testset "gravity compensation: = ID at rest = gradient of the potential; power balance" begin
            worst_id = 0.0
            worst_grad = 0.0
            for _ in 1:10
                q = 2 .* randn(rng, 6)
                tg = gravity_compensation(chain, q)
                worst_id = max(worst_id, maximum(abs.(tg .- inverse_dynamics(chain, q, zeros(6), zeros(6)))))
                h = 1e-6
                grad = [(_jl_pe(arm, q + h * e6[:, k]) - _jl_pe(arm, q - h * e6[:, k])) / 2h for k in 1:6]
                worst_grad = max(worst_grad, maximum(abs.(tg .- grad)) / maximum(abs.(grad)))
            end
            println("J-MB15 gravity compensation: |ID(rest) - gc| ", worst_id, ", relative gradient error ", worst_grad)
            @test worst_id == 0.0
            @test worst_grad <= 1e-7
            # d/dt(KE + PE) = tau . qd along q(t) = q + qd t + qdd t^2 / 2 (the Coriolis terms of the recursion)
            q, qd, qdd = randn(rng, 6), randn(rng, 6), randn(rng, 6)
            function energy(t)
                qt, qdt = q + qd * t + qdd * t^2 / 2, qd + qdd * t
                M = zeros(6, 6)
                for k in 1:6
                    M[:, k] = inverse_dynamics(chain, qt, zeros(6), e6[:, k]; g = 0.0)
                end
                return 0.5 * dot(qdt, M * qdt) + _jl_pe(arm, qt)
            end
            h = 1e-5
            dE = (energy(h) - energy(-h)) / 2h
            @test dE ≈ dot(inverse_dynamics(chain, q, qd, qdd), qd) rtol = 1e-7
        end

        @testset "lumpInto" begin
            payload = LinkRecord("payload"; mass = 0.5, com = [0.01, -0.02, 0.03],
                tensor = [0.004 0.0005 -0.0003; 0.0005 0.006 0.0002; -0.0003 0.0002 0.005])
            Rf, pf = joint_pose(; xyz = (0.02, -0.01, 0.05), rpy = (0.4, -0.3, 0.9))
            fixedj = JointRecord("mount"; parent = "l6", child = "payload", type = :fixed, origin = (Rf, pf))
            full = JointChain([chain.links; payload], [chain.joints; fixedj])
            lumped = lumpInto(full, "l6")
            @test length(lumped.links) == 6 && length(lumped.joints) == 6
            l6 = chain.links[6]
            m = l6.mass + payload.mass
            c = (l6.mass * l6.com + payload.mass * (pf + Rf * payload.com)) / m
            # analytic parallel axis: both tensors about the new CoM, in the link-6 frame
            I6 = l6.axes * Diagonal(l6.inertia) * l6.axes'
            Ip = Rf * payload.axes * Diagonal(payload.inertia) * (Rf * payload.axes)'
            s(d) = dot(d, d) * Matrix(1.0I, 3, 3) - d * d'
            T = I6 + l6.mass * s(l6.com - c) + Ip + payload.mass * s(pf + Rf * payload.com - c)
            L = lumped.links[6]
            @test L.mass ≈ m rtol = 1e-14
            @test L.com ≈ c atol = 1e-15
            @test L.axes * Diagonal(L.inertia) * L.axes' ≈ T rtol = 1e-12
            @test det(L.axes) ≈ 1.0
            @test maximum(abs.(L.axes * L.axes' - I)) < 1e-14
            @test sort(L.inertia) ≈ sort(eigvals(Symmetric(T))) rtol = 1e-12
            @test_throws ArgumentError lumpInto(full, "nope")
            # ID with the payload lumped = ID with the payload as a separate rigid child (fixed joint)
            worst = 0.0
            for _ in 1:10
                q, qd, qdd = 2 .* randn(rng, 6), 3 .* randn(rng, 6), 5 .* randn(rng, 6)
                a = inverse_dynamics(lumped, q, qd, qdd)
                b = inverse_dynamics(full, q, qd, qdd)
                worst = max(worst, maximum(abs.(a .- b)) / maximum(abs.(b)))
            end
            println("J-MB15 lumpInto: ID lumped vs separate fixed child, worst relative error ", worst)
            @test worst <= 1e-10
            # a body hanging on the lumped child is re-attached to the parent
            tool = LinkRecord("tool"; mass = 0.2, inertia = [1e-3, 1e-3, 1e-3])
            tj = JointRecord("tool_j"; parent = "payload", child = "tool", axis = [1.0, 0.0, 0.0],
                origin = joint_pose(; xyz = (0.0, 0.0, 0.1)))
            ext = JointChain([full.links; tool], [full.joints; tj])
            lext = lumpInto(ext, "l6")
            @test lext.joints[end].parent == "l6"
            q, qd, qdd = randn(rng, 7), randn(rng, 7), randn(rng, 7)
            @test inverse_dynamics(lext, q, qd, qdd) ≈ inverse_dynamics(ext, q, qd, qdd) rtol = 1e-10
        end

        @testset "loader: model checks clean; composed link poses = independent FK" begin
            drives = Dict("j$i" => 0.0 for i in 1:6)
            frag = load_chain(chain; deflect = false, drives = drives)
            @test frag["drive_ports"]["j3"] == (node = "j3", port = "drive")
            @test Set(keys(frag["pose_signals"])) == Set("l$i" for i in 1:6)
            checked = _ja_check(chain_model(frag; points = 2, t_end = 1e-6))
            @test isempty(_ja_errors(checked))
            @test _ja_w201(checked) == 0
            worst = 0.0
            for _ in 1:3
                q = 2 .* randn(rng, 6)
                doc = chain_model(load_chain(chain; q0 = q, deflect = false, drives = drives); points = 2, t_end = 1e-6)
                c, r, flat, wall = _ja_run(doc)
                ref = _jl_fk(arm, q)
                for i in 1:6
                    g(k) = c["j$(i)_cc/g[$k]"][1]
                    Rm = _ja_Rq(g(1), g(2), g(3), g(4))
                    worst = max(worst, maximum(abs.(Rm .- ref[i][1])), maximum(abs.([g(5), g(6), g(7)] .- ref[i][2])))
                end
            end
            println("J-MB15 composed link poses vs independent FK at 3 random q: max error ", worst)
            @test worst <= 1e-12
        end

        @testset "loader: gravity compensation holds the pose (e k <= C)" begin
            q0 = _JL_QH
            tau = gravity_compensation(chain, q0)
            @test maximum(abs.(tau)) > 20.0
            kk = 1.0e7
            frag = load_chain(chain; stiffness = kk, q0 = q0, drives = Dict("j$i" => tau[i] for i in 1:6))
            c, r, flat, wall = _ja_run(chain_model(frag; t_end = 1.5, points = 31))
            d = maximum(maximum(abs.(c["j$j/qout"] .- q0[j])) for j in 1:6)
            println("J-MB15 gravity compensation (loader arm, kk = ", kk, "): max joint drift ", d, " rad, e*k = ", d * kk,
                ", wall ", round(wall; digits = 1), " s")
            @test d * kk <= 7.0e3
            # without the compensation the same pose falls (so the hold above is not vacuous)
            doc2 = chain_model(load_chain(chain; stiffness = kk, q0 = q0, drives = Dict("j$i" => 0.0 for i in 1:6));
                t_end = 0.5, points = 11)
            c2, r2, _, _ = _ja_run(doc2)
            @test maximum(maximum(abs.(c2["j$j/qout"] .- q0[j])) for j in 1:6) > 0.1
        end

        @testset "prismatic and limited joints load and check clean" begin
            links = [LinkRecord("base"; mass = 2.0, inertia = [0.1, 0.1, 0.1]),
                LinkRecord("slide"; mass = 1.0, com = [0.0, 0.0, 0.1], inertia = [0.01, 0.02, 0.03])]
            joints = [JointRecord("rot"; parent = "world", child = "base", axis = [0.0, 1.0, 0.0], limits = (-1.0, 1.0)),
                JointRecord("lin"; parent = "base", child = "slide", type = :prismatic, axis = [1.0, 0.0, 0.0],
                    origin = joint_pose(; xyz = (0.0, 0.0, 0.2), rpy = (0.0, 0.2, 0.0)), limits = (0.0, 0.3))]
            frag = load_chain(JointChain(links, joints); drives = Dict("rot" => 0.0, "lin" => 0.0))
            ids = Dict(n["id"] => n["block"] for n in frag["nodes"])
            @test ids["rot"]["ref"] == "stdlib:spatial/Revolute3DLimit"
            @test ids["lin"]["ref"] == "stdlib:spatial/Prismatic3DLimit"
            checked = _ja_check(chain_model(frag))
            @test isempty(_ja_errors(checked))
            @test _ja_w201(checked) == 0
            # a vertical slide carries its weight and its inertia
            vc = JointChain([LinkRecord("m"; mass = 3.0, inertia = [1.0, 1.0, 1.0])],
                [JointRecord("z"; parent = "world", child = "m", type = :prismatic)])
            @test gravity_compensation(vc, [0.7]) ≈ [3.0 * 9.81] rtol = 1e-14
            @test inverse_dynamics(vc, [0.0], [0.0], [2.0]; g = 0.0) ≈ [6.0] rtol = 1e-14
        end
    end
    println("J-MB15 test_loader.jl total: ", round(t_total; digits = 1), " s")
end
