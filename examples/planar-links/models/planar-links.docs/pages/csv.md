# The CSV source

The comparison data enter the model through **`stdlib:sources/CsvSource`** (feature F5.1): a block that reads columns of a project CSV file and outputs them as signals. The data files live in the `data/` folder of the project ([A3_Csv](block:A3_Csv) reads `data/arm3.csv`).

## The file

A header row and numeric rows. A header cell is `name` or `name [unit]`; the first column is the time column unless `time_column` names another. The delimiter is the one of `,`, `;` or tab that the header uses. A bad cell is reported with its row and column, for example `data row 12, column q1 (line 14): abc is not a finite number`.

```
t [s],q1 [rad],q2 [rad],qd1 [rad/s],... ,tau_analytical1 [N*m],... ,tau_rtb1 [N*m],...
0.0,-1.5707963267948966,-0.0,...
```

## The settings

They are entries of the node constants, and the inspector edits them (file picker with an upload button, a preview of the header and the first rows, the detected columns):

| setting | meaning | default |
| --- | --- | --- |
| `file` | project-relative path; a path outside the project is refused | required |
| `time_column`, `columns` | header names; the output order is the order of `columns` | first column, all others |
| `method` | 0 hold, 1 linear, 2 cubic | cubic |
| `extrapolation` | 0 hold the end values, 1 error past the data | hold |
| `time_offset`, `scale` | seconds added to time; factor on the values | 0, 1 |

`CsvSourceSampled` adds `sample_period` and outputs the table value at every tick, held in between (a discrete partition).

## How it works

The compiler reads the file once while it instantiates the node and registers the table. The block equation is `y[i] ~ csv_value(table, i, t)`, an **opaque registered function**: the data are never unrolled into equations, so 100 000 rows × 10 columns load in about 0.2 s. The `table` constant is an id derived from the file content and the settings, so editing the CSV changes the compile key and recompiles; an unchanged file reuses the cache.

The cubic is a **not-a-knot spline, C²**, with analytic derivatives registered up to the third order. That is what makes the inverse dynamics possible: the speed of each joint is prescribed by the cubic CSV speed ([A3_Speed1](block:A3_Speed1)), so every inertia is in derivative causality and ModelingToolkit differentiates the interpolant once (the acceleration) with no numerical differentiation. For hold and linear tables the data rows are passed to the solver as `tstops`.

The output `y` is a vector; a `stdlib:continuous/Select` block ([A3_qd1](block:A3_qd1)) splits one element off.
