# Linked subsystems: a drawn subsystem definition of the project library
# (`library/<Name>.bgsub.json`, or the copy a document carries in `definitions`) and its
# instances, the nodes with `ref == "project:<Name>"`.
#
#   * an instance flattens to exactly what the subsystem it was drawn as flattens to;
#   * two instances share the structure and set their own pinned parameters and starts;
#   * a value that is not pinned, or that names nothing, is W218 and has no effect;
#   * a definition that contains itself is E101;
#   * a definition may hold an instance of another definition;
#   * the library file is read from the project, and the document's copy takes precedence;
#   * the catalog lists a definition with its ports.

using Test
using BGSim
import BGSim.IR
import BGSim.Compile
import BGSim.Library
import JSON3

const _LK_ROOT = normpath(joinpath(@__DIR__, "..", "..", ".."))

_lk_plain(v) = v isa AbstractDict ? Dict{String,Any}(String(k) => _lk_plain(x) for (k, x) in pairs(v)) :
               v isa AbstractVector ? Any[_lk_plain(x) for x in v] : v
_lk_read(path) = _lk_plain(JSON3.read(read(path, String)))

"""Everything of a flat model that an instance must reproduce, one line per item."""
function _lk_lines(f)
    out = String[]
    for v in f.variables; push!(out, "v $(v.id) $(v.kind) $(v.type) $(v.unit)"); end
    for p in f.parameters; push!(out, "p $(p.id) $(p.type) $(p.value)"); end
    for e in f.equations; push!(out, "e " * sprint(show, e.lhs) * " ~ " * sprint(show, e.rhs)); end
    for e in f.initial; push!(out, "i " * sprint(show, e.lhs) * " ~ " * sprint(show, e.rhs)); end
    for e in f.events; push!(out, "ev " * sprint(show, e)); end
    for e in f.discrete; push!(out, "d " * sprint(show, e)); end
    for d in f.derived; push!(out, "dv $(d.id) " * sprint(show, d.expr)); end
    for s in f.signals; push!(out, "s $(s.id) $(s.kind) $(s.unit)"); end
    for c in f.connections; push!(out, "c $(c.kind) $(c.from_path) $(c.from_port) $(c.to_path) $(c.to_port) $(c.domain)"); end
    for j in f.junctions; push!(out, "j $(j.path) $(j.kind)"); end
    for d in f.diagnostics; push!(out, "diag $(d.code) $(d.severity) $(d.path) $(d.message)"); end
    return out
end

"""`doc` with every top-level subsystem moved to `definitions` and its node made an instance."""
function _lk_linked(doc)
    linked = deepcopy(doc)
    definitions = Dict{String,Any}()
    count = 0
    for node in linked["diagram"]["nodes"]
        haskey(node["block"], "subsystem") || continue
        count += 1
        name = "Def_" * node["name"]
        sub = node["block"]["subsystem"]
        definitions[name] = Dict{String,Any}(
            "format" => "bgsim.subsystem", "name" => name,
            "ports" => sub["ports"], "diagram" => sub["diagram"],
        )
        node["block"] = Dict{String,Any}("ref" => "project:" * name)
    end
    linked["definitions"] = definitions
    return linked, count
end

_lk_block(id, name, ref; params = Dict{String,Any}(), starts = Dict{String,Any}()) =
    Dict{String,Any}("id" => id, "name" => name, "block" => Dict{String,Any}("ref" => ref),
        "position" => Dict("x" => 0, "y" => 0), "params" => params, "starts" => starts)

# A series RC branch behind one power port: a 1-junction with a resistor and a capacitor.
function _lk_branch(; r = "10.0", c = "1e-3", pins = Dict{String,Any}())
    return Dict{String,Any}(
        "format" => "bgsim.subsystem", "name" => "Branch",
        "ports" => Any[Dict{String,Any}("name" => "p", "kind" => "power", "domain" => "Electrical",
            "node" => "j", "port" => "junction")],
        "diagram" => Dict{String,Any}(
            "nodes" => Any[
                Dict{String,Any}("id" => "j", "name" => "J", "block" => Dict("junction" => "1"),
                    "position" => Dict("x" => 0, "y" => 0)),
                _lk_block("r", "R1", "stdlib:bondgraph/R"; params = Dict{String,Any}("r" => r)),
                _lk_block("c", "C1", "stdlib:bondgraph/C"; params = Dict{String,Any}("c" => c)),
            ],
            "connections" => Any[
                Dict{String,Any}("id" => "b1", "kind" => "bond",
                    "from" => Dict("node" => "j"), "to" => Dict("node" => "r", "port" => "p")),
                Dict{String,Any}("id" => "b2", "kind" => "bond",
                    "from" => Dict("node" => "j"), "to" => Dict("node" => "c", "port" => "p")),
            ],
        ),
        "pins" => pins,
    )
