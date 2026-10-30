# /// script
# requires-python = ">=3.11"
# dependencies = ["httpx>=0.28", "numpy>=2.0", "matplotlib>=3.9"]
# ///
"""Build the docs of the example models (X5.10).

Sources live in one bundle per example, ``tools/example_docs/src/<example>.md``. Sections start with
a line beginning ``@@ ``::

    @@ page <model> <page-id> <parent-id | -> | <Title>     a Markdown page (the tree follows the order)
    @@ figures <model>                                      JSON {"<name>": figure spec}
    @@ svg <model> <name>                                   a hand-written SVG (no script, no external refs)

Pages write figures as ``![alt|600](@fig:<name>)``.

The build renders every figure, names it ``assets/<first 12 hex of its SHA-256>.<ext>``, rewrites the
``@fig:`` references and writes ``examples/<example>/models/<model>.docs/`` (deleting every file the
new tree does not use). Result plots come from real runs through one real-worker backend (started
lazily and stopped at the end); run data and screenshots are cached under
``%TEMP%/bgsim-example-docs-cache`` (override with ``BGSIM_DOCS_CACHE``), keyed by the model, the
library files, the scene and the figure spec, so a rebuild without changes is quick.

    uv run tools/example_docs/build.py [--only a,b] [--refresh] [--no-shots]

Figure specs::

    {"kind": "plot", "model": "<model file>", "settings": {..}?, "xlim": [a, b]?, "xlabel": "t [s]",
     "rows": [{"ylabel": "..", "ylim": [a, b]?, "x": "<signal>"?, "xlabel": ".."?,
               "series": [{"signal": "..", "label": "..", "scale": 1.0?, "style": "-"?}],
               "hlines": [{"y": 1.0, "label": ".."}]?, "vlines": [{"x": 1.0, "label": ".."}]?}],
     "row_height": 2.3?, "width": 1000?}
    {"kind": "diagram", "model": "<model file>"}
    {"kind": "scene", "model": "<model file>", "t": 1.6}
    {"kind": "svg", "svg": "<name of an '@@ svg' section>"}
"""

from __future__ import annotations

import argparse
import atexit
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from typing import Any

import httpx
import numpy as np

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent.parent
SRC = HERE / "src"
EXAMPLES = ROOT / "examples"
sys.path.insert(0, str(EXAMPLES))
sys.path.insert(0, str(HERE))

import run_checks as rc
from docs_lint import lint_model_docs

CACHE = Path(os.environ.get("BGSIM_DOCS_CACHE") or Path(tempfile.gettempdir()) / "bgsim-example-docs-cache")
#: Bump a kind to retake its cached screenshots after a change of shots.mjs.
SHOT_VERSION = {"diagram": "3"}
FIGURE_REF = re.compile(r"!\[([^\]]*)\]\(@fig:([a-z0-9-]+)\)")
PALETTE = ["#1f77b4", "#d95f02", "#1b9e77", "#7570b3", "#e7298a", "#66a61e", "#a6761d", "#444444"]


def sha(*parts: bytes | str) -> str:
    digest = hashlib.sha256()
    for part in parts:
        digest.update(part if isinstance(part, bytes) else part.encode("utf-8"))
        digest.update(b"\0")
    return digest.hexdigest()


def example_fingerprint(example: str) -> str:
    """Everything that decides what a run or a picture of the example looks like."""
    base = EXAMPLES / example
    digest = hashlib.sha256()
    for sub in ("models", "library", "scenes", "meshes"):
        for path in sorted((base / sub).rglob("*")) if (base / sub).is_dir() else []:
            if path.is_file() and not any(part.endswith(".docs") for part in path.parts):
                digest.update(path.relative_to(base).as_posix().encode())
                digest.update(path.read_bytes())
    return digest.hexdigest()


# --------------------------------------------------------------------------- backend


