# Linear-elastic solid finite elements (Ferrite): stiffness K and consistent mass M of an
# isotropic material on ten-node (or four-node) tetrahedra, the scalar (per-component) mass
# matrix, stresses of a displacement field and the projection of geometric (initial-stress)
# stiffness matrices onto a set of modes.
#
# Degrees of freedom: Ferrite's vector Lagrange field `u` (3 components per node). `nodedofs`
# maps a grid node to its three global dofs, so nodal fields (rigid motions, linear fields,
# mode shapes) can be written as dof vectors and back.

"""
    Material(E, nu, rho)

Isotropic linear-elastic material: Young's modulus (Pa), Poisson ratio, density (kg/m^3)."""
struct Material
    E::Float64
    nu::Float64
    rho::Float64
end

lame(m::Material) = (m.E * m.nu / ((1 + m.nu) * (1 - 2m.nu)), m.E / (2 * (1 + m.nu)))

function elasticity_tensor(m::Material)
    λ, μ = lame(m)
    δ(i, j) = i == j ? 1.0 : 0.0
    return SymmetricTensor{4,3}((i, j, k, l) -> λ * δ(i, j) * δ(k, l) + μ * (δ(i, k) * δ(j, l) + δ(i, l) * δ(j, k)))
end

"""
    FEModel

The assembled finite element model: grid, dof handler, node coordinates `X` (3 x nn),
`nodedofs` (3 x nn global dofs), stiffness `K`, mass `M` (both ndofs x ndofs) and the
material."""
struct FEModel
    grid::Grid
    dh::DofHandler
    X::Matrix{Float64}
    nodedofs::Matrix{Int}
    K::SparseMatrixCSC{Float64,Int}
    M::SparseMatrixCSC{Float64,Int}
    material::Material
    order::Int
end

ndofs_fe(fe::FEModel) = ndofs(fe.dh)
nnodes_fe(fe::FEModel) = size(fe.X, 2)

function _interp(grid::Grid)
    c = getcells(grid, 1)
    return c isa QuadraticTetrahedron ? (Lagrange{RefTetrahedron,2}(), 2) : (Lagrange{RefTetrahedron,1}(), 1)
end

_cellvalues(grid::Grid, qorder::Int) = begin
    ip, _ = _interp(grid)
    CellValues(QuadratureRule{RefTetrahedron}(qorder), ip^3, ip)
end

"""
    assemble(grid, material) -> FEModel

Assemble K (exact for straight-sided quadratic tetrahedra with the 4-point rule) and the
consistent mass M (4th-order rule)."""
function assemble(grid::Grid, material::Material)
    ip, order = _interp(grid)
    dh = DofHandler(grid)
    add!(dh, :u, ip^3)
    close!(dh)
    nn = getnnodes(grid)
    nodedofs = zeros(Int, 3, nn)
    nb = getnbasefunctions(ip)
    for ci in 1:getncells(grid)
        cd = celldofs(dh, ci)
        nodes = getcells(grid, ci).nodes
        for j in 1:nb
            for a in 1:3
                nodedofs[a, nodes[j]] = cd[3(j - 1) + a]
            end
        end
    end
    any(==(0), nodedofs) && error("a node of the grid has no dofs")
    C = elasticity_tensor(material)
    cvk = _cellvalues(grid, 2 * order - 2 == 0 ? 1 : 2 * (order - 1))
    cvm = _cellvalues(grid, 2 * order)
    K = allocate_matrix(dh)
    M = allocate_matrix(dh)
    n = ndofs_per_cell(dh)
    Ke = zeros(n, n)
    Me = zeros(n, n)
    ak = start_assemble(K)
    am = start_assemble(M)
    epsj = Vector{SymmetricTensor{2,3,Float64,6}}(undef, n)
    for cell in CellIterator(dh)
        fill!(Ke, 0.0)
        fill!(Me, 0.0)
        reinit!(cvk, cell)
        reinit!(cvm, cell)
        for qp in 1:getnquadpoints(cvk)
            dΩ = getdetJdV(cvk, qp)
            for j in 1:n
                epsj[j] = shape_symmetric_gradient(cvk, qp, j)
            end
            for i in 1:n
                σi = C ⊡ epsj[i]
                for j in i:n
                    Ke[i, j] += (σi ⊡ epsj[j]) * dΩ
                end
            end
        end
        for qp in 1:getnquadpoints(cvm)
            dΩ = getdetJdV(cvm, qp) * material.rho
            for i in 1:n
                Ni = shape_value(cvm, qp, i)
                for j in i:n
                    Me[i, j] += (Ni ⋅ shape_value(cvm, qp, j)) * dΩ
                end
            end
        end
        for i in 1:n, j in 1:(i - 1)
            Ke[i, j] = Ke[j, i]
            Me[i, j] = Me[j, i]
        end
        assemble!(ak, celldofs(cell), Ke)
        assemble!(am, celldofs(cell), Me)
    end
    return FEModel(grid, dh, node_coordinates(grid), nodedofs, K, M, material, order)
