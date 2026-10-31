# The seeded random draws and the delay line of the discrete intrinsics (work package J-EX9,
# spec "Seeded noise and delay", plan/EXPORT_PLAN.md section 5.5).
#
# `noise_uniform(seed, k)` and `noise_normal(seed, k)` are *counter-based*: a sample is a pure
# function of the seed and the sample index `k`, so a noise source keeps no generator state
# beyond its tick counter, which is an ordinary held value. Nothing has to be reset,
# snapshotted or restored besides the discrete state that already is, and the same `(seed, k)`
# gives the same double in the simulator and in the exported C code (`bg_intrinsics.c`), bit
# for bit. The C twins follow these bodies operation for operation; the golden test
# (test/test_export_intrinsics.jl) compares them bitwise.
#
# The specification, in full:
#
#   1. `seed` and `k` are integer-valued numbers. A value that is not finite, not an integer
#      or outside [-2^63, 2^63) gives NaN. They become 64-bit two's complement words S and K.
#   2. Bits: SplitMix64 (Steele, Lea, Flood 2014; the `splitmix64` finalizer of Vigna):
#        mix(z) = z ^= z >> 30; z *= 0xBF58476D1CE4E5B9; z ^= z >> 27;
#                 z *= 0x94D049BB133111EB; z ^= z >> 31          (all mod 2^64)
#        key    = mix(S + G)                 G = 0x9E3779B97F4A7C15
#        bits   = mix(key + (K + 1) * G)
#      i.e. `bits` is output number K of a SplitMix64 generator whose state starts at `key`,
#      and `key` is the first output of a SplitMix64 generator started at the seed.
#   3. Uniform: j = bits >> 12 (52 bits), u = (2j + 1) * 2^-53, so u is in (0, 1), never 0
#      or 1, symmetric about 1/2, and computed exactly.
#   4. Normal: Wichura's AS 241 (PPND16, 1988), the inverse of the standard normal CDF with
#      a relative accuracy of about 1e-16, applied to u. Its tails need log(r) for
#      r = min(u, 1 - u) >= 2^-53: `noise_log` below, a fixed polynomial evaluated in plain
#      IEEE arithmetic (frexp, +, -, *, /), not the platform's `log`. `sqrt` is correctly
#      rounded by IEEE 754 everywhere. So every operation of the normal transform is exactly
#      rounded and identical in Julia and C; a libm `log`/`cos` (Box-Muller) differs in the
#      last bit between platforms and would break bit-identity. The largest |value| is 8.3
#      (u = 2^-53).
#
#  Constants are written as hex floats, the same digits in Julia and C. The polynomials are
#  evaluated by Horner's rule in the order written; neither Julia nor ISO C contracts `a*b + c`
#  into a fused multiply-add (the C file disables contraction for compilers that would).

const NOISE_GAMMA = 0x9e3779b97f4a7c15

"""    noise_mix(z::UInt64) -> UInt64

The SplitMix64 finalizer (a bijection on 64-bit words)."""
@inline function noise_mix(z::UInt64)
    z = (z ⊻ (z >> 30)) * 0xbf58476d1ce4e5b9
    z = (z ⊻ (z >> 27)) * 0x94d049bb133111eb
    return z ⊻ (z >> 31)
end

# Step 1: an integer-valued number as Int64; `nothing` for NaN, Inf, a fraction or a value
# outside [-2^63, 2^63).
_noise_int(x::Integer) = typemin(Int64) <= x <= typemax(Int64) ? Int64(x) : nothing
_noise_int(x::Bool) = Int64(x)
function _noise_int(x::Real)
    y = Float64(x)
    (y >= -0x1p63 && y < 0x1p63 && y == floor(y)) || return nothing
    return unsafe_trunc(Int64, y)
end

"""    noise_bits(seed, k) -> Union{UInt64,Nothing}

The 64 random bits of sample `k` of the stream `seed` (steps 1 and 2 of the file header)."""
function noise_bits(seed::Real, k::Real)
    s = _noise_int(seed)
    n = _noise_int(k)
    (s === nothing || n === nothing) && return nothing
    key = noise_mix(reinterpret(UInt64, s) + NOISE_GAMMA)
    return noise_mix(key + (reinterpret(UInt64, n) + 0x0000000000000001) * NOISE_GAMMA)
end

"""
    bg_noise_uniform(seed, k) -> Float64

Sample `k` of the uniform stream `seed`: `(2j + 1) * 2^-53` in (0, 1), with `j` the top 52 of
the SplitMix64 bits (file header). NaN when `seed` or `k` is not an integer. The intrinsic
`noise_uniform(seed, k)` of discrete code.
"""
function bg_noise_uniform(seed::Real, k::Real)
    z = noise_bits(seed, k)
    z === nothing && return NaN
    j = z >> 12
    return Float64(2 * j + 1) * 0x1p-53
end

"""
    bg_noise_normal(seed, k) -> Float64

Sample `k` of the standard normal stream `seed`: AS 241 applied to
`bg_noise_uniform(seed, k)` (file header). NaN when `seed` or `k` is not an integer. The
intrinsic `noise_normal(seed, k)` of discrete code.
"""
function bg_noise_normal(seed::Real, k::Real)
    u = bg_noise_uniform(seed, k)
    isnan(u) && return NaN
    return noise_ppnd(u)
