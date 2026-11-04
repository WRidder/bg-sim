# The numeric library of the code cells (`cells.jl`). Every function here is pure: numbers and
# arrays in, numbers and arrays out. A cell can reach nothing else. New analysis belongs here.

_cell_fail(message) = throw(ConstFoldError(message))

function _cell_real(v, what)
    v isa AbstractVector || _cell_fail("$what needs a vector")
    eltype(v) <: Complex && _cell_fail("$what needs a real vector; use abs(...) or real(...)")
    return v
end

function _cell_some(v, what)
    _cell_real(v, what)
    isempty(v) && _cell_fail("$what of an empty vector")
    return v
end

function _cell_size(n)
    (n isa Real && isinteger(n) && n >= 0) || _cell_fail("a size must be a whole number")
    return Int(n)
end

# ------------------------------------------------------------------------- statistics

_cell_mean(v) = sum(_cell_some(v, "mean")) / length(v)

function _cell_var(v)
    length(_cell_some(v, "var")) < 2 && return 0.0
    m = _cell_mean(v)
    return sum(abs2, v .- m) / (length(v) - 1)
end

function _cell_percentile(v, p)
    s = sort(_cell_some(v, "percentile"))
    0 <= p <= 100 || _cell_fail("a percentile is between 0 and 100")
    at = 1 + (length(s) - 1) * p / 100
    low = floor(Int, at)
    high = min(low + 1, length(s))
    return s[low] + (s[high] - s[low]) * (at - low)
end

# ------------------------------------------------------------------------- calculus

function _cell_same(x, y, what)
    _cell_real(x, what)
    _cell_real(y, what)
    length(x) == length(y) || _cell_fail("$what needs vectors of the same length")
end

function _cell_trapz(y, x)
    _cell_same(y, x, "trapz")
    length(y) < 2 && return 0.0
    return sum((x[i + 1] - x[i]) * (y[i + 1] + y[i]) / 2 for i in 1:(length(y) - 1))
end

function _cell_cumtrapz(y, x)
    _cell_same(y, x, "cumtrapz")
    out = zeros(Float64, length(y))
    for i in 2:length(y)
        out[i] = out[i - 1] + (x[i] - x[i - 1]) * (y[i] + y[i - 1]) / 2
    end
    return out
end

function _cell_gradient(y, x)
    _cell_same(y, x, "gradient")
    n = length(y)
    n < 2 && _cell_fail("gradient needs two points")
    out = zeros(Float64, n)
    out[1] = (y[2] - y[1]) / (x[2] - x[1])
    out[n] = (y[n] - y[n - 1]) / (x[n] - x[n - 1])
    for i in 2:(n - 1)
        out[i] = (y[i + 1] - y[i - 1]) / (x[i + 1] - x[i - 1])
    end
    return out
end

function _cell_interp(at, xs, ys)
    _cell_same(xs, ys, "interp")
    isempty(xs) && _cell_fail("interp on empty vectors")
    one_point = function (q)
        q <= xs[1] && return float(ys[1])
        q >= xs[end] && return float(ys[end])
        i = searchsortedlast(xs, q)
        xs[i + 1] == xs[i] && return float(ys[i])
        return ys[i] + (ys[i + 1] - ys[i]) * (q - xs[i]) / (xs[i + 1] - xs[i])
    end
    return at isa AbstractArray ? map(one_point, at) : one_point(at)
end

"""The local maxima of `y`, as indices; plateaus count once, at their first sample."""
function _cell_peaks(y)
    _cell_real(y, "peaks")
    out = Int[]
    i = 2
    n = length(y)
    while i < n
        if y[i] > y[i - 1]
            j = i
            while j < n && y[j + 1] == y[i]
                j += 1
            end
            j < n && y[j + 1] < y[i] && push!(out, i)
            i = j + 1
        else
            i += 1
        end
    end
    return out
end

