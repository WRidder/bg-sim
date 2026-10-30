"""Validate an exported FMU and compare it with the Julia reference run (spike).

    uv run --with fmpy spike/fmu/check.py spike/fmu/out/<model-dir> [signal ...]
"""

import json
import sys
from pathlib import Path

import numpy as np
from fmpy import simulate_fmu
from fmpy.validation import validate_fmu


def reference(ref_dir: Path):
    manifest = json.loads((ref_dir / "manifest.json").read_text())
    ids = [s["id"] for s in manifest["signals"]]
    raw = np.fromfile(ref_dir / "stream.f64", dtype="<f8")
    rows = raw.reshape(-1, 1 + len(ids))
    # An event instant is recorded twice (left, right); keep the right limit, which is what
    # the FMU reports after a doStep that ends on a tick.
    keep = np.append(rows[1:, 0] != rows[:-1, 0], True)
    return ids, rows[keep]


def main(model_dir: Path, wanted):
    meta = json.loads((model_dir / "meta.json").read_text())
    fmu = model_dir / f"{meta['identifier']}.fmu"
    problems = validate_fmu(str(fmu))
    print("fmpy validate:", "OK" if not problems else problems)

    res = simulate_fmu(str(fmu), stop_time=meta["t_end"], output_interval=meta["out_interval"],
                       output=meta["outputs"], fmi_type="CoSimulation")
    ids, ref = reference(model_dir / "reference")
    col = {s: i + 1 for i, s in enumerate(ids)}

    t_fmu = res["time"]
    idx = np.searchsorted(ref[:, 0], t_fmu - 1e-12)
    ok = (idx < len(ref)) & (np.abs(ref[np.minimum(idx, len(ref) - 1), 0] - t_fmu) < 1e-9)
    print(f"{meta['method']} dt = {meta['dt']} s, {ok.sum()} common output times of {len(t_fmu)}")

    rows = []
    for s in meta["outputs"]:
        if s not in col:
            continue
        a = res[s][ok]
        b = ref[idx[ok], col[s]]
        span = max(np.max(np.abs(b)), 1e-12)
        err = np.abs(a - b)
        k = int(np.argmax(err))
        rows.append((err[k] / span, err[k], s, t_fmu[ok][k], span))
    rows.sort(reverse=True)
    show = [r for r in rows if r[2] in wanted] if wanted else rows[:6]
    print(f"{'signal':28s} {'max |err|':>12s} {'rel. to peak':>12s} {'at t':>8s} {'peak':>12s}")
    for rel, abs_err, s, t, span in show:
        print(f"{s:28s} {abs_err:12.3e} {rel:12.3e} {t:8.4f} {span:12.5g}")
    print(f"worst over all {len(rows)} signals: {rows[0][0]:.3e} of peak ({rows[0][2]})")


if __name__ == "__main__":
    main(Path(sys.argv[1]).resolve(), sys.argv[2:])