end

"""Nodal field (3 x nn) to a dof vector."""
function nodal_to_dofs(fe::FEModel, U::AbstractMatrix)
    u = zeros(ndofs_fe(fe))
    for i in axes(U, 2), a in 1:3
        u[fe.nodedofs[a, i]] = U[a, i]
    end
    return u
end

"""Dof vector to a nodal field (3 x nn)."""
function dofs_to_nodal(fe::FEModel, u::AbstractVector)
    U = zeros(3, nnodes_fe(fe))
    for i in axes(U, 2), a in 1:3
        U[a, i] = u[fe.nodedofs[a, i]]
    end
    return U
end

"""The scalar (per-component) mass matrix over the nodes: M = Ms (x) I3 in node order."""
function scalar_mass(fe::FEModel)
    xd = fe.nodedofs[1, :]
    return fe.M[xd, xd]
end

function _cell_gradients!(out, cv, ue)
    for qp in 1:getnquadpoints(cv)
        out[qp] = function_gradient(cv, qp, ue)
    end
    return out
end

"""
    geometric_projection(fe, modes, displacements) -> Vector{Matrix}

For every static displacement field `displacements[c]` (dof vectors), the geometric
(initial-stress) stiffness of its stress state projected onto the columns of `modes`
(ndofs x nm):

    G_c[k, l] = int sigma_c : (grad phi_k^T grad phi_l) dV,

i.e. `modes' * K_sigma(sigma_c) * modes` without forming K_sigma. Symmetric."""
function geometric_projection(fe::FEModel, modes::AbstractMatrix, displacements::AbstractVector)
    C = elasticity_tensor(fe.material)
    nm = size(modes, 2)
    nc = length(displacements)
    cv = _cellvalues(fe.grid, 2 * fe.order - 2 == 0 ? 1 : 2 * (fe.order - 1))
    nq = getnquadpoints(cv)
    G = [zeros(nm, nm) for _ in 1:nc]
    H = [Vector{Tensor{2,3,Float64,9}}(undef, nq) for _ in 1:nm]
    S = [Vector{SymmetricTensor{2,3,Float64,6}}(undef, nq) for _ in 1:nc]
    n = ndofs_per_cell(fe.dh)
    ue = zeros(n)
    for cell in CellIterator(fe.dh)
        reinit!(cv, cell)
        cd = celldofs(cell)
        for k in 1:nm
            for i in 1:n
                ue[i] = modes[cd[i], k]
            end
            _cell_gradients!(H[k], cv, ue)
        end
        for c in 1:nc
            for i in 1:n
                ue[i] = displacements[c][cd[i]]
            end
            for qp in 1:nq
                S[c][qp] = C ⊡ symmetric(function_gradient(cv, qp, ue))
            end
        end
        for qp in 1:nq
            dΩ = getdetJdV(cv, qp)
            for k in 1:nm
                Hk = H[k][qp]
                for l in k:nm
                    A = transpose(Hk) ⋅ H[l][qp]     # A[m, n] = sum_i dphi_k,i/dx_m dphi_l,i/dx_n
                    As = symmetric(A)
                    for c in 1:nc
                        G[c][k, l] += (S[c][qp] ⊡ As) * dΩ
                    end
                end
            end
        end
    end
    for c in 1:nc, k in 1:nm, l in 1:(k - 1)
        G[c][k, l] = G[c][l, k]
    end
    return G