end

# A source on a 0-junction that feeds every instance in `instances` (name => node fields).
function _lk_model(instances; definitions = Dict{String,Any}())
    nodes = Any[
        _lk_block("se", "Se1", "stdlib:bondgraph/Se"; params = Dict{String,Any}("e" => "1.0")),
        Dict{String,Any}("id" => "z", "name" => "Z", "block" => Dict("junction" => "0"),
            "position" => Dict("x" => 0, "y" => 0)),
    ]
    connections = Any[Dict{String,Any}("id" => "s", "kind" => "bond",
        "from" => Dict("node" => "se", "port" => "p"), "to" => Dict("node" => "z"))]
    for (k, (name, fields)) in enumerate(instances)
        node = Dict{String,Any}("id" => "i$k", "name" => name,
            "position" => Dict("x" => 0, "y" => 0))
        merge!(node, fields)
        push!(nodes, node)
        push!(connections, Dict{String,Any}("id" => "k$k", "kind" => "bond",
            "from" => Dict("node" => "z"), "to" => Dict("node" => "i$k", "port" => "p")))
    end
    return Dict{String,Any}(
        "format" => "bgsim.model", "language" => "0.1.0", "name" => "Linked",
        "diagram" => Dict{String,Any}("nodes" => nodes, "connections" => connections),
        "settings" => Dict{String,Any}("t_start" => 0.0, "t_end" => 1.0),
        "definitions" => definitions,
    )
end

_lk_instance(; params = Dict{String,Any}(), starts = Dict{String,Any}(), ref = "project:Branch") =
    Dict{String,Any}("block" => Dict{String,Any}("ref" => ref), "params" => params, "starts" => starts)

function _lk_drawn(definition; params = Dict{String,Any}())
    diagram = deepcopy(definition["diagram"])
    for node in diagram["nodes"], (key, value) in params
        parts = split(key, '/')
        node["name"] == parts[1] && (node["params"][parts[2]] = value)
    end
    return Dict{String,Any}("block" => Dict{String,Any}("subsystem" => Dict{String,Any}(
        "ports" => definition["ports"], "diagram" => diagram)))
end

_lk_param(flat, id) = only(p for p in flat.parameters if p.id == id).value
# The toy models are all-Generic bond graphs, which is W205; it is not what is tested here.
_lk_diags(flat) = [d for d in flat.diagnostics if d.code != "W205"]
_lk_codes(flat) = sort([d.code for d in _lk_diags(flat)])

