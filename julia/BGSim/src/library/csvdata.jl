# CSV input source (work package F5.1): project data files as simulation signals.
#
# A `stdlib:sources/CsvSource` node names a CSV file of the project (`constants.file`, a
# project-relative path such as `data/trajectory.csv`). The compiler loads the file while it
# instantiates the node, registers the parsed table under an id, and the block's equations
# call the intrinsic `csv_value(table, k, t)` with that id as a literal. Nothing of the table
# is unrolled into symbolic equations (unlike `stdlib:sources/TimeTable`): the generated
# right-hand side calls the opaque function `bg_csv`, which binary-searches the breakpoints.
#
# Why the id is a content hash. The table id is the first 48 bits of the SHA-256 of the file
# bytes plus every setting that changes the data (selected columns, method, offset, scale).
# The id is a literal in the flattened equations, so the compile key (J2.8) contains it: an
# edit to the CSV file, or to one of its settings, changes the key and misses the cache,
# whereas an unchanged file reuses the compiled system. 48 bits are exact in a Float64.
#
# The file settings are plain JSON entries of the node's `constants` (they are structural:
# the number of columns fixes the size of the output vector). The compiler consumes them
# here and replaces them with the block's two declared constants `N` (number of columns) and
# `table` (the id), see `csv_node_constants` and `src/compile/instantiate.jl`.
#
# Interpolation (all of it generic over `Real`, because the adaptive solver evaluates the
# right-hand side with `ForwardDiff.Dual` numbers, and exact for the derivative orders the
# index-reduction of MTK asks for):
#
#   * hold:   piecewise constant; derivatives are 0 (the data breakpoints become tstops);
#   * linear: piecewise linear; the slope is piecewise constant (breakpoints are tstops);
#   * cubic:  a not-a-knot cubic spline, C2 everywhere, with analytic derivatives up to the
#             third order. Not-a-knot (and not "natural") because the natural end condition
#             forces a zero second derivative that smooth trajectories do not have, which
#             would spoil the first and last few intervals.
#
# `bg_csv(table, k, order, t)` is the value (`order = 0`) or the `order`-th time derivative.
# The registered symbolic derivative of order n w.r.t. `t` is order n + 1, so MTK can
# differentiate a CSV signal as often as its structural analysis needs.

using SHA: sha256
using LinearAlgebra: Tridiagonal

"""
    CsvError(message, hint)

A problem with a CSV data file or its settings. The instantiation pass turns it into an
`E108` diagnostic at the node that names the file."""
struct CsvError <: Exception
    message::String
    hint::String
end
CsvError(message::AbstractString) = CsvError(String(message), "")

Base.showerror(io::IO, e::CsvError) = print(io, "CSV data: ", e.message)

"""
    CsvFile

One parsed CSV file: the header names, the optional `[unit]` of every column, and the data
column-major (`data[j][i]` is row `i` of column `j`)."""
struct CsvFile
    names::Vector{String}
    units::Vector{String}
    data::Vector{Vector{Float64}}
end

"""
    CsvTable

A CSV file after column selection, time offset, scaling and spline set-up. `time` holds the
breakpoints (already shifted by `time_offset`), `values[k]` the selected column `k` (already
scaled) and `d2[k]` its spline second derivatives (empty unless `method == 2`)."""
struct CsvTable
    id::Int
    file::String
    time::Vector{Float64}
    names::Vector{String}
    units::Vector{String}
    values::Vector{Vector{Float64}}
    d2::Vector{Vector{Float64}}
    method::Int
    extrapolation::Int
end

const CSV_METHOD_NAMES = ["hold", "linear", "cubic"]
const CSV_EXTRAPOLATION_NAMES = ["hold", "error"]

# ---------------------------------------------------------------------------------------
# Parsing
# ---------------------------------------------------------------------------------------

function _csv_split(line::AbstractString, delim::Char)
    fields = SubString{String}[]
    start = firstindex(line)
    inquote = false
    i = start
    last = lastindex(line)
    while i <= last
        c = line[i]
        if c == '"'
            inquote = !inquote
        elseif c == delim && !inquote
            push!(fields, SubString(line, start, prevind(line, i)))
            start = nextind(line, i)
        end
        i = nextind(line, i)
    end
    push!(fields, SubString(line, start, last))
    return fields
