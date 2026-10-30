# /// script
# requires-python = ">=3.11"
# dependencies = ["httpx>=0.28", "numpy>=2.0", "scipy>=1.11", "matplotlib>=3.9"]
# ///
"""Write the model docs of `aerial-contact` (W5.6 format): `models/aerial-contact.docs/`.

The pages are Markdown with KaTeX math; the result plots are rendered from a REAL run of the model
through one real-worker backend (started here and stopped at the end, like `examples/run_checks.py`,
whose helpers are reused), named `assets/<first 12 hex of the SHA-256>.png`. The numbers in the text
that come from the design are taken from `design.py` at build time.

    uv run examples/aerial-contact/design/build_docs.py [--run-dir <existing run folder>]

`--run-dir` renders the figures from an existing run folder (`manifest.json` + `columns.f64`) and
does not start a backend.
"""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import math
import shutil
import sys
import tempfile
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
REPO = ROOT.parent.parent
sys.path.insert(0, str(HERE))
import design as d  # noqa: E402

DOCS = ROOT / "models" / "aerial-contact.docs"
DEG = 180.0 / math.pi


def _load_run_checks():
    spec = importlib.util.spec_from_file_location("run_checks", REPO / "examples" / "run_checks.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules["run_checks"] = module
    spec.loader.exec_module(module)
    return module


def real_run():
    """Run the example once through a fresh backend; return (time, signals)."""
    import httpx

    rc = _load_run_checks()
    rc._kill_children_with_me()
    projects_root = Path(tempfile.mkdtemp(prefix="bgsim-aerial-docs-"))
    log_path = projects_root / "backend.log"
    process, port = rc._start_backend(projects_root, log_path)
    client = httpx.Client(base_url=f"http://127.0.0.1:{port}", timeout=httpx.Timeout(180.0, connect=10.0))
    try:
        rc._wait_for_worker(client, process, log_path)
        response = client.post("/api/projects", json={"name": "aerial-docs", "example": "aerial-contact"})
        assert response.status_code == 201, response.text
        project_dir = Path(rc._get_json(client, "/api/projects/aerial-docs")["path"])
        run = rc._run_model(client, "aerial-docs", project_dir, "aerial-contact", None, 900.0)
        size = (run.run_dir / "columns.f64").stat().st_size
        print(f"run {run.run_id}: {run.time.size} rows, {len(run.signals)} signals, columns.f64 {size / 1e6:.1f} MB")
        return run.time, run.signals
    finally:
        client.close()
        rc._stop_backend(process)
        shutil.rmtree(projects_root, ignore_errors=True)


def read_run(run_dir: Path):
    manifest = json.loads((run_dir / "manifest.json").read_text(encoding="utf-8"))
    rc = _load_run_checks()
    return rc._read_columns(run_dir, manifest)


# ----------------------------------------------------------------------------- figures
def figures(t, s) -> dict[str, bytes]:
    import io

    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    plt.rcParams.update({"font.size": 8, "axes.grid": True, "grid.alpha": 0.3, "axes.spines.top": False,
                         "axes.spines.right": False, "legend.fontsize": 7, "lines.linewidth": 1.1})
    out: dict[str, bytes] = {}

    def shade(ax, ph):
        edges = [0.0] + [float(t[np.argmax(s["Sup/phase"] >= k - 0.5)]) for k in (1, 2, 3)] + [float(t[-1])]
        colors = ["#e8eef7", "#fdf0d5", "#dff1e3", "#f3dde0"]
        for i in range(4):
            ax.axvspan(edges[i], edges[i + 1], color=colors[i], alpha=0.7, lw=0)
        return edges

    def save(fig, name):
        buf = io.BytesIO()
        fig.savefig(buf, format="png", dpi=150, bbox_inches="tight", metadata={"Software": None})
        plt.close(fig)
        out[name] = buf.getvalue()

    # 1. the whole run
    fig, axes = plt.subplots(4, 1, figsize=(7.2, 8.2), sharex=True)
    edges = None
    for ax in axes:
        edges = shade(ax, None)
    axes[0].plot(t, s["Truth/x"], label="multirotor x")
    axes[0].plot(t, s["Sup/p_sp[1]"], ":", label="x set-point (free flight)")
    axes[0].plot(t, s["TruthE/x"], "--", label="end-effector x")
    axes[0].axhline(d.WALL_X, color="k", lw=0.8)
    axes[0].set_ylabel("x [m]")
    axes[0].legend(loc="upper left", ncol=3)
    axes[1].plot(t, s["Truth/z"], label="multirotor z")
    axes[1].plot(t, s["TruthE/z"], "--", label="end-effector z")
    axes[1].set_ylabel("height [m]")
    axes[1].legend(loc="upper left", ncol=2)
    axes[2].plot(t, np.degrees(s["Truth/pitch"]), label="pitch")
    axes[2].plot(t, np.degrees(s["Sup/theta_sp"]), ":", label="theta_sp")
    axes[2].plot(t, np.degrees(s["Truth/roll"]), label="roll")
    axes[2].plot(t, np.degrees(s["Truth/yaw"]), label="yaw")
    axes[2].set_ylabel("angle [deg]")
    axes[2].legend(loc="upper left", ncol=4)
    axes[3].plot(t, s["Sup/phase"], color="k")
    axes[3].plot(t, s["Sup/d_ee"], label="wheel plane to wall [m]", color="#2a7")
    axes[3].set_ylabel("phase / distance")
    axes[3].set_xlabel("t [s]")
    axes[3].legend(loc="upper right")
    axes[0].set_title("Free flight, engage, contact, disengage (phase shading: 0 free, 1 engage, 2 contact, 3 disengage)", fontsize=8)
    save(fig, "run")

    # 2. the wall force
    fig, axes = plt.subplots(2, 1, figsize=(7.2, 5.2), sharex=True)
    for ax in axes:
        shade(ax, None)
    for k in (1, 2, 3):
        axes[0].plot(t, s[f"Wheel{k}/f_n"], lw=0.8, label=f"wheel {k}")
    axes[0].plot(t, s["WallForce/N"], "k", label="total")
    axes[0].plot(t, s["WallForce/Npred"], "r--", label="m g tan(theta_sp)")
    axes[0].set_ylabel("normal force [N]")
    axes[0].legend(ncol=5, loc="upper left")
    axes[0].set_xlim(4, 30)
    axes[0].set_ylim(-1.0, 20.0)
    peak = float(np.max(s["WallForce/N"][(t > 5.0) & (t < 6.2)]))
    axes[0].text(5.2, 17.0, f"impact peak {peak:.0f} N (clipped)", fontsize=7)
    m = (t > 8.5) & (t < 28.4)
    axes[1].plot(t[m], (s["WallForce/N"] - s["WallForce/Npred"])[m], color="#a33")
    axes[1].set_ylabel("N - m g tan(theta_sp) [N]")
    axes[1].set_xlabel("t [s]")
    save(fig, "force")

    # 3. locomotion
    fig, axes = plt.subplots(3, 1, figsize=(7.2, 6.0), sharex=True)
    for ax in axes:
        shade(ax, None)
    axes[0].plot(t, s["Sup/cmd[2]"], color="k")
    axes[0].set_ylabel("velocity command vz")
    axes[1].plot(t, s["TruthE/z"], label="end-effector z")
    axes[1].plot(t, s["Truth/z"], "--", label="multirotor z")
    axes[1].set_ylabel("height [m]")
    axes[1].legend(loc="upper left")
    for k in (1, 2, 3):
        axes[2].plot(t, s[f"Wheel{k}/sd"] * 1e3, lw=0.7, label=f"wheel {k}")
    axes[2].set_ylabel("driven slip [mm/s]")
    axes[2].set_xlabel("t [s]")
    axes[2].legend(ncol=3, loc="upper left")
    axes[0].set_xlim(8, 30)
    save(fig, "locomotion")

    # 4. the angles in contact against the paper's bound
    fig, ax = plt.subplots(figsize=(7.2, 2.8))
    m = (t > 6.0) & (t < 28.5)
    ax.plot(t[m], np.degrees(s["Truth/roll"])[m], label="roll")
    ax.plot(t[m], np.degrees(s["Truth/yaw"])[m], label="yaw")
    ax.axhline(7.5, color="r", ls="--", lw=0.8, label="paper bound 7.5 deg")
    ax.axhline(-7.5, color="r", ls="--", lw=0.8)
    ax.set_ylabel("angle [deg]")
    ax.set_xlabel("t [s]")
    ax.legend(ncol=3, loc="upper right")
    save(fig, "angles")

    # 5. the scheduled gains over theta_sp
    table = d.PARAMS["_contact"]["table"]
    th = [x["theta_deg"] for x in table]
    fig, axes = plt.subplots(1, 2, figsize=(7.2, 2.9))
    rows = {"tau_x": 0, "F": 1, "tau_z": 2, "tau_y": 3}
    cols = {"phi": 0, "phi'": 1, "theta": 2, "theta'": 3, "psi": 4, "psi'": 5}
    for (rn, cn) in (("tau_x", "phi"), ("tau_x", "phi'"), ("tau_x", "psi"), ("tau_x", "psi'"), ("tau_z", "psi"), ("tau_z", "phi")):
        axes[0].plot(th, [x["K"][rows[rn], cols[cn]] for x in table], marker="o", ms=3, label=f"K[{rn}, {cn}]")
    axes[0].set_title("roll / yaw block", fontsize=8)
    axes[0].set_xlabel("theta_sp [deg]")
    axes[0].set_ylabel("gain")
    axes[0].legend(fontsize=6)
    for (rn, cn) in (("F", "theta"), ("F", "theta'"), ("tau_y", "theta"), ("tau_y", "theta'")):
        axes[1].plot(th, [x["K"][rows[rn], cols[cn]] for x in table], marker="o", ms=3, label=f"K[{rn}, {cn}]")
    axes[1].set_title("pitch block", fontsize=8)
    axes[1].set_xlabel("theta_sp [deg]")
    axes[1].legend(fontsize=6)
    save(fig, "gains")

    # 6. closed-loop poles over the grid
    fig, ax = plt.subplots(figsize=(4.6, 3.4))
    for x in table:
        ev = x["eig"]
        ax.plot(ev.real, ev.imag, "o", ms=3, color=plt.cm.viridis((x["theta_deg"] - 10) / 35))
    ax.axvline(0, color="k", lw=0.8)
    ax.set_xlim(-45, 2)
    ax.set_xlabel("real [1/s]")
    ax.set_ylabel("imag [1/s]")
    ax.set_title("eigenvalues of A - B K, theta_sp 10 to 45 deg", fontsize=8)
    save(fig, "poles")
    return out


# ----------------------------------------------------------------------------- text
def fmt_mat(a, digits=3) -> str:
    rows = [" & ".join(f"{float(v):.{digits}f}" for v in row) for row in a]
    return "\\begin{bmatrix} " + " \\\\ ".join(rows) + " \\end{bmatrix}"


def pages(assets: dict[str, str]) -> list[dict]:
    """The page tree: (id, title, markdown, children)."""
    table = d.PARAMS["_contact"]["table"]
    t20 = next(x for x in table if x["theta_deg"] == 20.0)
    k20 = t20["K"]
    k27 = d.lqr_gain(27.0)["K"]
    a20, b20 = t20["A"], t20["B"]
    mdl = t20["model"]
    sa_min = min(max(x["eig"].real) for x in table)
    sa_max = max(max(x["eig"].real) for x in table)
    rep = {
        "@RUN@": f"![The run|720]({assets['run']})",
        "@FORCE@": f"![Wall force|720]({assets['force']})",
        "@LOCO@": f"![Locomotion|720]({assets['locomotion']})",
        "@ANGLES@": f"![Roll and yaw|720]({assets['angles']})",
        "@GAINS@": f"![Scheduled gains|720]({assets['gains']})",
        "@POLES@": f"![Closed-loop poles|420]({assets['poles']})",
        "@K20@": fmt_mat(k20),
        "@K27@": fmt_mat(k27),
        "@A20@": fmt_mat(a20, 2),
        "@B20@": fmt_mat(b20, 2),
        "@IE@": ", ".join(f"{v:.3f}" for v in np.diag(mdl.ie)),
        "@MC@": f"{mdl.m:.2f}",
        "@E_X@": f"{mdl.e[0]:.3f}",
        "@E_Z@": f"{mdl.e[2]:.3f}",
        "@SA_MIN@": f"{sa_min:.2f}",
        "@SA_MAX@": f"{sa_max:.2f}",
        "@TAUFF@": f"{d.PARAMS['tau_ff']:.3f}",
        "@WH@": f"{math.sqrt(d.M_TRUE * d.G / 6 / d.KT_PROP):.0f}",
    }
    src = (HERE / "docs_pages.md").read_text(encoding="utf-8")
    sections = [sec for sec in src.split("\n@@ ") if sec.strip()]
    out = []
    for sec in sections:
        header, _, body = sec.partition("\n")
        header = header.removeprefix("@@ ").strip()
        pid, parent, title = [x.strip() for x in header.split("|")]
        for k, v in rep.items():
            body = body.replace(k, v)
        out.append({"id": pid, "parent": parent, "title": title, "body": body.strip() + "\n"})
    return out


def write_docs(png: dict[str, bytes]) -> None:
    if DOCS.exists():
        shutil.rmtree(DOCS)
    (DOCS / "pages").mkdir(parents=True)
    (DOCS / "assets").mkdir()
    assets = {}
    for name, data in png.items():
        digest = hashlib.sha256(data).hexdigest()[:12]
        (DOCS / "assets" / f"{digest}.png").write_bytes(data)
        assets[name] = f"assets/{digest}.png"
    plist = pages(assets)
    nodes = {p["id"]: {"id": p["id"], "title": p["title"], "file": f"pages/{p['id']}.md", "children": []} for p in plist}
    roots = []
    for p in plist:
        (DOCS / "pages" / f"{p['id']}.md").write_text(p["body"], encoding="utf-8", newline="\n")
        if p["parent"] == "-":
            roots.append(nodes[p["id"]])
        else:
            nodes[p["parent"]]["children"].append(nodes[p["id"]])
    manifest = {"format": "bgsim.docs", "version": 1, "pages": roots}
    (DOCS / "docs.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8", newline="\n")
    print(f"wrote {DOCS}: {len(plist)} pages, {len(assets)} assets")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--run-dir", type=Path)
    args = parser.parse_args()
    if args.run_dir:
        t, s = read_run(args.run_dir)
    else:
        t, s = real_run()
    write_docs(figures(t, s))
    return 0


if __name__ == "__main__":
    sys.exit(main())
