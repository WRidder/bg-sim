# Parameters

## Block parameters

Select a block to edit its parameters in the inspector. Each field shows its unit, limits and default; the reset button returns it to the default. A long default, such as a table constant, shows at most three lines ending in "…"; click it to see it whole. A field accepts a number or an expression, such as `2*pi*50`.

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

## Built-in constants

Every expression can use these names: block parameters and start values, global parameters, and block code (see [Code and Docs](page:code-and-docs)). For example, `30*deg`, `3000*rpm`, `m*g_n` or `T_0C + 20`. They are numbers in SI units, and the physical ones are the CODATA 2018 values. A constant cannot be redefined: a global, parameter or variable with one of these names is an error (E003). The editor completes the names in block code.

| Name | Value | Unit | Meaning |
| --- | --- | --- | --- |
| `pi`, `π` | 3.141592653589793 | | π |
| `ℯ` | 2.718281828459045 | | Euler's number, `exp(1)` |
| `Inf` | ∞ | | Infinity, for an open limit such as `clamp(x, -Inf, u_max)`. A global must stay finite. |
| `deg` | 0.017453292519943295 | rad | One degree: `30*deg` |
| `rpm` | 0.10471975511965977 | rad/s | One revolution per minute: `3000*rpm` |
| `g_n` | 9.80665 | m/s² | Standard gravity |
| `c_0` | 299792458 | m/s | Speed of light in vacuum |
| `G_grav` | 6.6743e-11 | m³/(kg·s²) | Newtonian constant of gravitation |
| `h_P` | 6.62607015e-34 | J·s | Planck constant |
| `hbar`, `ℏ` | 1.0545718176461565e-34 | J·s | Reduced Planck constant, `h_P/(2*pi)` |
| `k_B` | 1.380649e-23 | J/K | Boltzmann constant |
| `N_A` | 6.02214076e23 | 1/mol | Avogadro constant |
| `R_gas` | 8.31446261815324 | J/(mol·K) | Molar gas constant, `N_A*k_B` |
| `q_e` | 1.602176634e-19 | C | Elementary charge |
| `mu_0`, `μ₀` | 1.25663706212e-6 | N/A² | Vacuum magnetic permeability |
| `eps_0`, `ε₀` | 8.8541878128e-12 | F/m | Vacuum electric permittivity |
| `sigma_SB` | 5.670374419e-8 | W/(m²·K⁴) | Stefan–Boltzmann constant |
| `atm` | 101325 | Pa | One standard atmosphere: `2*atm` |
| `T_0C` | 273.15 | K | 0 °C in kelvin |

The Unicode names are spellings of the ASCII ones. `ħ` and `µ₀` (written with the micro sign) also work. Single letters such as `e`, `g`, `c`, `k`, `σ` or `μ` are not constants. They stay free for your own names, such as a gain `k` or a friction coefficient `μ` in block code.

## Units: degrees, percent and other scaled units

A unit such as `mm`, `deg`, `rpm` or `%` is a scaled SI unit: `deg` is a radian times π/180, `%` is a plain number times 0.01. The unit of a parameter tells what its number means; it never converts the number. A parameter declared in block code as `q_max::Real = 120.0, [unit = "deg"]` holds 120: you enter it in degrees and the inspector shows it in degrees.

There are two ways to give an angle in degrees:

- **Keep the parameter in rad** and type the value as `120*deg` (an equation, marked Σ, with the value in rad next to it). Nothing else changes.
- **Declare the parameter in deg** (or a readout in deg, or a value in `%`) and convert it where the block code mixes it with radians. The checker refuses `q - q_max` with `q` in rad (E006, "differ only in scale"), and its hint names the conversion. Write the factor out:

| You have | Write | Result |
| --- | --- | --- |
| `q_max` in deg, need rad | `q_max*deg` | rad |
| `q` in rad, need deg (an output in deg) | `q/deg` | deg |
| `f` in `1`, need % | `100*f` | % |
| `p` in %, need `1` | `p/100` or `p*0.01` | 1 |
| `n` in rpm, need rad/s | `n*rpm` | rad/s |
| `x` in mm, need m | `x/1000` | m |

Only the exact factor between the two units counts as a conversion; any other number (`2*x`) keeps the unit. A wire between two ports of the same dimension converts by itself: an output in deg can feed an input in rad, and the editor shows the factor on the wire.

## Other ways to change parameters

- **Dashboard inputs** override a parameter for the next run without changing the model (see [Dashboard](page:dashboard)).
- **Live edits** while paused in the debugger change the paused run (see [Debugging](page:debugging)).
