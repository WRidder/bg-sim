# Code and Docs tabs

## Code tab

Every block is defined in the BG-Sim modeling language, a small subset of Julia syntax. The **Code** tab shows and edits the source of one block at a time.

- **Choose a source…** opens a block: an inline block of this model, a block of the project library, or a standard library block (read-only).
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

Units are written as attributes, for example `R::Real = 1.0, [unit = "Ohm"]`, and are checked for consistency. The full language is described in the modeling language spec in the repository (`spec/`).

## Docs tab

Each model has its own pages of documentation, stored with the model in the project.

- The page tree on the left has **New page**, **New child page**, rename (`F2`) and delete. `Alt`+arrow keys move a page.
- Switch between **View**, **Edit** and **Split** (`Ctrl+E` toggles view and edit).
- **Docs do not save automatically:** click **Save** or press `Ctrl+S`. BG-Sim warns before you leave with unsaved pages.
- Pages are Markdown with tables, task lists, footnotes and math (`$…$` inline, `$$…$$` display).
- **Images:** paste or drop an image into the editor (png, jpg, gif, webp or svg). `![alt|300](…)` sets the width to 300 px. **Clean up** removes images no page uses.

Links can point into the model:

| Link | Does |
| --- | --- |
| `[text](page:<id>)` | opens another page of this model's docs (a page link cannot reach the docs of another model; name that model in the text) |
| `[text](block:Motor)` | opens the Diagram, selects the block and centres it (`block:Sub/Motor` inside a subsystem) |
| `[text](signal:Motor/w)` | plots the signal |
| `[text](https://…)` | opens a website in a new tab |

A link to something that does not exist is shown as broken, with the reason in its tooltip. The same Markdown and links work in [sticky notes](page:building-models).
