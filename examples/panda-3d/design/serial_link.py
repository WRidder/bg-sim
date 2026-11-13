"""The serial-link library subsystems `RevoluteLink3D` and `RevoluteLink3DRigid`.

One link of a spatial serial chain, as a drawn subsystem of the project library
(`library/<Name>.bgsub.json`, contract `subsystemDefinition`). The same file sits in the
`design/` folder of every example that uses it (robot-arm-3d, panda-3d, pendulum-triple-rotary,
quad-pendulum, humanoid-dual-arm), so the definitions stay identical until a shared library
version exists.

Inside (node names are the paths an instance pins and a plot reads, `L2/J/qout`):

    parent -> T -> J -> Link -> BJ (1-junction) <- B (RigidBody3D);  BJ is the port `child`
    gp -> CA (o LN) -> W (o J.pose) -> P (o LC) -> B.g;  W is the port `g`

* `T`    FixedTransform3DNeutral: the parent body's junction frame seen from the joint frame
         (for the first link of a chain: the base mount);
* `J`    the joint, `Revolute3D` (compliant held directions) or `Revolute3DRigid`;
* `Link` FixedTransform3DNeutral: the joint's child frame to the body's centre of mass;
* `B`    RigidBody3D on the body 1-junction `BJ`;
* `LN`, `CA`, `W`: the joint frame in the world, `W = gp o LN o J.pose`;
* `LC`, `P`: the body pose `P = W o LC` that B's gravity reads.

Ports: `gp` (pose of the parent joint's child frame, in), `g` (this joint's child frame, out),
`q`, `qd` (joint angle and rate), `V` (the body twist, B.V), `gb` (the body pose, P.g),
`parent` (Spatial bond in: from the parent body's junction or the ground), `drive` (the joint's
Rotation drive port), `child` (the body junction, bond out to the next link). Every offset, the joint parameters, the body and the joint's start deflections
are pinned, so an instance sets all of them.
"""

from __future__ import annotations

POSE_KEYS = ("qw", "qx", "qy", "qz", "x", "y", "z")
IDENTITY = {"qw": "1.0", "qx": "0.0", "qy": "0.0", "qz": "0.0", "x": "0.0", "y": "0.0", "z": "0.0"}
JOINT_PARAMS = {False: ("kt", "kr", "bt", "br", "q0"), True: ("q0", "Ja")}
JOINT_STARTS = {False: ("dth", "dl"), True: ()}
BODY_PARAMS = ("m", "J", "g0")
CARD = (164, 228)  # the instance card: six port rows on the right (34 + 6 * 26 + 18) and its label


def name(rigid: bool = False) -> str:
    return "RevoluteLink3DRigid" if rigid else "RevoluteLink3D"


def _node(key: str, block: dict, x: int, y: int, params: dict | None = None) -> dict:
    return {
        "id": key, "name": key, "block": block, "position": {"x": x, "y": y}, "rotation": 0, "flipX": False,
        "params": dict(params or {}), "constants": {}, "starts": {}, "ui": {"showLabel": True, "color": None},
    }  # fmt: skip


def _end(node: str, port: str | None) -> dict:
    return {"node": node} if port is None else {"node": node, "port": port}


