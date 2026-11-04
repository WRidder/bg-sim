# The assistant's code cells: parsed and interpreted, never evaluated (spec, principle 2).

using Test
using BGSim
import JSON3

@testset "code cells" begin
    t = collect(0.0:0.5:2.0)
    signals = Dict("Load/w" => 2 .* t, "Motor/i" => [1.0, 1.0, 1.0, 1.0, 1.0])

    run_cell(code; kw...) = cell_run(code; time = t, signals = signals, kw...)

    @testset "elementwise arithmetic, with or without the dot" begin
        r = run_cell("""
            w = s"Load/w"
            p = w * s"Motor/i"
            q = w .* s"Motor/i" .+ 1
            maximum(p)
            abs.(q)[1]
            q[end_index]
            """)
        @test !r.ok
        @test r.output == ["maximum(p) = 4.0", "abs.(q)[1] = 1.0"]
        @test occursin("end_index", r.diagnostics[1].message)
    end

    @testset "statements" begin
        r = run_cell("""
            total = 0.0
            for i in 1:length(t)
                if t[i] > 0.5
                    total += s"Load/w"[i]
                else
                    total -= 1
                end
            end
            total
            mean(s"Load/w")
            trapz(s"Load/w", t)
            """)
        @test r.ok
        @test r.output == ["total = 7.0", "mean(s\"Load/w\") = 2.0", "trapz(s\"Load/w\", t) = 4.0"]
        @test r.values["total"] == 7.0
    end

    @testset "masks, vectors and aggregates" begin
        r = run_cell("""
            late = s"Load/w"[t .>= 1.0]
            length(late)
            rms([3.0, 4.0])
            findfirst(t .> 1.2)
            interp(0.75, t, s"Load/w")
            """)
        @test r.ok
        @test r.output[1] == "length(late) = 3"
        @test r.output[3] == "findfirst(t .> 1.2) = 4"
        @test r.output[4] == "interp(0.75, t, s\"Load/w\") = 1.5"
    end

    @testset "tables and plots" begin
        r = run_cell("""
            w = s"Load/w"
            plot("Speed", t, w, 2 * w)
            table("Peaks", maximum(w), minimum(w))
            table("Series", t, w)
            """)
        @test r.ok
        chart, peaks, series = r.figures
        @test chart.kind == "chart" && chart.title == "Speed" && chart.xLabel == "t"
        @test [s.name for s in chart.series] == ["w", "2 * w"]
        @test chart.series[2].y[end] == 8.0
        @test peaks.columns == ["maximum(w)", "minimum(w)"] && peaks.rows == [[4.0, 0.0]]
        @test length(series.rows) == 5
    end

    @testset "outputs: shorthands, text and images" begin
        r = run_cell("""
            Plot(t, s"Load/w")
            scatter("Points", t, s"Load/w")
            bar(t, s"Load/w")
            Table(t)
            text("peak", maximum(t), "s")
            print("done")
            image("Heat", [1.0 2.0; 3.0 4.0])
            """)
        @test r.ok
        line, points, bars, table_figure, heat = r.figures
        @test line.style == "line" && line.title == ""
        @test points.style == "points" && points.title == "Points"
        @test bars.style == "bar"
        @test table_figure.columns == ["t"]
        @test r.output == ["peak 2.0 s", "done"]
        @test heat.kind == "image" && heat.rows[2] == [3.0, 4.0] && heat.max == 4.0
    end

    @testset "non-finite values are null" begin
        r = run_cell("""plot("x", t, s"Load/w" / 0)""")
        @test r.ok
        @test r.figures[1].series[1].y[2] === nothing
    end

    @testset "a thinned plot" begin
        long = collect(0.0:9999.0)
        r = cell_run("""plot("x", t, t)"""; time = long)
        @test length(r.figures[1].x) <= BGSim.CELL_MAX_POINTS
    end

    @testset "not Julia semantics: nothing is evaluated" begin
        for code in (
            "run(`calc`)",
            "open(\"x\", \"w\")",
            "eval(1)",
            "using Pkg",
            "import Base",
            "Base.exit()",
            "ccall(:exit, Cvoid, ())",
            "@show 1",
            "x = \"text\"",
            "(() -> 1)()",
            "x -> x",
            "try\n1\ncatch\nend",
            "struct S end",
            "@eval 1",
            "s\"a\" |> open",
            "Core.eval(Main, 1)",
        )
            r = run_cell(code)
            @test !r.ok
            @test !isempty(r.diagnostics)
        end
    end

    @testset "errors point at the code" begin
        r = run_cell("x = 1 +")
        @test !r.ok && r.diagnostics[1].code == "E001"
        @test startswith(r.diagnostics[1].message, "syntax error")

        r = run_cell("a = 1\na\nb = s\"No/such\"\n")
        @test !r.ok
        @test r.output == ["a = 1"]
        @test occursin("neither a signal", r.diagnostics[1].message)
        @test r.diagnostics[1].code == "E004"
    end

    @testset "work is bounded" begin
        for code in (
            "for i in 1:1000000000\nend",
            "while true\nend",
            "x = 1\nwhile x > 0\nx = x + 1\nend",
            "f(x) = f(x)\nf(1)",
            "zeros(100000000000)",
        )
            r = run_cell(code; time_limit_s = 0.2)
            @test !r.ok
            @test occursin("work limit", r.diagnostics[1].message) ||
                  occursin("too deep", r.diagnostics[1].message)
        end
    end

    @testset "functions, loops and tuples" begin
        r = run_cell("""
            square(x) = x * x
            function clip(v, level)
                out = zeros(length(v))
                for i in 1:length(v)
                    if v[i] > level
                        out[i] = level
                        continue
                    end
                    out[i] = v[i]
                end
                return out
            end
            function stats(v)
                return (minimum(v), maximum(v))
            end
            low, high = stats(clip(s"Load/w", 3.0))
            high
            square(4)
            n = 0
            while true
                n += 1
                if n == 5
                    break
                end
            end
            n
            fact(k) = ifelse(k <= 1, 1, k)
            function total(k)
                if k <= 0
                    return 0
                end
                k + total(k - 1)
            end
            total(4)
            """)
        @test r.ok
        @test r.output == ["high = 3.0", "square(4) = 16", "n = 5", "total(4) = 10"]
    end

    @testset "matrices" begin
        r = run_cell("""
            A = [2.0 0.0; 0.0 4.0]
            b = [2.0, 4.0]
            x = A \\ b
            x
            (A * b)[end]
            A[2, 2]
            A[:, 2]
            det(A)
            B = hcat(b, b)
            size(B)
            eigvals(A)[1]
            v = [1, 2, 3]
            v[2:end]
            """)
        @test r.ok
        @test r.output[1] == "x = [1.0, 1.0] (2 values)"
        @test r.output[2] == "(A * b)[end] = 16.0"
        @test r.output[3] == "A[2, 2] = 4.0"
        @test r.output[4] == "A[:, 2] = [0.0, 4.0] (2 values)"
        @test r.output[5] == "det(A) = 8.0"
        @test r.output[6] == "size(B) = [2, 2] (2 values)"
        @test r.output[7] == "eigvals(A)[1] = 2.0"
        @test r.output[8] == "v[2:end] = [2, 3] (2 values)"
    end

    @testset "spectra" begin
        # 3 Hz at amplitude 2 and 7 Hz at amplitude 0.5, 128 samples over 1 s and a prime length
        for n in (128, 127)
            u = collect(0:(n - 1)) ./ n
            r = cell_run("""
                y = 1.5 + 2 * sin(2 * pi * 3 * t) + 0.5 * cos(2 * pi * 7 * t)
                a = amplitude(y)
                f = ampfreq(t)
                plot("Spectrum", f, a)
                a[1]
                f[argmax(a[2:end]) + 1]
                a[4]
                a[8]
                maximum(abs(ifft(fft(y)) - y))
                """; time = u)
            @test r.ok
            @test r.output[1] == "a[1] = 1.5"
            @test r.output[2] == "f[argmax(a[2:end]) + 1] = 3.0"
            @test r.output[3] == "a[4] = 2.0"
            @test r.output[4] == "a[8] = 0.5"
            @test parse(Float64, split(r.output[5], " = ")[2]) < 1e-9
            @test length(r.figures[1].x) == n ÷ 2 + 1
        end
        r = cell_run("samplerate(t)"; time = [0.0, 1.0, 3.0])
        @test !r.ok && occursin("not uniform", r.diagnostics[1].message)
    end

    @testset "filters and fits" begin
        u = collect(0.0:0.001:2.0)
        r = cell_run("""
            slow = sin(2 * pi * t)
            y = slow + 0.5 * sin(2 * pi * 200 * t)
            b, a = butter(4, 20 / 500)
            maximum(abs(filtfilt(b, a, y) - slow)[100:1900])
            h, k = butterhigh(4, 20 / 500)
            rms(filtfilt(h, k, slow)[500:1500])
            sum(b) / sum(a)
            maximum(abs(movmean(slow, 1) - slow))
            p = polyfit(t, 3 + 2 * t - t * t, 2)
            p
            maximum(abs(detrend(1 + 2 * t)))
            maximum(abs(cumtrapz(cos(t), t) - sin(t)))
            maximum(abs(gradient(sin(t), t)[2:(end - 1)] - cos(t)[2:(end - 1)]))
            length(peaks(slow))
            length(crossings(slow, 0.5))
            percentile([1, 2, 3, 4, 5], 50)
            maximum(abs(convolve([1, 2], [1, 3]) - [1, 5, 6]))
            """; time = u)
        @test r.ok
        value(i) = parse(Float64, split(r.output[i], " = ")[end])
        @test value(1) < 0.01
        @test value(2) < 0.02
        @test abs(value(3) - 1) < 1e-9
        @test value(4) == 0
        @test r.output[5] == "p = [3.0, 2.0, -1.0] (3 values)"
        @test value(6) < 1e-9
        @test value(7) < 1e-3
        @test value(8) < 1e-3
        @test value(9) == 2
        @test value(10) == 4
        @test value(11) == 3
        @test value(12) < 1e-9
    end

    @testset "a stray string says what strings are for" begin
        r = run_cell("x = 1\ntable(\"T\", \"max\", x)")
        @test !r.ok
        @test occursin("a title or text to print", r.diagnostics[1].message)
    end

    @testset "parameters and globals of the model" begin
        file = joinpath(@__DIR__, "..", "..", "..", "contracts", "fixtures", "model", "valid",
            "model.dcmotor.json")
        model = JSON3.read(read(file, String), Dict{String,Any})
        model["parameters"] = Any[Dict{String,Any}("name" => "Kp", "value" => "4")]
        r = cell_run("Kp * 2\ns\"Motor1/R\""; model = model)
        @test r.ok
        @test r.output == ["Kp * 2 = 8", "s\"Motor1/R\" = 2.0"]
    end
end