"""The indices `i` where `y` crosses `level` between samples `i` and `i + 1`."""
function _cell_crossings(y, level)
    _cell_real(y, "crossings")
    return [i for i in 1:(length(y) - 1) if (y[i] - level) * (y[i + 1] - level) < 0 || y[i] == level]
end

# ------------------------------------------------------------------------- spectra

function _cell_radix2!(a::Vector{ComplexF64}, sign::Int)
    n = length(a)
    j = 0
    for i in 1:(n - 1)
        bit = n >> 1
        while j & bit != 0
            j ⊻= bit
            bit >>= 1
        end
        j |= bit
        i < j && ((a[i + 1], a[j + 1]) = (a[j + 1], a[i + 1]))
    end
    len = 2
    while len <= n
        step = cispi(sign * 2 / len)
        for start in 1:len:n
            w = ComplexF64(1)
            for k in 0:(len ÷ 2 - 1)
                u = a[start + k]
                v = a[start + k + len ÷ 2] * w
                a[start + k] = u + v
                a[start + k + len ÷ 2] = u - v
                w *= step
            end
        end
        len <<= 1
    end
    return a
end

# Any length, by Bluestein's chirp transform over a power-of-two convolution.
function _cell_dft(x::Vector{ComplexF64}, sign::Int)
    n = length(x)
    n <= 1 && return copy(x)
    ispow2(n) && return _cell_radix2!(copy(x), sign)
    chirp = ComplexF64[cispi(sign * mod(k * k, 2n) / n) for k in 0:(n - 1)]
    m = nextpow(2, 2n - 1)
    a = zeros(ComplexF64, m)
    b = zeros(ComplexF64, m)
    a[1:n] .= x .* chirp
    b[1:n] .= conj.(chirp)
    for k in 1:(n - 1)
        b[m - k + 1] = conj(chirp[k + 1])
    end
    _cell_radix2!(a, -1)
    _cell_radix2!(b, -1)
    c = _cell_radix2!(a .* b, 1) ./ m
    return ComplexF64[chirp[k] * c[k] for k in 1:n]
end

function _cell_fft(y)
    y isa AbstractVector || _cell_fail("fft needs a vector")
    return _cell_dft(ComplexF64.(y), -1)
end

function _cell_ifft(y)
    y isa AbstractVector || _cell_fail("ifft needs a vector")
    return _cell_dft(ComplexF64.(y), 1) ./ length(y)
end

function _cell_fftfreq(n, fs)
    count = _cell_size(n)
    fs > 0 || _cell_fail("the sample rate must be positive")
    return Float64[(k < (count + 1) ÷ 2 ? k : k - count) * fs / count for k in 0:(count - 1)]
end

"""The sample rate of a uniform time vector; a non-uniform one is an error with the way out."""
function _cell_samplerate(t)
    length(_cell_real(t, "samplerate")) >= 2 || _cell_fail("samplerate needs two times")
    h = (t[end] - t[1]) / (length(t) - 1)
    h > 0 || _cell_fail("the time vector does not increase")
    maximum(abs(t[i + 1] - t[i] - h) for i in 1:(length(t) - 1)) <= 0.01 * h ||
        _cell_fail("the samples are not uniform: use `u = linspace(t[1], t[end], length(t))` " *
                   "and `interp(u, t, y)` first")
    return 1 / h
end

"""One-sided amplitudes: a sine of amplitude A shows as A, the mean as itself."""
function _cell_amplitude(y)
    n = length(_cell_real(y, "amplitude"))
    n == 0 && return Float64[]
    x = _cell_fft(y)
    half = n ÷ 2 + 1
    out = abs.(x[1:half]) ./ n
    last_doubled = iseven(n) ? half - 1 : half
    out[2:last_doubled] .*= 2
    return out
end

"""The frequencies of `amplitude`, for a uniform time vector."""
function _cell_ampfreq(t)
    fs = _cell_samplerate(t)
    n = length(t)
    return Float64[k * fs / n for k in 0:(n ÷ 2)]
