# Flexible bodies, part 2: the assumed-modes beams `stdlib:spatial/FlexibleBeam3D` and
# `stdlib:planar/FlexibleBeam2D` on the real pipeline (`parse_model -> flatten -> simulate`).
#
#   * energy: a free spinning, vibrating 3D beam conserves T + V (no damping, no gravity), and
#     a flexible 3D pendulum (gravity, the G1 foreshortening field) conserves T + V + U_g;
#   * Southwell: a cantilever spun at Omega about an axis through its root has the flap
#     frequency w^2 = w0^2 + 1.193 Omega^2 and the lead-lag one w0^2 + 0.193 Omega^2
#     (centrifugal geometric stiffening, energy consistent);
#   * statics: a clamped beam with a tip force and torque converges to F L^3/(3 E I) and
#     T L/(G J) with the modal series 0.9707/0.9954/0.9986 and 0.811/0.901/0.933 for 1/2/3
#     modes; the planar beam under its own weight to q L^4/(8 E I);
#   * torsion: two disks on a slender shaft (the example `flex-torsion`): the first torsional
#     frequency equals the Ritz eigenvalue of the same truncated basis, and is compared with
#     the exact transcendental equation and the massless-shaft limit sqrt(k (J1 + J2)/(J1 J2));
#   * the composite: the structural constants reach the core (an inactive mode stays 0), the
#     free end B needs no connection, and the observables record at the composite path.
using Test
using BGSim
using LinearAlgebra

if !isdefined(@__MODULE__, :BondGraphGolden)
    include(joinpath(@__DIR__, "golden", "bondgraph", "golden_helpers.jl"))
end
using .BondGraphGolden

const FB_TAB = BGSim.Mech.beam_mode_tables(0)
_fbv(v) = "[" * join(string.(v), ", ") * "]"
_fbs(x) = string(x)

"""Steel rod (E 210 GPa, nu 0.3, rho 7850): area, second moments, mass, rigid inertias about A."""
function _fb_rod(; L = 1.0, d = 0.01, E = 2.1e11, rho = 7850.0, nu = 0.3)
    A = pi * d^2 / 4
    I = pi * d^4 / 64
    Ip = 2I
    m = rho * A * L
    return (; L, d, E, rho, nu, A, I, Ip, m, G = E / (2 * (1 + nu)), mt = rho * Ip * L,
        J0 = [rho * Ip * L, m * L^2 / 3 + rho * I * L, m * L^2 / 3 + rho * I * L])
end

"""Momenta of the straight (eta = 0) 3D beam for the frame twist `V` and modal rates."""
function _fb_momenta3(r, V, yd, zd, td)
    m, L = r.m, r.L
    S1 = m * L / 2
    MV = zeros(6, 6)
    MV[1, 1], MV[2, 2], MV[3, 3] = r.J0
    MV[2, 6] = MV[6, 2] = -S1
    MV[3, 5] = MV[5, 3] = S1
    MV[4, 4] = MV[5, 5] = MV[6, 6] = m
    Cy = [[0, 0, m * L * FB_TAB.b[i], 0, m * FB_TAB.a[i], 0] for i in 1:3]
    Cz = [[0, -m * L * FB_TAB.b[i], 0, 0, 0, m * FB_TAB.a[i]] for i in 1:3]
    Ct = [[r.mt * FB_TAB.at[i], 0, 0, 0, 0, 0] for i in 1:3]
    P = MV * V + sum(Cy[i] * yd[i] + Cz[i] * zd[i] + Ct[i] * td[i] for i in 1:3)
    py = [dot(Cy[i], V) + m * yd[i] for i in 1:3]
    pz = [dot(Cz[i], V) + m * zd[i] for i in 1:3]
    pt = [dot(Ct[i], V) + r.mt * td[i] for i in 1:3]
    return P, py, pz, pt
end

