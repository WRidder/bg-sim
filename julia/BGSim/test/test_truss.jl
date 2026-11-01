# Trusses: the pin-jointed bar blocks of `stdlib:planar` on the real pipeline
# (`parse_model -> flatten -> simulate`).
#
#   * the language features they rely on: `for` loops around `@events` entries (one event pair
#     per bar, `reinit(broken[k], 1.0)`), equation `if` on a constant folded at compile time
#     (the node supports), constant-matrix indices (`conn[k, 1]`), constant overrides bound in
#     declaration order (`nb` before `conn::Mat{nb,2}`);
#   * statics: a triangle of Bar2D/PinNode2D and the same triangle as one Truss2D settle to the
#     method-of-joints member forces and support reactions, whatever the bond directions;
#   * buckling: a Bar2D strut pushed by a ramp fails exactly at the Euler load and books the
#     strain energy it held in `Elost`;
#   * tension failure in Truss2D: a bar fails when its force passes fy A, only that bar, and the
#     energy balance `Ebal` stays constant through the failure;
#   * wheel-on-deck contact: a body dropped on a fixed deck settles on its tyres at m g / (2 k),
#     the contact damps, and the deck reactions carry the weight.
using Test
using BGSim

if !isdefined(@__MODULE__, :BondGraphGolden)
    include(joinpath(@__DIR__, "golden", "bondgraph", "golden_helpers.jl"))
end
using .BondGraphGolden

const TRUSS_BLOCKS = ["PointMass2D", "PinNode2D", "AxialBar2D", "Bar2D", "Truss2D", "MovingLoad2D",
    "DeckContact2D"]

function _tr_node(id, name, ref; params = Dict{String,Any}(), consts = Dict{String,Any}())
    n = bg_node(id, name, bg_ref(ref); params = params)
    isempty(consts) || (n["constants"] = consts)
    return n
end

function _tr_run(name, nodes, conns; t_end = 1.0, points = 201, reltol = 1.0e-8, abstol = 1.0e-10)
    m = bg_model(name, nodes, conns; t_end = t_end, points = points, reltol = reltol, abstol = abstol)
    cols, res, flat = bg_run(m)
    @test res.status == "done"
    return cols
end

const _TR_P = "stdlib:planar/"