end

_cell_hann(n) = Float64[_cell_size(n) <= 1 ? 1.0 : 0.5 - 0.5 * cospi(2k / (n - 1)) for k in 0:(n - 1)]
_cell_hamming(n) = Float64[_cell_size(n) <= 1 ? 1.0 : 0.54 - 0.46 * cospi(2k / (n - 1)) for k in 0:(n - 1)]
_cell_blackman(n) = Float64[
    _cell_size(n) <= 1 ? 1.0 : 0.42 - 0.5 * cospi(2k / (n - 1)) + 0.08 * cospi(4k / (n - 1))
    for k in 0:(n - 1)
]

function _cell_convolve(a, b)
    (isempty(_cell_real(a, "convolve")) || isempty(_cell_real(b, "convolve"))) && return Float64[]
    n = length(a) + length(b) - 1
    m = nextpow(2, n)
    x = zeros(ComplexF64, m)
    y = zeros(ComplexF64, m)
    x[1:length(a)] .= a
    y[1:length(b)] .= b
    _cell_radix2!(x, -1)
    _cell_radix2!(y, -1)
    return real.(_cell_radix2!(x .* y, 1) ./ m)[1:n]
end

_cell_xcorr(a, b) = _cell_convolve(a, reverse(_cell_real(b, "xcorr")))

# ------------------------------------------------------------------------- filters

function _cell_movmean(y, n)
    _cell_real(y, "movmean")
    width = _cell_size(n)
    width >= 1 || _cell_fail("the window must hold at least one sample")
    out = similar(y, Float64)
    half = (width - 1) ÷ 2
    for i in eachindex(y)
        low = max(1, i - half)
        high = min(length(y), low + width - 1)
        out[i] = sum(view(y, low:high)) / (high - low + 1)
    end
    return out
end

function _cell_detrend(y)
    n = length(_cell_real(y, "detrend"))
    n < 2 && return y .- (n == 1 ? y[1] : 0.0)
    x = collect(0.0:(n - 1))
    return y .- _cell_polyval(_cell_polyfit(x, y, 1), x)
end

function _cell_poly(roots::Vector{ComplexF64})
    p = ComplexF64[1]
    for r in roots
        p = [p; 0] .- r .* [0; p]
    end
    return real.(p)
end

function _cell_butter(order, cutoff, high::Bool)
    n = _cell_size(order)
    1 <= n <= 12 || _cell_fail("a Butterworth order is 1 to 12")
    0 < cutoff < 1 || _cell_fail("the cutoff is a fraction of the Nyquist frequency, between 0 and 1")
    warped = tan(pi * cutoff / 2)
    poles = ComplexF64[]
    for k in 0:(n - 1)
        p = cispi((2k + n + 1) / (2n))
        s = high ? warped / p : warped * p
        push!(poles, (1 + s) / (1 - s))
    end
    a = _cell_poly(poles)
    b = _cell_poly(fill(ComplexF64(high ? 1 : -1), n))
    at = high ? -1.0 : 1.0  # unit gain at Nyquist or at DC
    gain = sum(a[k + 1] * at^k for k in 0:n) / sum(b[k + 1] * at^k for k in 0:n)
    return (b .* gain, a)
end

function _cell_filter_core(b, a, y, state)
    n = max(length(a), length(b))
    bb = [b; zeros(n - length(b))] ./ a[1]
    aa = [a; zeros(n - length(a))] ./ a[1]
    z = copy(state)
    out = zeros(Float64, length(y))
    for i in eachindex(y)
        out[i] = bb[1] * y[i] + (n > 1 ? z[1] : 0.0)
        for k in 1:(n - 2)
            z[k] = bb[k + 1] * y[i] + z[k + 1] - aa[k + 1] * out[i]
        end
        n > 1 && (z[n - 1] = bb[n] * y[i] - aa[n] * out[i])
    end
    return out
end