end

_csv_clean(s::AbstractString) = strip(strip(s), '"')

function _csv_header(field::AbstractString)
    text = String(_csv_clean(field))
    m = match(r"^(.*?)\s*\[([^\]]*)\]\s*$", text)
    m === nothing && return (text, "")
    return (String(strip(m.captures[1])), String(strip(m.captures[2])))
end

function _csv_delimiter(header::AbstractString)
    best = ','
    best_count = count(==(','), header)
    for d in (';', '\t')
        c = count(==(d), header)
        if c > best_count
            best = d
            best_count = c
        end
    end
    return best
end

"""
    parse_csv(text; file = "") -> CsvFile

Parse CSV text: a header row (required, `name` or `name [unit]` per column) and numeric rows.
The delimiter is the one of `, ; <tab>` that the header uses. A cell that is not a finite
number, or a row with the wrong number of cells, raises a [`CsvError`](@ref) that names the
row and the column."""
function parse_csv(text::AbstractString; file::AbstractString = "")
    where = isempty(file) ? "the CSV file" : "`$file`"
    if startswith(text, '﻿')
        text = text[nextind(text, 1):end]
    end
    lines = split(text, '\n')
    header_index = 0
    for (i, line) in enumerate(lines)
        if !isempty(strip(line))
            header_index = i
            break
        end
    end
    header_index == 0 && throw(CsvError(
        "$where is empty",
        "a CSV source needs a header row with the column names, then numeric rows",
    ))
    header_line = rstrip(lines[header_index], '\r')
    delim = _csv_delimiter(header_line)
    fields = _csv_split(header_line, delim)
    names = String[]
    units = String[]
    for f in fields
        name, unit = _csv_header(f)
        isempty(name) && throw(CsvError(
            "$where has an empty column name in the header (line $header_index)",
            "give every column a name, e.g. `t,q1,q2`",
        ))
        name in names && throw(CsvError(
            "$where has the column name `$name` twice in the header",
            "column names must be unique",
        ))
        push!(names, name)
        push!(units, unit)
    end
    ncol = length(names)
    data = [Float64[] for _ in 1:ncol]
    nlines = length(lines)
    sizehint = max(nlines - header_index, 0)
    foreach(col -> sizehint!(col, sizehint), data)
    row = 0
    for li in (header_index + 1):nlines
        line = lines[li]
        if li == nlines && isempty(strip(line))
            break
        end
        line = rstrip(line, '\r')
        isempty(strip(line)) && continue
        row += 1
        cells = _csv_split(line, delim)
        length(cells) == ncol || throw(CsvError(
            "$where, data row $row (line $li) has $(length(cells)) cells but the header has $ncol columns",
            "check the delimiter and that no cell is missing",
        ))
        for j in 1:ncol
            cell = _csv_clean(cells[j])
            value = tryparse(Float64, cell)
            if value === nothing || !isfinite(value)
                throw(CsvError(
                    "$where, data row $row, column `$(names[j])` (line $li): `$cell` is not a finite number",
                    "every data cell must be a plain number such as 1.25 or -3e-4",
                ))
            end
            push!(data[j], value)
        end
    end
    row == 0 && throw(CsvError(
        "$where has a header but no data rows",
        "add at least one numeric row below the header",
    ))
    return CsvFile(names, units, data)
end

# ---------------------------------------------------------------------------------------
# Splines and evaluation
# ---------------------------------------------------------------------------------------

