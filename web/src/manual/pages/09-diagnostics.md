# Diagnostics

BG-Sim checks the model automatically shortly after each edit, without running it. The results are in the **Diagnostics** tab of the bottom dock; its badges count the errors and warnings.

## The Diagnostics tab

- Filter with **Errors**, **Warnings** and **Info**, or **Show all**.
- Items are grouped by block (instance path); model-wide items are under **Model**.
- Each item has a code, a message and usually a hint on how to fix it.
- Click an item to select the block on the canvas, or to show the source line in the Code tab.
- The status line says whether the latest edit has been checked. Checks wait while the worker is starting.

Errors and warnings also mark the canvas.

## Common codes

| Code | Meaning |
| --- | --- |
| E000–E006 | problems in block code: syntax, constructs or functions that are not allowed, undeclared names, type, size and unit errors |
| E101 | an input or power port is not connected |
| E102 | domain or type mismatch on a connection |
| E103 | unbalanced system (unknowns and equations do not match) |
| E104 | a discrete clock is not a multiple of the base tick or export step |
| E105 | a cycle between discrete blocks |
| E108 | a CSV data file or its settings cannot be used |
| E110–E112 | the model or scope cannot be [exported](page:export) as it is |
| E113 | a [global parameter](page:parameters) cannot be evaluated |
| E114 | a bond runs against a port's declared orientation (`@orientation`): it starts at an `in` port, ends at an `out` port, joins two `in` or two `out` ports, both bonds of a `through` pair arrive (or both leave), or the bond reaches a power port that declares no orientation. The hint says which bond to reverse, to put a junction in between, or to add `@orientation`. See [Bond direction and port orientation](page:building-models) |
| E301–E306 | 3D scene and binding problems |
| E401, W401 | a breakpoint could not be verified |
| E901 | the solver failed during the run. A failure at the very start of a run with W201 items usually means a dependent storage element next to a stiff compliance (an `Inertia` on the drive of a compliant `Revolute3D`, for example); the hint says so. Give the element its own state with a spring between it and what drives it (the gear or shaft stiffness), lump it into the body it moves with, or use `Revolute3DRigid` and its `Ja` armature |
| E902 | an [Assertion](page:control-blocks) block failed; the message names the block and the time |
| E903 | an algebraic loop cannot be solved: the compiler solves it through a feedthrough coefficient that is zero in this run (for example a `D` of 0 given as a parameter); the message names the blocks of the loop and the coefficient. It comes next to the run's own error (E900, E901 or E103) |
| W201 | a storage element is in derivative causality |
| W202 | an algebraic loop is solved iteratively |
| W204 | a declaration is not used |
| W205 | a Generic port could not be given a domain |
| W206 | the event limit was reached; the message names the condition that fired most when one did |
| W216 | two random sources share a `seed`, so they draw the same sequence |
| W217 | a [StopSimulation](page:control-blocks) block ended the run; the message names the block and the time |
| W203, W207–W215 | export warnings |

The message of each item explains the specific problem; this table is only a guide to the number ranges.
