# Craig–Bampton reduction for the floating-frame modal body (`stdlib:spatial/ModalBody3D`).
#
# 1. The interfaces tie their nodes rigidly to 6-dof interface frames (RBE2, `interfaces.jl`):
#    u = T [u_free; u_I1; ...; u_In].
# 2. The body's reference frame R is interface 1, and the elastic field is measured relative to
#    it: interface 1 is clamped (u_I1 = 0). This is the "clamped at the reference interface"
#    floating frame, the general form of the beam blocks' clamped-free basis.
# 3. Craig–Bampton on the remaining dofs: `nf` fixed-interface modes (all interfaces clamped)
#    plus the 6 (n - 1) static constraint modes of interfaces 2..n (unit motion of one
#    interface dof, the others clamped). The constraint modes are the static correction:
#    loads at the interfaces are represented exactly.
# 4. The reduced pair (K_r, M_r) is diagonalised, so the body block gets modal coordinates with
#    diagonal modal mass m_k and stiffness k_k (same span, the eigenvectors of the CB model of
#    the body clamped at interface 1). Each mode is scaled to a largest nodal translation of 1,
#    so the coordinates are in metres.
# 5. The inertia invariants of the floating-frame equations (all in R, exact for the FE mass
#    matrix because rigid and linear fields are in the FE space):
#      m, S0 = int rho x, J0 = int rho (|x|^2 I - x x^T),
#      St = int rho Phi (3 x nm), Sr = int rho x x Phi (3 x nm),
#      J1_k = int rho (2 x.phi_k I - x phi_k^T - phi_k x^T) (6 components per mode),
#      E_ab = int rho Phi_a^T Phi_b (nm x nm, a, b in x, y, z),
#    and the interface mode values: translation of interface j (R coordinates) and its rotation
#    (in the interface's own frame) per unit modal coordinate.
# 6. Geometric stiffening (optional): the second-order displacement field u2(q) of the linear
#    modes enters the kinetic energy and the interface positions through
#      int f . u2 dV = -1/2 q^T G(f) q,   G(f) = Phi^T K_sigma(sigma_f) Phi,
#    where sigma_f is the static stress under the load f with interface 1 clamped. The block
#    needs the load cases
#      translation  f = rho e_a                                 (a = x, y, z)
#      inertia      f = rho (2 delta_ab x - x_a e_b - x_b e_a)   (ab = xx yy zz xy xz yz)
#      rotation     f = rho (e_a x x)                           (a = x, y, z)
#      interface    unit force e_a at interface j >= 2           (a = x, y, z)
#    so the first moment, the inertia tensor, the rotational coupling and the interface
#    positions carry the second-order terms. Centrifugal, Euler and translational-inertia
#    stiffening and the stiffening by interface forces then follow from the equations of
#    motion; it is energy consistent (it is part of T and of the port kinematics). Not
#    included: the stiffening by interface moments and by distributed external loads other
#    than gravity.

const COMP6 = ((1, 1), (2, 2), (3, 3), (1, 2), (1, 3), (2, 3))
const COMP6_NAMES = ("xx", "yy", "zz", "xy", "xz", "yz")

"""
    ReducedModel

Everything the modal body block and the viewer need, plus validation data. All vectors in the
reference frame R (interface 1)."""
Base.@kwdef mutable struct ReducedModel
    name::String = "part"
    nm::Int = 0
    nf::Int = 0
    material::Material = Material(0, 0, 0)
    mass::Float64 = 0.0
    S0::Vector{Float64} = zeros(3)
    J0::Matrix{Float64} = zeros(3, 3)
    mk::Vector{Float64} = Float64[]
    kk::Vector{Float64} = Float64[]
    St::Matrix{Float64} = zeros(3, 0)
    Sr::Matrix{Float64} = zeros(3, 0)
    J1::Matrix{Float64} = zeros(6, 0)
    E::Vector{Matrix{Float64}} = Matrix{Float64}[]
    interfaces::Vector{Interface} = Interface[]
    PT::Vector{Matrix{Float64}} = Matrix{Float64}[]     # per interface 3 x nm (R coordinates)
    PR::Vector{Matrix{Float64}} = Matrix{Float64}[]     # per interface 3 x nm (interface frame)
    stiffening::Union{Nothing,Dict{String,Vector{Matrix{Float64}}}} = nothing
    stress_modes::Vector{Matrix{Float64}} = Matrix{Float64}[]   # per mode 6 x nn nodal stress (Pa per m)
    stress_points::Vector{Any} = Any[]                          # hotspots, then peak candidates
    rail::Union{Nothing,Dict{String,Any}} = nothing              # the rail tables (rail.jl)
    modes::Matrix{Float64} = zeros(0, 0)                 # ndofs x nm (full field)
    frame_position::Vector{Float64} = zeros(3)           # p1 in part coordinates
    frame_rotation::Matrix{Float64} = Matrix{Float64}(I, 3, 3)
    mode_kind::Vector{String} = String[]
    validation::Dict{String,Any} = Dict{String,Any}()
    timings::Dict{String,Float64} = Dict{String,Float64}()