function _cell_check_filter(b, a, y)
    _cell_real(b, "filter")
    _cell_real(a, "filter")
    _cell_real(y, "filter")
    (isempty(a) || a[1] == 0) && _cell_fail("the first denominator coefficient must not be zero")
end

function _cell_filter(b, a, y)
    _cell_check_filter(b, a, y)
    return _cell_filter_core(b, a, y, zeros(Float64, max(length(a), length(b)) - 1))
end

# The start state of a filter already settled on a unit input.
function _cell_filter_zi(b, a)
    n = max(length(a), length(b))
    n == 1 && return Float64[]
    bb = [b; zeros(n - length(b))] ./ a[1]
    aa = [a; zeros(n - length(a))] ./ a[1]
    m = n - 1
    system = zeros(Float64, m, m)
    for i in 1:m
        system[i, i] = 1.0
        system[i, 1] += aa[i + 1]
        i < m && (system[i, i + 1] -= 1.0)
    end
    return system \ (bb[2:end] .- aa[2:end] .* bb[1])
end

"""Zero-phase filtering: forward and backward, with odd reflections at both ends."""
function _cell_filtfilt(b, a, y)
    _cell_check_filter(b, a, y)
    pad = 3 * max(length(a), length(b))
    length(y) > pad || _cell_fail("filtfilt needs more than $pad samples")
    head = 2y[1] .- y[(pad + 1):-1:2]
    tail = 2y[end] .- y[(end - 1):-1:(end - pad)]
    long = vcat(head, y, tail)
    zi = _cell_filter_zi(b, a)
    forward = _cell_filter_core(b, a, long, zi .* long[1])
    backward = _cell_filter_core(b, a, reverse(forward), zi .* forward[end])
    return reverse(backward)[(pad + 1):(pad + length(y))]
end

# ------------------------------------------------------------------------- fits and matrices

function _cell_polyfit(x, y, order)
    _cell_same(x, y, "polyfit")
    n = _cell_size(order)
    length(x) > n || _cell_fail("polyfit needs more points than its order")
    design = Float64[Float64(xi)^k for xi in x, k in 0:n]
    return design \ Float64.(y)
end

function _cell_polyval(p, x)
    _cell_real(p, "polyval")
    horner(q) = foldr((c, acc) -> c + q * acc, p; init = zero(float(q)))
    return x isa AbstractArray ? map(horner, x) : horner(x)
end

function _cell_matrix(A, what)
    A isa AbstractMatrix || _cell_fail("$what needs a matrix")
    return A
end

function _cell_square(A, what)
    _cell_matrix(A, what)
    size(A, 1) == size(A, 2) || _cell_fail("$what needs a square matrix")
    return A
end

function _cell_solve(A, b)
    try
        return A \ b
    catch err
        err isa LinearAlgebra.SingularException && _cell_fail("the matrix of `\\` is singular")
        rethrow()
    end
end

function _cell_stack(args, horizontal::Bool)
    parts = Any[a isa Number ? [a] : a for a in args]
    try
        return horizontal ? hcat(parts...) : vcat(parts...)
    catch err
        err isa DimensionMismatch && _cell_fail("the sizes do not fit together")
        rethrow()
    end
end