@testset "linked subsystems" begin
    @testset "an instance flattens like the subsystem it was drawn as" begin
        cases = (
            ("contracts/fixtures/model/valid/model.subsystem-port-ui.json", nothing),
            ("contracts/fixtures/model/valid/model.frame-bridge.json", nothing),
            ("examples/rlc-dual/models/rlc-dual.bgmodel.json", "examples/rlc-dual"),
            ("examples/maglev-train/models/maglev-vehicle.bgmodel.json", "examples/maglev-train"),
            ("examples/van-der-pol/models/vdp-textbook.bgmodel.json", "examples/van-der-pol"),
            ("examples/hybrid-powersplit/models/hybrid-kinematics.bgmodel.json", "examples/hybrid-powersplit"),
            ("examples/panda-3d/models/panda-rigid.bgmodel.json", "examples/panda-3d"),
        )
        for (file, project) in cases
            doc = _lk_read(joinpath(_LK_ROOT, file))
            dir = project === nothing ? nothing : joinpath(_LK_ROOT, project)
            linked, count = _lk_linked(doc)
            @test count > 0
            drawn = Compile.flatten(IR.parse_model(doc); project_dir = dir)
            instanced = Compile.flatten(IR.parse_model(linked); project_dir = dir)
            @test _lk_lines(instanced) == _lk_lines(drawn)
            @test BGSim.compile_key(instanced) == BGSim.compile_key(drawn)
        end
    end

    @testset "instances share the structure and set their pinned values" begin
        pins = Dict{String,Any}("params" => Any["R1/r"], "starts" => Any["C1/q"])
        definition = _lk_branch(; pins = pins)
        linked = _lk_model(
            ["A" => _lk_instance(), "B" => _lk_instance(;
                params = Dict{String,Any}("R1/r" => "47.0"),
                starts = Dict{String,Any}("C1/q" => "2e-3"))];
            definitions = Dict{String,Any}("Branch" => definition),
        )
        flat = Compile.flatten(IR.parse_model(linked))
        @test isempty(_lk_diags(flat))
        @test _lk_param(flat, "A/R1/r") == 10.0
        @test _lk_param(flat, "B/R1/r") == 47.0
        @test _lk_param(flat, "A/C1/c") == _lk_param(flat, "B/C1/c") == 1e-3

        drawn = _lk_model(["A" => _lk_drawn(definition), "B" => merge(
            _lk_drawn(definition; params = Dict{String,Any}("R1/r" => "47.0")),
        )])
        for node in drawn["diagram"]["nodes"]
            node["name"] == "B" || continue
            for inner in node["block"]["subsystem"]["diagram"]["nodes"]
                inner["name"] == "C1" && (inner["starts"]["q"] = "2e-3")
            end
        end
        @test _lk_lines(flat) == _lk_lines(Compile.flatten(IR.parse_model(drawn)))

        # The definition is not touched by an instance's values.
        again = Compile.flatten(IR.parse_model(linked))
        @test _lk_param(again, "A/R1/r") == 10.0
    end

    @testset "a value that is not pinned has no effect (W218)" begin
        definition = _lk_branch(; pins = Dict{String,Any}("params" => Any["R1/r", "Gone/r"]))
        linked = _lk_model(
            ["A" => _lk_instance(; params = Dict{String,Any}(
                "R1/r" => "5.0", "C1/c" => "9.0", "Gone/r" => "1.0"))];
            definitions = Dict{String,Any}("Branch" => definition),
        )
        flat = Compile.flatten(IR.parse_model(linked))
        @test _lk_codes(flat) == ["W218", "W218"]
        @test all(d -> d.severity == "warning" && d.path == "A", _lk_diags(flat))
        @test _lk_param(flat, "A/R1/r") == 5.0
        @test _lk_param(flat, "A/C1/c") == 1e-3
    end

    @testset "a definition that contains itself is E101" begin
        definition = _lk_branch()
        push!(definition["diagram"]["nodes"], merge(
            Dict{String,Any}("id" => "self", "name" => "Again", "position" => Dict("x" => 0, "y" => 0)),
            _lk_instance(),
        ))
        linked = _lk_model(["A" => _lk_instance()];
            definitions = Dict{String,Any}("Branch" => definition))
        flat = Compile.flatten(IR.parse_model(linked))
        hits = [d for d in flat.diagnostics if d.code == "E101"]
        @test length(hits) == 1
        @test occursin("contains itself", only(hits).message)
        @test only(hits).path == "A/Again"
    end

    @testset "a definition holds an instance of another definition" begin
        outer = Dict{String,Any}(
            "format" => "bgsim.subsystem", "name" => "Pair",
            "ports" => Any[Dict{String,Any}("name" => "p", "kind" => "power", "domain" => "Electrical",
                "node" => "z", "port" => "junction")],
            "diagram" => Dict{String,Any}(
                "nodes" => Any[
                    Dict{String,Any}("id" => "z", "name" => "Z", "block" => Dict("junction" => "0"),
                        "position" => Dict("x" => 0, "y" => 0)),
                    merge(Dict{String,Any}("id" => "x", "name" => "X",
                        "position" => Dict("x" => 0, "y" => 0)), _lk_instance()),
                    merge(Dict{String,Any}("id" => "y", "name" => "Y",
                        "position" => Dict("x" => 0, "y" => 0)),
                        _lk_instance(; params = Dict{String,Any}("R1/r" => "3.0"))),
                ],
                "connections" => Any[
                    Dict{String,Any}("id" => "b1", "kind" => "bond",
                        "from" => Dict("node" => "z"), "to" => Dict("node" => "x", "port" => "p")),
                    Dict{String,Any}("id" => "b2", "kind" => "bond",
                        "from" => Dict("node" => "z"), "to" => Dict("node" => "y", "port" => "p")),
                ],
            ),
            "pins" => Dict{String,Any}("params" => Any["X/R1/r"]),
        )
        linked = _lk_model(
            ["A" => _lk_instance(; ref = "project:Pair",
                params = Dict{String,Any}("X/R1/r" => "8.0"))];
            definitions = Dict{String,Any}(
                "Pair" => outer,
                "Branch" => _lk_branch(; pins = Dict{String,Any}("params" => Any["R1/r"])),
            ),
        )
        flat = Compile.flatten(IR.parse_model(linked))
        @test isempty(_lk_diags(flat))
        @test _lk_param(flat, "A/X/R1/r") == 8.0
        @test _lk_param(flat, "A/Y/R1/r") == 3.0
    end

    @testset "the library file, the document's copy and the catalog" begin
        mktempdir() do dir
            mkpath(joinpath(dir, "library"))
            write(joinpath(dir, "library", "Branch.bgsub.json"),
                JSON3.write(_lk_branch(; r = "22.0")))
            linked = _lk_model(["A" => _lk_instance()])
            flat = Compile.flatten(IR.parse_model(linked); project_dir = dir)
            @test isempty(_lk_diags(flat))
            @test _lk_param(flat, "A/R1/r") == 22.0

            # Without the project the reference is unknown.
            @test "E101" in _lk_codes(Compile.flatten(IR.parse_model(linked)))

            # The editor's unsaved copy wins over the file.
            unsaved = _lk_model(["A" => _lk_instance()];
                definitions = Dict{String,Any}("Branch" => _lk_branch(; r = "33.0")))
            @test _lk_param(Compile.flatten(IR.parse_model(unsaved); project_dir = dir),
                "A/R1/r") == 33.0

            # A parameter override of a run reaches an instance's block.
            over = BGSim.flatten_with_overrides(IR.parse_model(linked),
                Dict{String,Any}("A/R1/r" => 4.0); project_dir = dir)
            @test _lk_param(over, "A/R1/r") == 4.0

            entry = only(b for b in Library.catalog(dir).blocks if b.ref == "project:Branch")
            @test entry.subsystem === true
            @test entry.path == "library/Branch.bgsub.json"
            @test [p.name for p in entry.ports] == ["p"]
            @test only(entry.ports).domain == "Electrical"
            @test isempty(entry.parameters) && isempty(entry.source)

            # A code block of the same name wins, as in the catalog, and the clash is reported.
            write(joinpath(dir, "library", "Twin.bgsub.json"), JSON3.write(_lk_branch()))
            write(joinpath(dir, "library", "Twin.jl"), read(joinpath(_LK_ROOT, "julia", "BGSim", "stdlib", "bondgraph", "R.jl"), String))
            twin = Compile.flatten(IR.parse_model(linked); project_dir = dir)
            @test any(d -> d.code == "E101" && occursin("Twin.jl", d.message), twin.diagnostics)
            @test only(b for b in Library.catalog(dir).blocks if b.ref == "project:Twin").source != ""
            rm(joinpath(dir, "library", "Twin.jl")); rm(joinpath(dir, "library", "Twin.bgsub.json"))

            # A file that is not a definition is reported, not thrown.
            write(joinpath(dir, "library", "Broken.bgsub.json"), "{\"format\": 3}")
            broken = _lk_model(["A" => _lk_instance(; ref = "project:Broken")])
            codes = _lk_codes(Compile.flatten(IR.parse_model(broken); project_dir = dir))
            @test "E101" in codes
        end
    end
end

@testset "linked subsystems: the contract fixture" begin
    fixtures = joinpath(_LK_ROOT, "contracts", "fixtures", "model", "valid")
    linked = Compile.flatten(IR.parse_model(_lk_read(joinpath(fixtures, "model.linked-subsystem.json"))))
    drawn = Compile.flatten(IR.parse_model(_lk_read(joinpath(fixtures, "model.linked-subsystem.drawn.json"))))
    @test _lk_lines(linked) == _lk_lines(drawn)
    @test _lk_param(linked, "A/R1/r") == 10.0
    @test _lk_param(linked, "B/R1/r") == 47.0
    @test isempty(_lk_diags(linked))
end