end

frequencies_hz(r::ReducedModel) = sqrt.(max.(r.kk, 0.0) ./ r.mk) ./ (2pi)

_sym(A) = (A + A') / 2

function _lowest_modes(K, M, nev; sigma = 0.0)
    nev = min(nev, size(K, 1) - 2)
    nev <= 0 && return Float64[], zeros(size(K, 1), 0)
    if size(K, 1) <= 1500
        F = eigen(Symmetric(Matrix(K)), Symmetric(Matrix(M)))
        return F.values[1:nev], F.vectors[:, 1:nev]
    end
    # shift-invert Lanczos on the symmetric operator L^-1 M L^-T, (K - sigma M) = L L^T
    F = cholesky(Symmetric(K - sigma * M))
    n = size(K, 1)
    # KrylovKit's tolerance is absolute: scale the operator to a unit spectral radius first
    # (a small part has M/K ~ 1e-15)
    x0 = randn(n)
    x0 ./= norm(x0)
    c = 1.0
    for _ in 1:3   # a few power steps for the scale
        y = F.PtL \ (M * (F.UP \ x0))
        c = 1.0 / norm(y)
        x0 = y .* c
    end
    op(y) = c * (F.PtL \ (M * (F.UP \ y)))
    θ, Y, info = KrylovKit.eigsolve(op, randn(n), nev, :LR; issymmetric = true, tol = 1e-11,
        krylovdim = max(2nev + 10, 30), maxiter = 300)
    info.converged >= nev || @warn "eigensolver: $(info.converged) of $nev eigenpairs converged"
    θ = real.(θ[1:nev]) ./ c
    λ = sigma .+ 1.0 ./ θ
    V = reduce(hcat, [F.UP \ real.(Y[k]) for k in 1:nev])
    for k in 1:nev
        V[:, k] ./= sqrt(dot(V[:, k], M * V[:, k]))
    end
    p = sortperm(λ)
    return λ[p], V[:, p]
end

"""Rigid and linear nodal fields as dof vectors."""
function _field(fe::FEModel, f)
    U = zeros(3, nnodes_fe(fe))
    for i in axes(U, 2)
        U[:, i] = f(fe.X[:, i])
    end
    return nodal_to_dofs(fe, U)
end

_e(a) = (v = zeros(3); v[a] = 1.0; v)

"""
    craig_bampton(fe, interfaces; nf, stiffening = true) -> ReducedModel

Reduce the assembled FE model (grid already in R coordinates, interfaces in R). See the file
comment for the method."""
function craig_bampton(fe::FEModel, ifs::Vector{Interface}; nf::Integer, stiffening::Bool = true,
        name::AbstractString = "part", drop_above_hz::Real = Inf,
        extra_loads::AbstractMatrix{<:Real} = zeros(0, 0))
    t0 = time()
    ni = length(ifs)
    T, nfree = rbe2_transform(fe, ifs)
    Kt = _sym(T' * fe.K * T)
    Mt = _sym(T' * fe.M * T)
    ib(j) = nfree + 6(j - 1) .+ (1:6)
    c = vcat(1:nfree, (ni >= 2 ? reduce(vcat, [collect(ib(j)) for j in 2:ni]) : Int[]))
    Tc = T[:, c]
    Kc = Kt[c, c]
    Mc = Mt[c, c]
    ii = 1:nfree
    bb = (nfree + 1):length(c)
    Kii = Kc[ii, ii]
    Mii = Mc[ii, ii]
    timings = Dict{String,Float64}("assemble_transform" => time() - t0)
    # fixed-interface modes
    t1 = time()
    # one more than kept: the first discarded fixed-interface frequency bounds the band in
    # which the reduced model is accurate (the Craig–Bampton rule of thumb)
    λf, Φf = _lowest_modes(Kii, Mii, nf + 1)
    first_discarded_hz = length(λf) > nf ? sqrt(max(λf[nf + 1], 0.0)) / 2pi : Inf
    λf = λf[1:min(nf, length(λf))]
    Φf = Φf[:, 1:length(λf)]
    timings["fixed_interface_modes"] = time() - t1
    # constraint modes
    t1 = time()
    Fii = cholesky(Symmetric(Kii))
    Ψ = isempty(bb) ? zeros(nfree, 0) : -(Fii \ Matrix(Kc[ii, bb]))
    timings["constraint_modes"] = time() - t1
    nb = length(bb)
    B = zeros(length(c), length(λf) + nb)
    B[ii, 1:length(λf)] = Φf
    B[ii, (length(λf) + 1):end] = Ψ
    for k in 1:nb
        B[nfree + k, length(λf) + k] = 1.0
    end
    # load modes (modal truncation augmentation): the static responses to given loads (a
    # carriage on a rail between the interfaces), each with the part of it the basis already
    # spans removed (M-orthogonal), so that such a load's static deflection becomes exact
    nl = 0
    if size(extra_loads, 2) > 0
        t1 = time()
        Fc = cholesky(Symmetric(Kc))
        for j in axes(extra_loads, 2)
            u = Fc \ (Tc' * extra_loads[:, j])
            n0 = sqrt(dot(u, Mc * u))
            for _ in 1:2                                   # Gram-Schmidt, twice for round-off
                MB = Mc * B
                u = u - B * ((B' * MB) \ (MB' * u))
            end
            nu = sqrt(max(dot(u, Mc * u), 0.0))
            nu > 1e-6 * n0 || continue                     # already in the span
            B = hcat(B, u ./ nu)
            nl += 1
        end
        timings["load_modes"] = time() - t1
    end
    Mr = _sym(B' * (Mc * B))
    Kr = _sym(B' * (Kc * B))
    F = eigen(Symmetric(Kr), Symmetric(Mr))
    keep = findall(λ -> sqrt(max(λ, 0.0)) / 2pi <= drop_above_hz, F.values)
    X = F.vectors[:, keep]
    Y = B * X                          # modes in the clamped independent dofs
    Φ = Tc * Y                         # full field
    nm = size(Φ, 2)
    # scale: largest nodal translation 1 (coordinates in metres), largest component positive
    for k in 1:nm
        U = dofs_to_nodal(fe, view(Φ, :, k))
        mags = [norm(U[:, i]) for i in axes(U, 2)]
        imax = argmax(mags)
        s = mags[imax]
        a = argmax(abs.(U[:, imax]))
        s *= sign(U[a, imax])
        Φ[:, k] ./= s
        Y[:, k] ./= s
    end
    mk = [dot(Φ[:, k], fe.M * Φ[:, k]) for k in 1:nm]
    kk = [dot(Φ[:, k], fe.K * Φ[:, k]) for k in 1:nm]
    # which part of each mode is a fixed-interface mode (modal mass fraction of the CB basis)
    kind = String[]
    for k in 1:nm
        x = X[:, k]
        wf = sum(abs2, x[1:length(λf)])
        wb = sum(abs2, x[(length(λf) + 1):(length(λf) + nb)])
        wl = sum(abs2, x[(length(λf) + nb + 1):end])
        push!(kind, wl > max(wf, wb) ? "load" : wb > wf ? "constraint" : "fixed-interface")
    end
    r = ReducedModel(name = String(name), nm = nm, nf = length(λf), material = fe.material,
        interfaces = ifs, modes = Φ, mk = mk, kk = kk, mode_kind = kind)
    # ---- rigid-body properties ----
    trv = [_field(fe, x -> _e(a)) for a in 1:3]
    rot = [_field(fe, x -> cross(_e(a), x)) for a in 1:3]
    lin = [_field(fe, x -> x[a] .* _e(b)) for a in 1:3, b in 1:3]   # x_a e_b
    Mtr = [fe.M * trv[a] for a in 1:3]
    r.mass = dot(trv[1], Mtr[1])
    r.S0 = [dot(lin[a, 1], Mtr[1]) for a in 1:3]
    Σ = [dot(lin[a, 1], fe.M * lin[b, 1]) for a in 1:3, b in 1:3]
    r.J0 = _sym(tr(Σ) * Matrix{Float64}(I, 3, 3) - Σ)
    MΦ = fe.M * Φ
    r.St = [dot(trv[a], MΦ[:, k]) for a in 1:3, k in 1:nm]
    r.Sr = [dot(rot[a], MΦ[:, k]) for a in 1:3, k in 1:nm]
    r.J1 = zeros(6, nm)
    for k in 1:nm
        Λ = [dot(lin[a, b], MΦ[:, k]) for a in 1:3, b in 1:3]    # int rho x_a phi_b
        J1 = 2tr(Λ) * Matrix{Float64}(I, 3, 3) - Λ - Λ'
        for (c6, (a, b)) in enumerate(COMP6)
            r.J1[c6, k] = J1[a, b]
        end
    end
    Ms = scalar_mass(fe)
    Φc = [Φ[fe.nodedofs[a, :], :] for a in 1:3]
    r.E = [Φc[a]' * (Ms * Φc[b]) for (a, b) in COMP6]
    for c6 in 1:3
        r.E[c6] = _sym(r.E[c6])
    end
    # ---- interface mode values ----
    r.PT = Matrix{Float64}[]
    r.PR = Matrix{Float64}[]
    for (j, f) in enumerate(ifs)
        if j == 1
            push!(r.PT, zeros(3, nm))
            push!(r.PR, zeros(3, nm))
        else
            rows = nfree + 6(j - 2) .+ (1:6)
            push!(r.PT, Y[rows[1:3], :])
            push!(r.PR, f.rotation' * Y[rows[4:6], :])
        end
    end
    # ---- geometric stiffening ----
    if stiffening
        t1 = time()
        Fc = cholesky(Symmetric(Kc))
        loads = Vector{Vector{Float64}}()
        for a in 1:3
            push!(loads, Tc' * (fe.M * trv[a]))
        end
        for (a, b) in COMP6
            g = _field(fe, x -> (a == b ? 2 .* x : zeros(3)) .- x[a] .* _e(b) .- x[b] .* _e(a))
            push!(loads, Tc' * (fe.M * g))
        end
        for a in 1:3
            push!(loads, Tc' * (fe.M * rot[a]))
        end
        for j in 2:ni, a in 1:3
            f = zeros(length(c))
            f[nfree + 6(j - 2) + a] = 1.0
            push!(loads, f)
        end
        disps = [Tc * (Fc \ f) for f in loads]
        G = geometric_projection(fe, Φ, disps)
        G = [_sym(g) for g in G]
        stiff = Dict{String,Vector{Matrix{Float64}}}(
            "translation" => G[1:3], "inertia" => G[4:9], "rotation" => G[10:12])
        stiff["interface_force"] = G[13:end]
        r.stiffening = stiff
        timings["stiffening"] = time() - t1
    end
    timings["total"] = time() - t0
    r.timings = timings
    r.validation["cb"] = Dict{String,Any}("fixed_interface_hz" => sqrt.(max.(λf, 0.0)) ./ 2pi,
        "first_discarded_fixed_interface_hz" => first_discarded_hz,
        "constraint_modes" => nb, "load_modes" => nl, "dropped" => size(F.vectors, 2) - nm)
    return r, (T = T, Kt = Kt, Mt = Mt, nfree = nfree, c = c, Y = Y)
end

"""
    linearized_free(r) -> (M, K) of the floating-frame model at rest

The frame twist V = (omega, v) and the modal coordinates: M = [M_VV C'; C diag(m)],
K = diag(0, k). Its eigenvalues are the free-free frequencies of the reduced body."""
function linearized_free(r::ReducedModel)
    nm = r.nm
    S = r.S0
    Sx = [0 -S[3] S[2]; S[3] 0 -S[1]; -S[2] S[1] 0]
    MVV = [r.J0 Sx; Sx' r.mass*I]
    C = vcat(r.Sr, r.St)'                       # nm x 6
    M = [MVV C'; C Diagonal(r.mk)]
    K = zeros(6 + nm, 6 + nm)
    for k in 1:nm
        K[6 + k, 6 + k] = r.kk[k]
    end
    return M, K
end

"""
    validate!(r, fe, aux; nmodes = 6) -> Dict

Reduced against full FE eigenfrequencies (Hz) for the first `nmodes` elastic modes:

* `clamped`: interface 1 clamped, the other interfaces free (rigid spiders) — the reduced
  values are the diagonal modal frequencies sqrt(k/m);
* `free`: all interfaces free — the reduced values come from the linearised floating-frame
  model (`linearized_free`), which also checks the inertia invariants."""
function validate!(r::ReducedModel, aux; nmodes::Integer = 6)
    c = aux.c
    Kc = aux.Kt[c, c]
    Mc = aux.Mt[c, c]
    n = nmodes
    band = _band(r)
    λ, _ = _lowest_modes(Kc, Mc, n)
    full_c = sqrt.(max.(λ, 0.0)) ./ 2pi
    red_all_c = sort(frequencies_hz(r))
    λf, _ = _lowest_modes(aux.Kt, aux.Mt, n + 6; sigma = -1.0)
    full_f = sqrt.(max.(λf[7:end], 0.0)) ./ 2pi
    rigid_f = sqrt.(abs.(λf[1:6])) ./ 2pi
    M, K = linearized_free(r)
    ev = sort(real.(eigvals(K, M)))
    red_all_f = sqrt.(max.(ev[7:end], 0.0)) ./ 2pi
    out = Dict{String,Any}(
        "band_hz" => band,
        "clamped" => _compare(full_c, red_all_c, band),
        "free" => merge(_compare(full_f, red_all_f, band), Dict("full_rigid_hz_max" => maximum(rigid_f))))
    r.validation["frequencies"] = out
    return out
end

"""Mass matrix of a rigid body (mass `m`, inertia `J` about its centre of mass, centre of mass
at `c` from the interface origin; all in R) on the interface dofs (u, theta)."""
function attached_mass_matrix(m::Real, J::AbstractMatrix, c::AbstractVector)
    cx = [0 -c[3] c[2]; c[3] 0 -c[1]; -c[2] c[1] 0]
    return [m*I(3) -m*cx; m*cx J - m*cx*cx]
end

"""
    validate_attached!(r, aux, attach; nmodes = 4) -> Dict

The body clamped at interface 1 with rigid bodies attached at other interfaces (a payload):
the full FE eigenfrequencies against the reduced model's. `attach` is a list of
`(interface = j, mass, inertia (3x3 about the CoM, in R), com (offset from the interface
origin, in R))`. This is the configuration of a part in a mechanism, so it checks the
constraint modes (the static correction) where it matters."""
function validate_attached!(r::ReducedModel, aux, attach; nmodes::Integer = 4)
    c = aux.c
    nfree = aux.nfree
    Kc = aux.Kt[c, c]
    Mc = copy(aux.Mt[c, c])
    Mred = Matrix(Diagonal(r.mk))
    for a in attach
        j = a.interface
        2 <= j <= length(r.interfaces) || throw(ArgumentError("attach: interface $j is not one of 2..$(length(r.interfaces))"))
        Mb = attached_mass_matrix(a.mass, a.inertia, a.com)
        rows = nfree + 6(j - 2) .+ (1:6)
        Mc[rows, rows] .+= Mb
        P = vcat(r.PT[j], r.interfaces[j].rotation * r.PR[j])   # (u, theta) per mode, in R
        Mred .+= P' * Mb * P
    end
    λ, _ = _lowest_modes(Kc, _sym(Mc), nmodes)
    full = sqrt.(max.(λ, 0.0)) ./ 2pi
    ev = sort(real.(eigvals(Symmetric(Matrix(Diagonal(r.kk))), Symmetric(_sym(Mred)))))
    red = sqrt.(max.(ev, 0.0)) ./ 2pi
    band = _band(r)
    out = _compare(full, red, band)
    out["attached"] = [Dict{String,Any}("interface" => r.interfaces[a.interface].name, "mass" => a.mass,
        "inertia" => _rows(Matrix{Float64}(a.inertia)), "com" => collect(Float64, a.com)) for a in attach]
    r.validation["attached"] = out
    return out
end

# The band in which the reduced model is expected to be accurate: 80 % of the first discarded
# fixed-interface frequency (a free mode just below that frequency needs the discarded mode).
_band(r::ReducedModel) =
    0.8 * get(get(r.validation, "cb", Dict()), "first_discarded_fixed_interface_hz", Inf)

# Each full FE frequency against the nearest unused reduced one; the reduced model is expected
# to be accurate below `band`.
function _compare(full, reduced, band)
    used = falses(length(reduced))
    red = Float64[]
    for f in full
        cand = [k for k in eachindex(reduced) if !used[k]]
        if isempty(cand)
            push!(red, NaN)
            continue
        end
        k = cand[argmin(abs.(reduced[cand] .- f))]
        used[k] = true
        push!(red, reduced[k])
    end
    err = red ./ full .- 1
    inb = [f < band for f in full]
    return Dict{String,Any}("full_hz" => full, "reduced_hz" => red, "rel_error" => err,
        "in_band" => inb,
        "max_rel_error_in_band" => any(inb) ? maximum(abs.(err[inb])) : NaN)
end
