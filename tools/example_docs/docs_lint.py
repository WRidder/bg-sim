"""Lint the docs of one model (X5.10): used by ``examples/run_checks.py`` and by ``build.py``.

Checks (every problem is one ``file:line: what is wrong; what to fix`` string):

* ``docs.json`` parses, ids are unique, ``file`` is ``pages/<id>.md`` and exists;
* every ``pages/*.md`` is in the tree;
* every ``assets/<hash>.<ext>`` reference exists, every asset file is referenced and is named by the
  first 12 hex digits of its SHA-256;
* ``page:`` links name a page, ``block:`` links a node of the model (``Sub/Name`` for a node inside
  a subsystem), ``signal:`` links a signal the run produced;
* every ``$...$`` / ``$$...$$`` span parses in KaTeX (``katex_check.mjs``), no unmatched ``$``,
  no raw HTML, no ``|`` inside math in a table row.

Standalone: ``uv run tools/example_docs/docs_lint.py <docs-dir> [<model.bgmodel.json> [<signals.txt>]]``.
"""

from __future__ import annotations

import hashlib
import json
import re
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent
PAGE_FILE = re.compile(r"^pages/([a-z0-9][a-z0-9-]{0,63})\.md$")
ASSET = re.compile(r"^assets/([0-9a-f]{12})\.(png|jpg|gif|webp|svg)$")
LINK = re.compile(r"(!?)\[((?:[^\[\]]|\[[^\]]*\])*)\]\(([^)\s]+)(?:\s+\"[^\"]*\")?\)")
INLINE_MATH = re.compile(r"(?<![\\$])\$(?![\s$])((?:\\.|[^$\\\n])+?)(?<![\s\\])\$(?!\d)")
INLINE_DISPLAY = re.compile(r"(?<!\\)\$\$(.+?)(?<!\\)\$\$")
CODE_SPAN = re.compile(r"(`+)(.+?)\1")
RAW_HTML = re.compile(r"<\s*/?\s*[a-zA-Z][^>]*>")


def _walk(pages: list[dict[str, Any]]):
    for page in pages:
        yield page
        yield from _walk(page.get("children", []))


def find_block(document: dict[str, Any], reference: str) -> bool:
    """The ``findBlock`` of web/src/docs/docsLinks.ts: ``A/B/C`` through subsystem names."""
    names = [part for part in reference.split("/") if part]
    nodes = document["diagram"]["nodes"]
    for depth, name in enumerate(names):
        node = next((n for n in nodes if n["name"] == name), None)
        if node is None:
            return False
        if depth == len(names) - 1:
            return True
        if "subsystem" not in node["block"]:
            return False
        nodes = node["block"]["subsystem"]["diagram"]["nodes"]
    return False


class Page:
    """A page's math spans, links and images (code blanked out) and its markup problems."""

    def __init__(self, path: Path):
        self.lines = path.read_text(encoding="utf-8").split("\n")
        self.math: list[tuple[int, str, bool]] = []  # (line, tex, display)
        self.links: list[tuple[int, bool, str, str]] = []  # (line, is_image, text, target)
        self.problems: list[tuple[int, str]] = []
        self._scan()

    def _scan(self) -> None:
        fence: str | None = None
        block: tuple[int, list[str]] | None = None
        for number, raw in enumerate(self.lines, 1):
            marker = re.match(r"^\s*(`{3,}|~{3,})", raw)
            if marker is not None:
                if fence is None:
                    fence = marker.group(1)[0]
                elif marker.group(1)[0] == fence:
                    fence = None
                continue
            if fence is not None:
                continue
            if block is not None:
                if raw.strip() == "$$":
                    self.math.append((block[0], "\n".join(block[1]), True))
                    block = None
                else:
                    block[1].append(raw)
                continue
            if raw.strip() == "$$":
                block = (number, [])
                continue
            single = re.match(r"^\s*\$\$(?!\$)(.+?)\$\$\s*$", raw)
            if single is not None:
                self.math.append((number, single.group(1), True))
                continue
            text = CODE_SPAN.sub(lambda m: " " * len(m.group(0)), raw)

            def blank(match: re.Match[str], number: int = number, text: str = text) -> str:
                tex = match.group(1)
                self.math.append((number, tex, False))
                if "|" in tex and text.lstrip().startswith("|"):
                    self.problems.append(
                        (number, "a '|' inside math in a table row splits the cell; use \\lvert/\\rvert or \\mid")
                    )
                return " " * len(match.group(0))

            text = INLINE_DISPLAY.sub(blank, text)
            text = INLINE_MATH.sub(blank, text)
            if "$" in text.replace("\\$", ""):
                self.problems.append(
                    (number, "unmatched '$': write math as $...$ on one line or escape a dollar sign as \\$")
                )
            for found in LINK.finditer(text):
                self.links.append((number, found.group(1) == "!", found.group(2), found.group(3)))
            stripped = LINK.sub(lambda m: " " * len(m.group(0)), text)
            if RAW_HTML.search(stripped):
                self.problems.append((number, "raw HTML is dropped by the renderer; use Markdown"))
        if fence is not None:
            self.problems.append((len(self.lines), "an unclosed code fence"))
        if block is not None:
            self.problems.append((block[0], "a '$$' block is never closed"))


