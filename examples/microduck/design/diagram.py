"""A small writer for bgsim model documents (after panda-3d's design/diagram.py)."""

from __future__ import annotations

import numpy as np


def fmt(value) -> str:
    if isinstance(value, str):
        return value
    return repr(float(value))


def vec(values) -> str:
    return "[" + ", ".join(fmt(v) for v in values) + "]"


def clean(value: float) -> float:
    return 0.0 if abs(value) < 1e-15 else float(value)


def quat_of(rot: np.ndarray) -> np.ndarray:
    """Unit quaternion (w, x, y, z) of a rotation matrix, w >= 0."""
    m = rot
    tr = m[0, 0] + m[1, 1] + m[2, 2]
    if tr > 0:
        s = np.sqrt(tr + 1.0) * 2
        q = [0.25 * s, (m[2, 1] - m[1, 2]) / s, (m[0, 2] - m[2, 0]) / s, (m[1, 0] - m[0, 1]) / s]
    elif m[0, 0] > m[1, 1] and m[0, 0] > m[2, 2]:
        s = np.sqrt(1.0 + m[0, 0] - m[1, 1] - m[2, 2]) * 2
        q = [(m[2, 1] - m[1, 2]) / s, 0.25 * s, (m[0, 1] + m[1, 0]) / s, (m[0, 2] + m[2, 0]) / s]
    elif m[1, 1] > m[2, 2]:
        s = np.sqrt(1.0 + m[1, 1] - m[0, 0] - m[2, 2]) * 2
        q = [(m[0, 2] - m[2, 0]) / s, (m[0, 1] + m[1, 0]) / s, 0.25 * s, (m[1, 2] + m[2, 1]) / s]
    else:
        s = np.sqrt(1.0 + m[2, 2] - m[0, 0] - m[1, 1]) * 2
        q = [(m[1, 0] - m[0, 1]) / s, (m[0, 2] + m[2, 0]) / s, (m[1, 2] + m[2, 1]) / s, 0.25 * s]
    q = np.array(q)
    q /= np.linalg.norm(q)
    return -q if q[0] < 0 else q


def pose_params(t: np.ndarray) -> dict:
    """LocalPose3D / FixedTransform3DNeutral parameters of a homogeneous transform."""
    q = quat_of(t[:3, :3])
    names = ("qw", "qx", "qy", "qz", "x", "y", "z")
    vals = [*q, *t[:3, 3]]
    return {n: fmt(clean(v)) for n, v in zip(names, vals, strict=True)}


class Diagram:
    def __init__(self) -> None:
        self.nodes: list[dict] = []
        self.connections: list[dict] = []
        self.ports: list[dict] = []
        self.annotations: list[dict] = []
        self._names: set[str] = set()

    def node(self, name, block, x, y, params=None, constants=None, starts=None):
        assert name not in self._names, name
        self._names.add(name)
        self.nodes.append(
            {
                "id": name,
                "name": name,
                "block": block,
                "position": {"x": int(x), "y": int(y)},
                "rotation": 0,
                "flipX": False,
                "params": {k: fmt(v) for k, v in (params or {}).items()},
                "constants": {k: fmt(v) for k, v in (constants or {}).items()},
                "starts": {k: fmt(v) for k, v in (starts or {}).items()},
                "ui": {"showLabel": True, "color": None},
            }
        )
        return name

    def ref(self, name, ref, x, y, **kw):
        return self.node(name, {"ref": ref}, x, y, **kw)

    def junction(self, name, kind, x, y):
        return self.node(name, {"junction": kind}, x, y)

    def _end(self, node, port):
        return {"node": node} if port is None else {"node": node, "port": port}

    def bond(self, a, ap, b, bp=None):
        self.connections.append({"id": f"b{len(self.connections) + 1:04d}", "kind": "bond",
                                 "from": self._end(a, ap), "to": self._end(b, bp), "route": [], "label": None})

    def wire(self, a, ap, b, bp):
        self.connections.append({"id": f"w{len(self.connections) + 1:04d}", "kind": "wire",
                                 "from": self._end(a, ap), "to": self._end(b, bp), "route": [], "label": None})

    def sig(self, a, ap, b, bp, label=None):
        self.connections.append({"id": f"s{len(self.connections) + 1:04d}", "kind": "signal",
                                 "from": self._end(a, ap), "to": self._end(b, bp), "route": [], "label": label})

    def note(self, text, x, y, w=420, h=120, color="blue"):
        self.annotations.append({"id": f"a{len(self.annotations) + 1:03d}", "kind": "text", "text": text,
                                 "x": int(x), "y": int(y), "w": int(w), "h": int(h), "color": color})

    def signal_port(self, name, direction, node, port, unit=None, x=None, y=None):
        self.ports.append({"name": name, "kind": "signal", "direction": direction, "type": "Real",
                           "size": [1], "unit": unit, "node": node, "port": port})

    def power_port(self, name, domain, node, port="junction"):
        self.ports.append({"name": name, "kind": "power", "domain": domain, "size": [1],
                           "node": node, "port": port})

    def document(self) -> dict:
        return {"nodes": self.nodes, "connections": self.connections, "subsystemPorts": [],
                "annotations": self.annotations}
