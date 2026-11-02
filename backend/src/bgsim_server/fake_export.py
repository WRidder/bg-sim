"""The export runner of the fake worker (``BGSIM_FAKE_WORKER=1``; plan P-EX1, W-EX1).

The web lane tests the Export dialog against this module: it runs no Julia and no compiler,
but it answers like the real pipeline at the contract level, deterministically and fast.

* The **interface** follows the real rules (``BGSim.Export.scope_document`` and the marker
  scan of ``export_model``): the whole model publishes its ``ExportInput``/``ExportOutput``/
  ``ExportParameter`` markers under their instance paths; a scope publishes the subsystem's
  ports (a signal port under its name, a power port as ``<port>_e``/``<port>_f`` by the
  chosen effort or flow) plus the markers inside it.
* **Refusals**: E112 for a missing scope, a node that is not a subsystem, a power port without
  a choice, a vector port or a domain the scope cannot take; E110 for a ``CsvSource`` inside
  what is exported, at its instance path.
* The **report** is the fixture ``contracts/fixtures/export-report/valid/export-report.rk4.json``
  with this request's name, interface and forced method/dt; W209 when the interface is empty.
* The **build** zips ``modelDescription.xml`` and ``sources/`` into ``<identifier>.fmu``
  (a source-only FMU) and says in its note that nothing was compiled.

Each phase takes ``BGSIM_FAKE_EXPORT_S`` seconds (default 0.3), so the dialog's progress is
visible and a cancel can land in the middle. A job's ``fakeDelayS`` (set from the POST's
``X-BGSim-Fake-Export-S`` header, see :mod:`bgsim_server.exports`) overrides it per job.
"""

from __future__ import annotations

import asyncio
import copy
import json
import os
import re
import zipfile
from collections.abc import Callable
from pathlib import Path
from typing import Any
from xml.sax.saxutils import quoteattr

from .config import Settings

MARKER_INPUT = "stdlib:converters/ExportInput"
MARKER_INPUT_PASS = "stdlib:converters/ExportInputPass"
MARKER_OUTPUT = "stdlib:converters/ExportOutput"
MARKER_PARAMETER = "stdlib:converters/ExportParameter"
CSV_SOURCES = ("stdlib:sources/CsvSource", "stdlib:sources/CsvSourceSampled")
SCOPE_DOMAINS = ("Generic", "Electrical", "Translation", "Rotation", "Hydraulic", "Thermal")
REPORT_FIXTURE = Path("contracts/fixtures/export-report/valid/export-report.rk4.json")
FAKE_NOTE = ("fake export runner (BGSIM_FAKE_WORKER): nothing was compiled; "
             "the FMU holds the sources only")


def _diag(code: str, message: str, *, hint: str | None = None, path: str | None = None
          ) -> dict[str, Any]:
    return {
        "code": code, "severity": "error" if code.startswith("E") else "warning",
        "message": message, "hint": hint, "path": path, "block": None, "scope": None,
        "source": None, "node": None, "connection": None, "related": [],
    }


def _number(text: Any, default: float = 0.0) -> float:
    try:
        return float(text)
    except (TypeError, ValueError):
        return default


def _walk(diagram: dict[str, Any], prefix: str = ""):
    """Every node with its instance path, depth first."""
    for node in diagram.get("nodes", []):
        path = f"{prefix}{node['name']}"
        yield path, node
        block = node.get("block") or {}
        if "subsystem" in block:
            yield from _walk(block["subsystem"]["diagram"], path + "/")


def _c_identifier(name: str) -> str:
    text = re.sub(r"[^A-Za-z0-9_]", "_", name)
    return "m_" + text if not text or text[0].isdigit() else text