function _fb_beam3(id, name; r = _fb_rod(), n = (2, 2, 1), zeta = 0.0, g0 = 0.0, starts = Dict{String,Any}())
    node = bg_node(id, name, bg_ref("stdlib:spatial/FlexibleBeam3D");
        params = Dict{String,Any}("L" => _fbs(r.L), "d" => _fbs(r.d), "E" => _fbs(r.E), "rho" => _fbs(r.rho),
            "nu" => _fbs(r.nu), "g0" => _fbs(g0), "zeta_y" => _fbs(zeta), "zeta_z" => _fbs(zeta),
            "zeta_t" => _fbs(zeta)),
        starts = starts)
    node["constants"] = Dict{String,Any}("ny" => string(n[1]), "nz" => string(n[2]), "nt" => string(n[3]))
    return node
end

"""Mean angular frequency of a signal from its upward mean crossings."""
function _fb_freq(t, x)
    xm = x .- (maximum(x) + minimum(x)) / 2
    cr = Float64[]
    for i in 1:(length(x) - 1)
        if xm[i] < 0 && xm[i + 1] >= 0
            push!(cr, t[i] - xm[i] * (t[i + 1] - t[i]) / (xm[i + 1] - xm[i]))
        end
    end
    return 2pi * (length(cr) - 1) / (cr[end] - cr[1])
end

_fb_errors(flat) = [d for d in flat.diagnostics if d.severity == "error"]
_fb_drift(E) = (maximum(E) - minimum(E)) / maximum(abs.(E))

# ---- rigs ----------------------------------------------------------------------------------

"""A free 3D beam, no gravity: spinning about a skew axis and vibrating."""
function _fb_free3()
    r = _fb_rod()
    P, py, pz, pt = _fb_momenta3(r, [0.5, 2.0, -3.0, 0.2, 0.1, -0.3], [0.05, -0.02, 0.0],
        [-0.03, 0.01, 0.0], [0.5, 0.0, 0.0])
    beam = _fb_beam3("n1", "Beam"; r = r, n = (2, 2, 1),
        starts = Dict{String,Any}("beam/P" => _fbv(P), "beam/py" => _fbv(py), "beam/pz" => _fbv(pz),
            "beam/pth" => _fbv(pt)))
    nodes = Any[beam, bg_node("n2", "Mount", bg_ref("stdlib:spatial/LocalPose3D"))]
    conns = Any[bg_conn("c1", "signal", "n2", "g", "n1", "gA")]
    return bg_model("FlexFree3", nodes, conns; t_end = 0.05, points = 1001, reltol = 1e-10, abstol = 1e-12)
end

"""A flexible 3D pendulum: a compliant revolute (axis world y) at end A, released horizontal."""
function _fb_pendulum3(; n = (2, 2, 1), t_end = 0.6)
    r = _fb_rod()
    s2 = sqrt(0.5)
    kk = 1.0e8
    nodes = Any[
        bg_node("n1", "World", bg_ref("stdlib:multibond/GroundSpatial")),
        # the joint frame is Rx(90 deg) in the world (joint z = world -y); the mount carries
        # the inverse pose (ground on its `b` side, the joint on `a`, as in test_mech_spatial)
        bg_node("n2", "Axis", bg_ref("stdlib:multibond/FixedTransform3DNeutral");
            params = Dict{String,Any}("qw" => _fbs(s2), "qx" => _fbs(-s2))),
        bg_node("n3", "Hinge", bg_ref("stdlib:spatial/Revolute3D");
            params = Dict{String,Any}("kt" => _fbs(kk), "kr" => _fbs(kk))),
        _fb_beam3("n4", "Beam"; r = r, n = n, g0 = 9.81),
        bg_node("n5", "AxisPose", bg_ref("stdlib:spatial/LocalPose3D");
            params = Dict{String,Any}("qw" => _fbs(s2), "qx" => _fbs(s2))),
        bg_node("n6", "PoseA", bg_ref("stdlib:multibond/ComposePose3D")),
        bg_node("n7", "Free", bg_ref("stdlib:bondgraph/Se"); params = Dict{String,Any}("e" => "0.0")),
    ]
    conns = Any[
        bg_conn("c1", "bond", "n1", "p", "n2", "b"),
        bg_conn("c2", "bond", "n2", "a", "n3", "parent"),
        bg_conn("c3", "bond", "n3", "child", "n4", "A"),
        bg_conn("c4", "signal", "n5", "g", "n6", "gp"),
        bg_conn("c5", "signal", "n3", "pose", "n6", "gl"),
        bg_conn("c6", "signal", "n6", "g", "n4", "gA"),
        bg_conn("c7", "bond", "n7", "p", "n3", "drive"),
    ]
    return bg_model("FlexPendulum3", nodes, conns; t_end = t_end, points = 1201, reltol = 1e-10, abstol = 1e-12)