"""
    spline_second_derivatives(x, y) -> Vector{Float64}

The second derivatives `M` at the breakpoints of the not-a-knot cubic spline through
`(x, y)` (natural for 3 points, empty for fewer than 3). One tridiagonal solve, O(n)."""
function spline_second_derivatives(x::Vector{Float64}, y::Vector{Float64})
    n = length(x)
    n < 3 && return zeros(n)
    h = diff(x)
    rhs = zeros(n - 2)
    for i in 2:(n - 1)
        rhs[i - 1] = 6 * ((y[i + 1] - y[i]) / h[i] - (y[i] - y[i - 1]) / h[i - 1])
    end
    m = n - 2
    lower = zeros(max(m - 1, 0))
    diagm = zeros(m)
    upper = zeros(max(m - 1, 0))
    for i in 2:(n - 1)
        r = i - 1
        diagm[r] = 2 * (h[i - 1] + h[i])
        r > 1 && (lower[r - 1] = h[i - 1])
        r < m && (upper[r] = h[i])
    end
    if n >= 4
        # Not-a-knot: M1 = ((h1+h2) M2 - h1 M3)/h2 and the mirror at the right end.
        diagm[1] += h[1] * (h[1] + h[2]) / h[2]
        upper[1] += -h[1]^2 / h[2]
        k = n - 1
        diagm[m] += h[k] * (h[k] + h[k - 1]) / h[k - 1]
        lower[m - 1] += -h[k]^2 / h[k - 1]
    end
    inner = Tridiagonal(lower, diagm, upper) \ rhs
    M = zeros(n)
    M[2:(n - 1)] = inner
    if n >= 4
        M[1] = ((h[1] + h[2]) * M[2] - h[1] * M[3]) / h[2]
        k = n - 1
        M[n] = ((h[k] + h[k - 1]) * M[n - 1] - h[k] * M[n - 2]) / h[k - 1]
    end
    return M
end

# Index of the interval `[x[k], x[k+1]]` that contains `t` (clamped to 1:n-1).
function _csv_segment(x::Vector{Float64}, t)
    n = length(x)
    lo = 1
    hi = n
    while hi - lo > 1
        mid = (lo + hi) >>> 1
        if t < x[mid]
            hi = mid
        else
            lo = mid
        end
    end
    return lo
end

"""
    csv_eval(table, k, order, t)

Column `k` of `table` at time `t`, or its `order`-th time derivative (0 to 3; higher orders
are 0). Outside the data the first/last value is held (derivatives 0) when the table was
loaded with `extrapolation = hold`; `extrapolation = error` throws a [`CsvError`](@ref).
Generic over `Real`, so `ForwardDiff` duals pass through."""
function csv_eval(tab::CsvTable, k::Int, order::Int, t::Real)
    x = tab.time
    n = length(x)
    1 <= k <= length(tab.values) || throw(CsvError(
        "column $k does not exist in `$(tab.file)` ($(length(tab.values)) columns selected)"
    ))
    y = tab.values[k]
    span = x[n] - x[1]
    if t < x[1] || t > x[n]
        slack = 1.0e-9 * max(span, 1.0)
        if tab.extrapolation == 1 && (t < x[1] - slack || t > x[n] + slack)
            throw(CsvError(
                "t = $(Float64(t isa Real ? real(t) : t)) is outside the data range [$(x[1]), $(x[n])] of `$(tab.file)`",
                "extend the file, shift it with `time_offset`, or set `extrapolation` to hold",
            ))
        end
        order == 0 || return zero(t)
        return t < x[1] ? one(t) * y[1] : one(t) * y[n]
    end
    n == 1 && return order == 0 ? one(t) * y[1] : zero(t)
    i = _csv_segment(x, t)
    h = x[i + 1] - x[i]
    if tab.method == 0
        return order == 0 ? one(t) * y[i] : zero(t)
    elseif tab.method == 1 || length(tab.d2[k]) < 3
        order >= 2 && return zero(t)
        slope = (y[i + 1] - y[i]) / h
        order == 1 && return one(t) * slope
        return y[i] + slope * (t - x[i])
    end
    M = tab.d2[k]
    a = x[i + 1] - t
    b = t - x[i]
    if order == 0
        return M[i] * a^3 / (6h) + M[i + 1] * b^3 / (6h) +
               (y[i] / h - M[i] * h / 6) * a + (y[i + 1] / h - M[i + 1] * h / 6) * b
    elseif order == 1
        return -M[i] * a^2 / (2h) + M[i + 1] * b^2 / (2h) -
               (y[i] / h - M[i] * h / 6) + (y[i + 1] / h - M[i + 1] * h / 6)
    elseif order == 2
        return (M[i] * a + M[i + 1] * b) / h
    elseif order == 3
        return one(t) * (M[i + 1] - M[i]) / h
    end
    return zero(t)
