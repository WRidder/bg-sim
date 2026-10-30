/* bg-sim C runtime: the table intrinsics (plan/EXPORT_PLAN.md, work package J-EX5).

   `interp1` and `interp2` as C functions over constant tables. The exporter writes every
   table as a `static const double` array into model.c and passes it here with its size.
   Each function has the same edge and extrapolation semantics as its Julia twin
   (src/lower/fnmap.jl). `csv_value` is not exported: a CSV source is simulation data, and
   in an exported model the host supplies that signal through an ExportInput.

   The interval search is a binary search (a bounded loop of ceil(log2 n) steps). For the
   strictly increasing breakpoints the language requires, it picks the same interval as the
   linear scan of the Julia `bg_interp1`/`bg_interp2`.

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

#endif