end

"""Southwell: a cantilever on a stiff hub driven at Omega (flywheel J = 1e4 through a stiff
coupling), released with 1 mm tip-ish deflection in both bending planes."""
function _fb_spin(Omega; y0 = 1e-3, z0 = 1e-3, t_end = 3.0)
    r = _fb_rod()
    m, L = r.m, r.L
    Q1 = m / L * FB_TAB.G1[1, 1] * (y0^2 + z0^2)
    Q2 = m * FB_TAB.G2[1, 1] * (y0^2 + z0^2)
    S1 = m * L / 2 - Q1 / 2
    S2 = m * FB_TAB.a[1] * y0
    P0 = [-m * L * FB_TAB.b[1] * z0, -m * y0 * z0, r.J0[3] - Q2 + m * y0^2, -S2, S1, 0.0] .* Omega
    py0 = [m * L * FB_TAB.b[1] * Omega, 0.0, 0.0]
    kk = 1.0e7
    nodes = Any[
        bg_node("n1", "World", bg_ref("stdlib:multibond/GroundSpatial")),
        bg_node("n2", "Hub", bg_ref("stdlib:spatial/Revolute3D");
            params = Dict{String,Any}("kt" => _fbs(kk), "kr" => _fbs(kk),
                "bt" => _fbs(2 * sqrt(kk * m)), "br" => _fbs(2 * sqrt(kk * m / 3)))),
        _fb_beam3("n3", "Beam"; r = r, n = (1, 1, 0),
            starts = Dict{String,Any}("beam/P" => _fbv(P0), "beam/py" => _fbv(py0),
                "beam/y" => _fbv([y0, 0.0, 0.0]), "beam/z" => _fbv([z0, 0.0, 0.0]))),
        bg_node("n4", "Ground", bg_ref("stdlib:rotation/FixedShaft")),
        bg_node("n5", "Flywheel", bg_ref("stdlib:rotation/Inertia"); params = Dict{String,Any}("J" => "1.0e4"),
            starts = Dict{String,Any}("w" => _fbs(-Omega))),
        bg_node("n6", "Coupling", bg_ref("stdlib:rotation/TorsionSpring"); params = Dict{String,Any}("k" => "1.0e6")),
        bg_node("n7", "Mount", bg_ref("stdlib:spatial/LocalPose3D")),
        bg_node("n8", "PoseA", bg_ref("stdlib:multibond/ComposePose3D")),
    ]
    conns = Any[
        bg_conn("c1", "bond", "n1", "p", "n2", "parent"),
        bg_conn("c2", "bond", "n2", "child", "n3", "A"),
        bg_conn("c3", "wire", "n4", "a", "n5", "a"),
        bg_conn("c4", "wire", "n5", "b", "n6", "a"),
        bg_conn("c5", "wire", "n6", "b", "n2", "drive"),
        bg_conn("c6", "signal", "n7", "g", "n8", "gp"),
        bg_conn("c7", "signal", "n2", "pose", "n8", "gl"),
        bg_conn("c8", "signal", "n8", "g", "n3", "gA"),
    ]
    return bg_model("FlexSpin", nodes, conns; t_end = t_end, points = 3001, reltol = 1e-9, abstol = 1e-12)
end

