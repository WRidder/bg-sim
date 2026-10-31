# Code and Docs tabs

## Code tab

Every block is defined in the BG-Sim modeling language, a small subset of Julia syntax. The **Code** tab shows and edits the source of one block at a time.

- **Choose a source…** opens a block: an inline block of this model, a block of the project library, or a standard library block (read-only).
- **+ Equation** and **+ Discrete** add a new inline code block to the diagram. Double-click an inline code block on the canvas to open its source.
- Inline blocks are saved with the model. Project library blocks save automatically a moment after you stop typing.
- To change a standard block, use **Copy to project library**; the copy is editable and the instance points to it.
- Autocomplete suggests allowed functions, declared names, port fields (`p.e`, `p.f`) and units. The source is checked while you type; problems are underlined.
- Click the gutter (or press `F9`) to set a [breakpoint](page:debugging).

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
| `[text](page:<id>)` | opens another docs page |
| `[text](block:Motor)` | selects the block on the canvas (`block:Sub/Motor` inside a subsystem) |
| `[text](signal:Motor/w)` | plots the signal |
| `[text](https://…)` | opens a website in a new tab |

A link to something that does not exist is shown as broken, with the reason in its tooltip. The same Markdown and links work in [sticky notes](page:building-models).