end

# ln 2 split as in fdlibm: the high part has 32 trailing zero bits, so `e * NOISE_LN2_HI` is
# exact for |e| < 2^21.
const NOISE_LN2_HI = 0x1.62e42feep-1
const NOISE_LN2_LO = 0x1.a39ef35793c76p-33
const NOISE_SQRT_HALF = 0x1.6a09e667f3bcdp-1

"""
    noise_log(x) -> Float64

The natural logarithm used by the normal transform, for 0 < x <= 1 (finite, normal x):
`x = m 2^e` by `frexp`, `m` moved into [sqrt(1/2), sqrt(2)), then
`log m = 2 atanh(s) = 2s (1 + z/3 + z^2/5 + ... + z^11/23)` with `s = (m - 1)/(m + 1)`,
`z = s^2 <= 0.0295` (truncation error below 1e-18), and `log x = e ln2_hi + (log m + e ln2_lo)`.
Within 2 ulp of the true logarithm on the transform's range; what matters is that it is the
same double in Julia and C.
"""
function noise_log(x::Float64)
    m, e = frexp(x)
    if m < NOISE_SQRT_HALF
        m = m + m
        e = e - 1
    end
    f = m - 1.0
    s = f / (2.0 + f)
    z = s * s
    p = 0x1.642c8590b2164p-5                # 1/23
    p = p * z + 0x1.8618618618618p-5        # 1/21
    p = p * z + 0x1.af286bca1af28p-5        # 1/19
    p = p * z + 0x1.e1e1e1e1e1e1ep-5        # 1/17
    p = p * z + 0x1.1111111111111p-4        # 1/15
    p = p * z + 0x1.3b13b13b13b14p-4        # 1/13
    p = p * z + 0x1.745d1745d1746p-4        # 1/11
    p = p * z + 0x1.c71c71c71c71cp-4        # 1/9
    p = p * z + 0x1.2492492492492p-3        # 1/7
    p = p * z + 0x1.999999999999ap-3        # 1/5
    p = p * z + 0x1.5555555555555p-2        # 1/3
    p = p * z + 1.0
    logm = (2.0 * s) * p
    de = Float64(e)
    return de * NOISE_LN2_HI + (logm + de * NOISE_LN2_LO)
end

