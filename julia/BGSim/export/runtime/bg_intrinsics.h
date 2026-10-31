/* bg-sim C runtime: the table intrinsics (plan/EXPORT_PLAN.md, work package J-EX5).

   `interp1` and `interp2` as C functions over constant tables. The exporter writes every
   table as a `static const double` array into model.c and passes it here with its size.
   Each function has the same edge and extrapolation semantics as its Julia twin
   (src/lower/fnmap.jl). `csv_value` is not exported: a CSV source is simulation data, and
   in an exported model the host supplies that signal through an ExportInput.

   The interval search is a binary search (a bounded loop of ceil(log2 n) steps). For the
   strictly increasing breakpoints the language requires, it picks the same interval as the
   linear scan of the Julia `bg_interp1`/`bg_interp2`.

   The seeded draws `noise_uniform`/`noise_normal` and the discrete `delay` ring (work package
   J-EX9) are specified in src/library/random.jl and the language spec; these C twins follow
   the Julia bodies operation for operation and return the same doubles, bit for bit.

   No allocation, no I/O, no error exits. */
#ifndef BG_INTRINSICS_H
#define BG_INTRINSICS_H

/* interp1(u, xs, ys): piecewise linear, the end values held outside [xs[0], xs[n-1]]. */
double bg_interp1(double u, const double *xs, const double *ys, int n);

/* interp2(u, v, breaks, table) on an n x n grid, the edge values held outside it.
   `breaks` is row-major 2 x n (row 0: the x breakpoints, row 1: the y breakpoints) and
   `table` row-major n x n, `table[i*n + j]` the value at (x = breaks[j], y = breaks[n + i]),
   which is `table[i, j]` of the language. */
double bg_interp2(double u, double v, const double *breaks, const double *table, int n);

/* Sample k of the uniform stream `seed`, in (0, 1): SplitMix64 bits, (2j + 1) 2^-53 with j
   the top 52 bits. `seed` and `k` must be integer-valued in [-2^63, 2^63); otherwise NaN. */
double bg_noise_uniform(double seed, double k);

/* Sample k of the standard normal stream `seed`: Wichura's AS 241 of bg_noise_uniform, with
   a logarithm of plain IEEE arithmetic (no libm `log`), so it equals the Julia value. */
double bg_noise_normal(double seed, double k);

/* One call of the discrete `delay`: `ring` holds k >= 1 slots (zero after bg_reset) and
   `*pos` the write position. Returns the value written k calls ago, stores x in its place
   and advances the position. */
double bg_delay_ring(double *ring, int *pos, int k, double x);

/* One call of the variable-read `delay(x, Tmax, tau)`: the ring as above, read d = tau / Ts
   calls back (clamped to [0, k]; 0 is x itself), linearly interpolated between the two
   stored values around it; then x is stored and the position advanced. */
double bg_delay_ring_at(double *ring, int *pos, int k, double x, double d);

#endif
