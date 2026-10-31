/* bg-sim C runtime: the table intrinsics (see bg_intrinsics.h). The arithmetic follows the
   Julia bodies term by term, so the results are bit-identical to Julia for the same
   interval; the golden tests in test/test_export_intrinsics.jl check it. */
#include <math.h>
#include <stdint.h>
#include "bg_intrinsics.h"

/* The noise transform must not fuse `a*b + c` into an FMA: Julia does not, and a fused
   result differs in the last bit. ISO C mode (-std=c99) keeps GCC from contracting across
   expressions; clang and MSVC honour their pragmas. */
#if defined(__clang__)
#pragma STDC FP_CONTRACT OFF
#elif defined(_MSC_VER)
#pragma fp_contract(off)
#endif

/* The interval [x[k], x[k+1]] the Julia scan stops at: the first k in [0, n-2] with
   u <= x[k+1], or n-2. Needs n >= 2. */
static int bg_segment(const double *x, int n, double u) {
    int lo = 0, hi = n - 2;
    while (lo < hi) {
        int mid = lo + (hi - lo) / 2;
        if (u > x[mid + 1]) {
            lo = mid + 1;
        } else {
            hi = mid;
        }
    }
    return lo;
}

double bg_interp1(double u, const double *xs, const double *ys, int n) {
    int k;
    double x0, x1, w;
    if (u <= xs[0]) return ys[0];
    if (u >= xs[n - 1]) return ys[n - 1];
    if (n < 2) return ys[0];
    k = bg_segment(xs, n, u);
    x0 = xs[k];
    x1 = xs[k + 1];
    if (x1 == x0) return ys[k];
    w = (u - x0) / (x1 - x0);
    return (1.0 - w) * ys[k] + w * ys[k + 1];
}

double bg_interp2(double u, double v, const double *breaks, const double *table, int n) {
    const double *bx = breaks, *by = breaks + n;
    double ux = u, vx = v, x0, x1, y0, y1, fx, fy, low, high;
    int i, j;
    if (n < 2) return table[0];
    if (ux <= bx[0]) ux = bx[0];
    if (ux >= bx[n - 1]) ux = bx[n - 1];
    if (vx <= by[0]) vx = by[0];
    if (vx >= by[n - 1]) vx = by[n - 1];
    j = bg_segment(bx, n, ux);
    i = bg_segment(by, n, vx);
    x0 = bx[j]; x1 = bx[j + 1];
    y0 = by[i]; y1 = by[i + 1];
    fx = x1 == x0 ? 0.0 : (ux - x0) / (x1 - x0);
    fy = y1 == y0 ? 0.0 : (vx - y0) / (y1 - y0);
    low = (1.0 - fx) * table[i * n + j] + fx * table[i * n + j + 1];
    high = (1.0 - fx) * table[(i + 1) * n + j] + fx * table[(i + 1) * n + j + 1];
    return (1.0 - fy) * low + fy * high;
}

/* ---- J-EX9: seeded noise (src/library/random.jl has the specification) ---- */

#define BG_NOISE_GAMMA UINT64_C(0x9e3779b97f4a7c15)

static uint64_t bg_noise_mix(uint64_t z) {
    z = (z ^ (z >> 30)) * UINT64_C(0xbf58476d1ce4e5b9);
    z = (z ^ (z >> 27)) * UINT64_C(0x94d049bb133111eb);
    return z ^ (z >> 31);
}

/* An integer-valued double in [-2^63, 2^63) as int64; 0 for anything else. */
static int bg_noise_int(double x, int64_t *out) {
    if (!(x >= -0x1p63 && x < 0x1p63) || x != floor(x)) return 0;
    *out = (int64_t)x;
    return 1;
}

double bg_noise_uniform(double seed, double k) {
    int64_t s, n;
    uint64_t key, z;
    if (!bg_noise_int(seed, &s) || !bg_noise_int(k, &n)) return NAN;
    key = bg_noise_mix((uint64_t)s + BG_NOISE_GAMMA);
    z = bg_noise_mix(key + ((uint64_t)n + UINT64_C(1)) * BG_NOISE_GAMMA);
    return (double)(2 * (z >> 12) + 1) * 0x1p-53;
}

