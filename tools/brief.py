# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""Assemble a sub-agent brief for a bg-sim work package.

The brief embeds the work package text and the governing plan sections verbatim,
so a sub-agent never has to guess at project rules.

Usage: uv run tools/brief.py <out.md> --title "M0.3 ..." --wp-file <file> --sections 0.2,0.3,1,2
"""

from __future__ import annotations

import argparse
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PLAN = ROOT / "plan" / "IMPLEMENTATION_PLAN.md"
SPEC = ROOT / "spec" / "Modeling Language Spec v0.1.md"

HEADING = re.compile(r"^(#{1,6})\s+(.*)$")


def load_lines(path: Path) -> list[str]:
    return path.read_text(encoding="utf-8").splitlines()


def level_of(line: str) -> int:
    m = HEADING.match(line)
    return len(m.group(1)) if m else 0


def extract(lines: list[str], heading_prefix: str) -> str:
    """Extract from the first heading whose text starts with heading_prefix
    to the next heading of the same or a higher level."""
    for i, line in enumerate(lines):
        m = HEADING.match(line)
        if m and m.group(2).strip().lower().startswith(heading_prefix.strip().lower()):
            lvl = len(m.group(1))
            out = [line]
            for j in range(i + 1, len(lines)):
                lv = level_of(lines[j])
                if lv and lv <= lvl:
                    break
                out.append(lines[j])
            return "\n".join(out).rstrip()
    raise SystemExit(f"section not found: {heading_prefix}")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("out")
    ap.add_argument("--title", required=True)
    ap.add_argument("--wp-file", required=True, help="file holding the verbatim WP text")
    ap.add_argument("--sections", default="0.2,0.3,1,2")
    ap.add_argument("--more", default="", help="extra section headings, comma separated")
    ap.add_argument("--spec", action="store_true", help="point at the spec as mandatory reading")
    ap.add_argument("--notes", default="", help="extra guidance inserted before the rules")
    args = ap.parse_args()

    plan = load_lines(PLAN)
    wp = Path(args.wp_file).read_text(encoding="utf-8").strip()
    base = [s.strip() for s in args.sections.split(",") if s.strip()]
    more = [s.strip() for s in args.more.split(",") if s.strip()]
    # section 0.2/0.3/1/2 live under "## 0", so extract by their own headings
    names = {
        "0.1": "0.1 Orchestrator protocol",
        "0.2": "0.2 Rules for every sub-agent",
        "0.3": "0.3 Environment facts",
        "1": "1. Decisions and assumptions",
        "2": "2. Architecture",
    }

    parts: list[str] = []
    parts.append(f"# Work package brief: {args.title}\n")
    parts.append(
        "You are a sub-agent working on **bg-sim**, a bond-graph / block-diagram / equation "
        "modeling and simulation tool at `D:\\bg-sim` (Windows 11, PowerShell or Git Bash).\n"
    )
    parts.append(
        "Read `D:\\bg-sim\\CLAUDE.md` first (toolchain rules). Then execute the work package "
        "below. The orchestrator verifies your work by running the acceptance commands itself; "
        "anything less than green does not count.\n"
    )

    parts.append("## Your work package (verbatim from the implementation plan)\n")
    parts.append(wp + "\n")

    parts.append("## Governing plan sections (verbatim)\n")
    for s in base:
        key = names.get(s, s)
        parts.append(extract(plan, key) + "\n")

    for s in more:
        parts.append(extract(plan, s) + "\n")

    if args.spec:
        parts.append("## Normative specification\n")
        parts.append(
            f"`{SPEC}` is normative and binding. Read all of it before writing language, "
            "parser, checker, unit or stdlib code. Where the plan's decision table (section 1.2) "
            "and the spec differ, the plan wins. Do not read the `background/` PDFs.\n"
        )

    notes_path = ROOT / "julia" / "BGSim" / "NOTES.md"
    if notes_path.exists() and args.spec:
        parts.append("## MTK / Julia API notes from M0.3 (authoritative for the J lane)\n")
        parts.append(notes_path.read_text(encoding="utf-8").strip() + "\n")

    if args.notes:
        parts.append("## Orchestrator notes\n")
        parts.append(args.notes.strip() + "\n")

    parts.append(
        """## Hard rules for this session

- Touch only the paths named under `Owns` in your WP, plus new test files next to them. Never
  modify `plan/`, `plan/STATUS.md`, `spec/` or anything outside `D:\\bg-sim`. Do not run
  `git commit` or `git checkout`; the orchestrator owns git.
- Never guess a third-party API. Probe it first (`@doc`, `methods`, package sources under
  `~/.julia/packages`, the `.d.ts` files in `node_modules`) and write the probe into a test.
- Python only through `uv run`; add dependencies only with `uv add`. Julia only with
  `--project=julia/BGSim`. Node only through `npm` inside `web/`.
- Deliver real implementations. No stubs, no `TODO`, no skipped or weakened tests. If a check
  in the plan proves impossible, implement the closest honest thing and say exactly what and why
  in your report; do not silently change an assertion.
- Every diagnostic must carry the contract shape of plan section 3.4 if your WP produces
  diagnostics.
- Run the acceptance commands yourself, in full, before reporting.

## Report (at most 15 lines, no markdown headings)

1. Files added or changed (paths only).
2. Decisions you took where the WP was silent.
3. Deviations from the plan, and why.
4. The exact commands you ran and their pass/fail result.
5. Anything the next WP or the orchestrator must know.
"""
    )

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text("\n".join(parts), encoding="utf-8", newline="\n")
    print(f"wrote {out} ({len(out.read_text(encoding='utf-8').splitlines())} lines)")


if __name__ == "__main__":
    main()