"""A clamped 3D beam (compliant CSpatial + RSpatial clamp at A) with a constant tip wrench
(torque `tx` about the axis, forces `fy`, `fz`) at B."""
function _fb_static3(n; tx = 0.02, fy = 0.3, fz = -0.5, t_end = 1.5)
    r = _fb_rod()
    k, b = 1.0e9, 1.0e4
    nodes = Any[
        _fb_beam3("n1", "Beam"; r = r, n = (n, n, n), zeta = 0.7),
        bg_node("n2", "Clamp", bg_ref("stdlib:multibond/CSpatial");
            params = Dict{String,Any}("krx" => _fbs(k), "kry" => _fbs(k), "krz" => _fbs(k),
                "kx" => _fbs(k), "ky" => _fbs(k), "kz" => _fbs(k))),
        bg_node("n3", "ClampR", bg_ref("stdlib:multibond/RSpatial");
            params = Dict{String,Any}("brx" => _fbs(b), "bry" => _fbs(b), "brz" => _fbs(b),
                "bx" => _fbs(b), "by" => _fbs(b), "bz" => _fbs(b))),
        bg_node("n4", "Load", bg_ref("stdlib:multibond/ExternalWrenchSpatial")),
        bg_node("n5", "Mount", bg_ref("stdlib:spatial/LocalPose3D")),
    ]
    conns = Any[
        bg_conn("c1", "bond", "n1", "A", "n2", "p"),
        bg_conn("c2", "bond", "n1", "A", "n3", "p"),
        bg_conn("c3", "bond", "n4", "p", "n1", "B"),    # source -> junction
        bg_conn("c4", "signal", "n5", "g", "n1", "gA"),
    ]
    for (i, (port, v)) in enumerate((("tx", tx), ("ty", 0.0), ("tz", 0.0), ("fx", 0.0), ("fy", fy), ("fz", fz)))
        push!(nodes, bg_node("k$i", "W$i", bg_ref("stdlib:sources/Constant"); params = Dict{String,Any}("value" => _fbs(v))))
        push!(conns, bg_conn("w$i", "signal", "k$i", "y", "n4", port))
    end
    return bg_model("FlexStatic3", nodes, conns; t_end = t_end, points = 301, reltol = 1e-9, abstol = 1e-13), r
end

"""A planar cantilever under its own weight (CPlanar + RPlanar clamp at A)."""
function _fb_static2(n; zeta = 0.3, t_end = 2.0)
    nodes = Any[
        bg_node("n1", "Beam", bg_ref("stdlib:planar/FlexibleBeam2D"); params = Dict{String,Any}("zeta_y" => _fbs(zeta))),
        bg_node("n2", "Clamp", bg_ref("stdlib:multibond/CPlanar");
            params = Dict{String,Any}("kr" => "1e7", "kx" => "1e9", "ky" => "1e9")),
        bg_node("n3", "ClampR", bg_ref("stdlib:multibond/RPlanar");
            params = Dict{String,Any}("br" => "1e3", "bx" => "1e4", "by" => "1e4")),
        bg_node("n4", "Mount", bg_ref("stdlib:planar/LocalPose2D")),
    ]
    nodes[1]["constants"] = Dict{String,Any}("ny" => string(n))
    conns = Any[
        bg_conn("c1", "bond", "n1", "A", "n2", "p"),
        bg_conn("c2", "bond", "n1", "A", "n3", "p"),
        bg_conn("c3", "signal", "n4", "g", "n1", "gA"),
    ]
    return bg_model("FlexStatic2", nodes, conns; t_end = t_end, points = 401, reltol = 1e-8, abstol = 1e-12)
end

"""A free planar beam, no gravity, spinning and vibrating (momenta of the straight beam)."""
function _fb_free2()
    r = _fb_rod()
    m, L = r.m, r.L
    V = [3.0, 0.2, -0.4]
    yd = [0.05, -0.02, 0.01]
    MV = [r.J0[3] 0 m*L/2; 0 m 0; m*L/2 0 m]
    Cy = [[m * L * FB_TAB.b[i], 0.0, m * FB_TAB.a[i]] for i in 1:3]
    P = MV * V + sum(Cy[i] * yd[i] for i in 1:3)
    py = [dot(Cy[i], V) + m * yd[i] for i in 1:3]
    nodes = Any[
        bg_node("n1", "Beam", bg_ref("stdlib:planar/FlexibleBeam2D");
            params = Dict{String,Any}("g0" => "0.0", "zeta_y" => "0.0"),
            starts = Dict{String,Any}("beam/P" => _fbv(P), "beam/py" => _fbv(py))),
        bg_node("n2", "Mount", bg_ref("stdlib:planar/LocalPose2D")),
    ]
    nodes[1]["constants"] = Dict{String,Any}("ny" => "3")
    conns = Any[bg_conn("c1", "signal", "n2", "g", "n1", "gA")]
    return bg_model("FlexFree2", nodes, conns; t_end = 0.2, points = 2001, reltol = 1e-10, abstol = 1e-12)