class Backend:
    """One real-worker backend, started on first use and stopped with ``taskkill /T`` at exit."""

    def __init__(self) -> None:
        self.process: subprocess.Popen | None = None
        self.client: httpx.Client | None = None
        self.url = ""
        self.root: Path | None = None
        self.projects: dict[str, tuple[str, Path]] = {}
        atexit.register(self.stop)

    def start(self) -> None:
        if self.process is not None:
            return
        self.root = Path(tempfile.mkdtemp(prefix="bgsim-example-docs-"))
        log = self.root / "backend.log"
        self.process, port = rc._start_backend(self.root, log)
        self.url = f"http://127.0.0.1:{port}"
        self.client = httpx.Client(base_url=self.url, timeout=httpx.Timeout(300.0, connect=10.0))
        rc._wait_for_worker(self.client, self.process, log)
        print(f"backend ready on {self.url} (pid {self.process.pid})", flush=True)

    def stop(self) -> None:
        if self.client is not None:
            self.client.close()
            self.client = None
        if self.process is not None:
            pid = self.process.pid
            if os.name == "nt":
                subprocess.run(["taskkill", "/PID", str(pid), "/T", "/F"], capture_output=True, check=False)
            else:
                self.process.kill()
            self.process = None
        if self.root is not None:
            shutil.rmtree(self.root, ignore_errors=True)
            self.root = None

    def project(self, example: str) -> tuple[str, Path]:
        self.start()
        assert self.client is not None
        if example not in self.projects:
            name = f"docs-{example}"
            response = self.client.post("/api/projects", json={"name": name, "example": example})
            if response.status_code != 201:
                raise RuntimeError(f"cannot create project {name}: {response.status_code} {response.text[:300]}")
            self.projects[example] = (name, Path(rc._get_json(self.client, f"/api/projects/{name}")["path"]))
        return self.projects[example]

    def run(self, example: str, model: str, settings: Any) -> rc.Run:
        name, directory = self.project(example)
        assert self.client is not None
        return rc._run_model(self.client, name, directory, model, settings, 1800.0)


def cached_run(backend: Backend, example: str, model: str, settings: Any) -> tuple[np.ndarray, dict[str, np.ndarray]]:
    key = sha(example_fingerprint(example), model, json.dumps(settings, sort_keys=True))[:24]
    path = CACHE / "runs" / f"{example}-{model}-{key}.npz"
    if path.is_file():
        data = np.load(path, allow_pickle=False)
        ids = json.loads(str(data["ids"]))
        return data["time"], {signal: data[f"s{index}"] for index, signal in enumerate(ids)}
    print(f"  running {example}/{model} ...", flush=True)
    started = time.perf_counter()
    run = backend.run(example, model, settings)
    print(f"  {example}/{model}: {run.time.size} points, {len(run.signals)} signals in {time.perf_counter() - started:.0f} s", flush=True)
    path.parent.mkdir(parents=True, exist_ok=True)
    ids = list(run.signals)
    np.savez_compressed(path, time=run.time, ids=json.dumps(ids), **{f"s{i}": run.signals[s] for i, s in enumerate(ids)})
    return run.time, run.signals


# --------------------------------------------------------------------------- figures


def plot_png(spec: dict[str, Any], time_column: np.ndarray, signals: dict[str, np.ndarray], out: Path) -> None:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    rows = spec["rows"]
    width = spec.get("width", 1000)
    row_height = spec.get("row_height", 2.3)
    plt.rcParams.update(
        {
            "font.size": 10,
            "axes.grid": True,
            "grid.color": "#d9d9d9",
            "grid.linewidth": 0.6,
            "axes.spines.top": False,
            "axes.spines.right": False,
            "figure.facecolor": "white",
            "axes.facecolor": "white",
            "svg.hashsalt": "bgsim",
        }
    )
    figure, axes = plt.subplots(
        len(rows), 1, figsize=(width / 100, row_height * len(rows) + 0.55), dpi=100, squeeze=False, sharex=False
    )
    xlim = spec.get("xlim")
    for index, row in enumerate(rows):
        axis = axes[index][0]
        x_signal = row.get("x")
        for number, series in enumerate(row["series"]):
            signal = series["signal"]
            if signal not in signals:
                raise KeyError(f"figure signal {signal!r} is not in the run ({len(signals)} signals)")
            values = signals[signal] * series.get("scale", 1.0)
            x = signals[x_signal] * row.get("x_scale", 1.0) if x_signal else time_column
            selection = np.ones(x.shape, dtype=bool)
            if xlim and not x_signal:
                selection = (x >= xlim[0]) & (x <= xlim[1])
            axis.plot(
                x[selection],
                values[selection],
                series.get("style", "-"),
                color=series.get("color", PALETTE[number % len(PALETTE)]),
                linewidth=series.get("lw", 1.5),
                label=series.get("label", signal),
            )
        for line in row.get("hlines", []):
            axis.axhline(line["y"], color="#888888", linestyle="--", linewidth=1.0, label=line.get("label"))
        for line in row.get("vlines", []):
            axis.axvline(line["x"], color="#888888", linestyle=":", linewidth=1.0, label=line.get("label"))
        axis.set_ylabel(row["ylabel"])
        if row.get("ylim"):
            axis.set_ylim(*row["ylim"])
        if xlim and not x_signal:
            axis.set_xlim(*xlim)
        if row.get("xlim"):
            axis.set_xlim(*row["xlim"])
        axis.set_xlabel(row.get("xlabel", spec.get("xlabel", "t [s]")))
        _handles, labels = axis.get_legend_handles_labels()
        if len(labels) > 1 or row.get("legend"):
            axis.legend(loc=row.get("legend_loc", "best"), frameon=False, fontsize=9)
        if row.get("equal"):
            axis.set_aspect("equal", adjustable="datalim")
    if spec.get("title"):
        figure.suptitle(spec["title"], fontsize=11)
    figure.tight_layout()
    figure.savefig(out, format="png", metadata={"Software": None})
    plt.close(figure)


