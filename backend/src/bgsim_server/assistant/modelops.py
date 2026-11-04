"""Pure operations on model documents (plain dicts) for the assistant's tools.

The agent names things as the user does: a node is ``Motor`` or, inside a subsystem,
``Drive/Motor``; an endpoint is ``Motor.p``, or ``J1`` for a junction. Ids stay inside this
module. The connection rules are those of ``web/src/editor/connectionRules.ts`` (plan 5.5, 5.6).
"""

from __future__ import annotations

import re
from typing import Any
from xml.etree import ElementTree

NODE_WIDTH = 100.0
NODE_HEIGHT = 60.0
NODE_NAME = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
GRID_X = 220
GRID_Y = 140
MAX_ROWS_PER_FILE = 200


class ToolError(Exception):
    """A refusal returned to the model as the tool result, with optional details."""

    def __init__(self, message: str, **details: Any):
        super().__init__(message)
        self.message = message
        self.details = details


def empty_model(name: str, language: str = "0.1.0") -> dict[str, Any]:
    """The same document as ``createEmptyModel`` in ``web/src/state/modelFactory.ts``."""
    return {
        "format": "bgsim.model",
        "language": language,
        "name": name,
        "diagram": {"nodes": [], "connections": [], "subsystemPorts": [], "annotations": []},
        "settings": {
            "t_start": 0,
            "t_end": 1,
            "solver": "auto",
            "reltol": 1e-6,
            "abstol": 1e-8,
            "max_step": None,
            "output": {"mode": "points", "points": 5000},
            "event_limit": 10000,
        },
        "plots": [],
        "scene": None,
        "bindings": [],
    }


# ---------------------------------------------------------------------------- navigation


def split_path(text: str | None) -> list[str]:
    return [part for part in (text or "").split("/") if part]


def subsystem_of(node: dict[str, Any]) -> dict[str, Any] | None:
    return node["block"].get("subsystem")


def diagram_at(doc: dict[str, Any], path: list[str]) -> dict[str, Any]:
    """The diagram at a path of subsystem names; a wrong step is refused with what exists."""
    diagram = doc["diagram"]
    for index, name in enumerate(path):
        node = next((n for n in diagram["nodes"] if n["name"] == name), None)
        where = "/".join(path[:index]) or "the top level"
        if node is None:
            raise ToolError(
                f"no node {name!r} at {where}",
                nodes=[n["name"] for n in diagram["nodes"]][:60],
            )
        inner = subsystem_of(node)
        if inner is None:
            raise ToolError(f"{'/'.join(path[: index + 1])} is not a subsystem")
        diagram = inner["diagram"]
    return diagram


def locate(doc: dict[str, Any], ref: str) -> tuple[dict[str, Any], dict[str, Any], list[str]]:
    """``(diagram, node, parent path)`` of ``Drive/Motor``."""
    parts = split_path(ref)
    if not parts:
        raise ToolError("name a node, like Motor or Drive/Motor")
    diagram = diagram_at(doc, parts[:-1])
    node = next((n for n in diagram["nodes"] if n["name"] == parts[-1]), None)
    if node is None:
        raise ToolError(
            f"no node {parts[-1]!r} in {'/'.join(parts[:-1]) or 'the top level'}",
            nodes=[n["name"] for n in diagram["nodes"]][:60],
        )
    return diagram, node, parts[:-1]


def walk_diagrams(doc: dict[str, Any]):
    """Yield ``(path, diagram)`` for every level of the model."""
    stack: list[tuple[list[str], dict[str, Any]]] = [([], doc["diagram"])]
    while stack:
        path, diagram = stack.pop()
        yield path, diagram
        for node in diagram["nodes"]:
            inner = subsystem_of(node)
            if inner is not None:
                stack.append(([*path, node["name"]], inner["diagram"]))


def _next_id(doc: dict[str, Any], prefix: str, key: str) -> str:
    used = {
        item["id"]
        for _, diagram in walk_diagrams(doc)
        for item in diagram.get(key) or []
    }
    number = len(used) + 1
    while f"{prefix}{number}" in used:
        number += 1
    return f"{prefix}{number}"


def unique_name(diagram: dict[str, Any], base: str) -> str:
    used = {n["name"] for n in diagram["nodes"]}
    if base not in used:
        return base
    number = 1
    while f"{base}{number}" in used:
        number += 1
    return f"{base}{number}"


def block_ref(node: dict[str, Any]) -> str | None:
    return node["block"].get("ref")


def block_label(node: dict[str, Any]) -> str:
    block = node["block"]
    if "ref" in block:
        return re.split(r"[:/]", block["ref"])[-1]
    if "junction" in block:
        return str(block["junction"])
    return "subsystem" if "subsystem" in block else "inline"


# ---------------------------------------------------------------------------- blocks


def _footprint(diagram: dict[str, Any]) -> list[tuple[float, float, float, float]]:
    """What takes room on the canvas: nodes, and the notes and shapes around them."""
    boxes = [
        (n["position"]["x"], n["position"]["y"], NODE_WIDTH, NODE_HEIGHT) for n in diagram["nodes"]
    ]
    boxes.extend(
        (a["x"], a["y"], a.get("w", NODE_WIDTH), a.get("h", NODE_HEIGHT))
        for a in diagram.get("annotations") or []
    )
    return boxes


