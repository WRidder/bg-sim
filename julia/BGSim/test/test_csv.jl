# Work package F5.1: CSV input sources (src/library/csvdata.jl, stdlib/sources/CsvSource*.jl).
#
# Covered: parsing diagnostics (row/column in the message), the hold/linear/cubic values and
# derivatives, tstops, extrapolation, column/offset/scale settings, the path-safety refusal,
# the continuous and the sampled block in a real run, MTK differentiating a CSV velocity
# (a mass driven through derivative causality), cache invalidation by content, and the load
# time of a 100k-row x 10-column file.

using Test
using BGSim
import BGSim.IR
import BGSim.Compile
import JSON3

function _csv_project()
    dir = mktempdir()
    mkpath(joinpath(dir, "data"))
    return dir
end

function _csv_write(dir, name, text)
    path = joinpath(dir, "data", name)
    write(path, text)
    return path
end

_csv_text(f, ts; header = "t [s],x [m],y") = header * "\n" *
    join(("$t,$(f(t)[1]),$(f(t)[2])" for t in ts), "\n") * "\n"

function _csv_node(id, name, ref; constants = Dict{String,Any}(), params = Dict{String,Any}())
    return Dict{String,Any}(
        "id" => id, "name" => name, "block" => Dict{String,Any}("ref" => ref),
        "position" => Dict{String,Any}("x" => 0.0, "y" => 0.0),
        "params" => params, "constants" => constants, "starts" => Dict{String,Any}(),
    )
end

function _csv_conn(id, kind, a, ap, b, bp)
    return Dict{String,Any}(
        "id" => id, "kind" => kind,
        "from" => Dict{String,Any}("node" => a, "port" => ap),
        "to" => Dict{String,Any}("node" => b, "port" => bp),
    )
end

function _csv_model(nodes, conns; t_end = 1.0, points = 11)
    return Dict{String,Any}(
        "format" => "bgsim.model", "language" => "0.1.0", "name" => "csvtest",
        "diagram" => Dict{String,Any}("nodes" => nodes, "connections" => conns),
        "settings" => Dict{String,Any}(
            "t_start" => 0.0, "t_end" => t_end, "solver" => "auto", "reltol" => 1e-10,
            "abstol" => 1e-12, "max_step" => nothing,
            "output" => Dict{String,Any}("mode" => "points", "points" => points),
            "event_limit" => 10000,
        ),
        "plots" => [], "bindings" => [],
    )
end

function _csv_columns(dir)
    m = JSON3.read(read(joinpath(dir, "manifest.json"), String))
    n = Int(m.time.n)
    nsig = length(m.signals)
    raw = reinterpret(Float64, read(joinpath(dir, "columns.f64")))
    cols = reshape(collect(raw), (n, nsig + 1))
    out = Dict{String,Vector{Float64}}("time" => cols[:, 1])
    for (j, s) in enumerate(m.signals)
        out[String(s.id)] = cols[:, j + 1]
    end
    return out
end

# A one-state sink so a CSV source model has something to integrate (a stateless model has
# nothing to simulate): Sum the first two columns (signs +1 +1) into an Integrator.
function _csv_run(dir, constants; ref = "stdlib:sources/CsvSource", extra = Dict{String,Any}(),
    t_end = 1.0, points = 11)
    nodes = [
        _csv_node("n1", "Csv", ref; constants = merge(Dict{String,Any}("file" => "data/a.csv"),
            constants, extra)),
        _csv_node("n2", "S", "stdlib:continuous/Sum"; constants = Dict{String,Any}("N" => 2)),
        _csv_node("n3", "Int", "stdlib:continuous/Integrator"),
    ]
    conns = [_csv_conn("c1", "signal", "n1", "y", "n2", "u"),
        _csv_conn("c2", "signal", "n2", "y", "n3", "u")]
    model = _csv_model(nodes, conns; t_end = t_end, points = points)
    flat = Compile.flatten(IR.parse_model(model); project_dir = dir)
    result = BGSim.simulate(flat; run_dir = mktempdir(),
        settings = BGSim.RunSettings(model["settings"]))
    return result, flat
end