end

# ---- the two-disk torsion rig (the `flex-torsion` example, aluminium shaft, steel disks) ----

const FB_TOR = (rho = 2700.0, E = 70.0e9, nu = 0.33, d = 0.006, L = 1.0, R = 0.08, t = 0.02, rho_d = 7850.0)

function _fb_disk()
    m = FB_TOR.rho_d * pi * FB_TOR.R^2 * FB_TOR.t
    return (m = m, Jax = 0.5 * m * FB_TOR.R^2, Jt = 0.25 * m * FB_TOR.R^2 + m * FB_TOR.t^2 / 12)
end

"""Hanging shaft: World -> Bearing (Revolute3D, motor torque pulse on its drive) -> Disk1 ->
Weld1 (Revolute3D with a stiff torsion spring on its drive) -> Mount (x along world -z) ->
Shaft (FlexibleBeam3D, torsion only) -> Weld2 -> Disk2."""
function _fb_torsion(nt; T0 = 0.05, t_end = 3.0, kw = 1.0e5)
    dk = _fb_disk()
    kt, kr = 1.0e8, 1.0e5
    jp() = Dict{String,Any}("kt" => _fbs(kt), "kr" => _fbs(kr),
        "bt" => _fbs(2 * 0.05 * sqrt(kt * dk.m)), "br" => _fbs(2 * 0.05 * sqrt(kr * dk.Jt)))
    s2 = sqrt(0.5)
    shaft = bg_node("n6", "Shaft", bg_ref("stdlib:spatial/FlexibleBeam3D");
        params = Dict{String,Any}("L" => _fbs(FB_TOR.L), "d" => _fbs(FB_TOR.d), "E" => _fbs(FB_TOR.E),
            "nu" => _fbs(FB_TOR.nu), "rho" => _fbs(FB_TOR.rho), "zeta_t" => "0.002"))
    shaft["constants"] = Dict{String,Any}("ny" => "0", "nz" => "0", "nt" => string(nt))
    nodes = Any[
        bg_node("n1", "World", bg_ref("stdlib:multibond/GroundSpatial")),
        bg_node("n2", "Bearing", bg_ref("stdlib:spatial/Revolute3D"); params = jp()),
        bg_node("n3", "Disk1", bg_ref("stdlib:spatial/RigidBody3D");
            params = Dict{String,Any}("m" => _fbs(dk.m), "J" => _fbv([dk.Jt, dk.Jt, dk.Jax]))),
        bg_node("n4", "Weld1", bg_ref("stdlib:spatial/Revolute3D"); params = jp()),
        bg_node("n5", "Mount", bg_ref("stdlib:multibond/FixedTransform3DNeutral");
            params = Dict{String,Any}("qw" => _fbs(s2), "qy" => _fbs(s2))),
        shaft,
        bg_node("n7", "Weld2", bg_ref("stdlib:spatial/Revolute3D"); params = jp()),
        bg_node("n8", "Disk2", bg_ref("stdlib:spatial/RigidBody3D");
            params = Dict{String,Any}("m" => _fbs(dk.m), "J" => _fbv([dk.Jax, dk.Jt, dk.Jt]))),
        bg_node("n9", "Ground", bg_ref("stdlib:rotation/FixedShaft")),
        bg_node("n10", "Motor", bg_ref("stdlib:rotation/TorqueSource"); params = Dict{String,Any}("T" => _fbs(T0))),
        bg_node("n11", "Pulse", bg_ref("stdlib:sources/Pulse");
            params = Dict{String,Any}("amplitude" => "1.0", "period" => "1000.0", "duty" => "0.0001", "t_start" => "0.05")),
        bg_node("n12", "Ground1", bg_ref("stdlib:rotation/FixedShaft")),
        bg_node("n13", "WeldSpring1", bg_ref("stdlib:rotation/TorsionSpring"); params = Dict{String,Any}("k" => _fbs(kw))),
        bg_node("n14", "Ground2", bg_ref("stdlib:rotation/FixedShaft")),
        bg_node("n15", "WeldSpring2", bg_ref("stdlib:rotation/TorsionSpring"); params = Dict{String,Any}("k" => _fbs(kw))),
        bg_node("n20", "Origin", bg_ref("stdlib:spatial/LocalPose3D")),
        bg_node("n21", "PDisk1", bg_ref("stdlib:multibond/ComposePose3D")),
        bg_node("n22", "PWeld1", bg_ref("stdlib:multibond/ComposePose3D")),
        bg_node("n23", "MountPose", bg_ref("stdlib:spatial/LocalPose3D");
            params = Dict{String,Any}("qw" => _fbs(s2), "qy" => _fbs(s2))),
        bg_node("n24", "PShaftA", bg_ref("stdlib:multibond/ComposePose3D")),
        bg_node("n25", "PDisk2", bg_ref("stdlib:multibond/ComposePose3D")),
    ]
    conns = Any[
        bg_conn("c1", "bond", "n1", "p", "n2", "parent"),
        bg_conn("c2", "bond", "n2", "child", "n3", "p"),
        bg_conn("c3", "bond", "n3", "p", "n4", "parent"),
        bg_conn("c4", "bond", "n4", "child", "n5", "a"),
        bg_conn("c5", "bond", "n5", "b", "n6", "A"),
        bg_conn("c6", "bond", "n6", "B", "n7", "parent"),
        bg_conn("c7", "bond", "n7", "child", "n8", "p"),
        bg_conn("c8", "wire", "n9", "a", "n10", "a"),
        bg_conn("c9", "wire", "n10", "b", "n2", "drive"),
        bg_conn("c10", "signal", "n11", "y", "n10", "u"),
        bg_conn("c11", "wire", "n12", "a", "n13", "a"),
        bg_conn("c12", "wire", "n13", "b", "n4", "drive"),
        bg_conn("c13", "wire", "n14", "a", "n15", "a"),
        bg_conn("c14", "wire", "n15", "b", "n7", "drive"),
        bg_conn("c20", "signal", "n20", "g", "n21", "gp"),
        bg_conn("c21", "signal", "n2", "pose", "n21", "gl"),
        bg_conn("c22", "signal", "n21", "g", "n3", "g"),
        bg_conn("c23", "signal", "n21", "g", "n22", "gp"),
        bg_conn("c24", "signal", "n4", "pose", "n22", "gl"),
        bg_conn("c25", "signal", "n22", "g", "n24", "gp"),
        bg_conn("c26", "signal", "n23", "g", "n24", "gl"),
        bg_conn("c27", "signal", "n24", "g", "n6", "gA"),
        bg_conn("c28", "signal", "n6", "poseB", "n25", "gp"),
        bg_conn("c29", "signal", "n7", "pose", "n25", "gl"),
        bg_conn("c30", "signal", "n25", "g", "n8", "g"),
    ]
    return bg_model("FlexTorsion", nodes, conns; t_end = t_end, points = 6001, reltol = 1e-8, abstol = 1e-11)
