# Parameters

## Block parameters

Select a block to edit its parameters in the inspector. Each field shows its unit, limits and default; the reset button returns it to the default. A long default, such as a table constant, shows as one line ending in "…"; click it to see it whole. A field accepts a number or an expression, such as `2*pi*50`.

## Global parameters

Global parameters are named values of the model, such as a mass `m` or a gear ratio `n`, that block parameters can use. Change the global and every block that uses it follows.

- Open the **Parameters** tab (or select nothing and click **Open the Parameters tab** in the inspector).
- **+ Add global parameter** adds a row with **Name**, **Expression**, **Value**, **Unit** and **Comment**.
- A global can use other globals, for example `k = 4*m`.
- **Renaming** a global rewrites every use of it in one undo step.
- A global that is used cannot be deleted; its **used by** count lists the blocks that use it.
- The unit of a global is documentation only; it is not checked.

### Use a global in a block

Type the name, or an expression with it, into a block parameter or start value: `m`, `4*m`, `m/2 + 0.1`. Names are completed while you type (`Tab` or `Enter` accepts). A leading `=` is allowed and removed.

A field driven by an expression shows a **Σ** badge ("Driven by an equation") and its computed value next to it. An unknown name is an error that tells you to declare it as a global.

### The three views

| View | Shows |
| --- | --- |
| **Global variables** | the globals, editable |
| **Equations** | every block parameter, start value or constant driven by an expression, editable in place; click through to the block |
| **Order** | the order in which the globals are evaluated |

Globals are evaluated once, before the model is compiled, so simulation and export see plain numbers. To change a global at FMU run time, expose it as a tunable in the [export dialog](page:export).

## Other ways to change parameters

- **Dashboard inputs** override a parameter for the next run without changing the model (see [Dashboard](page:dashboard)).
- **Live edits** while paused in the debugger change the paused run (see [Debugging](page:debugging)).