# name => (argument counts, function). A cell's own function of the same name takes precedence.
const CELL_LIBRARY = Dict{Symbol,Tuple{Any,Function}}(
    :length => (1, length),
    :sum => (1, v -> sum(v)),
    :prod => (1, v -> prod(v)),
    :mean => (1, _cell_mean),
    :var => (1, _cell_var),
    :std => (1, v -> sqrt(_cell_var(v))),
    :median => (1, v -> _cell_percentile(v, 50)),
    :percentile => (2, _cell_percentile),
    :rms => (1, v -> sqrt(_cell_mean(abs2.(v)))),
    :maximum => (1, v -> maximum(_cell_some(v, "maximum"))),
    :minimum => (1, v -> minimum(_cell_some(v, "minimum"))),
    :argmax => (1, v -> argmax(_cell_some(v, "argmax"))),
    :argmin => (1, v -> argmin(_cell_some(v, "argmin"))),
    :first => (1, v -> first(_cell_some(v, "first"))),
    :last => (1, v -> last(_cell_some(v, "last"))),
    :diff => (1, v -> diff(_cell_real(v, "diff"))),
    :cumsum => (1, v -> cumsum(_cell_real(v, "cumsum"))),
    :reverse => (1, v -> reverse(v)),
    :sort => (1, v -> sort(_cell_real(v, "sort"))),
    :any => (1, v -> any(identity, v)),
    :all => (1, v -> all(identity, v)),
    :count => (1, v -> count(identity, v)),
    :findfirst => (1, v -> something(findfirst(identity, v), 0)),
    :findall => (1, v -> findall(identity, v)),
    :trapz => (2, _cell_trapz),
    :cumtrapz => (2, _cell_cumtrapz),
    :gradient => (2, _cell_gradient),
    :interp => (3, _cell_interp),
    :peaks => (1, _cell_peaks),
    :crossings => (2, _cell_crossings),
    :fft => (1, _cell_fft),
    :ifft => (1, _cell_ifft),
    :fftfreq => (2, _cell_fftfreq),
    :samplerate => (1, _cell_samplerate),
    :amplitude => (1, _cell_amplitude),
    :ampfreq => (1, _cell_ampfreq),
    :hann => (1, _cell_hann),
    :hamming => (1, _cell_hamming),
    :blackman => (1, _cell_blackman),
    :convolve => (2, _cell_convolve),
    :xcorr => (2, _cell_xcorr),
    :movmean => (2, _cell_movmean),
    :detrend => (1, _cell_detrend),
    :butter => (2, (n, w) -> _cell_butter(n, w, false)),
    :butterhigh => (2, (n, w) -> _cell_butter(n, w, true)),
    :filter => (3, _cell_filter),
    :filtfilt => (3, _cell_filtfilt),
    :polyfit => (3, _cell_polyfit),
    :polyval => (2, _cell_polyval),
    :inv => (1, A -> _cell_solve(_cell_square(A, "inv"), Matrix{Float64}(LinearAlgebra.I, size(A)...))),
    :det => (1, A -> LinearAlgebra.det(_cell_square(A, "det"))),
    :rank => (1, A -> LinearAlgebra.rank(_cell_matrix(A, "rank"))),
    :trace => (1, A -> LinearAlgebra.tr(_cell_square(A, "trace"))),
    :eigvals => (1, A -> LinearAlgebra.eigvals(_cell_square(A, "eigvals"))),
    :svdvals => (1, A -> LinearAlgebra.svdvals(_cell_matrix(A, "svdvals"))),
    :pinv => (1, A -> LinearAlgebra.pinv(_cell_matrix(A, "pinv"))),
    :diag => (1, A -> LinearAlgebra.diag(_cell_matrix(A, "diag"))),
    :eye => (1, n -> Matrix{Float64}(LinearAlgebra.I, _cell_size(n), _cell_size(n))),
    :size => (1, A -> A isa AbstractArray ? collect(size(A)) : Int[]),
    :hcat => (1:64, (a...) -> _cell_stack(a, true)),
    :vcat => (1:64, (a...) -> _cell_stack(a, false)),
    :real => (1, x -> real.(x)),
    :imag => (1, x -> imag.(x)),
    :conj => (1, x -> conj.(x)),
    :angle => (1, x -> angle.(x)),
    :abs2 => (1, x -> abs2.(x)),
    :isnan => (1, x -> isnan.(x)),
    :isfinite => (1, x -> isfinite.(x)),
    :log2 => (1, x -> log2.(x)),
    :deg2rad => (1, x -> deg2rad.(x)),
    :rad2deg => (1, x -> rad2deg.(x)),
    :cbrt => (1, x -> cbrt.(x)),
)