end

"""The first torsional frequency of the two-disk shaft: the Ritz eigenvalue of `nt`
clamped-free torsion modes plus the rigid rotation (disk 1 at A, disk 2 at B), the exact root
of `(mu1 + mu2) z cos z + (1 - mu1 mu2 z^2) sin z = 0` (z = w L / c, mu = J_disk / J_shaft) and
the massless-shaft limit `sqrt(k (J1 + J2) / (J1 J2))`, `k = G J_t / L`."""
function _fb_torsion_refs(nt)
    dk = _fb_disk()
    G = FB_TOR.E / (2 * (1 + FB_TOR.nu))
    Ip = pi * FB_TOR.d^4 / 32
    Js = FB_TOR.rho * Ip * FB_TOR.L
    k = G * Ip / FB_TOR.L
    c = sqrt(G / FB_TOR.rho)
    mu = dk.Jax / Js
    t = BGSim.Mech.beam_mode_tables(0)
    M = zeros(nt + 1, nt + 1)
    K = zeros(nt + 1, nt + 1)
    M[1, 1] = 2mu + 1
    for i in 1:nt
        M[1, i + 1] = M[i + 1, 1] = t.at[i] + mu * t.psi0[i] + mu * t.psiL[i]
        for j in 1:nt
            M[i + 1, j + 1] = (i == j) + mu * t.psi0[i] * t.psi0[j] + mu * t.psiL[i] * t.psiL[j]
        end
        K[i + 1, i + 1] = (t.k[i] * pi)^2
    end
    ritz = sqrt(minimum(filter(>(1e-9), eigvals(Symmetric(K), Symmetric(M))))) * c / FB_TOR.L
    f(z) = 2mu * z * cos(z) + (1 - mu^2 * z^2) * sin(z)
    a, b = 1e-9, pi - 1e-9
    zs = range(a, b; length = 200001)
    i = findfirst(j -> sign(f(zs[j])) != sign(f(zs[j + 1])), 1:(length(zs) - 1))
    a, b = zs[i], zs[i + 1]
    for _ in 1:200
        mid = (a + b) / 2
        sign(f(mid)) == sign(f(a)) ? (a = mid) : (b = mid)
    end
    return (ritz = ritz, exact = (a + b) / 2 * c / FB_TOR.L, massless = sqrt(2k / dk.Jax), mu = mu)