end

# ---------------------------------------------------------------------------------------
# The registry (lock-free reads, copy-on-write updates)
# ---------------------------------------------------------------------------------------

const CSV_TABLE_LIMIT = 64
const CSV_TABLES = Ref(Dict{Int,CsvTable}())
const CSV_ORDER = Int[]
const CSV_LOCK = ReentrantLock()

function _csv_register!(tab::CsvTable)
    lock(CSV_LOCK) do
        tables = CSV_TABLES[]
        haskey(tables, tab.id) && return nothing
        updated = copy(tables)
        updated[tab.id] = tab
        push!(CSV_ORDER, tab.id)
        while length(CSV_ORDER) > CSV_TABLE_LIMIT
            delete!(updated, popfirst!(CSV_ORDER))
        end
        CSV_TABLES[] = updated
    end
    return nothing
end

"""    csv_table(id) -> CsvTable

The registered table with this id (the literal in the flattened equations)."""
function csv_table(id::Integer)
    tab = get(CSV_TABLES[], Int(id), nothing)
    tab === nothing && throw(CsvError(
        "the CSV table $id is not loaded",
        "flatten the model again (run it) so the data file is read",
    ))
    return tab
end

"""    clear_csv_tables!()

Forget every registered table (the worker's `cache.clear`)."""
function clear_csv_tables!()
    lock(CSV_LOCK) do
        CSV_TABLES[] = Dict{Int,CsvTable}()
        empty!(CSV_ORDER)
    end
    return nothing
end

# Parsed files by content hash, so `model.check` and `run.start` do not parse a 100k-row file
# twice.
const CSV_FILE_CACHE = Dict{String,CsvFile}()
const CSV_FILE_ORDER = String[]

# ---------------------------------------------------------------------------------------
# The opaque functions
# ---------------------------------------------------------------------------------------

"""
    bg_csv(table, k, order, t)

The `csv_value` intrinsic as an opaque Symbolics function (value or `order`-th derivative of
column `k` of the registered table). Its symbolic derivative w.r.t. `t` is `order + 1`."""
function bg_csv(id::Real, k::Real, order::Real, t::Real)
    return csv_eval(csv_table(id), Int(k), Int(order), t)
end

Symbolics.@register_symbolic bg_csv(id::Real, k::Real, order::Real, t::Real)
Symbolics.@register_derivative bg_csv(id, k, order, t) 4 bg_csv(id, k, order + 1, t)

# ---------------------------------------------------------------------------------------
# Loading a node's file
# ---------------------------------------------------------------------------------------

"""
    csv_resolve_path(project_dir, file) -> String

The absolute path of the project-relative `file`. Absolute paths, `..` escapes and a missing
project are refused with a [`CsvError`] that says what to do instead."""
function csv_resolve_path(project_dir::Union{Nothing,AbstractString}, file::AbstractString)
    isempty(strip(file)) && throw(CsvError(
        "no CSV file is selected",
        "set the node's `file` to a data file of the project, e.g. `data/trajectory.csv`",
    ))
    project_dir === nothing && throw(CsvError(
        "`$file` cannot be read because the model is not part of a project",
        "open the model from a project and put the file in its `data/` folder",
    ))
    inside_hint = "put the file in the project's `data/` folder and refer to it as `data/<name>.csv`"
    (isabspath(file) || startswith(file, "/") || startswith(file, "\\") ||
     occursin(r"^[A-Za-z]:", file)) && throw(CsvError(
        "`$file` is an absolute path; data files must be inside the project", inside_hint,
    ))
    root = abspath(String(project_dir))
    full = normpath(joinpath(root, replace(String(file), '\\' => '/')))
    rel = relpath(full, root)
    (startswith(rel, "..") || isabspath(rel)) && throw(CsvError(
        "`$file` is outside the project", inside_hint,
    ))
    return full