def lint_model_docs(
    docs_dir: Path,
    model_document: dict[str, Any] | None,
    signal_ids: set[str] | None,
    label: str | None = None,
) -> list[str]:
    """All problems of ``docs_dir`` as ``path:line: message`` strings (empty = clean)."""
    label = label or docs_dir.as_posix()
    errors: list[str] = []
    manifest_path = docs_dir / "docs.json"
    if not manifest_path.is_file():
        return [f"{label}/docs.json:1: missing; create the manifest (see contracts/schemas/docs.schema.json)"]
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except ValueError as exc:
        return [f"{label}/docs.json:1: not valid JSON ({exc}); fix the syntax"]
    if manifest.get("format") != "bgsim.docs" or manifest.get("version") != 1:
        errors.append(f"{label}/docs.json:1: format must be 'bgsim.docs' and version 1")
    ids: set[str] = set()
    files: set[str] = set()
    for page in _walk(manifest.get("pages", [])):
        page_id = page.get("id", "")
        if page_id in ids:
            errors.append(f"{label}/docs.json:1: page id {page_id!r} is used twice; rename one")
        ids.add(page_id)
        file = page.get("file", "")
        files.add(file)
        found = PAGE_FILE.match(file)
        if found is None or found.group(1) != page_id:
            errors.append(f"{label}/docs.json:1: page {page_id!r} must use the file 'pages/{page_id}.md', not {file!r}")
        elif not (docs_dir / file).is_file():
            errors.append(f"{label}/docs.json:1: page {page_id!r} has no file {file}; create it or remove the page")
        if not page.get("title"):
            errors.append(f"{label}/docs.json:1: page {page_id!r} has no title")
    pages_dir = docs_dir / "pages"
    for path in sorted(pages_dir.glob("*.md")) if pages_dir.is_dir() else []:
        if f"pages/{path.name}" not in files:
            errors.append(f"{label}/pages/{path.name}:1: not in docs.json; add the page to the tree or delete the file")

    referenced: set[str] = set()
    spans: list[dict[str, Any]] = []
    for file in sorted(files):
        path = docs_dir / file
        if not path.is_file():
            continue
        page = Page(path)
        where = f"{label}/{file}"
        for number, message in page.problems:
            errors.append(f"{where}:{number}: {message}")
        for number, tex, display in page.math:
            spans.append({"file": where, "line": number, "tex": tex, "display": display})
        for number, is_image, _text, target in page.links:
            if is_image:
                if ASSET.match(target) is None:
                    errors.append(f"{where}:{number}: image {target!r} must be assets/<12 hex>.<png|jpg|gif|webp|svg>")
                    continue
                referenced.add(target)
                if not (docs_dir / target).is_file():
                    errors.append(f"{where}:{number}: image {target} does not exist; run tools/example_docs/build.py")
                continue
            scheme, _, rest = target.partition(":")
            if scheme == "page":
                if rest not in ids:
                    errors.append(f"{where}:{number}: link page:{rest} names no page; pick one of {sorted(ids)}")
            elif scheme == "block":
                if model_document is None:
                    errors.append(f"{where}:{number}: block:{rest} cannot be checked without the model")
                elif not find_block(model_document, rest):
                    errors.append(f"{where}:{number}: link block:{rest} names no node of the model; use the node name (Sub/Name inside a subsystem)")
            elif scheme == "signal":
                if signal_ids is None:
                    errors.append(f"{where}:{number}: signal:{rest} cannot be checked because the model has no run in expected.json")
                elif rest not in signal_ids:
                    errors.append(f"{where}:{number}: link signal:{rest} is not a signal of the run; copy the id from the signal browser")
            elif scheme in {"http", "https", "mailto"} or target.startswith("#"):
                pass
            else:
                errors.append(f"{where}:{number}: link {target!r} is not page:, block:, signal: or https; fix the target")
    assets_dir = docs_dir / "assets"
    for path in sorted(assets_dir.iterdir()) if assets_dir.is_dir() else []:
        relative = f"assets/{path.name}"
        found = ASSET.match(relative)
        if found is None:
            errors.append(f"{label}/{relative}:1: not a valid asset name; assets are <12 hex>.<ext>")
            continue
        if relative not in referenced:
            errors.append(f"{label}/{relative}:1: no page references this asset; delete it (build.py does) or link it")
        digest = hashlib.sha256(path.read_bytes()).hexdigest()[:12]
        if digest != found.group(1):
            errors.append(f"{label}/{relative}:1: the name is not the SHA-256 prefix of the content ({digest}); run tools/example_docs/build.py")
    errors.extend(_katex_errors(spans))
    return errors


def _katex_errors(spans: list[dict[str, Any]]) -> list[str]:
    if not spans:
        return []
    node = shutil.which("node")
    if node is None:
        return ["tools/example_docs/katex_check.mjs:1: node is not on PATH; install Node to check the math"]
    result = subprocess.run(
        [node, str(HERE / "katex_check.mjs")],
        input=json.dumps(spans),
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=False,
    )
    if result.returncode != 0:
        return [f"tools/example_docs/katex_check.mjs:1: failed: {result.stderr.strip()[:400]}"]
    # KaTeX messages quote the source with combining characters that a cp1252 console cannot print.
    return [
        f"{e['file']}:{e['line']}: KaTeX cannot parse ${e['tex'][:60]}$: {e['error'][:200]}; fix the TeX".encode(
            "ascii", "replace"
        ).decode("ascii")
        for e in json.loads(result.stdout)
    ]


def main() -> int:
    if len(sys.argv) < 2:
        print(__doc__)
        return 2
    docs_dir = Path(sys.argv[1])
    model = json.loads(Path(sys.argv[2]).read_text(encoding="utf-8")) if len(sys.argv) > 2 else None
    signals = set(Path(sys.argv[3]).read_text(encoding="utf-8").split()) if len(sys.argv) > 3 else None
    errors = lint_model_docs(docs_dir, model, signals)
    print("\n".join(errors) if errors else "docs clean")
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