@testset "trusses" begin
    @testset "the blocks check clean, in the planar mechanics group" begin
        blocks = Dict(b.ref => b for b in BGSim.Library.load_stdlib())
        for name in TRUSS_BLOCKS
            b = blocks[_TR_P * name]
            @test b.group == "Planar mechanics"
            @test isempty(check_block(b.ast))
            @test !isempty(b.description)
        end
        for name in ("PinNode2D", "Bar2D", "DeckContact2D", "PointMass2D", "AxialBar2D")
            b = blocks[_TR_P * name]
            @test b.interface.dimension == 2
            @test all(p -> haskey(p, :frame), b.interface.ports)
        end
    end

    @testset "language: event loops, static if, constant-matrix indices" begin
        src = """
        @block LoopEvents begin
            @constants begin
                n::Int = 2
                pick::Mat{2,2} = [1 2; 2 1]
                mode::Int = 1
            end
            @variables begin
                x::Vec{n} = [0.0, 0.0]
                hit::Vec{n} = [0.0, 0.0]
                y::Real
            end
            @equations begin
                for k in 1:n
                    ddt(x[k]) ~ k * 1.0
                    ddt(hit[k]) ~ 0.0
                end
                if mode == 1
                    y ~ x[pick[1, 2]]
                else
                    y ~ x[1] + 1.0
                end
            end
            @events begin
                for k in 1:n
                    x[k] > 0.5 => begin
                        reinit(hit[k], hit[k] + 1.0)
                        reinit(x[pick[k, 1]], 0.0)
                    end
                end
            end
        end
        """
        pb = BGSim.parse_block(src; filename = "LoopEvents.jl", ref = "inline:LoopEvents")
        evs = BGSim.events(pb)
        @test length(evs) == 1
        @test length(evs[1].loops) == 1
        # loop variables in the event condition, the reinit target index and a constant-matrix
        # index (`pick[k, 1]`, a Real matrix of whole numbers) all check clean
        errors = [d for d in check_block(pb) if d.severity == "error"]
        @test isempty(errors)
    end

    tri_nodes(bar, pin) = Any[
        _tr_node("A", "A", _TR_P * "PinNode2D"; params = Dict{String,Any}("m" => "10.0", "x0" => "0.0", "y0" => "0.0"),
            consts = Dict{String,Any}("support" => "1")),
        _tr_node("B", "B", _TR_P * "PinNode2D"; params = Dict{String,Any}("m" => "10.0", "x0" => "4.0", "y0" => "0.0"),
            consts = Dict{String,Any}("support" => "2")),
        _tr_node("C", "C", _TR_P * "PinNode2D"; params = Dict{String,Any}("m" => "1000.0", "x0" => "2.0", "y0" => "1.5")),
        _tr_node("b1", "AC", _TR_P * "Bar2D"; params = Dict{String,Any}("beta" => "0.002")),
        _tr_node("b2", "BC", _TR_P * "Bar2D"; params = Dict{String,Any}("beta" => "0.002")),
        _tr_node("b3", "AB", _TR_P * "Bar2D"; params = Dict{String,Any}("beta" => "0.002")),
    ]

    # method of joints for the triangle A(0,0) B(4,0) C(2,1.5) with 1000 kg at C and 10 kg at A
    # and B (a Bar2D's own mass belongs to the node masses; the Truss2D runs use rho = 0 to
    # match); the roller B carries no horizontal reaction. The static sag changes the geometry
    # by about 1e-4, hence the tolerance.
    g0 = 9.81
    WC = 1000.0 * g0
    NAC = -(WC / 2) / (1.5 / 2.5)                    # vertical equilibrium at C
    NAB = -NAC * (2.0 / 2.5)                         # horizontal equilibrium at B
    Wtot = 1020.0 * g0

    @testset "statics: Bar2D/PinNode2D triangle (both bond directions) and Truss2D" begin
        for flip in (false, true)
            conns = Any[
                bg_conn("c1", "bond", "A", "p", "b1", "a"), bg_conn("c2", "bond", "C", "p", "b1", "b"),
                flip ? bg_conn("c3", "bond", "b2", "a", "B", "p") : bg_conn("c3", "bond", "B", "p", "b2", "a"),
                bg_conn("c4", "bond", "C", "p", "b2", "b"),
                bg_conn("c5", "bond", "A", "p", "b3", "a"), bg_conn("c6", "bond", "b3", "b", "B", "p"),
                bg_conn("s1", "signal", "A", "g", "b1", "ga"), bg_conn("s2", "signal", "C", "g", "b1", "gb"),
                bg_conn("s3", "signal", "B", "g", "b2", "ga"), bg_conn("s4", "signal", "C", "g", "b2", "gb"),
                bg_conn("s5", "signal", "A", "g", "b3", "ga"), bg_conn("s6", "signal", "B", "g", "b3", "gb"),
            ]
            cols = _tr_run("triangle", tri_nodes(nothing, nothing), conns)
            @test cols["AC/N"][end] ≈ NAC rtol = 5.0e-4
            @test cols["BC/N"][end] ≈ NAC rtol = 5.0e-4
            @test cols["AB/N"][end] ≈ NAB rtol = 5.0e-4
            @test cols["A/R[2]"][end] + cols["B/R[2]"][end] ≈ Wtot rtol = 1.0e-6
            @test abs(cols["A/R[1]"][end]) < 1.0e-3 * Wtot
            @test cols["AC/broken"][end] == 0.0
        end

        nodes = Any[
            _tr_node("T", "Truss", _TR_P * "Truss2D"; params = Dict{String,Any}(
                    "xy" => "[0.0 0.0; 4.0 0.0; 2.0 1.5]", "mn" => "[10.0, 10.0, 1000.0]", "beta" => "0.002", "rho" => "0.0",
                    "A" => "[0.001, 0.001, 0.001]", "I" => "[1.0e-6, 1.0e-6, 1.0e-6]"),
                consts = Dict{String,Any}("nn" => "3", "nb" => "3", "conn" => "[1 3; 2 3; 1 2]",
                    "fix" => "[1 1; 0 1; 0 0]")),
            _tr_node("L", "Load", _TR_P * "MovingLoad2D"; params = Dict{String,Any}("P" => "0.0"),
                consts = Dict{String,Any}("nn" => "3", "nd" => "2")),
        ]
        conns = Any[bg_conn("s1", "signal", "T", "x", "L", "x"), bg_conn("s2", "signal", "L", "Fx", "T", "Fx"),
            bg_conn("s3", "signal", "L", "Fy", "T", "Fy")]
        cols = _tr_run("truss", nodes, conns)
        @test cols["Truss/N[1]"][end] ≈ NAC rtol = 5.0e-4
        @test cols["Truss/N[2]"][end] ≈ NAC rtol = 5.0e-4
        @test cols["Truss/N[3]"][end] ≈ NAB rtol = 5.0e-4
        @test cols["Truss/Ry[1]"][end] + cols["Truss/Ry[2]"][end] ≈ Wtot rtol = 1.0e-6
        @test abs(cols["Truss/Ebal"][end] - cols["Truss/Ebal"][1]) < 1.0e-6 * Wtot
        @test all(cols["Truss/failed[$k]"][end] == 0.0 for k in 1:3)
    end

    @testset "buckling: a Bar2D strut fails at the Euler load" begin
        E, A, I, L, slope = 2.1e11, 1.0e-3, 1.0e-8, 2.0, 1.0e5
        Pcr = pi^2 * E * I / L^2
        nodes = Any[
            _tr_node("A", "A", _TR_P * "PinNode2D"; params = Dict{String,Any}("m" => "1.0", "g0" => "0.0"),
                consts = Dict{String,Any}("support" => "1")),
            _tr_node("B", "B", _TR_P * "PinNode2D"; params = Dict{String,Any}("m" => "100.0", "x0" => "2.0", "g0" => "0.0"),
                consts = Dict{String,Any}("support" => "2")),
            _tr_node("S", "Strut", _TR_P * "Bar2D"; params = Dict{String,Any}("I" => "1.0e-8", "rho" => "0.0")),
            _tr_node("P", "Push", "stdlib:multibond/ExternalWrenchPlanar"),
            _tr_node("R", "Ramp", "stdlib:sources/Ramp"; params = Dict{String,Any}("slope" => "-1.0e5")),
            _tr_node("Z", "Zero", "stdlib:sources/Constant"; params = Dict{String,Any}("value" => "0.0")),
        ]
        conns = Any[
            bg_conn("c1", "bond", "A", "p", "S", "a"), bg_conn("c2", "bond", "S", "b", "B", "p"),
            bg_conn("c3", "bond", "P", "p", "B", "p"),
            bg_conn("s1", "signal", "A", "g", "S", "ga"), bg_conn("s2", "signal", "B", "g", "S", "gb"),
            bg_conn("s3", "signal", "R", "y", "P", "wx"), bg_conn("s4", "signal", "Z", "y", "P", "wr"),
            bg_conn("s5", "signal", "Z", "y", "P", "wy"),
        ]
        cols = _tr_run("strut", nodes, conns; t_end = 0.1, points = 2001)
        @test cols["Strut/Pcr"][end] ≈ Pcr rtol = 1.0e-9
        t = cols["time"]
        i = findfirst(>(0.5), cols["Strut/broken"])
        @test i !== nothing
        # the push is nearly quasi-static: the bar force lags the ramp by at most 1/omega of the
        # strut on the 100 kg node (about 1 ms); failure where the force reaches Pcr
        @test abs(t[i] - Pcr / slope) < sqrt(100.0 / (E * A / L))
        @test minimum(cols["Strut/N"]) ≈ -Pcr rtol = 1.0e-6
        @test abs(cols["Strut/N"][end]) < 1.0e-6
        @test cols["Strut/util"][i - 1] ≈ -1.0 atol = 0.01
        @test cols["Strut/Elost"][end] ≈ Pcr^2 * L / (2 * E * A) rtol = 1.0e-3
    end

    @testset "tension failure in Truss2D: only the weak bar, energy balance kept" begin
        # AB (bar 3) is thin: Ft = fy A = 3.55e8 * 1.5e-5 = 5325 N, below the static 6541 N
        Ft = 3.55e8 * 1.5e-5
        nodes = Any[
            _tr_node("T", "Truss", _TR_P * "Truss2D"; params = Dict{String,Any}(
                    "xy" => "[0.0 0.0; 4.0 0.0; 2.0 1.5]", "mn" => "[10.0, 10.0, 1000.0]", "rho" => "0.0",
                    "beta" => "0.0", "A" => "[0.001, 0.001, 1.5e-5]", "I" => "[1.0e-6, 1.0e-6, 1.0e-6]"),
                consts = Dict{String,Any}("nn" => "3", "nb" => "3", "conn" => "[1 3; 2 3; 1 2]",
                    "fix" => "[1 1; 0 1; 0 0]")),
            _tr_node("L", "Load", _TR_P * "MovingLoad2D"; params = Dict{String,Any}("P" => "0.0"),
                consts = Dict{String,Any}("nn" => "3", "nd" => "2")),
        ]
        conns = Any[bg_conn("s1", "signal", "T", "x", "L", "x"), bg_conn("s2", "signal", "L", "Fx", "T", "Fx"),
            bg_conn("s3", "signal", "L", "Fy", "T", "Fy")]
        cols = _tr_run("truss-fail", nodes, conns; t_end = 0.05, points = 2001)
        @test cols["Truss/failed[3]"][end] == 1.0
        @test cols["Truss/failed[1]"][end] == 0.0
        @test cols["Truss/failed[2]"][end] == 0.0
        @test maximum(cols["Truss/N[3]"]) ≈ Ft rtol = 1.0e-3
        L0 = 4.0
        @test cols["Truss/Elost"][end] ≈ Ft^2 * L0 / (2 * 2.1e11 * 1.5e-5) rtol = 1.0e-2
        Eb = cols["Truss/Ebal"]
        @test maximum(abs.(Eb .- Eb[1])) < 1.0e-4 * cols["Truss/Elost"][end]
        @test cols["Truss/nfail"][end] == 1.0
    end

    @testset "wheel-on-deck contact: a body settles on its tyres" begin
        # 1000 kg on two wheels (k = 1e6 N/m, c = 1e5 N s/m at dref = 3 cm) dropped 2 cm onto a fixed deck of
        # two 10 m panels; the wheels sit at x = 6.5 and 9.5 m, both on panel 1
        m, k, g0 = 1000.0, 1.0e6, 9.81
        nodes = Any[
            _tr_node("T", "Deck", _TR_P * "Truss2D"; params = Dict{String,Any}(
                    "xy" => "[0.0 0.0; 10.0 0.0; 20.0 0.0]", "rho" => "0.0", "mn" => "[1.0, 1.0, 1.0]",
                    "A" => "[0.001, 0.001]", "I" => "[1.0e-6, 1.0e-6]"),
                consts = Dict{String,Any}("nn" => "3", "nb" => "2", "conn" => "[1 2; 2 3]",
                    "fix" => "[1 1; 1 1; 1 1]")),
            _tr_node("C", "Contact", _TR_P * "DeckContact2D"; params = Dict{String,Any}("k" => "1.0e6", "c" => "1.0e5"),
                consts = Dict{String,Any}("nn" => "3", "nd" => "3", "nw" => "2")),
            _tr_node("B", "Body", _TR_P * "Free2D"; params = Dict{String,Any}("m" => "1000.0", "J" => "500.0",
                "x0" => "8.0", "y0" => "1.02")),
            _tr_node("Z", "Zero", "stdlib:sources/Constant"; params = Dict{String,Any}("value" => "0.0")),
        ]
        conns = Any[
            bg_conn("c1", "bond", "C", "p", "B", "p"),
            bg_conn("s1", "signal", "B", "g", "C", "g"),
            bg_conn("s2", "signal", "T", "x", "C", "x"), bg_conn("s3", "signal", "T", "y", "C", "y"),
            bg_conn("s4", "signal", "T", "xd", "C", "xd"), bg_conn("s5", "signal", "T", "yd", "C", "yd"),
            bg_conn("s6", "signal", "Z", "y", "C", "Fd"),
            bg_conn("s7", "signal", "C", "Fx", "T", "Fx"), bg_conn("s8", "signal", "C", "Fy", "T", "Fy"),
        ]
        cols = _tr_run("contact", nodes, conns; t_end = 3.0, points = 601)
        delta = m * g0 / (2k)
        @test cols["Contact/delta[1]"][end] ≈ delta rtol = 1.0e-6
        @test cols["Contact/delta[2]"][end] ≈ delta rtol = 1.0e-6
        @test cols["Contact/fn[1]"][end] ≈ m * g0 / 2 rtol = 1.0e-6
        y = cols["Body/pose/g[3]"]
        @test y[end] ≈ 1.0 - delta atol = 1.0e-7
        @test minimum(y) > 1.0 - 4 * delta                     # damped landing, no tunnelling
        # the deck nodes carry the weight in the ratio of the shape functions (1 - xi, xi)
        @test cols["Deck/Ry[1]"][end] ≈ m * g0 / 2 * (0.35 + 0.05) + g0 rtol = 1.0e-6
        @test sum(cols["Deck/Ry[$i]"][end] for i in 1:3) ≈ (m + 3) * g0 rtol = 1.0e-6
    end
end