end

# ---- tests ---------------------------------------------------------------------------------

@testset "flexible bodies: beam dynamics" begin
    @testset "free 3D beam: energy, observables, free ends" begin
        cols, res, flat = bg_run(_fb_free3())
        @test isempty(_fb_errors(flat))
        @test !any(d -> d.code == "E101", flat.diagnostics)      # both ends open
        @test res.status == "done"
        for k in ("Beam/pose[1]", "Beam/poseB[7]", "Beam/V[6]", "Beam/eta_y[1]", "Beam/eta_z[2]",
            "Beam/eta_t[1]", "Beam/f_y[3]", "Beam/f_t[1]", "Beam/twist", "Beam/dB[3]", "Beam/Ek")
            @test haskey(cols, k)
        end
        # the constants reach the core: nt = 1, so the second torsion mode never moves
        @test all(==(0.0), cols["Beam/eta_t[2]"])
        @test all(==(0.0), cols["Beam/eta_y[3]"])
        @test maximum(abs.(cols["Beam/eta_y[1]"])) > 1e-5
        E = cols["Beam/Ek"] .+ cols["Beam/Ee"]
        @test _fb_drift(E) < 1e-6
        # the free eigenfrequencies of the clamped-free basis
        r = _fb_rod()
        w1 = BGSim.Mech.bending_omega(0, 1; E = r.E, I = r.I, rho = r.rho, A = r.A, L = r.L)
        @test cols["Beam/f_y[1]"][1] ≈ w1 / 2pi rtol = 1e-9
        wt = BGSim.Mech.torsion_omega(0, 1; G = r.G, Jt = r.Ip, rho = r.rho, Ip = r.Ip, L = r.L)
        @test cols["Beam/f_t[1]"][1] ≈ wt / 2pi rtol = 1e-9
    end

    @testset "flexible 3D pendulum: T + V + U_g conserved" begin
        cols, res, flat = bg_run(_fb_pendulum3())
        @test res.status == "done"
        E = cols["Beam/Ek"] .+ cols["Beam/Ee"] .+ cols["Beam/Eg"]
        swing = maximum(cols["Beam/Ek"])
        @test swing > 1.0                                   # it really fell
        @test maximum(abs.(cols["Beam/eta_y[1]"])) > 1e-4    # and bent (local y = world z)
        @test (maximum(E) - minimum(E)) / swing < 1e-5
    end

    @testset "Southwell: centrifugal stiffening of a spinning cantilever" begin
        cols0, res0, _ = bg_run(_fb_spin(0.0))
        cols, res, _ = bg_run(_fb_spin(30.0))
        @test res0.status == "done" && res.status == "done"
        w0 = 2pi * cols["Beam/f_y[1]"][1]
        t = cols["time"]
        @test _fb_freq(cols0["time"], cols0["Beam/eta_z[1]"]) ≈ w0 rtol = 2e-3
        @test minimum(cols["Beam/V[3]"]) > 29.99 && maximum(cols["Beam/V[3]"]) < 30.01
        flap = (_fb_freq(t, cols["Beam/eta_z[1]"])^2 - w0^2) / 30.0^2
        lag = (_fb_freq(t, cols["Beam/eta_y[1]"])^2 - w0^2) / 30.0^2
        @info "Southwell coefficients" flap lag
        @test flap ≈ FB_TAB.G2[1, 1] rtol = 0.01               # 1.193
        @test lag ≈ FB_TAB.G2[1, 1] - 1 rtol = 0.03            # 0.193
    end

    @testset "3D statics: tip force and torque converge with the modal series" begin
        for n in 1:3
            doc, r = _fb_static3(n)
            cols, res, _ = bg_run(doc)
            @test res.status == "done"
            t = BGSim.Mech.beam_mode_tables(0)
            series = sum(t.phiL[i]^2 / t.lambda[i]^4 for i in 1:n) * 3     # fraction of F L^3/(3 E I)
            tseries = sum(t.psiL[i]^2 / (t.k[i] * pi)^2 for i in 1:n)       # fraction of T L/(G J)
            EI = r.E * r.I
            dy = cols["Beam/dB[2]"][end]
            dz = cols["Beam/dB[3]"][end]
            tw = cols["Beam/twist"][end]
            @info "static n=$n" dy / (0.3 / (3EI)) dz / (-0.5 / (3EI)) tw / (0.02 / (r.G * r.Ip))
            @test dy ≈ 0.3 * r.L^3 / (3EI) * series rtol = 2e-3
            @test dz ≈ -0.5 * r.L^3 / (3EI) * series rtol = 2e-3
            @test tw ≈ 0.02 * r.L / (r.G * r.Ip) * tseries rtol = 2e-3
            n == 1 && @test series ≈ 0.9707 atol = 1e-4
            n == 3 && @test series ≈ 0.9986 atol = 1e-4
            n == 3 && @test tseries ≈ 0.9331 atol = 1e-4
        end
    end

    @testset "planar beam: free energy and the self-weight cantilever" begin
        cols, res, flat = bg_run(_fb_free2())
        @test res.status == "done"
        @test _fb_drift(cols["Beam/Ek"] .+ cols["Beam/Ee"]) < 1e-6
        r = _fb_rod()
        qL4 = r.rho * r.A * 9.81 * r.L^4 / (r.E * r.I)
        t = BGSim.Mech.beam_mode_tables(0)
        for n in 1:3
            cols, res, _ = bg_run(_fb_static2(n))
            @test res.status == "done"
            modal = -qL4 * sum(t.phiL[i] * t.a[i] / t.lambda[i]^4 for i in 1:n)
            @test cols["Beam/dB[2]"][end] ≈ modal rtol = 1e-6
            n == 3 && @test cols["Beam/dB[2]"][end] ≈ -qL4 / 8 rtol = 5e-4
        end
    end

    @testset "two disks on a torsion shaft: Ritz, transcendental, massless limit" begin
        for nt in (1, 3)
            ref = _fb_torsion_refs(nt)
            cols, res, _ = bg_run(_fb_torsion(nt))
            @test res.status == "done"
            t = cols["time"]
            sel = t .> 0.3
            w = _fb_freq(t[sel], cols["Shaft/twist"][sel])
            @info "torsion nt=$nt" w ref.ritz ref.exact ref.massless (w / ref.exact - 1)
            @test w ≈ ref.ritz rtol = 1e-3
            # the truncation error of the assumed modes for heavy end disks (mu ~ 3e4):
            # 11.1 % with one mode, 3.5 % with three
            @test ref.exact ≈ ref.massless rtol = 1e-4
            @test w / ref.exact - 1 ≈ (nt == 1 ? 0.1107 : 0.0352) atol = 2e-3
        end
        # a large twist (0.27 rad) keeps the frequency: the end rotation is exact in torsion
        cols, _, _ = bg_run(_fb_torsion(3; T0 = 1.0))
        t = cols["time"]
        sel = t .> 0.3
        @test maximum(abs.(cols["Shaft/twist"])) > 0.25
        @test _fb_freq(t[sel], cols["Shaft/twist"][sel]) ≈ _fb_torsion_refs(3).ritz rtol = 1e-3
    end
end