"""
    noise_ppnd(p) -> Float64

Wichura's AS 241 PPND16: the standard normal quantile of `0 < p < 1`, relative accuracy
about 1e-16. The coefficients are the published ones, as hex floats.
"""
function noise_ppnd(p::Float64)
    q = p - 0.5
    if abs(q) <= 0.425
        r = 0.180625 - q * q
        num = 0x1.39a296f7d925ep11            # a7 = 2509.0809287301226727
        num = num * r + 0x1.052d26b2e45e4p15  # a6 = 33430.575583588128105
        num = num * r + 0x1.06c1c55b78f2p16   # a5 = 67265.770927008700853
        num = num * r + 0x1.66c3e869b752ap15  # a4 = 45921.953931549871457
        num = num * r + 0x1.ad1d8cd4ee71dp13  # a3 = 13731.693765509461125
        num = num * r + 0x1.ece5d2213c0ccp10  # a2 = 1971.5909503065514427
        num = num * r + 0x1.0a4888b1a436ep7   # a1 = 133.14166789178437745
        num = num * r + 0x1.b18d91e9eef75p1   # a0 = 3.3871328727963666080
        den = 0x1.46a7eca984b69p12            # b7 = 5226.4952788528545610
        den = den * r + 0x1.c0e457cb1ae76p14  # b6 = 28729.085735721942674
        den = den * r + 0x1.3317caa64f4bep15  # b5 = 39307.895800092710610
        den = den * r + 0x1.4b772d5d65266p14  # b4 = 21213.794301586595867
        den = den * r + 0x1.512322e75c89fp12  # b3 = 5394.1960214247511077
        den = den * r + 0x1.5797efdc8b3f7p9   # b2 = 687.18700749205790830
        den = den * r + 0x1.5281b386e1ab5p5   # b1 = 42.313330701600911252
        den = den * r + 1.0
        return q * num / den
    end
    r = q < 0.0 ? p : 1.0 - p
    r = sqrt(-noise_log(r))
    if r <= 5.0
        r = r - 1.6
        num = 0x1.9615ac0b7ace9p-11           # c7 = 7.74545014278341407640e-4
        num = num * r + 0x1.744eb6c45ec67p-6  # c6 = 2.27238449892691845833e-2
        num = num * r + 0x1.ef2abb9b85c37p-3  # c5 = 2.41780725177450611770e-1
        num = num * r + 0x1.453cc085375b2p0   # c4 = 1.27045825245236838258
        num = num * r + 0x1.d2ecb1a3d02c4p1   # c3 = 3.64784832476320460504
        num = num * r + 0x1.713f71462256ap2   # c2 = 5.76949722146069140550
        num = num * r + 0x1.2857748cab19bp2   # c1 = 4.63033784615654529590
        num = num * r + 0x1.6c665fde9526ap0   # c0 = 1.42343711074968357734
        den = 0x1.20d3f686439e4p-30           # d7 = 1.05075007164441684324e-9
        den = den * r + 0x1.1f18cbfdf2728p-11 # d6 = 5.47593808499534494600e-4
        den = den * r + 0x1.f207a7eab17bfp-7  # d5 = 1.51986665636164571966e-2
        den = den * r + 0x1.2f5123394f04p-3   # d4 = 1.48103976427480074590e-1
        den = den * r + 0x1.61292f23385c9p-1  # d3 = 6.89767334985100004550e-1
        den = den * r + 0x1.ad278e6526633p0   # d2 = 1.67638483018380384940
        den = den * r + 0x1.06cefbb46a449p1   # d1 = 2.05319162663775882187
        den = den * r + 1.0
    else
        r = r - 5.0
        num = 0x1.afb74d693bf93p-23           # e7 = 2.01033439929228813265e-7
        num = num * r + 0x1.c6ec6cc59e02ap-16 # e6 = 2.71155556874348757815e-5
        num = num * r + 0x1.45c1908425345p-10 # e5 = 1.24266094738807843860e-3
        num = num * r + 0x1.b2b41193b4ee7p-6  # e4 = 2.65321895265761230930e-2
        num = num * r + 0x1.2fad9315255cfp-2  # e3 = 2.96560571828504891230e-1
        num = num * r + 0x1.c8ea6461fa445p0   # e2 = 1.78482653991729133580
        num = num * r + 0x1.5daea6e875003p2   # e1 = 5.46378491116411436990
        num = num * r + 0x1.aa1b1c13ee526p2   # e0 = 6.65790464350110377720
        den = 0x1.269bff1f8c19p-49            # f7 = 2.04426310338993978564e-15
        den = den * r + 0x1.31446f740b9ep-23  # f6 = 1.42151175831644588870e-7
        den = den * r + 0x1.35c2c496374bfp-16 # f5 = 1.84631831751005468180e-5
        den = den * r + 0x1.9c8bc979dc5d7p-11 # f4 = 7.86869131145613259100e-4
        den = den * r + 0x1.e76f93215462ap-7  # f3 = 1.48753612908506148525e-2
        den = den * r + 0x1.186eb183443fbp-3  # f2 = 1.36929880922735805310e-1
        den = den * r + 0x1.331d34fc7d77fp-1  # f1 = 5.99832206555887937690e-1
        den = den * r + 1.0
    end
    v = num / den
    return q < 0.0 ? -v : v
end

"""
    bg_delay_ring!(ring, pos, id, off, k, x) -> Float64

One call of the discrete `delay` intrinsic (J-EX9): ring `id` holds `k >= 1` slots at
`ring[off + 1 : off + k]` (zero at the start of a run) and its write position `pos[id]`
(0-based). Returns the value written `k` calls ago (0.0 before the ring has filled), then
writes `x` in its place and advances the position. The C twin is `bg_delay_ring` in
`bg_intrinsics.c` (same slot order, so the export is bit-exact).
"""
function bg_delay_ring!(ring::Vector{Float64}, pos::Vector{Int}, id::Int, off::Int, k::Int,
    x::Real)
    p = pos[id]
    out = ring[off + p + 1]
    ring[off + p + 1] = Float64(x)
    p += 1
    pos[id] = p == k ? 0 : p
    return out
end

"""
    bg_delay_ring_at!(ring, pos, id, off, k, x, d) -> Float64

One call of the variable-read `delay(x, Tmax, tau)` (spec "Seeded noise and delay"): the ring
holds the last `k = Tmax / Ts` values of `x` (0.0 before they have arrived) and `d = tau / Ts`
says how many calls back to read. `d` is clamped to `[0, k]` (NaN reads 0 back); with
`n = floor(d)` and `f = d - n` the result is `h(n) + f * (h(n + 1) - h(n))`, where `h(0)` is
`x` itself and `h(j)` the value written `j` calls ago. Then `x` is written as in
[`bg_delay_ring!`](@ref). The C twin is `bg_delay_ring_at` in `bg_intrinsics.c`, operation for
operation, so the export is bit-exact.
"""
function bg_delay_ring_at!(ring::Vector{Float64}, pos::Vector{Int}, id::Int, off::Int,
    k::Int, x::Real, d::Real)
    xf = Float64(x)
    dd = Float64(d)
    dd = dd > 0.0 ? (dd < Float64(k) ? dd : Float64(k)) : 0.0
    n = unsafe_trunc(Int, dd)
    f = dd - Float64(n)
    p = pos[id]
    # The value written j calls ago (1 <= j <= k) is at slot p - j, modulo k.
    a = n == 0 ? xf : ring[off + mod(p - n, k) + 1]
    out = n < k ? a + f * (ring[off + mod(p - n - 1, k) + 1] - a) : a
    ring[off + p + 1] = xf
    pos[id] = p + 1 == k ? 0 : p + 1
    return out
end
