"""A small writer for bgsim model documents (the `Diagram` of panda-3d's design/diagram.py)."""

from __future__ import annotations

import numpy as np

import srs


def fmt(value: float) -> str:
    return repr(float(value))


def vec(values) -> str:
    return "[" + ", ".join(fmt(v) for v in values) + "]"


def mat(m) -> str:
    return "[" + "; ".join(" ".join(fmt(x) for x in row) for row in m) + "]"


def clean(value: float) -> float:
    return 0.0 if abs(value) < 1e-15 else float(value)


def pose_params(t: np.ndarray) -> dict:
    """LocalPose3D / FixedTransform3DNeutral parameters of a homogeneous transform."""
    names = ("qw", "qx", "qy", "qz", "x", "y", "z")
    return {n: fmt(clean(v)) for n, v in zip(names, srs.pose7(t), strict=True)}


class Diagram:
    def __init__(self) -> None:
        self.nodes: list[dict] = []
        self.connections: list[dict] = []
        self.annotations: list[dict] = []

    def node(self, key, name, block, x, y, params=None, constants=None, starts=None, rotation=0, flip=False):
        self.nodes.append(
            {
                "id": key,
                "name": name,
                "block": block,
                "position": {"x": int(x), "y": int(y)},
                "rotation": rotation,
                "flipX": flip,
                "params": {k: str(v) for k, v in (params or {}).items()},
                "constants": {k: str(v) for k, v in (constants or {}).items()},
                "starts": {k: str(v) for k, v in (starts or {}).items()},
                "ui": {"showLabel": True, "color": None},
            }
        )
        return key

    def ref(self, key, name, ref, x, y, **kw):
        return self.node(key, name, {"ref": ref}, x, y, **kw)

    def junction(self, key, name, kind, x, y):
        return self.node(key, name, {"junction": kind}, x, y)

    def connect(self, kind, a, b, route=None, label=None):
        def end(pair):
            node, port = pair
            return {"node": node} if port is None else {"node": node, "port": port}

        self.connections.append(
            {
                "id": f"{kind[0]}{len(self.connections) + 1:04d}",
                "kind": kind,
                "from": end(a),
                "to": end(b),
                "route": [{"x": int(px), "y": int(py)} for px, py in (route or [])],
                "label": label,
            }
        )

    def note(self, key, text, x, y, w=420, h=120):
        self.annotations.append(
            {"id": key, "kind": "note", "text": text, "position": {"x": int(x), "y": int(y)},
             "size": {"width": int(w), "height": int(h)}}  # fmt: skip
        )

    def document(self) -> dict:
        return {"nodes": self.nodes, "connections": self.connections, "subsystemPorts": [], "annotations": self.annotations}
