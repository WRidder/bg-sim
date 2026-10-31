# FMI 2.0 Co-Simulation model description (plan/EXPORT_PLAN.md D-EX3).
#
# Variable order (and so the 1-based ScalarVariable index): outputs, locals, parameters,
# inputs. Value references follow model.h: y [0, NY), p [NY, NY + NP), u [NY + NP, ...).
#
# Parameters (J-EX8): a tunable one is `causality="parameter" variability="tunable"`, a fixed
# one (a picked tunable, an exposed global) `causality="parameter" variability="fixed"`, both
# with `initial="exact"`, their start and their range; a value computed from them at
# initialization is `causality="calculatedParameter" variability="fixed"
# initial="calculated"` and an initial unknown. A parameter's unit (documentation, as in the
# model) is declared under `UnitDefinitions`.

xml_escape(s) = replace(String(s), "&" => "&amp;", "<" => "&lt;", ">" => "&gt;", "\"" => "&quot;")

_xml_num(v::Float64) = repr(v)

function _range_attrs(v)
    s = ""
    isfinite(v.lo) && (s *= " min=\"$(_xml_num(v.lo))\"")
    isfinite(v.hi) && (s *= " max=\"$(_xml_num(v.hi))\"")
    return s
end

_unit_attr(v) = v.unit === nothing ? "" : " unit=\"$(xml_escape(v.unit))\""
_description_attr(v) = v.description === nothing ? "" :
    " description=\"$(xml_escape(v.description))\""

"""    write_fmi2_description(path; name, ident, guid, vars, params, inputs, t_end, step)"""
function write_fmi2_description(path; name, ident, guid, vars, params, inputs, t_end, step)
    units = sort!(unique(String[v.unit for v in params if v.unit !== nothing]))
    open(path, "w") do io
        println(io, """<?xml version="1.0" encoding="UTF-8"?>
        <fmiModelDescription fmiVersion="2.0" modelName="$(xml_escape(name))" guid="$(guid)"
          generationTool="bg-sim C/FMU export (runtime $(RUNTIME_VERSION))"
          variableNamingConvention="flat" numberOfEventIndicators="0">
          <CoSimulation modelIdentifier="$(ident)" canHandleVariableCommunicationStepSize="true"
            canInterpolateInputs="false" canBeInstantiatedOnlyOncePerProcess="false"
            canNotUseMemoryManagementFunctions="false" canGetAndSetFMUstate="false"
            canSerializeFMUstate="false" providesDirectionalDerivative="false">
            <SourceFiles>
              <File name="model.c"/>
              <File name="bg_solver.c"/>
              <File name="fmi2_cs.c"/>
              <File name="bg_intrinsics.c"/>
              <File name="bg_mech.c"/>
            </SourceFiles>
          </CoSimulation>""")
        if !isempty(units)
            println(io, "  <UnitDefinitions>")
            foreach(u -> println(io, """    <Unit name="$(xml_escape(u))"/>"""), units)
            println(io, "  </UnitDefinitions>")
        end
        println(io, """  <DefaultExperiment startTime="0" stopTime="$(_xml_num(Float64(t_end)))" stepSize="$(_xml_num(Float64(step)))"/>""")
        println(io, "  <ModelVariables>")
        vr = 0
        for v in vars
            println(io, """    <ScalarVariable name="$(xml_escape(v.name))" valueReference="$vr" causality="$(v.kind === :output ? "output" : "local")" variability="$(v.variability)"><Real/></ScalarVariable>""")
            vr += 1
        end
        calculated = Int[]          # 1-based ScalarVariable indices (= value reference + 1)
        for v in params
            if v.kind === :calculated
                push!(calculated, vr + 1)
                println(io, """    <ScalarVariable name="$(xml_escape(v.name))" valueReference="$vr"$(_description_attr(v)) causality="calculatedParameter" variability="fixed" initial="calculated"><Real$(_unit_attr(v))/></ScalarVariable>""")
            else
                println(io, """    <ScalarVariable name="$(xml_escape(v.name))" valueReference="$vr"$(_description_attr(v)) causality="parameter" variability="$(v.variability)" initial="exact"><Real start="$(_xml_num(v.start))"$(_unit_attr(v))$(_range_attrs(v))/></ScalarVariable>""")
            end
            vr += 1
        end
        for v in inputs
            println(io, """    <ScalarVariable name="$(xml_escape(v.name))" valueReference="$vr" causality="input" variability="continuous"><Real start="$(_xml_num(v.start))"$(_range_attrs(v))/></ScalarVariable>""")
            vr += 1
        end
        println(io, "  </ModelVariables>\n  <ModelStructure>")
        outs = [k for (k, v) in enumerate(vars) if v.kind === :output]
        if !isempty(outs)
            println(io, "    <Outputs>")
            foreach(k -> println(io, """      <Unknown index="$k"/>"""), outs)
            println(io, "    </Outputs>")
        end
        # Initial unknowns: the outputs and the calculated parameters, in index order.
        initial = sort!(vcat(outs, calculated))
        if !isempty(initial)
            println(io, "    <InitialUnknowns>")
            foreach(k -> println(io, """      <Unknown index="$k"/>"""), initial)
            println(io, "    </InitialUnknowns>")
        end
        println(io, "  </ModelStructure>\n</fmiModelDescription>")
    end
end