def run_shots(backend: Backend, jobs: list[dict[str, Any]]) -> None:
    """Screenshot jobs through ``shots.mjs`` against the backend that already serves ``web/dist``."""
    if not jobs:
        return
    backend.start()
    work = Path(tempfile.mkdtemp(prefix="bgsim-docs-shots-"))
    try:
        for job in jobs:
            job["project"] = backend.project(job["example"])[0]
        spec = work / "jobs.json"
        spec.write_text(json.dumps({"baseUrl": backend.url, "jobs": jobs}), encoding="utf-8")
        node = shutil.which("node") or "node"
        result = subprocess.run([node, str(HERE / "shots.mjs"), str(spec)], cwd=ROOT / "web", check=False)
        if result.returncode != 0:
            raise RuntimeError(f"shots.mjs failed with exit code {result.returncode}")
    finally:
        shutil.rmtree(work, ignore_errors=True)


# --------------------------------------------------------------------------- build


def parse_bundle(path: Path) -> dict[str, dict[str, Any]]:
    """``src/<example>.md`` -> {model: {"pages": [(id, parent, title, text)], "figures": {..}, "svgs": {..}}}.

    Sections start with ``@@ page <model> <id> <parent|-> | <Title>``, ``@@ figures <model>`` (JSON) or
    ``@@ svg <model> <name>`` (a hand-written SVG).
    """
    models: dict[str, dict[str, Any]] = {}
    header = None
    body: list[str] = []

    def flush() -> None:
        if header is None:
            return
        kind, model = header[0], header[1]
        entry = models.setdefault(model, {"pages": [], "figures": {}, "svgs": {}})
        text = "\n".join(body).strip("\n") + "\n"
        if kind == "page":
            entry["pages"].append((header[2], header[3], header[4], text))
        elif kind == "figures":
            entry["figures"].update(json.loads(text))
        else:
            entry["svgs"][header[2]] = text

    for number, line in enumerate(path.read_text(encoding="utf-8").split("\n"), 1):
        if line.startswith("@@ "):
            flush()
            body = []
            parts = line[3:].split(" | ", 1)
            words = parts[0].split()
            if words[0] == "page" and len(words) == 4 and len(parts) == 2:
                header = ("page", words[1], words[2], words[3], parts[1].strip())
            elif words[0] in {"figures"} and len(words) == 2:
                header = ("figures", words[1])
            elif words[0] == "svg" and len(words) == 3:
                header = ("svg", words[1], words[2])
            else:
                raise SystemExit(f"{path}:{number}: bad section header {line!r}")
        else:
            body.append(line)
    flush()
    return models


def tree(pages: list[tuple[str, str, str, str]]) -> list[dict[str, Any]]:
    nodes = {
        page_id: {"id": page_id, "title": title, "file": f"pages/{page_id}.md", "children": []}
        for page_id, _parent, title, _text in pages
    }
    roots: list[dict[str, Any]] = []
    for page_id, parent, _title, _text in pages:
        if parent == "-":
            roots.append(nodes[page_id])
        elif parent in nodes:
            nodes[parent]["children"].append(nodes[page_id])
        else:
            raise SystemExit(f"page {page_id}: parent {parent!r} is not a page of the model")
    return roots