def interface(model: dict[str, Any], scope: str | None, power_inputs: dict[str, str],
              input_values: dict[str, float]) -> tuple[dict[str, list], list[dict[str, Any]]]:
    """``({inputs, outputs, parameters}, diagnostics)`` of an export request."""
    inputs: list[dict[str, Any]] = []
    outputs: list[dict[str, Any]] = []
    parameters: list[dict[str, Any]] = []
    diags: list[dict[str, Any]] = []
    root = model["diagram"]
    subtree = root
    if scope:
        diagram, node = root, None
        segments = scope.split("/")
        for k, segment in enumerate(segments):
            where = "/".join(segments[: k + 1])
            node = next((n for n in diagram.get("nodes", []) if n["name"] == segment), None)
            if node is None:
                return {}, [_diag("E112", f"the export scope `{scope}` does not exist",
                                  hint=f"no instance `{where}` in the model", path=where)]
            if "subsystem" not in node["block"]:
                return {}, [_diag("E112", f"the export scope `{where}` is not a subsystem",
                                  hint="select a subsystem; a library block can be wrapped in one",
                                  path=where)]
            diagram = node["block"]["subsystem"]["diagram"]
        assert node is not None
        subtree = {"nodes": [node]}
        for port in node["block"]["subsystem"]["ports"]:
            name, here = port["name"], f"{scope}/{port['name']}"
            size = 1
            for n in port.get("size") or [1]:
                size *= int(n)
            start = float(input_values.get(name, 0.0))
            if port["kind"] == "signal":
                if size != 1:
                    diags.append(_diag(
                        "E112", f"the vector signal port `{name}` cannot be an export interface yet",
                        hint="export a scalar signal (a Select block inside the subsystem)",
                        path=here))
                elif port.get("direction") == "input":
                    inputs.append({"name": name, "id": f"{name}/value", "start": start})
                else:
                    outputs.append({"name": name, "id": f"{name}/u"})
                continue
            domain = port.get("domain") or "Generic"
            if domain not in SCOPE_DOMAINS or size != 1:
                diags.append(_diag(
                    "E112", f"the power port `{name}` ({domain}) cannot be an export interface yet",
                    hint="only scalar Electrical, Translation, Rotation, Hydraulic, Thermal or generic bond ports",
                    path=here))
                continue
            choice = power_inputs.get(name)
            if choice not in ("effort", "flow"):
                diags.append(_diag(
                    "E112", f"the power port `{name}` needs the variable the host imposes",
                    hint=f'set power_inputs["{name}"] to "effort" or "flow"', path=here))
                continue
            imposed, measured = ("e", "f") if choice == "effort" else ("f", "e")
            inputs.append({"name": f"{name}_{imposed}", "id": f"{name}_{imposed}/value",
                           "start": start})
            outputs.append({"name": f"{name}_{measured}", "id": f"{name}_{measured}/u"})
        if diags:
            return {}, diags

    # The scoped model has the subsystem node at its root, so a marker inside it is
    # `<subsystem>/<marker>` however deep the subsystem sat.
    csv = []
    for local, node in _walk(subtree):
        ref = (node.get("block") or {}).get("ref")
        if ref in (MARKER_INPUT, MARKER_INPUT_PASS):
            inputs.append({"name": local, "id": f"{local}/value",
                           "start": _number((node.get("params") or {}).get("value"))})
        elif ref == MARKER_OUTPUT:
            outputs.append({"name": local, "id": f"{local}/u"})
        elif ref == MARKER_PARAMETER:
            parameters.append({"name": local, "id": f"{local}/value",
                               "start": _number((node.get("params") or {}).get("value")),
                               "variability": "tunable"})
        elif ref in CSV_SOURCES:
            csv.append(local)
    if csv:
        return {}, [_diag("E110", f"`{p}` reads a CSV file, which is not exported", path=p,
                          hint="in an export variant an ExportInput replaces the CSV source, "
                               "so the host supplies the signal") for p in csv]
    return {"inputs": inputs, "outputs": outputs, "parameters": parameters}, []


#: Fake operation counts of the tunables report: each kept value costs this many operations.
FAKE_RHS_OPS = 120
FAKE_OPS_PER_TUNABLE = 7


