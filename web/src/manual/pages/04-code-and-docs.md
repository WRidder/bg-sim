# Code and Docs tabs

## Code tab

Every block is defined in the BG-Sim modeling language, a small subset of Julia syntax. The **Code** tab shows and edits the source of one block at a time.

- **Choose a source…** opens a block: an inline block of this model, a block of the project library, or a standard library block (read-only).
- **Open source** in the inspector's Library section opens the selected block here.
- **+ Equation** and **+ Discrete** add a new inline code block to the diagram. Double-click an inline code block on the canvas to open its source.
- **+ Library block** creates a reusable block in the project library (see below).
- Inline blocks are saved with the model. Project library blocks save automatically a moment after you stop typing.
- To change a standard block, use **Copy to project library**; the copy is editable and the instance points to it.
- Autocomplete suggests allowed functions, declared names, port fields (`p.e`, `p.f`) and units. The source is checked while you type; problems are underlined.
- Click the gutter (or press `F9`) to set a [breakpoint](page:debugging).

### From code to a reusable block

An inline code block belongs to one model. To use the same code as a block you can drag from the library, put it in the [project library](page:projects-and-library):

1. Open the inline block in the Code tab (or select it on the diagram) and click **Save to project library**.
2. Enter a block name, for example `FirstOrderLag`. The proposed name comes from the `@block` line. It must be a Julia identifier that no project block uses yet. The `@block` line is renamed to match, because a library block is named like its file.
3. If other inline blocks have exactly the same code, tick **Also use it for …** to switch them over too.
4. Click **Save to library**. The code goes to `library/FirstOrderLag.jl` and the block on the diagram becomes an instance of `project:FirstOrderLag`. Its name, position and values are kept, and one **Undo** reverts it. The Code tab shows the library block, and the library's **Project** category opens with the new block highlighted.
5. Drag **FirstOrderLag** from the **Project** category to add more instances, in this model or any other model of the project. Editing its code changes every instance.

To start a library block from scratch, click **+ Library block**. Choose *Equation block* (continuous, `@equations`) or *Discrete block* (sampled, `@discrete`) and a name. The new block opens in the Code tab and appears in the **Project** category. Drag it onto the diagram, or click **Place on diagram** in the message above the editor.

If the library does not list the new block (for example while the simulation worker restarts), the file is still saved and the inline block stays as it was. Reopen the project to use the library block.

A minimal equation block:

```julia
@block Equation begin
    @inputs u::Real
    @outputs y::Real
    @equations y ~ u
end
```

The main sections of a block:

| Section | Holds |
| --- | --- |
| `@parameters` | values set per instance; `tunable = true` keeps one adjustable |
| `@constants` | structural values (changing one recompiles) |
| `@inputs` / `@outputs` | signal ports |
| `@ports` | power ports (effort `e`, flow `f`) |
| `@variables` | internal variables with start values |
| `@equations` | equations written with `~` |
| `@discrete Ts = …` | code that runs every `Ts` seconds, with `=` assignments |
| `@events` | `condition => begin … end`, with `reinit` |

An event changes only the states its `reinit` lines name; all other states keep their values. A state that only events change is written `ddt(x) ~ 0.0`: it holds its start value until an event sets it.

An event fires when its condition crosses zero upward, also when the crossing is a jump: a condition that reads a `@discrete` value (or an input driven by one, a recorded input trajectory or a scheduled parameter change) can change sign at a tick. The event then fires at the tick itself, after the discrete code has run, and its new values appear in the row at that instant. A condition that is already true before the jump does not fire again.

### A nonlinear bond-graph element

The standard `R` is linear. A nonlinear resistor is a small library block with one power port. Write its law in the causality it will have on the diagram, and state that causality with `@causality`. For example, a tunnel diode on a capacitor's 0-junction gets the voltage and returns the current:

```julia
@block TunnelDiode begin
    @ports p::Power{Generic}
    @parameters begin
        a::Real = 0.0212
        b::Real = 0.336
    end
    @equations p.f ~ -a * p.e + b * p.e^3
    @causality p => :flow_out
end
```

