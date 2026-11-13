# Linked subsystems: put the drawn definition in place of every instance.
#
# A drawn subsystem definition (`IR.SubsystemDefinition`, the project library file
# `library/<Name>.bgsub.json`) is a diagram that several nodes share. A node with
# `ref == "project:<Name>"` is an instance. This pass runs before anything else: it replaces
# each instance by an ordinary subsystem node that carries its own copy of the definition's
# diagram, with the instance's pinned values written into the nodes they name. Everything
# after it (instantiation, connections, causality, export) sees plain subsystems, so an
# instance flattens exactly like the subsystem it was drawn as, at its own path
# (`Arm/Actuator3/rotor/w`).
#
# What an instance may set is the definition's pin list. A key of the instance's `params` or
# `starts` is a path inside the definition: node names, then what the last node calls the
# value (`rotor/J`, `Inner/gear/n`, and `drive/inertia/P` for a start of a textual composite).
# A key that is not pinned, or that names nothing, is W218 and has no effect: unpinning a
# parameter in the library must not break the models that still carry a value for it.

"""    project_definitions(md, project_dir) -> (definitions, diagnostics)

The drawn subsystem definitions a model sees: the files of the project library, with the
definitions the document carries (the editor's unsaved copies) taking precedence. A library
file that cannot be read is E101 for the models of the project."""
function project_definitions(md::IR.ModelDoc, project_dir)
    definitions = Dict{String,IR.SubsystemDefinition}()
    diagnostics = Diagnostic[]
    if project_dir !== nothing
        dir = Library.project_library_dir(String(project_dir))
        loaded, problems = IR.load_project_definitions(dir)
        for name in sort!(collect(keys(loaded)))
            # One name, two files: the code block is the block, as in the catalog, and the
            # clash is reported instead of silently compiling the drawing.
            if isfile(joinpath(dir, name * ".jl"))
                push!(diagnostics, diag(
                    "E101",
                    "the project library has both `$(name).jl` and `$(name)$(IR.DEFINITION_SUFFIX)`; `project:$(name)` is the block `$(name).jl`";
                    hint = "a block and a subsystem cannot share a name: rename or remove one of the two files",
                    block = "project:" * name,
                ))
                continue
            end
            definitions[name] = loaded[name]
        end
        for (name, message) in problems
            haskey(md.definitions, name) && continue
            push!(diagnostics, diag(
                "E101",
                "the subsystem definition `library/$(name)$(IR.DEFINITION_SUFFIX)` cannot be read: $message";
                hint = "save the subsystem to the library again, or remove the file",
                block = "project:" * name,
            ))
        end
    end
    merge!(definitions, md.definitions)
    return definitions, diagnostics
end

"""    link_definitions(md; project_dir = nothing) -> (ModelDoc, Vector{Diagnostic})

`md` with every instance of a drawn subsystem definition replaced by a subsystem node that
holds its own copy of the definition (see the file header). A document without instances is
returned as it is."""
function link_definitions(md::IR.ModelDoc; project_dir = nothing)
    definitions, diagnostics = project_definitions(md, project_dir)
    isempty(definitions) && return md, diagnostics
    diagram = _link_diagram!(diagnostics, md.diagram, definitions, String[], "")
    diagram === md.diagram && return md, diagnostics
    linked = IR.ModelDoc(md.format, md.language, md.name, diagram, md.settings, md.plots,
        md.scene, md.bindings, md.globals, md.definitions)
    return linked, diagnostics
end

function _definition_of(node::IR.ModelNode, definitions)
    node.block_kind === :ref || return nothing
    ref = something(node.ref, "")
    startswith(ref, "project:") || return nothing
    return get(definitions, ref[(length("project:") + 1):end], nothing)
end

# The diagram with its instances replaced, or the same object when it has none.
function _link_diagram!(diagnostics, diagram::IR.ModelDiagram, definitions, stack, prefix)
    changed = false
    nodes = IR.ModelNode[]
    for node in diagram.nodes
        path = _join(prefix, node.name)
        definition = _definition_of(node, definitions)
        if definition !== nothing
            changed = true
            push!(nodes, _link_instance!(diagnostics, node, definition, definitions, stack, path))
        elseif node.block_kind === :subsystem && node.subsystem !== nothing
            sub = _link_diagram!(diagnostics, node.subsystem, definitions, stack, path)
            if sub === node.subsystem
                push!(nodes, node)
            else
                changed = true
                push!(nodes, _as_subsystem(node, sub, node.subsystem_ports))
            end
        else
            push!(nodes, node)
        end
    end
    return changed ? IR.ModelDiagram(nodes, diagram.connections) : diagram
end

_as_subsystem(node::IR.ModelNode, diagram, ports) = IR.ModelNode(
    node.id, node.name, :subsystem, nothing, nothing, nothing, diagram, ports,
    Dict{String,String}(), Dict{String,Any}(), Dict{String,String}(), node.position,
)

function _link_instance!(diagnostics, node, definition, definitions, stack, path)
    if definition.name in stack
        push!(diagnostics, diag(
            "E101",
            "the subsystem `$(definition.name)` contains itself";
            hint = "a library subsystem cannot hold an instance of itself, directly or through another library subsystem",
            path = path, block = node.ref, node = node.id,
        ))
        return _as_subsystem(node, IR.ModelDiagram(IR.ModelNode[], IR.ModelConnection[]),
            IR.SubsystemPort[])
    end
    # A copy of its own: the values below are written into this instance's nodes only.
    diagram = deepcopy(definition.diagram)
    push!(stack, definition.name)
    try
        diagram = _link_diagram!(diagnostics, diagram, definitions, stack, path)
    finally
        pop!(stack)
    end
    for (values, pins, what, field) in (
        (node.params, definition.pin_params, "parameter", :params),
        (node.starts, definition.pin_starts, "start value", :starts),
    )
        for key in sort!(collect(keys(values)))
            if !(key in pins)
                push!(diagnostics, diag(
                    "W218",
                    "`$(node.name)` sets the $what `$key`, which `$(definition.name)` does not pin; the value is ignored";
                    hint = "pin `$key` in the subsystem `$(definition.name)`, or reset the value on `$(node.name)`",
                    path = path, block = node.ref, node = node.id,
                ))
                continue
            end
            target, rest = _pin_target(diagram, key)
            if target === nothing
                push!(diagnostics, diag(
                    "W218",
                    "`$(node.name)` sets the $what `$key`, but `$(definition.name)` has nothing of that name; the value is ignored";
                    hint = "the pin names a block inside `$(definition.name)` that was renamed or removed; pin the value again",
                    path = path, block = node.ref, node = node.id,
                ))
                continue
            end
            getfield(target, field)[rest] = values[key]
        end
    end
    return _as_subsystem(node, diagram, definition.ports)
end

# The node a pinned path names and what that node calls the value: node names are followed
# through nested subsystems as far as they go, and the rest is the key on the node reached.
function _pin_target(diagram::IR.ModelDiagram, key::String)
    parts = split(key, '/')
    current = diagram
    for k in 1:(length(parts) - 1)
        index = findfirst(n -> n.name == parts[k], current.nodes)
        index === nothing && return nothing, ""
        node = current.nodes[index]
        if node.block_kind === :subsystem && node.subsystem !== nothing && k < length(parts) - 1
            current = node.subsystem
            continue
        end
        node.block_kind in (:ref, :inline) || return nothing, ""
        return node, join(parts[(k + 1):end], "/")
    end
    return nothing, ""
end