def tunables(model: dict[str, Any], scope: str | None, settings: dict[str, Any]
             ) -> tuple[list[dict[str, Any]], dict[str, Any] | None, list[dict[str, Any]]]:
    """``(parameters, report section, diagnostics)`` of the request's tunables (J-EX8).

    The real rules in brief: a picked block parameter (``Inst/param``) or global
    (``global:<name>``) becomes a fixed parameter with its range; an unknown id or a driven
    global is W215 (folded); a range that does not contain the value is E110. The value of a
    block parameter is its literal on the node (0 when it is an expression or a default)."""
    picks = list(settings.get("tunables") or [])
    if settings.get("exposeGlobals"):
        have = {p["id"] for p in picks}
        picks += [{"id": f"global:{g['name']}"} for g in model.get("parameters") or []
                  if f"global:{g['name']}" not in have]
    if not picks:
        return [], None, []
    globals_ = {g["name"]: g for g in model.get("parameters") or []}
    nodes: dict[str, dict[str, Any]] = {}
    diagram = model.get("diagram") or {}
    prefix = ""
    if scope:
        node = next((n for p, n in _walk(diagram) if p == scope), None)
        if node is not None and "subsystem" in (node.get("block") or {}):
            diagram, prefix = node["block"]["subsystem"]["diagram"], f"{node['name']}/"
    for path, node in _walk(diagram, prefix):
        nodes[path] = node
    params: list[dict[str, Any]] = []
    diags: list[dict[str, Any]] = []
    requested: list[str] = []
    exposed: list[str] = []
    for pick in picks:
        pid = str(pick["id"])
        entry: dict[str, Any]
        if pid.startswith("global:"):
            g = globals_.get(pid[len("global:"):])
            if g is None or not re.fullmatch(r"\s*[-+0-9.eE]+\s*", str(g.get("value", ""))):
                diags.append(_diag("W215", f"`{pid}` is not an independent global parameter "
                                           "of the model, so it is not exposed"))
                continue
            entry = {"name": g["name"], "id": pid, "start": _number(g["value"])}
            if g.get("unit"):
                entry["unit"] = g["unit"]
            exposed.append(g["name"])
        else:
            path, _, name = pid.rpartition("/")
            node = nodes.get(path)
            if node is None or not name:
                diags.append(_diag("W215", f"`{pid}` is not a parameter of the exported model, "
                                           "so it cannot be tunable"))
                continue
            entry = {"name": pid, "id": pid,
                     "start": _number((node.get("params") or {}).get(name), 0.0)}
            requested.append(pid)
        entry.update(variability="fixed", causality="parameter")
        for end in ("min", "max"):
            if pick.get(end) is not None:
                entry[end] = float(pick[end])
        lo, hi = entry.get("min", float("-inf")), entry.get("max", float("inf"))
        if not lo <= entry["start"] <= hi:
            diags.append(_diag("E110", f"the value {entry['start']} of `{pid}` is outside its "
                                       f"range [{lo}, {hi}]",
                               hint="widen the range so it contains the value the model has"))
        params.append(entry)
    section = {
        "requested": requested, "globals": exposed, "calculated": 0, "starts": 0,
        "heldValues": 0, "newton": False,
        "rhsOps": FAKE_RHS_OPS + FAKE_OPS_PER_TUNABLE * len(params),
        "rhsOpsFolded": FAKE_RHS_OPS if params else None, "initializationChecks": [],
    }
    return params, section, diags


def _model_description(ident: str, guid: str, vars_: dict[str, list]) -> str:
    lines = [
        '<?xml version="1.0" encoding="UTF-8"?>',
        (
            f'<fmiModelDescription fmiVersion="2.0" modelName={quoteattr(ident)} guid={quoteattr(guid)} '
            'generationTool="bg-sim fake export" variableNamingConvention="structured" '
            'numberOfEventIndicators="0">'
        ),
        f'  <CoSimulation modelIdentifier={quoteattr(ident)} canHandleVariableCommunicationStepSize="true"/>',
        '  <DefaultExperiment startTime="0" stopTime="1" stepSize="0.001"/>',
        "  <ModelVariables>",
    ]
    vr = 0
    outputs = []
    for v in vars_["outputs"]:
        vr += 1
        outputs.append(vr)
        lines.append(f'    <ScalarVariable name={quoteattr(v["name"])} valueReference="{vr}" '
                     'causality="output" variability="continuous"><Real/></ScalarVariable>')
    for v in vars_["parameters"]:
        vr += 1
        lines.append(f'    <ScalarVariable name={quoteattr(v["name"])} valueReference="{vr}" '
                     f'causality="parameter" variability="{v.get("variability", "tunable")}">'
                     f'<Real start="{v["start"]!r}"/></ScalarVariable>')
    for v in vars_["inputs"]:
        vr += 1
        lines.append(f'    <ScalarVariable name={quoteattr(v["name"])} valueReference="{vr}" '
                     'causality="input" variability="continuous">'
                     f'<Real start="{v["start"]!r}"/></ScalarVariable>')
    lines.append("  </ModelVariables>")
    lines.append("  <ModelStructure>")
    if outputs:
        lines.append("    <Outputs>")
        lines.extend(f'      <Unknown index="{k}"/>' for k in range(1, len(outputs) + 1))
        lines.append("    </Outputs>")
    lines.append("  </ModelStructure>")
    lines.append("</fmiModelDescription>")
    return "\n".join(lines) + "\n"


