"""Model-document helpers of the `cars` example: a small diagram builder (nodes, bonds, signals,
junctions, subsystems with signal and power ports) and quaternion/pose utilities."""

from __future__ import annotations

import math


def num(v: float) -> str:
    return repr(float(v))


def vec(values) -> str:
    return "[" + ", ".join(repr(float(v)) for v in values) + "]"


def ex(v) -> str:
    """A number, or an expression over global parameters as it is."""
    return v if isinstance(v, str) else num(v)


def quat_x(angle: float) -> tuple[float, float, float, float]:
    return (math.cos(angle / 2), math.sin(angle / 2), 0.0, 0.0)


def quat_z(angle: float) -> tuple[float, float, float, float]:
    return (math.cos(angle / 2), 0.0, 0.0, math.sin(angle / 2))


# The wheel carrier frame in the chassis-aligned frame: carrier z = chassis y (the axle, to the
# left), carrier x = chassis x, carrier y = -chassis z. Rx(-90 deg).
Q_CARRIER = quat_x(-math.pi / 2)


def pose_params(q, p) -> dict:
    return {"qw": num(q[0]), "qx": num(q[1]), "qy": num(q[2]), "qz": num(q[3]),
            "x": num(p[0]), "y": num(p[1]), "z": num(p[2])}


class Diagram:
    """A diagram of nodes and connections; `subsystem` wraps it as a node of a parent."""

    def __init__(self) -> None:
        self.nodes: list[dict] = []
        self.connections: list[tuple] = []
        self.annotations: list[dict] = []
        self.ports: list[dict] = []
        self.ids: dict[str, str] = {}

    def node(self, name, block, x, y, params=None, starts=None, constants=None) -> str:
        assert name not in self.ids, name
        nid = f"n{len(self.nodes) + 1:03d}"
        b = {"ref": block} if isinstance(block, str) else block
        self.nodes.append({
            "id": nid, "name": name, "block": b, "position": {"x": int(x), "y": int(y)}, "rotation": 0,
            "flipX": False, "params": {k: str(v) for k, v in (params or {}).items()},
            "constants": {k: str(v) for k, v in (constants or {}).items()},
            "starts": {k: str(v) for k, v in (starts or {}).items()},
            "ui": {"showLabel": True, "color": None},
        })
        self.ids[name] = nid
        return name

    def junction(self, name, kind, x, y) -> str:
        return self.node(name, {"junction": str(kind)}, x, y)

    def _conn(self, kind, a, pa, b, pb):
        self.connections.append((kind, a, pa, b, pb))

    def sig(self, a, pa, b, pb):
        self._conn("signal", a, pa, b, pb)

    def bond(self, a, pa, b, pb):
        self._conn("bond", a, pa, b, pb)

    def note(self, text, x, y, w, h, color=None):
        a = {"id": f"a{len(self.annotations) + 1}", "kind": "text", "text": text, "x": x, "y": y, "w": w, "h": h}
        if color:
            a["color"] = color
        self.annotations.append(a)

    def port(self, name, direction, node, port, unit=None, size=1):
        self.ports.append({"name": name, "kind": "signal", "direction": direction, "type": "Real", "size": [size],
                           "unit": unit, "node": self.ids[node], "port": port})

    def power_port(self, name, domain, node, port=None, size=1):
        p = {"name": name, "kind": "power", "domain": domain, "size": [size], "node": self.ids[node]}
        if port is not None:
            p["port"] = port
        self.ports.append(p)

    def doc(self, prefix: str = "") -> dict:
        """The diagram document; `prefix` makes the connection ids unique across subsystems
        (the causality analysis keys bonds by connection id over the whole flattened model)."""
        conns = []
        for k, (kind, a, pa, b, pb) in enumerate(self.connections):
            frm = {"node": self.ids[a]}
            if pa is not None:
                frm["port"] = pa
            to = {"node": self.ids[b]}
            if pb is not None:
                to["port"] = pb
            conns.append({"id": f"{prefix}c{k + 1:03d}", "kind": kind, "from": frm, "to": to})
        d = {"nodes": self.nodes, "connections": conns, "annotations": self.annotations}
        if self.ports:
            d["subsystemPorts"] = self.ports
        return d

    def subsystem(self, parent: "Diagram", name: str, x: float, y: float) -> str:
        parent.node(name, {"subsystem": {"ports": self.ports, "diagram": self.doc(name + "_")}}, x, y)
        return name


def g(name, value, unit=None, description=None) -> dict:
    return {"name": name, "value": value if isinstance(value, str) else num(value), "unit": unit,
            "description": description}


def settings(t_end: float, points: int, solver="Rodas5P", reltol=1e-6, abstol=1e-8) -> dict:
    return {"t_start": 0.0, "t_end": float(t_end), "solver": solver, "reltol": reltol, "abstol": abstol,
            "max_step": None, "output": {"mode": "points", "points": int(points)}, "event_limit": 100000}


def model_doc(name, comment, d: Diagram, sett, plots, scene, bindings, parameters, dashboard=None) -> dict:
    doc = {"format": "bgsim.model", "language": "0.1.0", "name": name, "$comment": comment,
           "diagram": d.doc(), "settings": sett, "plots": plots,
           "scene": {"file": scene} if scene else None, "bindings": bindings, "parameters": parameters}
    if dashboard is not None:
        doc["dashboard"] = dashboard
    return doc