@testset "F5.1 CSV input source" begin
    @testset "parsing and diagnostics" begin
        file = BGSim.parse_csv("t [s],q [rad],qd\n0,1,2\n1,3,4\n"; file = "data/a.csv")
        @test file.names == ["t", "q", "qd"]
        @test file.units == ["s", "rad", ""]
        @test file.data[2] == [1.0, 3.0]
        semi = BGSim.parse_csv("t;a\r\n0;1.5\r\n"; file = "x")
        @test semi.names == ["t", "a"] && semi.data[2] == [1.5]
        bad = try
            BGSim.parse_csv("t,a,b\n0,1,2\n1,oops,3\n"; file = "data/a.csv")
        catch e
            e
        end
        @test bad isa BGSim.CsvError
        @test occursin("data row 2", bad.message) && occursin("column `a`", bad.message) &&
              occursin("oops", bad.message)
        ragged = try
            BGSim.parse_csv("t,a\n0,1\n1\n")
        catch e
            e
        end
        @test ragged isa BGSim.CsvError && occursin("data row 2", ragged.message)
        @test_throws BGSim.CsvError BGSim.parse_csv("")
        @test_throws BGSim.CsvError BGSim.parse_csv("t,a\n")
        @test_throws BGSim.CsvError BGSim.parse_csv("t,t\n0,1\n")
        @test_throws BGSim.CsvError BGSim.parse_csv("t,a\n0,NaN\n")
    end

    @testset "path safety and settings errors" begin
        dir = _csv_project()
        _csv_write(dir, "a.csv", "t,x\n0,1\n1,2\n")
        for bad in ("../a.csv", "data/../../a.csv", "/etc/a.csv", "C:/a.csv", "")
            err = try
                BGSim.load_csv_table(dir, Dict("file" => bad))
            catch e
                e
            end
            @test err isa BGSim.CsvError
            @test !isempty(err.hint)
        end
        @test_throws BGSim.CsvError BGSim.load_csv_table(nothing, Dict("file" => "data/a.csv"))
        @test_throws BGSim.CsvError BGSim.load_csv_table(dir, Dict("file" => "data/missing.csv"))
        @test_throws BGSim.CsvError BGSim.load_csv_table(
            dir, Dict("file" => "data/a.csv", "columns" => "nope"))
        @test_throws BGSim.CsvError BGSim.load_csv_table(
            dir, Dict("file" => "data/a.csv", "time_column" => "nope"))
        @test_throws BGSim.CsvError BGSim.load_csv_table(
            dir, Dict("file" => "data/a.csv", "method" => 7))
        _csv_write(dir, "dup.csv", "t,x\n0,1\n0,2\n")
        e = try
            BGSim.load_csv_table(dir, Dict("file" => "data/dup.csv"))
        catch e
            e
        end
        @test e isa BGSim.CsvError && occursin("strictly increasing", e.message)
    end

    @testset "hold, linear and cubic values and derivatives" begin
        dir = _csv_project()
        f(t) = (t^3 - 2t, 4t)
        ts = 0:0.25:2
        _csv_write(dir, "a.csv", _csv_text(f, ts))
        hold = BGSim.load_csv_table(dir, Dict("file" => "data/a.csv", "method" => "hold"))
        lin = BGSim.load_csv_table(dir, Dict("file" => "data/a.csv", "method" => 1))
        cub = BGSim.load_csv_table(dir, Dict("file" => "data/a.csv", "method" => 2))
        @test hold.names == ["x", "y"] && hold.units == ["m", ""]
        @test BGSim.csv_eval(hold, 1, 0, 0.3) == f(0.25)[1]
        @test BGSim.csv_eval(hold, 1, 1, 0.3) == 0.0
        @test BGSim.csv_eval(lin, 2, 0, 0.3) ≈ 4 * 0.3
        @test BGSim.csv_eval(lin, 2, 1, 0.3) ≈ 4.0
        @test BGSim.csv_eval(lin, 1, 2, 0.3) == 0.0
        # a not-a-knot cubic spline reproduces a cubic polynomial exactly, derivatives included
        for t in (0.01, 0.37, 0.8, 1.5, 1.99)
            @test BGSim.csv_eval(cub, 1, 0, t) ≈ t^3 - 2t atol = 1e-12
            @test BGSim.csv_eval(cub, 1, 1, t) ≈ 3t^2 - 2 atol = 1e-11
            @test BGSim.csv_eval(cub, 1, 2, t) ≈ 6t atol = 1e-10
            @test BGSim.csv_eval(cub, 1, 3, t) ≈ 6 atol = 1e-9
            @test BGSim.csv_eval(cub, 1, 4, t) == 0.0
        end
        # C2: value, slope and curvature are continuous across a knot
        for order in 0:2
            @test BGSim.csv_eval(cub, 1, order, 0.75 - 1e-12) ≈
                  BGSim.csv_eval(cub, 1, order, 0.75 + 1e-12) atol = 1e-8
        end
        # a smooth function sampled at 1 kHz is interpolated to ~h^4
        n = 1001
        _csv_write(dir, "s.csv", _csv_text(t -> (sin(2π * t), cos(2π * t)), range(0, 1; length = n)))
        s = BGSim.load_csv_table(dir, Dict("file" => "data/s.csv"))
        worst = maximum(abs(BGSim.csv_eval(s, 1, 1, t) - 2π * cos(2π * t)) for t in 0.0005:0.00123:0.9995)
        @test worst < 1e-7
    end

    @testset "tstops" begin
        dir = _csv_project()
        _csv_write(dir, "a.csv", _csv_text(t -> (t, t), 0:0.25:1))
        hold = BGSim.load_csv_table(dir, Dict("file" => "data/a.csv", "method" => 0))
        lin = BGSim.load_csv_table(dir, Dict("file" => "data/a.csv", "method" => 1))
        cub = BGSim.load_csv_table(dir, Dict("file" => "data/a.csv", "method" => 2))
        @test BGSim.csv_tstops(hold, 0.0, 1.0) == [0.25, 0.5, 0.75, 1.0]
        @test BGSim.csv_tstops(lin, 0.0, 0.6) == [0.25, 0.5]
        @test BGSim.csv_tstops(cub, 0.0, 1.0) == [1.0]
        shifted = BGSim.load_csv_table(
            dir, Dict("file" => "data/a.csv", "method" => 1, "time_offset" => 0.1))
        @test BGSim.csv_tstops(shifted, 0.0, 0.5) ≈ [0.1, 0.35]
    end

    @testset "extrapolation, offset, scale, columns" begin
        dir = _csv_project()
        _csv_write(dir, "a.csv", "time,a,b,c\n0,1,10,100\n1,2,20,200\n2,3,30,300\n")
        t = BGSim.load_csv_table(dir, Dict("file" => "data/a.csv", "method" => 1))
        @test t.names == ["a", "b", "c"]
        @test BGSim.csv_eval(t, 1, 0, -5.0) == 1.0 && BGSim.csv_eval(t, 1, 0, 9.0) == 3.0
        @test BGSim.csv_eval(t, 1, 1, 9.0) == 0.0
        strict = BGSim.load_csv_table(
            dir, Dict("file" => "data/a.csv", "method" => 1, "extrapolation" => "error"))
        @test BGSim.csv_eval(strict, 1, 0, 2.0) == 3.0
        err = try
            BGSim.csv_eval(strict, 1, 0, 2.5)
        catch e
            e
        end
        @test err isa BGSim.CsvError && occursin("outside the data range", err.message)
        sel = BGSim.load_csv_table(dir, Dict("file" => "data/a.csv", "columns" => "c, a",
            "time_offset" => 1.0, "scale" => 2.0, "method" => 1))
        @test sel.names == ["c", "a"]
        @test BGSim.csv_eval(sel, 1, 0, 1.5) ≈ 2 * 150.0   # t = 0.5 in the file, scaled
        tc = BGSim.load_csv_table(dir, Dict("file" => "data/a.csv", "time_column" => "b",
            "columns" => "a", "method" => 1))
        @test BGSim.csv_eval(tc, 1, 0, 25.0) ≈ 2.5
        # one id per file content and settings
        same = BGSim.load_csv_table(dir, Dict("file" => "data/a.csv", "method" => 1))
        @test same.id == t.id
        @test sel.id != t.id && strict.id != t.id
    end

    @testset "blocks in a run: continuous and sampled" begin
        dir = _csv_project()
        _csv_write(dir, "a.csv", _csv_text(t -> (2t, 10t), 0:0.1:1))
        result, flat = _csv_run(dir, Dict("method" => 1, "columns" => "x,y"))
        @test result.status == "done"
        @test isempty([d for d in flat.diagnostics if d.severity == "error"])
        cols = _csv_columns(result.run_dir)
        @test cols["Csv/y[1]"] ≈ 2 .* cols["time"] atol = 1e-12
        @test cols["Csv/y[2]"] ≈ 10 .* cols["time"] atol = 1e-12
        @test cols["Int/y"][end] ≈ 6.0 atol = 1e-6   # ∫ (2t + 10t) dt = 6
        # N follows the file: one selected column gives a one-element output
        r1, _ = begin
            nodes = [_csv_node("n1", "Csv", "stdlib:sources/CsvSource";
                    constants = Dict{String,Any}("file" => "data/a.csv", "columns" => "y")),
                _csv_node("n3", "Sel", "stdlib:continuous/Select";
                    constants = Dict{String,Any}("N" => 1, "index" => 1)),
                _csv_node("n4", "Int", "stdlib:continuous/Integrator")]
            conns = [_csv_conn("c1", "signal", "n1", "y", "n3", "u"),
                _csv_conn("c2", "signal", "n3", "y", "n4", "u")]
            m = _csv_model(nodes, conns)
            f = Compile.flatten(IR.parse_model(m); project_dir = dir)
            (BGSim.simulate(f; run_dir = mktempdir(), settings = BGSim.RunSettings(m["settings"])), f)
        end
        @test r1.status == "done"
        @test length(_csv_columns(r1.run_dir)["Csv/y[1]"]) == 11

        # sampled: the table value at every tick, held in between
        res, _ = _csv_run(dir, Dict("method" => 1);
            ref = "stdlib:sources/CsvSourceSampled", extra = Dict{String,Any}("sample_period" => 0.25),
            t_end = 1.0, points = 41)
        @test res.status == "done"
        c = _csv_columns(res.run_dir)
        for (t, y) in zip(c["time"], c["Csv/y[1]"])
            tick = floor(t / 0.25 + 1e-9) * 0.25
            # an event instant is recorded twice (left and right limit): at a tick the left
            # row still shows the previous held value
            @test isapprox(y, 2 * tick; atol = 1e-12) || isapprox(y, 2 * (tick - 0.25); atol = 1e-12)
        end
    end

    @testset "diagnostics reach the model check" begin
        dir = _csv_project()
        node = _csv_node("n1", "Csv", "stdlib:sources/CsvSource";
            constants = Dict{String,Any}("file" => "../outside.csv"))
        flat = Compile.flatten(IR.parse_model(_csv_model([node], [])); project_dir = dir)
        d = [x for x in flat.diagnostics if x.code == "E108"]
        @test length(d) == 1
        @test d[1].path == "Csv" && occursin("outside the project", d[1].message)
        @test d[1].hint !== nothing && occursin("data/", d[1].hint)
        _csv_write(dir, "bad.csv", "t,a\n0,1\n1,x\n")
        node2 = _csv_node("n1", "Csv", "stdlib:sources/CsvSource";
            constants = Dict{String,Any}("file" => "data/bad.csv"))
        flat2 = Compile.flatten(IR.parse_model(_csv_model([node2], [])); project_dir = dir)
        d2 = [x for x in flat2.diagnostics if x.code == "E108"]
        @test length(d2) == 1 && occursin("data row 2", d2[1].message)
    end

    @testset "MTK differentiates a CSV velocity (mass in derivative causality)" begin
        dir = _csv_project()
        n = 1001
        _csv_write(dir, "v.csv", _csv_text(t -> (sin(2π * t), 0.0), range(0, 1; length = n)))
        nodes = [
            _csv_node("n1", "Csv", "stdlib:sources/CsvSource";
                constants = Dict{String,Any}("file" => "data/v.csv", "columns" => "x")),
            _csv_node("n2", "Sel", "stdlib:continuous/Select";
                constants = Dict{String,Any}("N" => 1, "index" => 1)),
            _csv_node("n3", "Src", "stdlib:translation/VelocitySource"),
            _csv_node("n4", "FS", "stdlib:converters/ForceSensor"),
            _csv_node("n5", "M", "stdlib:translation/Mass"; params = Dict{String,Any}("m" => "2.0")),
            _csv_node("n6", "Fix", "stdlib:translation/Fixed"),
        ]
        conns = [
            _csv_conn("c1", "signal", "n1", "y", "n2", "u"),
            _csv_conn("c2", "signal", "n2", "y", "n3", "u"),
            _csv_conn("c3", "wire", "n3", "a", "n4", "a"),
            _csv_conn("c4", "wire", "n4", "b", "n5", "a"),
            _csv_conn("c5", "wire", "n5", "b", "n6", "a"),
        ]
        model = _csv_model(nodes, conns; points = 101)
        flat = Compile.flatten(IR.parse_model(model); project_dir = dir)
        @test isempty([d for d in flat.diagnostics if d.severity == "error"])
        result = BGSim.simulate(flat; run_dir = mktempdir(),
            settings = BGSim.RunSettings(model["settings"]))
        @test result.status == "done"
        c = _csv_columns(result.run_dir)
        # force = m dv/dt with v = sin(2πt): the registered derivative of the spline
        expected = 2 .* 2π .* cos.(2π .* c["time"])
        @test maximum(abs.(abs.(c["FS/y"]) .- abs.(expected))) < 1e-5
    end

    @testset "the compile cache key contains the file content" begin
        dir = _csv_project()
        _csv_write(dir, "a.csv", _csv_text(t -> (t, 2t), 0:0.25:1))
        run1, f1 = _csv_run(dir, Dict("method" => 1))
        builds = BGSim.compile_build_count()
        run2, f2 = _csv_run(dir, Dict("method" => 1))
        @test BGSim.compile_build_count() == builds              # same content: cache hit
        @test BGSim.compile_key(f1) == BGSim.compile_key(f2)
        @test run2.cache_hit
        _csv_write(dir, "a.csv", _csv_text(t -> (t, 3t), 0:0.25:1))   # edit the file
        run3, f3 = _csv_run(dir, Dict("method" => 1))
        @test BGSim.compile_key(f3) != BGSim.compile_key(f1)
        @test BGSim.compile_build_count() == builds + 1          # recompiled
        @test !run3.cache_hit
        @test _csv_columns(run3.run_dir)["Csv/y[2]"][end] ≈ 3.0 atol = 1e-12
        _csv_write(dir, "a.csv", _csv_text(t -> (t, 2t), 0:0.25:1))   # revert
        run4, f4 = _csv_run(dir, Dict("method" => 1))
        @test BGSim.compile_key(f4) == BGSim.compile_key(f1)
        @test _csv_columns(run4.run_dir)["Csv/y[2]"][end] ≈ 2.0 atol = 1e-12
        # a setting that changes the data changes the key too
        _, f5 = _csv_run(dir, Dict("method" => 1, "scale" => 2.0))
        @test BGSim.compile_key(f5) != BGSim.compile_key(f1)
    end

    @testset "100k rows x 10 columns" begin
        dir = _csv_project()
        n = 100_000
        io = IOBuffer()
        println(io, "t,", join(("c$k" for k in 1:10), ","))
        for i in 0:(n - 1)
            t = i * 1e-5
            println(io, t, ",", join((sin(k * t) for k in 1:10), ","))
        end
        _csv_write(dir, "big.csv", String(take!(io)))
        BGSim.load_csv_table(dir, Dict("file" => "data/big.csv")) # warm up the parser
        time_load = @elapsed tab = BGSim.load_csv_table(
            dir, Dict("file" => "data/big.csv", "scale" => 1.5))
        @test length(tab.time) == n && length(tab.values) == 10
        @test time_load < 10.0
        @info "100k x 10 CSV load (parse + spline set-up)" seconds = round(time_load; digits = 3)
        lookups = @elapsed for t in range(0.0, 0.99; length = 100_000)
            BGSim.csv_eval(tab, 3, 1, t)
        end
        @test lookups < 1.0
        @test BGSim.csv_eval(tab, 2, 0, 0.5) ≈ 1.5 * sin(2 * 0.5) atol = 1e-9
    end
end