def _taken(x: float, y: float, boxes: list[tuple[float, float, float, float]]) -> bool:
    return any(
        x < bx + bw and x + NODE_WIDTH > bx and y < by + bh and y + NODE_HEIGHT > by
        for bx, by, bw, bh in boxes
    )


def _free_spot(
    diagram: dict[str, Any], x: float, y: float, step: tuple[float, float]
) -> dict[str, float]:
    """The first free place from (x, y), walking along ``step`` to both sides."""
    boxes = _footprint(diagram)
    for offset in range(200):
        for sign in (1, -1):
            cx = x + sign * offset * step[0]
            cy = y + sign * offset * step[1]
            if cx >= 0 and cy >= 0 and not _taken(cx, cy, boxes):
                return {"x": cx, "y": cy}
    return {"x": x, "y": y}


def _median(values: list[float], fallback: float) -> float:
    return sorted(values)[len(values) // 2] if values else fallback


def house_style(diagram: dict[str, Any]) -> dict[str, Any]:
    """How a diagram is laid out already: its flow direction and its spacing."""
    at = {n["id"]: n["position"] for n in diagram["nodes"]}
    dxs, dys = [], []
    for c in diagram["connections"]:
        a, b = at.get(c["from"]["node"]), at.get(c["to"]["node"])
        if a is not None and b is not None:
            dxs.append(b["x"] - a["x"])
            dys.append(b["y"] - a["y"])
    across = [abs(v) for v in dxs if abs(v) >= NODE_WIDTH / 2]
    down = [abs(v) for v in dys if abs(v) >= NODE_HEIGHT / 2]
    vertical = sum(abs(v) for v in dys) > 1.5 * sum(abs(v) for v in dxs)
    forward = sum(dys if vertical else dxs) >= 0
    return {
        "vertical": vertical,
        "forward": forward,
        "dx": max(_median(across, GRID_X), NODE_WIDTH + 20),
        "dy": max(_median(down, GRID_Y), NODE_HEIGHT + 20),
    }


def place_near(
    diagram: dict[str, Any], anchor: dict[str, Any], side: str
) -> dict[str, float]:
    """A free place beside ``anchor``, at the spacing the diagram already uses."""
    style = house_style(diagram)
    x, y = anchor["position"]["x"], anchor["position"]["y"]
    if side in ("right", "left"):
        x += style["dx"] if side == "right" else -style["dx"]
        return _free_spot(diagram, max(x, 0), y, (0, style["dy"]))
    y += style["dy"] if side == "below" else -style["dy"]
    return _free_spot(diagram, x, max(y, 0), (style["dx"], 0))


def next_position(diagram: dict[str, Any]) -> dict[str, float]:
    """A free place under what is there; connecting and ``auto_layout`` place it properly."""
    if not diagram["nodes"]:
        return {"x": 80.0, "y": 80.0}
    bottom = max(n["position"]["y"] for n in diagram["nodes"])
    left = min(n["position"]["x"] for n in diagram["nodes"])
    return _free_spot(diagram, left, bottom + GRID_Y, (GRID_X, 0))


def place_new(diagram: dict[str, Any], names: set[str]) -> list[str]:
    """Place the named nodes among the others, which stay exactly where they are: each one goes
    next to what it connects to, in the diagram's own direction and spacing."""
    style = house_style(diagram)
    by_id = {n["id"]: n for n in diagram["nodes"]}
    pending = [n for n in diagram["nodes"] if n["name"] in names]
    fixed = {n["id"] for n in diagram["nodes"] if n["name"] not in names}
    placed: list[str] = []
    ahead = 1 if style["forward"] else -1
    while pending:
        scored = []
        for node in pending:
            before = [
                c["from"]["node"] for c in diagram["connections"]
                if c["to"]["node"] == node["id"] and c["from"]["node"] in fixed
            ]
            after = [
                c["to"]["node"] for c in diagram["connections"]
                if c["from"]["node"] == node["id"] and c["to"]["node"] in fixed
            ]
            scored.append((len(before) + len(after), node, before, after))
        scored.sort(key=lambda entry: -entry[0])
        count, node, before, after = scored[0]
        pending.remove(node)
        others = [o for o in diagram["nodes"] if o is not node]
        rest = {**diagram, "nodes": others}
        if count == 0:
            node["position"] = next_position(rest)
        else:
            axis = "y" if style["vertical"] else "x"
            step = style["dy"] if style["vertical"] else style["dx"]
            cross = "x" if style["vertical"] else "y"
            near = [by_id[i]["position"] for i in [*before, *after]]
            main = [by_id[i]["position"][axis] + ahead * step for i in before] + [
                by_id[i]["position"][axis] - ahead * step for i in after
            ]
            spot = {
                axis: sum(main) / len(main),
                cross: sum(p[cross] for p in near) / len(near),
            }
            walk = (style["dx"], 0.0) if style["vertical"] else (0.0, style["dy"])
            node["position"] = _free_spot(rest, max(spot["x"], 0), max(spot["y"], 0), walk)
        fixed.add(node["id"])
        placed.append(node["name"])
    return placed


def overlaps(diagram: dict[str, Any]) -> list[str]:
    """Pairs of nodes on top of each other."""
    out = []
    nodes = diagram["nodes"]
    for i, a in enumerate(nodes):
        for b in nodes[i + 1:]:
            if (
                abs(a["position"]["x"] - b["position"]["x"]) < NODE_WIDTH - 20
                and abs(a["position"]["y"] - b["position"]["y"]) < NODE_HEIGHT - 20
            ):
                out.append(f"{a['name']} and {b['name']}")
    return out


def add_node(
    doc: dict[str, Any],
    diagram: dict[str, Any],
    name: str,
    block: dict[str, Any],
    *,
    params: dict[str, str] | None = None,
    constants: dict[str, Any] | None = None,
    starts: dict[str, str] | None = None,
    position: dict[str, float] | None = None,
) -> dict[str, Any]:
    if not NODE_NAME.fullmatch(name):
        raise ToolError(f"{name!r} is not a node name (letters, digits, _; no leading digit)")
    if any(n["name"] == name for n in diagram["nodes"]):
        raise ToolError(f"this diagram already has a node {name!r}")
    node = {
        "id": _next_id(doc, "n", "nodes"),
        "name": name,
        "block": block,
        "position": position or next_position(diagram),
        "rotation": 0,
        "flipX": False,
        "params": params or {},
        "constants": constants or {},
        "starts": starts or {},
        "ui": {"showLabel": True, "color": None},
    }
    diagram["nodes"].append(node)
    return node


def empty_subsystem() -> dict[str, Any]:
    return {
        "subsystem": {
            "ports": [],
            "diagram": {"nodes": [], "connections": [], "subsystemPorts": [], "annotations": []},
        }
    }


def remove_node(diagram: dict[str, Any], node: dict[str, Any]) -> list[str]:
    """Remove a node, its connections and the subsystem ports that attach to it."""
    identifier = node["id"]
    gone = [
        c for c in diagram["connections"]
        if identifier in (c["from"]["node"], c["to"]["node"])
    ]
    diagram["connections"] = [c for c in diagram["connections"] if c not in gone]
    diagram["nodes"] = [n for n in diagram["nodes"] if n["id"] != identifier]
    return [c["id"] for c in gone]


# ---------------------------------------------------------------------------- ports


def ports_of(
    node: dict[str, Any], interface: dict[str, Any] | None
) -> list[dict[str, Any]]:
    """One descriptor per port of a node; ``interface`` is its catalog entry (blocks only)."""
    block = node["block"]
    if "subsystem" in block:
        out = []
        for port in block["subsystem"]["ports"]:
            if port["kind"] == "signal":
                out.append({
                    "name": port["name"], "kind": "signal", "direction": port["direction"],
                    "type": port.get("type"), "size": port.get("size", []),
                    "unit": port.get("unit"),
                })
            else:
                size = port.get("size", [1])
                out.append({
                    "name": port["name"], "kind": "power", "domain": port["domain"],
                    "size": [] if size == [1] else size,
                })
        return out
    if interface is None:
        return []
    return [
        *({"name": p["name"], "kind": "signal", "direction": "input", "type": p["type"],
           "size": p["size"], "unit": p.get("unit")} for p in interface["inputs"]),
        *({"name": p["name"], "kind": "signal", "direction": "output", "type": p["type"],
           "size": p["size"], "unit": p.get("unit")} for p in interface["outputs"]),
        *({"name": p["name"], "kind": "power", "domain": p["domain"], "size": p["size"],
           "frame": p.get("frame")} for p in interface["ports"]),
    ]


def split_endpoint(text: str) -> tuple[str, str | None]:
    node, dot, port = text.rpartition(".")
    return (node, port) if dot else (text, None)


def _endpoint(node_id: str, port: str | None) -> dict[str, str]:
    return {"node": node_id} if port is None else {"node": node_id, "port": port}


def _same(end: dict[str, Any], node_id: str, port: str | None) -> bool:
    return end["node"] == node_id and end.get("port") == port


def connect(
    doc: dict[str, Any],
    from_text: str,
    to_text: str,
    interfaces: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    """Add a connection; signals are put output -> input, the kind follows from the ports."""
    ends = []
    for text in (from_text, to_text):
        ref, port = split_endpoint(text)
        diagram, node, parent = locate(doc, ref)
        ends.append((diagram, node, parent, port))
    (diagram, a_node, a_parent, a_port), (_, b_node, b_parent, b_port) = ends
    if a_parent != b_parent:
        raise ToolError(
            "both ends must be in the same diagram; use expose_port to bring a port "
            "to the subsystem's boundary"
        )
    if a_node["id"] == b_node["id"]:
        raise ToolError("a block cannot connect to itself")

    def describe(node: dict[str, Any], port: str | None) -> dict[str, Any]:
        if "junction" in node["block"]:
            if port is not None:
                raise ToolError(f"junction {node['name']} has no named ports: use just its name")
            return {"junction": True, "kind": "power", "domain": "Generic", "size": []}
        if port is None:
            raise ToolError(f"name the port of {node['name']}, like {node['name']}.p",
                            ports=ports_of(node, interfaces.get(node["id"])))
        known = ports_of(node, interfaces.get(node["id"]))
        found = next((p for p in known if p["name"] == port), None)
        if found is None:
            if not known:
                return {"kind": None}  # an interface we cannot read: model.check decides
            raise ToolError(f"{node['name']} has no port {port!r}", ports=known)
        return found

    a, b = describe(a_node, a_port), describe(b_node, b_port)
    connections = diagram["connections"]
    source, target = (a_node, a_port), (b_node, b_port)
    if a["kind"] is None or b["kind"] is None:
        kind = "signal" if "signal" in (a["kind"], b["kind"]) else "bond"
    elif a["kind"] != b["kind"]:
        raise ToolError("a power port cannot connect to a signal port; use a sensor or a source")
    elif a["kind"] == "signal":
        kind = "signal"
        if a["direction"] == b["direction"]:
            raise ToolError("a signal connection runs from an output to an input")
        if a["direction"] == "input":
            source, target = target, source
            a, b = b, a
        taken = any(
            c["kind"] == "signal" and _same(c["to"], target[0]["id"], target[1])
            for c in connections
        )
        if taken:
            raise ToolError(f"input {target[0]['name']}.{target[1]} already has a source")
        if a.get("type") != b.get("type") and None not in (a.get("type"), b.get("type")):
            raise ToolError(f"{a['type']} cannot connect to {b['type']}; insert a conversion")
        if a.get("size", []) != b.get("size", []):
            raise ToolError(f"sizes differ: {a.get('size')} and {b.get('size')}")
    else:
        generic = a["domain"] == "Generic" or b["domain"] == "Generic"
        kind = "bond" if a.get("junction") or b.get("junction") or generic else "wire"
        if not generic and a["domain"] != b["domain"]:
            raise ToolError(
                f"{a['domain']} cannot connect to {b['domain']}; use a converter block"
            )
        if a.get("size", []) != b.get("size", []):
            raise ToolError(f"power port sizes differ: {a.get('size')} and {b.get('size')}")
        for node, port, info in ((a_node, a_port, a), (b_node, b_port, b)):
            bonded = any(
                c["kind"] == "bond" and (_same(c["from"], node["id"], port) or _same(c["to"], node["id"], port))
                for c in connections
            )
            if not info.get("junction") and bonded:
                raise ToolError(f"port {node['name']}.{port} already has a bond")
    duplicate = any(
        (_same(c["from"], source[0]["id"], source[1]) and _same(c["to"], target[0]["id"], target[1]))
        or (_same(c["to"], source[0]["id"], source[1]) and _same(c["from"], target[0]["id"], target[1]))
        for c in connections
    )
    if duplicate:
        raise ToolError("these ports are already connected")
    connection = {
        "id": _next_id(doc, "c", "connections"),
        "kind": kind,
        "from": _endpoint(source[0]["id"], source[1]),
        "to": _endpoint(target[0]["id"], target[1]),
        "route": [],
        "label": None,
    }
    connections.append(connection)
    return connection


def disconnect(doc: dict[str, Any], from_text: str, to_text: str) -> str:
    from_ref, from_port = split_endpoint(from_text)
    to_ref, to_port = split_endpoint(to_text)
    diagram, a, _ = locate(doc, from_ref)
    _, b, _ = locate(doc, to_ref)
    for connection in diagram["connections"]:
        forward = _same(connection["from"], a["id"], from_port) and _same(connection["to"], b["id"], to_port)
        back = _same(connection["from"], b["id"], to_port) and _same(connection["to"], a["id"], from_port)
        if forward or back:
            diagram["connections"].remove(connection)
            return connection["id"]
    raise ToolError(f"no connection between {from_text} and {to_text}")


def expose_port(
    doc: dict[str, Any],
    inner_endpoint: str,
    name: str,
    interfaces: dict[str, dict[str, Any]],
    domain: str | None,
) -> dict[str, Any]:
    """Expose a port of a node inside a subsystem on the subsystem's outside face."""
    ref, port = split_endpoint(inner_endpoint)
    parts = split_path(ref)
    if len(parts) < 2:
        raise ToolError("expose_port takes a node inside a subsystem, like Drive/Motor.p")
    _, node, parent = locate(doc, ref)
    outer = diagram_at(doc, parent[:-1])
    owner = next(n for n in outer["nodes"] if n["name"] == parent[-1])
    subsystem = subsystem_of(owner)
    assert subsystem is not None
    if any(p["name"] == name for p in subsystem["ports"]):
        raise ToolError(f"{parent[-1]} already has a port {name!r}")
    if not NODE_NAME.fullmatch(name):
        raise ToolError(f"{name!r} is not a port name")
    if "junction" in node["block"]:
        info: dict[str, Any] = {"kind": "power", "domain": domain or "Generic", "size": []}
        port_name = ""
    else:
        known = ports_of(node, interfaces.get(node["id"]))
        found = next((p for p in known if p["name"] == port), None)
        if found is None:
            raise ToolError(f"{node['name']} has no port {port!r}", ports=known)
        info, port_name = found, str(port)
    if info["kind"] == "signal":
        entry: dict[str, Any] = {
            "name": name, "kind": "signal", "direction": info["direction"],
            "type": info.get("type") or "Real", "size": info.get("size", []),
            "unit": info.get("unit"), "node": node["id"], "port": port_name,
        }
    else:
        adopted = domain or info["domain"]
        axis = {"Planar": 3, "Spatial": 6}.get(adopted, 1)
        entry = {
            "name": name, "kind": "power", "domain": adopted, "size": [axis],
            "node": node["id"], "port": port_name,
        }
    subsystem["ports"].append(entry)
    return entry


# ---------------------------------------------------------------------------- layout


def _hanging(diagram: dict[str, Any]) -> dict[str, str]:
    """node id -> junction id, for elements with one bond that end on a junction: they read best
    above and below their junction, as in a bond graph drawn by hand."""
    degree: dict[str, list[str]] = {}
    for c in diagram["connections"]:
        degree.setdefault(c["from"]["node"], []).append(c["to"]["node"])
        degree.setdefault(c["to"]["node"], []).append(c["from"]["node"])
    junctions = {n["id"] for n in diagram["nodes"] if "junction" in n["block"]}
    elements = {
        n["id"] for n in diagram["nodes"]
        if re.fullmatch(r"stdlib:bondgraph/M?[RCI]", n["block"].get("ref") or "")
    }
    return {
        node: around[0]
        for node, around in degree.items()
        if node in elements and len(around) == 1 and around[0] in junctions
    }


def auto_layout(diagram: dict[str, Any]) -> None:
    """A layered layout: left to right along the connections, barycentre order per layer, and the
    elements of a bond graph above and below their junctions."""
    hanging = _hanging(diagram)
    spine = {**diagram, "nodes": [n for n in diagram["nodes"] if n["id"] not in hanging]}
    _layer(spine, 3 if hanging else 1)
    at = {n["id"]: n for n in spine["nodes"]}
    sides: dict[str, int] = {}
    for node in diagram["nodes"]:
        junction = hanging.get(node["id"])
        if junction is None:
            continue
        count = sides.get(junction, 0)
        sides[junction] = count + 1
        base = at[junction]["position"]
        direction = -1 if count % 2 == 0 else 1
        node["position"] = {
            "x": base["x"] + (count // 2) * (NODE_WIDTH + 20),
            "y": base["y"] + direction * GRID_Y,
        }
    top = min(n["position"]["y"] for n in diagram["nodes"]) if diagram["nodes"] else 80
    if top < 80:
        for node in diagram["nodes"]:
            node["position"]["y"] += 80 - top
    for connection in diagram["connections"]:
        connection["route"] = []


def _layer(diagram: dict[str, Any], rows: int) -> None:
    nodes = diagram["nodes"]
    index = {n["id"]: i for i, n in enumerate(nodes)}
    successors: list[list[int]] = [[] for _ in nodes]
    predecessors: list[list[int]] = [[] for _ in nodes]
    state = [0] * len(nodes)
    order: list[int] = []
    edges = [
        (index[c["from"]["node"]], index[c["to"]["node"]])
        for c in diagram["connections"]
        if c["from"]["node"] in index and c["to"]["node"] in index
    ]
    raw: list[list[int]] = [[] for _ in nodes]
    for source, target in edges:
        raw[source].append(target)

    # Depth-first, dropping the edges that close a cycle (a feedback path keeps its layer).
    def visit(start: int) -> None:
        stack = [(start, iter(raw[start]))]
        state[start] = 1
        while stack:
            current, children = stack[-1]
            for child in children:
                if state[child] == 1:
                    continue
                successors[current].append(child)
                predecessors[child].append(current)
                if state[child] == 0:
                    state[child] = 1
                    stack.append((child, iter(raw[child])))
                    break
            else:
                state[current] = 2
                order.append(current)
                stack.pop()

    incoming = {target for _, target in edges}
    for i in sorted(range(len(nodes)), key=lambda k: (k in incoming, k)):
        if state[i] == 0:
            visit(i)

    layer = [0] * len(nodes)
    for current in reversed(order):
        for child in successors[current]:
            layer[child] = max(layer[child], layer[current] + 1)

    columns: dict[int, list[int]] = {}
    for i, column in enumerate(layer):
        columns.setdefault(column, []).append(i)
    rank = {i: position for members in columns.values() for position, i in enumerate(members)}
    for column in sorted(columns):
        members = columns[column]
        def barycentre(i: int, members: list[int] = members) -> float:
            around = predecessors[i]
            return sum(rank[p] for p in around) / len(around) if around else rank[i]
        members.sort(key=barycentre)
        for position, i in enumerate(members):
            rank[i] = position
    for column, members in columns.items():
        for position, i in enumerate(members):
            nodes[i]["position"] = {"x": 80 + GRID_X * column, "y": 80 + rows * GRID_Y * position}


# ---------------------------------------------------------------------------- views


def _end_text(diagram: dict[str, Any], end: dict[str, Any], names: dict[str, str]) -> str:
    name = names.get(end["node"], end["node"])
    return f"{name}.{end['port']}" if end.get("port") else name


def describe_diagram(doc: dict[str, Any], path: list[str]) -> dict[str, Any]:
    """One level of a model in the agent's vocabulary: names, not ids."""
    diagram = diagram_at(doc, path)
    names = {n["id"]: n["name"] for n in diagram["nodes"]}
    nodes = []
    for node in diagram["nodes"]:
        entry: dict[str, Any] = {
            "name": node["name"], "at": [node["position"]["x"], node["position"]["y"]],
        }
        block = node["block"]
        if "ref" in block:
            entry["block"] = block["ref"]
        elif "junction" in block:
            entry["junction"] = block["junction"]
        elif "inline" in block:
            entry["inline"] = block["inline"]["source"]
        else:
            entry["subsystem"] = {
                "ports": [p["name"] for p in block["subsystem"]["ports"]],
                "nodes": len(block["subsystem"]["diagram"]["nodes"]),
            }
        for key in ("params", "constants", "starts"):
            if node.get(key):
                entry[key] = node[key]
        nodes.append(entry)
    result: dict[str, Any] = {
        "nodes": nodes,
        "connections": [
            f"{_end_text(diagram, c['from'], names)} -> {_end_text(diagram, c['to'], names)} [{c['kind']}]"
            for c in diagram["connections"]
        ],
    }
    notes = [a["text"] for a in diagram.get("annotations") or [] if a.get("text")]
    if notes:
        result["notes"] = notes
    if nodes:
        style = house_style(diagram)
        result["layout"] = {
            "flow": ("down" if style["forward"] else "up") if style["vertical"]
            else ("right" if style["forward"] else "left"),
            "spacing": [style["dx"], style["dy"]],
        }
        crowded = overlaps(diagram)
        if crowded:
            result["layout"]["overlapping"] = crowded
    return result


def describe_model(doc: dict[str, Any], path: list[str]) -> dict[str, Any]:
    result = {"name": doc["name"], "level": "/".join(path) or "top", **describe_diagram(doc, path)}
    if not path:
        result["settings"] = doc["settings"]
        result["globals"] = doc.get("parameters") or []
        result["plots"] = [
            {"title": p["title"], "signals": p["signals"]} for p in doc.get("plots") or []
        ]
        result["hasDashboard"] = bool((doc.get("dashboard") or {}).get("cards"))
        result["hasScene"] = doc.get("scene") is not None
        subsystems = [
            "/".join([*level, n["name"]])
            for level, diagram in walk_diagrams(doc)
            for n in diagram["nodes"]
            if subsystem_of(n) is not None
        ]
        if subsystems:
            result["subsystems"] = subsystems
    return result


def diagram_figure(
    doc: dict[str, Any], path: list[str], figure_id: str, title: str
) -> dict[str, Any]:
    diagram = diagram_at(doc, path)
    kinds = {"junction": "junction", "subsystem": "subsystem"}
    known = {n["id"] for n in diagram["nodes"]}
    return {
        "id": figure_id,
        "kind": "diagram",
        "title": title,
        "model": doc["name"],
        "path": path,
        "nodes": [
            {
                "id": n["id"], "name": n["name"],
                "kind": next((kinds[k] for k in kinds if k in n["block"]), "block"),
                "label": block_label(n),
                "x": n["position"]["x"], "y": n["position"]["y"],
            }
            for n in diagram["nodes"]
        ],
        "edges": [
            {"from": c["from"]["node"], "to": c["to"]["node"], "kind": c["kind"]}
            for c in diagram["connections"]
            if c["from"]["node"] in known and c["to"]["node"] in known
        ],
    }


# ---------------------------------------------------------------------------- draft support


def inline_blocks(doc: dict[str, Any], sources: dict[str, str | None]) -> dict[str, Any]:
    """A copy of ``doc`` whose ``project:<name>`` nodes carry the draft's block source inline.

    The worker reads project blocks from disk, so this is how a draft block is checked and
    simulated before it is saved. Instance names, hence signal ids, do not change.
    """

    def block(node: dict[str, Any]) -> dict[str, Any]:
        value = node["block"]
        ref = value.get("ref", "")
        if ref.startswith("project:") and sources.get(ref[len("project:"):]) is not None:
            return {"inline": {"source": sources[ref[len("project:"):]]}}
        if "subsystem" in value:
            inner = value["subsystem"]
            return {"subsystem": {**inner, "diagram": rewrite(inner["diagram"])}}
        return value

    def rewrite(diagram: dict[str, Any]) -> dict[str, Any]:
        return {**diagram, "nodes": [{**n, "block": block(n)} for n in diagram["nodes"]]}

    return {**doc, "diagram": rewrite(doc["diagram"])}


def lint(doc: dict[str, Any]) -> list[str]:
    """What would make the document unsaveable or unreadable beyond the schema."""
    problems = []
    for path, diagram in walk_diagrams(doc):
        where = "/".join(path) or "top level"
        names = [n["name"] for n in diagram["nodes"]]
        for name in sorted({n for n in names if names.count(n) > 1}):
            problems.append(f"{where}: two nodes are called {name}")
        ids = {n["id"] for n in diagram["nodes"]}
        for connection in diagram["connections"]:
            for side in ("from", "to"):
                if connection[side]["node"] not in ids:
                    problems.append(f"{where}: connection {connection['id']} has a dangling {side} end")
    return problems


DISPLAY_CARDS = ("plot", "value", "gauge", "bar", "indicator")
INPUT_CARDS = ("number", "slider", "knob", "toggle", "select")
SDF_GEOMETRY = ("box", "cylinder", "sphere", "mesh")
SDF_JOINTS = ("revolute", "continuous", "prismatic", "fixed")


def card_problems(doc: dict[str, Any]) -> list[str]:
    """Dashboard cards that pass the schema but would show nothing: the wrong binding field, or
    none. The UI only says so on the card."""
    problems = []
    globals_ = {p["name"] for p in doc.get("parameters") or []}
    for card in (doc.get("dashboard") or {}).get("cards", []):
        where, kind = f"card {card['id']} ({card['kind']})", card["kind"]
        if kind in DISPLAY_CARDS:
            if "parameter" in card:
                problems.append(f"{where}: display cards bind through `signals`, not `parameter`")
            if not card.get("signals"):
                problems.append(f"{where}: give `signals`, an array of signal ids")
        elif kind in INPUT_CARDS:
            if "signals" in card:
                problems.append(f"{where}: input cards bind through `parameter`, not `signals`")
            parameter = card.get("parameter")
            if parameter is None:
                problems.append(f"{where}: give `parameter`, global:<name> or <instance path>/<param>")
            elif parameter.startswith("global:"):
                name = parameter[len("global:"):]
                if kind in ("toggle", "select"):
                    problems.append(f"{where}: bind a block parameter; only number, slider and knob take a global")
                if name not in globals_:
                    problems.append(f"{where}: no global {name!r}: create it with set_globals first")
        elif kind == "schedule" and not (card.get("schedule") or {}).get("parameters"):
            problems.append(f"{where}: give `schedule` with `parameters` and `rows`")
        elif kind == "text" and "text" not in (card.get("options") or {}):
            problems.append(f"{where}: give the text as `options.text`")
    return problems


def bound_parameters(doc: dict[str, Any]) -> list[str]:
    """The block parameters the dashboard's input and schedule cards name."""
    out = []
    for card in (doc.get("dashboard") or {}).get("cards", []):
        parameter = card.get("parameter")
        if parameter is not None and not parameter.startswith("global:"):
            out.append(parameter)
        out.extend((card.get("schedule") or {}).get("parameters", []))
    return out


def scene_names(text: str) -> dict[str, set[str]]:
    """The targets an SDF scene offers to bindings. The viewer draws the supported subset of SDF
    (web/src/scene/sdf.ts) and refuses the rest: this says so while the agent can still fix it."""
    if "<!DOCTYPE" in text or "<!ENTITY" in text:
        raise ToolError("the scene may not have a DOCTYPE or entities")
    try:
        root = ElementTree.fromstring(text)
    except ElementTree.ParseError as exc:
        raise ToolError(f"the scene is not well-formed XML: {exc}") from None
    if root.tag != "sdf":
        raise ToolError(f"the root element is <{root.tag}>, it must be <sdf>")
    if root.find(".//model") is None:
        raise ToolError("the scene has no <model>")
    names: dict[str, set[str]] = {"link": set(), "visual": set(), "joint": set()}
    for kind, found in names.items():
        for element in root.iter(kind):
            name = element.get("name")
            if not name:
                raise ToolError(f"a <{kind}> has no name")
            if name in found:
                raise ToolError(f"two <{kind}> elements are called {name}")
            found.add(name)
    if not names["visual"]:
        raise ToolError("the scene has no <visual>: there is nothing to draw")
    for visual in root.iter("visual"):
        geometry = visual.find("geometry")
        shapes = [] if geometry is None else [child.tag for child in geometry]
        if not set(shapes) & set(SDF_GEOMETRY):
            raise ToolError(f"visual {visual.get('name')}: <geometry> needs one of {list(SDF_GEOMETRY)}")
    for joint in root.iter("joint"):
        if joint.get("type") not in SDF_JOINTS:
            raise ToolError(f"joint {joint.get('name')}: type must be one of {list(SDF_JOINTS)}")
    return names


def binding_warnings(bindings: list[dict[str, Any]], names: dict[str, set[str]]) -> list[str]:
    """Bindings whose target is not in the scene: they would move nothing, without an error."""
    out = []
    for binding in bindings:
        kind, _, name = str(binding.get("target", "")).partition(":")
        if kind in names and name not in names[kind]:
            out.append(f"{binding['target']} is not in the scene; it has {sorted(names[kind])[:30]}")
    return out


def _text(value: Any) -> str | None:
    return None if value is None else (value if isinstance(value, str) else str(value))


def _diff_map(rows: list[dict[str, Any]], prefix: str, before: dict, after: dict) -> None:
    for key in sorted({*before, *after}):
        if before.get(key) != after.get(key):
            op = "added" if key not in before else "removed" if key not in after else "changed"
            rows.append({
                "op": op, "what": f"{prefix}{key}",
                "before": _text(before.get(key)), "after": _text(after.get(key)),
            })


def _diff_diagram(
    rows: list[dict[str, Any]], path: list[str], before: dict[str, Any], after: dict[str, Any]
) -> bool:
    """Add the rows of one level; True when only positions and routes differ here."""
    prefix = "".join(f"{p}/" for p in path)
    old = {n["id"]: n for n in before["nodes"]}
    new = {n["id"]: n for n in after["nodes"]}
    moved = False
    for identifier, node in new.items():
        if identifier not in old:
            rows.append({"op": "added", "what": f"block {prefix}{node['name']}",
                         "before": None, "after": block_label(node)})
    for identifier, node in old.items():
        if identifier not in new:
            rows.append({"op": "removed", "what": f"block {prefix}{node['name']}",
                         "before": block_label(node), "after": None})
    for identifier in old.keys() & new.keys():
        a, b = old[identifier], new[identifier]
        label = f"{prefix}{b['name']}"
        if a["name"] != b["name"]:
            rows.append({"op": "changed", "what": f"name of {prefix}{a['name']}",
                         "before": a["name"], "after": b["name"]})
        moved = moved or a["position"] != b["position"]
        for key, tag in (("params", ""), ("constants", "constant "), ("starts", "start ")):
            _diff_map(rows, f"{label}.{tag}", a.get(key) or {}, b.get(key) or {})
        inner_a, inner_b = subsystem_of(a), subsystem_of(b)
        if inner_a is not None and inner_b is not None:
            moved = _diff_diagram(rows, [*path, b["name"]], inner_a["diagram"], inner_b["diagram"]) or moved
            names_a = [p["name"] for p in inner_a["ports"]]
            names_b = [p["name"] for p in inner_b["ports"]]
            if names_a != names_b:
                rows.append({"op": "changed", "what": f"ports of {label}",
                             "before": ", ".join(names_a), "after": ", ".join(names_b)})
        elif a["block"] != b["block"]:
            rows.append({"op": "changed", "what": f"block of {label}",
                         "before": block_label(a), "after": block_label(b)})

    def connection_text(diagram: dict[str, Any]) -> dict[str, str]:
        names = {n["id"]: n["name"] for n in diagram["nodes"]}
        return {
            c["id"]: f"{prefix}{_end_text(diagram, c['from'], names)} -> {_end_text(diagram, c['to'], names)}"
            for c in diagram["connections"]
        }

    old_text, new_text = connection_text(before), connection_text(after)
    for identifier, text in new_text.items():
        if identifier not in old_text:
            rows.append({"op": "added", "what": f"connection {text}", "before": None, "after": None})
    for identifier, text in old_text.items():
        if identifier not in new_text:
            rows.append({"op": "removed", "what": f"connection {text}", "before": None, "after": None})
    if (before.get("annotations") or []) != (after.get("annotations") or []):
        rows.append({"op": "changed", "what": f"notes of {prefix or 'top level'}", "before": None, "after": None})
    return moved


def diff_models(before: dict[str, Any] | None, after: dict[str, Any] | None) -> list[dict[str, Any]]:
    if before is None or after is None:
        doc = after or before
        assert doc is not None
        blocks = sum(len(d["nodes"]) for _, d in walk_diagrams(doc))
        connections = sum(len(d["connections"]) for _, d in walk_diagrams(doc))
        op = "added" if before is None else "removed"
        return [{"op": op, "what": f"{blocks} blocks, {connections} connections",
                 "before": None, "after": None}]
    rows: list[dict[str, Any]] = []
    moved = _diff_diagram(rows, [], before["diagram"], after["diagram"])
    globals_a = {p["name"]: p["value"] for p in before.get("parameters") or []}
    globals_b = {p["name"]: p["value"] for p in after.get("parameters") or []}
    _diff_map(rows, "global ", globals_a, globals_b)
    _diff_map(rows, "settings.", before["settings"], after["settings"])
    for key in ("plots", "dashboard", "scene", "bindings"):
        if (before.get(key) or None) != (after.get(key) or None):
            rows.append({"op": "changed", "what": key, "before": None, "after": None})
    if moved:
        rows.append({"op": "changed", "what": "layout", "before": None, "after": None})
    if len(rows) > MAX_ROWS_PER_FILE:
        extra = len(rows) - MAX_ROWS_PER_FILE
        rows = [*rows[:MAX_ROWS_PER_FILE],
                {"op": "changed", "what": f"... and {extra} more changes", "before": None, "after": None}]
    return rows
