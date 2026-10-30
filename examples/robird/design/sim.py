"""Harness: start one backend with the real worker and run robird models through its HTTP API.

Used by design.py for trim and identification runs (full flapping model, no averaging shortcut).
"""

from __future__ import annotations

import json
import shutil
import sys
import tempfile
import time
from pathlib import Path

import httpx
import numpy as np

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[2]
sys.path.insert(0, str(REPO / "examples"))
import run_checks as rc  # noqa: E402


class Sim:
    def __init__(self, keep_runs: bool = False):
        self.root = Path(tempfile.mkdtemp(prefix="robird-sim-"))
        self.log = self.root / "backend.log"
        self.proc, self.port = rc._start_backend(self.root, self.log)
        self.client = httpx.Client(base_url=f"http://127.0.0.1:{self.port}", timeout=60.0)
        rc._wait_for_worker(self.client, self.proc, self.log)
        r = self.client.post("/api/projects", json={"name": "robird", "example": "robird"})
        assert r.status_code == 201, r.text
        self.dir = Path(rc._get_json(self.client, "/api/projects/robird")["path"])
        self.keep = keep_runs

    def run(self, doc: dict, timeout: float = 3600.0):
        """Run a model document (dict) and return a rc.Run."""
        name = doc["name"]
        r = self.client.post("/api/projects/robird/runs", json={"model": doc})
        if r.status_code != 201:
            raise RuntimeError(f"{r.status_code} {r.text[:800]}")
        rid = str(r.json()["runId"])
        t0 = time.monotonic()
        while time.monotonic() - t0 < timeout:
            man = rc._get_json(self.client, f"/api/runs/{rid}")
            if man.get("status") != "running":
                break
            time.sleep(0.2)
        if man.get("status") != "done":
            raise RuntimeError(f"run {rid} {man.get('status')}: {"; ".join(f"{d['code']} {d.get('path')}: {d['message'][:200]}" for d in [d for d in (man.get('diagnostics') or []) if d['code'] != 'E102'][:10])}")
        tc, sg = rc._read_columns(self.dir / "runs" / rid, man)
        run = rc.Run(model=name, run_id=rid, manifest=man, time=tc, signals=sg, run_dir=self.dir / "runs" / rid)
        run.wall = time.monotonic() - t0
        if not self.keep:
            shutil.rmtree(run.run_dir, ignore_errors=True)
        return run

    def close(self):
        rc._stop_backend(self.proc)
        shutil.rmtree(self.root, ignore_errors=True)