`:flow_out` means the element sets the flow (the conductance form, `i = g(v)`). `:effort_out` means it sets the effort (the resistance form, `F = F(w)`, such as a friction contact driven by a slip velocity). The **van-der-pol** example (in the Example gallery) builds Van der Pol oscillators this way. One is a tunnel-diode LC oscillator, the other a block on a spring riding a belt with a falling friction curve.

Units are written as attributes, for example `R::Real = 1.0, [unit = "Ohm"]`, and are checked for consistency. A scaled unit (`deg`, `%`, `mm`, `rpm`) needs an explicit conversion where it meets the SI unit, such as `q_max*deg` (see [Parameters](page:parameters)). The full language is described in the modeling language spec in the repository (`spec/`).

### Vectors, matrices and linear solves

`Vec{n}` and `Mat{n,m}` values support `A * x`, `A * B`, `transpose(A)`, `dot`, `norm`, `cross` and the linear solve `A \ b` (or `A \ B` for several right-hand sides) with a square `A`. The solve is an LU factorisation with partial pivoting, written out by the compiler, so it works in `@equations` (also with a matrix that changes in time) and in `@discrete` code, but not in an `@events` body. A pivot change does not stop the solver. For example, the damped least-squares step of an inverse kinematics block:

```julia
@discrete Ts = 0.001 begin
    JJt = J * transpose(J) + lam * [1.0 0.0 0.0; 0.0 1.0 0.0; 0.0 0.0 1.0]
    dq = transpose(J) * (JJt \ e)
end
```

## Docs tab

Each model has its own pages of documentation, stored with the model in the project.

- The page tree on the left has **New page**, **New child page**, rename (`F2`) and delete. `Alt`+arrow keys move a page.
- Switch between **View**, **Edit** and **Split** (`Ctrl+E` toggles view and edit).
- **Docs do not save automatically:** click **Save** or press `Ctrl+S`. BG-Sim warns before you leave with unsaved pages.
- Pages are Markdown with tables, task lists, footnotes and math (`$…$` inline, `$$…$$` display).
- **Images:** paste or drop an image into the editor (png, jpg, gif, webp or svg). `![alt|300](…)` sets the width to 300 px. **Clean up** removes images no page uses.

### Project docs

Most of what you write about an example (the rig, the design, the results) applies to all its models. Put that text in the **project docs** instead of copying it into each model. The project docs are stored in the project's `docs/` folder and every model of the project shows them.

- With project docs, the page tree has two sections. **Project** is at the top and can be collapsed (click its header). **This model** is below. You edit both in the same way: new page, rename, reorder, delete and images.
- A model opens on its own first page. The path above the page starts with **Project docs**, which opens the first project page. A model without pages of its own opens on the project docs.
- A project without project docs shows only the model's pages, with a small **+ Add project docs** link below them. It creates the first project page.
- The project overview's **Docs** tab lists the project docs and the docs of every model together (see [Projects](page:projects-and-library)).

### Links

Links can point into the model and to the other docs of the project:

| Link | Does |
| --- | --- |
| `[text](page:<id>)` | opens another page of the same docs (in a model's docs: that model's pages; in the project docs: the project pages) |
| `[text](project:<id>)` | opens a page of the project docs, from any page |
| `[text](model:<name>/<id>)` | opens a page of another model's docs (the model opens on its Docs tab) |
| `[text](model:<name>)` | opens the first page of that model's docs |
| `[text](block:Motor)` | opens the Diagram, selects the block and centres it (`block:Sub/Motor` inside a subsystem); model docs only |
| `[text](signal:Motor/w)` | plots the signal; model docs only |
| `[text](https://…)` | opens a website in a new tab |

A link to something that does not exist is shown as broken, with the reason in its tooltip: a page that is not there, a model without docs, or a `block:` link in the project docs. The same Markdown and links work in [sticky notes](page:building-models).