end

function _csv_setting_int(value, names::Vector{String}, what::AbstractString)
    if value isa AbstractString
        k = findfirst(==(lowercase(String(value))), names)
        k === nothing && throw(CsvError(
            "`$what` is `$value`; choose one of $(join(names, ", "))",
            "use the inspector's drop-down",
        ))
        return k - 1
    end
    value isa Integer || throw(CsvError(
        "`$what` must be one of $(join(names, ", ")) (0 to $(length(names) - 1))",
        "use the inspector's drop-down",
    ))
    0 <= value < length(names) || throw(CsvError(
        "`$what` = $value is not one of $(join(["$(i - 1) = $n" for (i, n) in enumerate(names)], ", "))",
        "use the inspector's drop-down",
    ))
    return Int(value)
end

function _csv_setting_real(value, what::AbstractString, default::Float64)
    value === nothing && return default
    value isa Real && !(value isa Bool) && isfinite(value) && return Float64(value)
    if value isa AbstractString
        parsed = tryparse(Float64, strip(value))
        parsed !== nothing && isfinite(parsed) && return parsed
    end
    throw(CsvError("`$what` must be a finite number, got `$value`"))
end

function _csv_setting_list(value)
    value === nothing && return String[]
    if value isa AbstractString
        return String[strip(s) for s in split(value, ',') if !isempty(strip(s))]
    end
    value isa AbstractVector && return String[strip(String(s)) for s in value]
    throw(CsvError("`columns` must be a comma separated list of column names"))
end

"""
    load_csv_table(project_dir, settings) -> CsvTable

Read and register the table that the node `settings` (the node's `constants`) describe:
`file` (required), `time_column`, `columns`, `method` (`0/1/2` or `hold/linear/cubic`),
`extrapolation` (`0/1` or `hold/error`), `time_offset`, `scale`."""
function load_csv_table(project_dir, settings::AbstractDict)
    file = String(get(settings, "file", ""))
    path = csv_resolve_path(project_dir, file)
    isfile(path) || throw(CsvError(
        "the data file `$file` does not exist in the project",
        "upload it to the project's `data/` folder or pick another file",
    ))
    bytes = read(path)
    method = _csv_setting_int(get(settings, "method", 2), CSV_METHOD_NAMES, "method")
    extrapolation = _csv_setting_int(
        get(settings, "extrapolation", 0), CSV_EXTRAPOLATION_NAMES, "extrapolation"
    )
    offset = _csv_setting_real(get(settings, "time_offset", nothing), "time_offset", 0.0)
    scale = _csv_setting_real(get(settings, "scale", nothing), "scale", 1.0)
    time_column = String(get(settings, "time_column", ""))
    wanted = _csv_setting_list(get(settings, "columns", nothing))

    digest = sha256(bytes)
    filehash = bytes2hex(digest)
    parsed = lock(CSV_LOCK) do
        get(CSV_FILE_CACHE, filehash, nothing)
    end
    if parsed === nothing
        parsed = parse_csv(String(copy(bytes)); file = file)
        lock(CSV_LOCK) do
            CSV_FILE_CACHE[filehash] = parsed
            push!(CSV_FILE_ORDER, filehash)
            while length(CSV_FILE_ORDER) > 8
                delete!(CSV_FILE_CACHE, popfirst!(CSV_FILE_ORDER))
            end
        end
    end

    names = parsed.names
    tindex = 1
    if !isempty(time_column)
        tindex = something(findfirst(==(time_column), names), 0)
        tindex == 0 && throw(CsvError(
            "`$file` has no time column `$time_column`; its columns are $(join(names, ", "))",
            "set `time_column` to one of the header names",
        ))
    end
    selected = Int[]
    if isempty(wanted)
        selected = [j for j in eachindex(names) if j != tindex]
    else
        for w in wanted
            j = findfirst(==(w), names)
            j === nothing && throw(CsvError(
                "`$file` has no column `$w`; its columns are $(join(names, ", "))",
                "set `columns` to header names, separated by commas",
            ))
            j == tindex && throw(CsvError(
                "column `$w` of `$file` is the time column and cannot be an output",
                "remove it from `columns`",
            ))
            push!(selected, j)
        end
    end
    isempty(selected) && throw(CsvError(
        "`$file` has no data column besides the time column `$(names[tindex])`",
        "add at least one value column",
    ))

    time = parsed.data[tindex]
    for i in 2:length(time)
        time[i] > time[i - 1] || throw(CsvError(
            "the time column `$(names[tindex])` of `$file` is not strictly increasing at data row $i ($(time[i - 1]) then $(time[i]))",
            "sort the rows by time and remove duplicate time stamps",
        ))
    end
    shifted = offset == 0.0 ? copy(time) : time .+ offset
    values = [scale == 1.0 ? copy(parsed.data[j]) : parsed.data[j] .* scale for j in selected]
    d2 = if method == 2
        [spline_second_derivatives(shifted, v) for v in values]
    else
        [Float64[] for _ in values]
    end

    key = IOBuffer()
    print(key, filehash, '|', tindex, '|', join(selected, ','), '|', method, '|',
        extrapolation, '|', repr(offset), '|', repr(scale))
    id = Int(foldl((a, b) -> (a << 8) | UInt64(b), sha256(take!(key))[1:6]; init = UInt64(0)))
    tab = CsvTable(
        id, file, shifted, names[selected], parsed.units[selected], values, d2, method,
        extrapolation,
    )
    _csv_register!(tab)
    return tab