end

# ---------------------------------------------------------------------------------------
# Stress recovery
# ---------------------------------------------------------------------------------------

"""
    nodal_stress(fe, U) -> Vector{Matrix{Float64}}

The stress field of every column of `U` (dof vectors, e.g. the mode shapes) at the grid nodes,
by element-wise recovery and averaging: in each cell the stress `C : sym(grad u)` is evaluated
at the cell's own nodes (for ten-node tetrahedra the strain is linear in the cell, so this is
the cell's exact stress there), then every node takes the plain mean over the cells that share
it. Returns one `6 x nn` matrix per column, components xx yy zz xy xz yz (Pa per unit of the
column). Linear in `U`, so the stress of a superposition is the superposition of the stresses."""
function nodal_stress(fe::FEModel, U::AbstractMatrix)
    ip, _ = _interp(fe.grid)
    refc = Ferrite.reference_coordinates(ip)
    nb = length(refc)
    qr = QuadratureRule{RefTetrahedron}(fill(1.0 / nb, nb), refc)
    cv = CellValues(qr, ip^3, ip)
    C = elasticity_tensor(fe.material)
    nn = nnodes_fe(fe)
    ncol = size(U, 2)
    S = [zeros(6, nn) for _ in 1:ncol]
    count = zeros(Int, nn)
    n = ndofs_per_cell(fe.dh)
    ue = zeros(n)
    for cell in CellIterator(fe.dh)
        reinit!(cv, cell)
        cd = celldofs(cell)
        nodes = getnodes(cell)
        for j in 1:nb
            count[nodes[j]] += 1
        end
        for k in 1:ncol
            Sk = S[k]
            for i in 1:n
                ue[i] = U[cd[i], k]
            end
            for j in 1:nb
                σ = C ⊡ function_symmetric_gradient(cv, j, ue)
                m = nodes[j]
                Sk[1, m] += σ[1, 1]
                Sk[2, m] += σ[2, 2]
                Sk[3, m] += σ[3, 3]
                Sk[4, m] += σ[1, 2]
                Sk[5, m] += σ[1, 3]
                Sk[6, m] += σ[2, 3]
            end
        end
    end
    for k in 1:ncol, m in 1:nn
        count[m] > 0 || continue
        for c in 1:6
            S[k][c, m] /= count[m]
        end
    end
    return S
end

nodal_stress(fe::FEModel, u::AbstractVector) = nodal_stress(fe, reshape(u, :, 1))[1]

"""von Mises stress of the six components (xx yy zz xy xz yz)."""
von_mises(s) = sqrt(0.5 * ((s[1] - s[2])^2 + (s[2] - s[3])^2 + (s[3] - s[1])^2) +
                    3 * (s[4]^2 + s[5]^2 + s[6]^2))

"""von Mises per column of a `6 x n` stress matrix."""
von_mises_cols(S::AbstractMatrix) = [von_mises(view(S, :, i)) for i in axes(S, 2)]

"""The superposition `sum_k q_k S[k]` of per-mode stress fields (`6 x n` each)."""
function superpose(S::AbstractVector{<:AbstractMatrix}, q::AbstractVector)
    out = zeros(size(S[1]))
    for k in eachindex(S)
        q[k] == 0 && continue
        out .+= q[k] .* S[k]
    end
    return out
end