def build_model(
    example: str, model: str, entry: dict[str, Any], args: argparse.Namespace, backend: Backend
) -> tuple[int, int, int]:
    source = SRC / f"{example}.md"
    figures: dict[str, Any] = entry["figures"]
    pages = {f"{page_id}.md": text for page_id, _parent, _title, text in entry["pages"]}
    used: list[str] = []
    for name, text in pages.items():
        for _alt, figure in FIGURE_REF.findall(text):
            if figure not in figures:
                raise SystemExit(f"{source}: page {name} uses @fig:{figure}, which has no entry in '@@ figures {model}'; add it")
            if figure not in used:
                used.append(figure)
    if any("(signal:" in text for text in pages.values()):
        cached_run(backend, example, model, None)  # signal links are checked against a real run
    unused = sorted(set(figures) - set(used))
    if unused:
        raise SystemExit(f"{source}: figure(s) {unused} of {model} are not used by any page; delete them or reference them")

    fingerprint = example_fingerprint(example)
    images: dict[str, tuple[bytes, str]] = {}
    shot_jobs: list[dict[str, Any]] = []
    shot_paths: dict[str, Path] = {}
    for name in used:
        spec = figures[name]
        kind = spec["kind"]
        if kind == "plot":
            time_column, signals = cached_run(backend, example, spec["model"], spec.get("settings"))
            with tempfile.TemporaryDirectory() as directory:
                out = Path(directory) / "figure.png"
                plot_png(spec, time_column, signals, out)
                images[name] = (out.read_bytes(), "png")
        elif kind == "svg":
            images[name] = (entry["svgs"][spec["svg"]].encode("utf-8"), "svg")
        elif kind in {"diagram", "scene"}:
            if args.no_shots:
                continue
            version = SHOT_VERSION.get(kind, "")
            key = sha(fingerprint, model, name, json.dumps(spec, sort_keys=True), *([version] if version else []))[:24]
            cached = CACHE / "shots" / f"{example}-{model}-{name}-{key}.png"
            shot_paths[name] = cached
            if not cached.is_file() or args.refresh:
                cached.parent.mkdir(parents=True, exist_ok=True)
                shot_jobs.append({"example": example, "name": name, "out": str(cached), **spec})
        else:
            raise SystemExit(f"{source / 'figures.json'}: figure {name!r} has the unknown kind {kind!r}")
    run_shots(backend, shot_jobs)
    for name, path in shot_paths.items():
        images[name] = (path.read_bytes(), "png")

    out_dir = EXAMPLES / example / "models" / f"{model}.docs"
    assets: dict[str, bytes] = {}
    names: dict[str, str] = {}
    for name, (data, extension) in images.items():
        file = f"{hashlib.sha256(data).hexdigest()[:12]}.{extension}"
        assets[file] = data
        names[name] = file

    def replace(match: re.Match[str]) -> str:
        figure = match.group(2)
        if figure not in names:
            return match.group(0)
        return f"![{match.group(1)}](assets/{names[figure]})"

    (out_dir / "pages").mkdir(parents=True, exist_ok=True)
    (out_dir / "assets").mkdir(parents=True, exist_ok=True)
    for name, text in pages.items():
        (out_dir / "pages" / name).write_text(FIGURE_REF.sub(replace, text), encoding="utf-8", newline="\n")
    manifest = {"format": "bgsim.docs", "version": 1, "pages": tree(entry["pages"])}
    (out_dir / "docs.json").write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8", newline="\n")
    for file, data in assets.items():
        (out_dir / "assets" / file).write_bytes(data)
    for path in list((out_dir / "pages").glob("*.md")):
        if path.name not in pages:
            path.unlink()
    for path in list((out_dir / "assets").iterdir()):
        if path.name not in assets:
            path.unlink()
    if not assets:
        (out_dir / "assets").rmdir()
    return len(pages), len(assets), sum(len(data) for data in assets.values())


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--only", default="", help="comma-separated example names")
    parser.add_argument("--refresh", action="store_true", help="retake the cached screenshots")
    parser.add_argument("--no-shots", action="store_true", help="skip diagram and 3D screenshots")
    args = parser.parse_args()
    wanted = {name for name in args.only.split(",") if name}
    backend = Backend()
    failures = 0
    try:
        for bundle in sorted(SRC.glob("*.md")):
            example = bundle.stem
            if wanted and example not in wanted:
                continue
            for model, entry in parse_bundle(bundle).items():
                pages, assets, size = build_model(example, model, entry, args, backend)
                out_dir = EXAMPLES / example / "models" / f"{model}.docs"
                document = json.loads((EXAMPLES / example / "models" / f"{model}.bgmodel.json").read_text(encoding="utf-8"))
                signal_ids: set[str] | None = None
                files = sorted((CACHE / "runs").glob(f"{example}-{model}-" + "[0-9a-f]" * 24 + ".npz"))
                if files:
                    newest = max(files, key=lambda p: p.stat().st_mtime)
                    signal_ids = set(json.loads(str(np.load(newest, allow_pickle=False)["ids"])))
                problems = lint_model_docs(out_dir, document, signal_ids, out_dir.relative_to(ROOT).as_posix())
                signal_hint = "" if signal_ids is not None else " (signal links unchecked: no cached run)"
                print(f"{example}/{model}: {pages} pages, {assets} assets, {size / 1024:.0f} KiB{signal_hint}", flush=True)
                for problem in problems:
                    print(f"  {problem}", flush=True)
                failures += len(problems)
    finally:
        backend.stop()
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