def definition(rigid: bool = False, generator: str = "design/serial_link.py") -> dict:
    """The subsystem definition (`library/<name>.bgsub.json`)."""
    joint = "stdlib:spatial/Revolute3DRigid" if rigid else "stdlib:spatial/Revolute3D"
    nodes = [
        _node("T", {"ref": "stdlib:multibond/FixedTransform3DNeutral"}, 0, 0, IDENTITY),
        _node("J", {"ref": joint}, 120, 0),
        _node("Link", {"ref": "stdlib:multibond/FixedTransform3DNeutral"}, 240, 0, IDENTITY),
        _node("BJ", {"junction": "1"}, 360, 10),
        _node("B", {"ref": "stdlib:spatial/RigidBody3D"}, 350, 100, {"m": "1.0", "J": "[0.1, 0.1, 0.1]", "g0": "9.81"}),
        _node("CA", {"ref": "stdlib:multibond/ComposePose3D"}, 0, 240),
        _node("W", {"ref": "stdlib:multibond/ComposePose3D"}, 120, 240),
        _node("LN", {"ref": "stdlib:spatial/LocalPose3D"}, 0, 340, IDENTITY),
        _node("P", {"ref": "stdlib:multibond/ComposePose3D"}, 350, 360),
        _node("LC", {"ref": "stdlib:spatial/LocalPose3D"}, 350, 480, IDENTITY),
    ]
    links = [
        ("bond", "T", "a", "J", "parent"),
        ("bond", "J", "child", "Link", "a"),
        ("bond", "Link", "b", "BJ", None),
        ("bond", "B", "p", "BJ", None),
        ("signal", "LN", "g", "CA", "gl"),
        ("signal", "CA", "g", "W", "gp"),
        ("signal", "J", "pose", "W", "gl"),
        ("signal", "W", "g", "P", "gp"),
        ("signal", "LC", "g", "P", "gl"),
        ("signal", "P", "g", "B", "g"),
    ]
    connections = [
        {"id": f"link_{kind[0]}{k:02d}", "kind": kind, "from": _end(a, pa), "to": _end(b, pb), "route": [], "label": None}
        for k, (kind, a, pa, b, pb) in enumerate(links, start=1)
    ]

    def signal(port: str, direction: str, node: str, inner: str, size: int, unit: str | None) -> dict:
        return {"name": port, "kind": "signal", "direction": direction, "type": "Real", "size": [size],
                "unit": unit, "node": node, "port": inner}  # fmt: skip

    def power(port: str, domain: str, node: str, inner: str, size: int) -> dict:
        return {"name": port, "kind": "power", "domain": domain, "size": [size], "node": node, "port": inner}

    ports = [
        signal("gp", "input", "CA", "gp", 7, None),
        signal("g", "output", "W", "g", 7, None),
        signal("q", "output", "J", "qout", 1, "rad"),
        signal("qd", "output", "J", "qdout", 1, "rad/s"),
        signal("V", "output", "B", "V", 6, None),
        signal("gb", "output", "P", "g", 7, None),
        power("parent", "Spatial", "T", "b", 6),
        power("drive", "Rotation", "J", "drive", 1),
        power("child", "Spatial", "BJ", "junction", 6),
    ]
    kind = ("the rigid joint J (Revolute3DRigid, held directions as hard constraints)" if rigid
            else "the compliant joint J (Revolute3D)")
    pins = (
        [f"T/{p}" for p in POSE_KEYS]
        + [f"J/{p}" for p in JOINT_PARAMS[rigid]]
        + [f"Link/{p}" for p in POSE_KEYS]
        + [f"B/{p}" for p in BODY_PARAMS]
        + [f"LN/{p}" for p in POSE_KEYS]
        + [f"LC/{p}" for p in POSE_KEYS]
    )
    return {
        "format": "bgsim.subsystem",
        "name": name(rigid),
        "description": (
            f"One link of a spatial serial chain: the offset T from the parent body's frame to the joint, {kind}, "
            "the offset Link from the joint's child frame to the body's centre of mass, the body B (RigidBody3D) on "
            "its 1-junction BJ, and the pose band W = gp o LN o J.pose, P = W o LC that B's gravity reads. Ports: "
            "parent (bond in, from the parent body's junction or the ground), child (the body junction, bond out to "
            "the next link's parent), drive (the joint's Rotation drive port), gp (the parent joint's child-frame "
            "pose in), g (this joint's child-frame pose out), q and qd (joint angle and rate), V and gb (the body "
            "twist and the body pose). Every offset, the "
            f"joint parameters, the body and the joint's start values are pinned. Generated by {generator}."
        ),
        "ports": ports,
        "diagram": {"nodes": nodes, "connections": connections, "subsystemPorts": [], "annotations": []},
        "pins": {"params": pins, "starts": [f"J/{s}" for s in JOINT_STARTS[rigid]]},
    }


def pins(t: dict, joint: dict, link: dict, body: dict, ln: dict, lc: dict, starts: dict | None = None) -> tuple[dict, dict]:
    """An instance's `params` and `starts`: the pose dicts use the keys qw..z, `joint` and `body`
    the block parameter names, `starts` the joint's start values (all as strings)."""
    params: dict = {}
    for prefix, values in (("T", t), ("J", joint), ("Link", link), ("B", body), ("LN", ln), ("LC", lc)):
        params.update({f"{prefix}/{k}": v for k, v in values.items()})
    return params, {f"J/{k}": v for k, v in (starts or {}).items()}