class FakeExportRunner:
    """Answers export jobs without Julia or a compiler (see the module docstring)."""

    def __init__(self, settings: Settings):
        self.settings = settings
        self.delay = float(os.environ.get("BGSIM_FAKE_EXPORT_S", "0.3"))

    def _delay(self, request: dict[str, Any] | None) -> float:
        """The phase duration: the job's ``fakeDelayS`` (a test header), else the default."""
        value = (request or {}).get("fakeDelayS")
        return float(value) if isinstance(value, int | float) else self.delay

    async def export(self, job_dir: Path, request: dict[str, Any],
                     on_phase: Callable[[str], None]) -> dict[str, Any]:
        timings: dict[str, float] = {}
        export_dir = job_dir / "export"
        model = request["model"]
        scope = request.get("scope") or None
        delay = self._delay(request)
        await asyncio.sleep(delay)
        timings["juliaS"] = delay
        if scope:
            on_phase("scope")
            await asyncio.sleep(delay / 3)
            timings["scopeS"] = delay / 3
        vars_, diags = interface(model, scope, request.get("powerInputs") or {},
                                 request.get("inputValues") or {})
        if diags:
            return {"status": "refused", "diagnostics": diags, "timings": timings, "notes": []}
        settings = request.get("settings") or {}
        tunable_params, tunable_section, tunable_diags = tunables(model, scope, settings)
        if any(d["severity"] == "error" for d in tunable_diags):
            return {"status": "refused", "diagnostics": tunable_diags, "timings": timings,
                    "notes": []}
        for phase in ("flatten", "reference", "export"):
            on_phase(phase)
            await asyncio.sleep(delay)
            timings[f"{phase}S"] = delay

        repo = self.settings.repo_root
        report = json.loads((repo / REPORT_FIXTURE).read_text(encoding="utf-8"))
        report.pop("build", None)
        name = str(model.get("name") or "model")
        if scope:
            name = f"{name}_{scope.replace('/', '_')}"
        ident = _c_identifier(name)
        vars_["parameters"] = vars_["parameters"] + tunable_params
        report.update(name=name, identifier=ident, **vars_)
        if tunable_section is not None:
            report["tunables"] = tunable_section
        if settings.get("method") not in (None, "auto"):
            report["method"] = settings["method"]
        if settings.get("dt") is not None:
            report["dt"] = float(settings["dt"])
            report["substeps"] = max(1, round(report["step"] / report["dt"]))
        diagnostics = [d for d in report["diagnostics"] if d["code"] != "W210"
                       or vars_["parameters"]]
        if not vars_["inputs"] and not vars_["outputs"]:
            diagnostics.append(_diag(
                "W209", "the model has no ExportInput or ExportOutput markers, so the FMU has "
                "no inputs or outputs",
                hint="place ExportInput blocks where the controller supplies a signal and "
                     "ExportOutput blocks on the signals to publish"))
        diagnostics += tunable_diags
        report["diagnostics"] = diagnostics
        (export_dir / "sources").mkdir(parents=True, exist_ok=True)
        (export_dir / "sources" / "model.c").write_text(
            f"/* fake export of {name}: no generated code */\n", encoding="utf-8")
        (export_dir / "modelDescription.xml").write_text(
            _model_description(ident, report["guid"], vars_), encoding="utf-8")
        (export_dir / "export.json").write_text(json.dumps(report, indent=4), encoding="utf-8")
        return {"status": "exported", "diagnostics": copy.deepcopy(diagnostics),
                "timings": timings, "notes": [], "exportDir": str(export_dir)}

    async def build(self, export_dir: Path) -> dict[str, Any]:
        """Zip a source-only FMU; returns ``{fmu, error}`` like the real build."""
        request_path = export_dir.parent / "request.json"
        request = (json.loads(request_path.read_text(encoding="utf-8"))
                   if request_path.is_file() else None)
        delay = self._delay(request)
        await asyncio.sleep(delay)
        report = json.loads((export_dir / "export.json").read_text(encoding="utf-8"))
        fmu = export_dir / f"{report['identifier']}.fmu"
        with zipfile.ZipFile(fmu, "w", zipfile.ZIP_DEFLATED) as archive:
            archive.write(export_dir / "modelDescription.xml", "modelDescription.xml")
            for path in sorted((export_dir / "sources").iterdir()):
                archive.write(path, f"sources/{path.name}")
        report["build"] = {
            "compilerFound": False, "compiler": None, "sourceOnly": True, "platform": None,
            "ok": True, "forbiddenSymbols": [], "symbolCheck": None, "cxxOk": None,
            "harnessDoSteps": None, "internalStepsPerDoStep": None,
            "allocationsAfterInstantiate": None, "doStepMeanUs": None, "doStepMaxUs": None,
            "buildS": delay, "error": None, "note": FAKE_NOTE,
        }
        (export_dir / "export.json").write_text(json.dumps(report, indent=4), encoding="utf-8")
        return {"fmu": fmu, "error": None}