end

"""
    csv_tstops(tab, t_start, t_end) -> Vector{Float64}

The times the solver must not step across: every data breakpoint inside `(t_start, t_end]`
for hold and linear tables (the signal or its slope jumps there), and for every table the
first and last breakpoint (the extrapolation corner)."""
function csv_tstops(tab::CsvTable, t_start::Real, t_end::Real)
    x = tab.time
    out = Float64[]
    if tab.method == 2
        for v in (x[1], x[end])
            t_start < v <= t_end && push!(out, v)
        end
    else
        lo = searchsortedfirst(x, nextfloat(Float64(t_start)))
        hi = searchsortedlast(x, Float64(t_end))
        lo <= hi && append!(out, @view x[lo:hi])
    end
    return out
end

"""
    csv_tables_in(flat) -> Vector{CsvTable}

The registered tables that the flattened model's equations reference (the literal first
argument of each `bg_csv`/`csv_value` call), in first-use order."""
function csv_tables_in(equations)
    ids = Int[]
    seen = Set{Int}()
    function walk(e)
        if e isa Call
            if e.fn isa Name && e.fn.name === :csv_value && !isempty(e.args) &&
               e.args[1] isa Lit && e.args[1].value isa Integer
                id = Int(e.args[1].value)
                if !(id in seen)
                    push!(seen, id)
                    push!(ids, id)
                end
            end
            foreach(walk, e.args)
        elseif e isa BinOp
            walk(e.lhs)
            walk(e.rhs)
        elseif e isa UnOp
            walk(e.operand)
        elseif e isa IfElse
            walk(e.cond)
            walk(e.then)
            walk(e.otherwise)
        elseif e isa Comparison
            walk(e.lhs)
            walk(e.rhs)
        elseif e isa BoolOp
            foreach(walk, e.operands)
        end
        return nothing
    end
    for eq in equations
        walk(eq.rhs)
        walk(eq.lhs)
    end
    return CsvTable[csv_table(id) for id in ids if haskey(CSV_TABLES[], id)]
end

"""
    csv_model_tstops(flat, t_start, t_end) -> Vector{Float64}

The solver `tstops` that the CSV tables of a flattened model need (see [`csv_tstops`](@ref)),
sorted and without duplicates; empty when the model reads no CSV file."""
function csv_model_tstops(flat, t_start::Real, t_end::Real)
    tables = csv_tables_in(flat.equations)
    isempty(tables) && return Float64[]
    out = Float64[]
    for tab in tables
        append!(out, csv_tstops(tab, t_start, t_end))
    end
    return sort!(unique!(out))
end