/* log x for 0 < x <= 1 by frexp and the atanh series; the same operations as `noise_log`. */
static double bg_noise_log(double x) {
    int e;
    double m = frexp(x, &e), f, s, z, p, logm, de;
    if (m < 0x1.6a09e667f3bcdp-1) {
        m = m + m;
        e = e - 1;
    }
    f = m - 1.0;
    s = f / (2.0 + f);
    z = s * s;
    p = 0x1.642c8590b2164p-5;
    p = p * z + 0x1.8618618618618p-5;
    p = p * z + 0x1.af286bca1af28p-5;
    p = p * z + 0x1.e1e1e1e1e1e1ep-5;
    p = p * z + 0x1.1111111111111p-4;
    p = p * z + 0x1.3b13b13b13b14p-4;
    p = p * z + 0x1.745d1745d1746p-4;
    p = p * z + 0x1.c71c71c71c71cp-4;
    p = p * z + 0x1.2492492492492p-3;
    p = p * z + 0x1.999999999999ap-3;
    p = p * z + 0x1.5555555555555p-2;
    p = p * z + 1.0;
    logm = (2.0 * s) * p;
    de = (double)e;
    return de * 0x1.62e42feep-1 + (logm + de * 0x1.a39ef35793c76p-33);
}

/* Wichura's AS 241 (PPND16), as `noise_ppnd`. */
static double bg_noise_ppnd(double p) {
    double q = p - 0.5, r, num, den, v;
    if (fabs(q) <= 0.425) {
        r = 0.180625 - q * q;
        num = 0x1.39a296f7d925ep11;
        num = num * r + 0x1.052d26b2e45e4p15;
        num = num * r + 0x1.06c1c55b78f2p16;
        num = num * r + 0x1.66c3e869b752ap15;
        num = num * r + 0x1.ad1d8cd4ee71dp13;
        num = num * r + 0x1.ece5d2213c0ccp10;
        num = num * r + 0x1.0a4888b1a436ep7;
        num = num * r + 0x1.b18d91e9eef75p1;
        den = 0x1.46a7eca984b69p12;
        den = den * r + 0x1.c0e457cb1ae76p14;
        den = den * r + 0x1.3317caa64f4bep15;
        den = den * r + 0x1.4b772d5d65266p14;
        den = den * r + 0x1.512322e75c89fp12;
        den = den * r + 0x1.5797efdc8b3f7p9;
        den = den * r + 0x1.5281b386e1ab5p5;
        den = den * r + 1.0;
        return q * num / den;
    }
    r = q < 0.0 ? p : 1.0 - p;
    r = sqrt(-bg_noise_log(r));
    if (r <= 5.0) {
        r = r - 1.6;
        num = 0x1.9615ac0b7ace9p-11;
        num = num * r + 0x1.744eb6c45ec67p-6;
        num = num * r + 0x1.ef2abb9b85c37p-3;
        num = num * r + 0x1.453cc085375b2p0;
        num = num * r + 0x1.d2ecb1a3d02c4p1;
        num = num * r + 0x1.713f71462256ap2;
        num = num * r + 0x1.2857748cab19bp2;
        num = num * r + 0x1.6c665fde9526ap0;
        den = 0x1.20d3f686439e4p-30;
        den = den * r + 0x1.1f18cbfdf2728p-11;
        den = den * r + 0x1.f207a7eab17bfp-7;
        den = den * r + 0x1.2f5123394f04p-3;
        den = den * r + 0x1.61292f23385c9p-1;
        den = den * r + 0x1.ad278e6526633p0;
        den = den * r + 0x1.06cefbb46a449p1;
        den = den * r + 1.0;
    } else {
        r = r - 5.0;
        num = 0x1.afb74d693bf93p-23;
        num = num * r + 0x1.c6ec6cc59e02ap-16;
        num = num * r + 0x1.45c1908425345p-10;
        num = num * r + 0x1.b2b41193b4ee7p-6;
        num = num * r + 0x1.2fad9315255cfp-2;
        num = num * r + 0x1.c8ea6461fa445p0;
        num = num * r + 0x1.5daea6e875003p2;
        num = num * r + 0x1.aa1b1c13ee526p2;
        den = 0x1.269bff1f8c19p-49;
        den = den * r + 0x1.31446f740b9ep-23;
        den = den * r + 0x1.35c2c496374bfp-16;
        den = den * r + 0x1.9c8bc979dc5d7p-11;
        den = den * r + 0x1.e76f93215462ap-7;
        den = den * r + 0x1.186eb183443fbp-3;
        den = den * r + 0x1.331d34fc7d77fp-1;
        den = den * r + 1.0;
    }
    v = num / den;
    return q < 0.0 ? -v : v;
}

double bg_noise_normal(double seed, double k) {
    double u = bg_noise_uniform(seed, k);
    if (u != u) return u;
    return bg_noise_ppnd(u);
}

/* ---- J-EX9: the discrete delay ring ---- */

double bg_delay_ring(double *ring, int *pos, int k, double x) {
    int p = *pos;
    double out = ring[p];
    ring[p] = x;
    p += 1;
    *pos = p == k ? 0 : p;
    return out;
}
