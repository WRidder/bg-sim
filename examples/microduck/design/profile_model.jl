# Where the time goes in one microduck model: size, stiffness and cost per step.
#
#   julia --project=julia/BGSim examples/microduck/design/profile_model.jl <model> [t_run]
#
# Prints the number of states (differential / algebraic), the cost of one right-hand side
# and of one dense finite-difference Jacobian (Rodas5P builds one per step with ForwardDiff,
# which costs about the same number of right-hand sides), the spectrum at the start
# (eigenvalues of J, or of (J, M) for a DAE) with the states that carry the fastest modes,
# and a timed Rodas5P run of `t_run` seconds (default 0.05) after a warm-up.

using BGSim
import JSON3
import LinearAlgebra
using OrdinaryDiffEqRosenbrock
import ModelingToolkit

const PROJECT = normpath(joinpath(@__DIR__, ".."))

todict(x::AbstractDict) = Dict{String,Any}(String(k) => todict(v) for (k, v) in pairs(x))
todict(x::AbstractVector) = Any[todict(v) for v in x]
todict(x) = x

function fd_jacobian(f!, u, p, t)
    n = length(u)
    J = zeros(n, n)
    f0 = similar(u)
    f1 = similar(u)
    f!(f0, u, p, t)
    for j in 1:n
        h = sqrt(eps()) * max(1.0, abs(u[j]))
        uj = u[j]
        u[j] = uj + h
        f!(f1, u, p, t)
        u[j] = uj
        @views J[:, j] .= (f1 .- f0) ./ h
    end
    return J
end

function main(args)
    model = args[1]
    t_run = length(args) >= 2 ? parse(Float64, args[2]) : 0.05
    doc = todict(JSON3.read(read(joinpath(PROJECT, "models", model * ".bgmodel.json"), String)))
    t0 = time()
    flat = BGSim.Compile.flatten(BGSim.IR.parse_model(doc); project_dir = PROJECT)
    println("flatten          ", round(time() - t0; digits = 1), " s")
    t0 = time()
    low = BGSim.lower_model(flat; t_start = 0.0, t_end = t_run)
    println("lower+compile    ", round(time() - t0; digits = 1), " s")
    prob = low.problem
    sys = low.model.system
    sts = string.(ModelingToolkit.unknowns(sys))
    M = prob.f.mass_matrix
    n = length(prob.u0)
    nalg = M isa LinearAlgebra.UniformScaling ? 0 : count(i -> M[i, i] == 0, 1:n)
    println("states           ", n, " (", n - nalg, " differential, ", nalg, " algebraic)")
    println("equations        ", length(ModelingToolkit.equations(sys)), " (observed ", length(ModelingToolkit.observed(sys)), ")")
    # initialise as the solver does
    integ = OrdinaryDiffEqRosenbrock.init(prob, Rodas5P(); reltol = 1e-5, abstol = 1e-7)
    u = copy(integ.u)
    p = integ.p
    du = similar(u)
    prob.f(du, u, p, 0.0)
    nrep = 200
    t0 = time_ns()
    for _ in 1:nrep
        prob.f(du, u, p, 0.0)
    end
    t_f = (time_ns() - t0) / nrep / 1e3
    println("rhs              ", round(t_f; digits = 2), " us per call")
    J = fd_jacobian(prob.f, copy(u), p, 0.0)
    t0 = time_ns()
    J = fd_jacobian(prob.f, copy(u), p, 0.0)
    t_j = (time_ns() - t0) / 1e3
    println("dense FD Jacobian ", round(t_j; digits = 1), " us (", n + 1, " rhs)")
    nz = count(!iszero, J)
    println("Jacobian non-zeros ", nz, " of ", n * n)
    # spectrum
    Mm = M isa LinearAlgebra.UniformScaling ? Matrix{Float64}(LinearAlgebra.I, n, n) : Matrix{Float64}(M)
    F = LinearAlgebra.eigen(J, Mm)
    lam = F.values
    fin = findall(isfinite, lam)
    order = sort(fin; by = i -> -abs(lam[i]))
    println("finite eigenvalues ", length(fin), "; the 12 fastest (|lambda| rad/s, re, im) and their largest state components:")
    shown = Set{Float64}()
    k = 0
    for i in order
        a = abs(lam[i])
        any(s -> abs(s - a) < 1e-6 * a, shown) && continue
        push!(shown, a)
        v = abs.(F.vectors[:, i])
        v ./= maximum(v)
        top = sort(1:n; by = j -> -v[j])[1:3]
        println("  ", lpad(string(round(a; sigdigits = 4)), 10), "  ", lpad(string(round(real(lam[i]); sigdigits = 3)), 10), " ",
            lpad(string(round(imag(lam[i]); sigdigits = 3)), 10), "   ", join([first(sts[j], 50) for j in top], ", "))
        k += 1
        k >= 12 && break
    end
    slow = sort(fin; by = i -> real(lam[i]))
    println("most positive real part: ", round(real(lam[last(slow)]); sigdigits = 4))
    # a timed run
    solve(prob, Rodas5P(); reltol = 1e-5, abstol = 1e-7, tspan = (0.0, 1e-3))
    t0 = time()
    sol = solve(remake(prob; tspan = (0.0, t_run)), Rodas5P(); reltol = 1e-5, abstol = 1e-7, save_everystep = false)
    wall = time() - t0
    st = sol.stats
    println("Rodas5P ", t_run, " s: ", sol.retcode, ", ", round(wall; digits = 2), " s wall (", round(wall / t_run; digits = 1),
        " s per simulated s), steps ", st.naccept, " accepted / ", st.nreject, " rejected, rhs ", st.nf, ", jac ", st.njacs,
        ", LU ", st.nw)
end

main(ARGS)
