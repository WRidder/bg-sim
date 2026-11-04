"""The reference texts the agent can search: the language spec, the design notes that define
modelling behaviour and the user manual, split into sections at their headings."""

from __future__ import annotations

import re
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

_SOURCES = (
    ("spec", "spec/Modeling Language Spec v0.1.md"),
    ("multibond", "docs/multibond.md"),
    ("modal", "docs/modal-body-format.md"),
    ("globals", "plan/GLOBAL_PARAMETERS.md"),
    ("dashboard", "plan/DASHBOARD_PLAN.md"),
)
_MANUAL_DIR = "web/src/manual/pages"
_HEADING = re.compile(r"^(#{1,4})\s+(.+?)\s*$")
_SLUG = re.compile(r"[^a-z0-9]+")
MAX_SECTION_CHARS = 16000


@dataclass(frozen=True)
class Section:
    id: str
    title: str
    text: str


def _slug(text: str) -> str:
    return _SLUG.sub("-", text.lower()).strip("-")


def _split(prefix: str, text: str) -> list[Section]:
    sections: list[Section] = []
    title, lines = prefix, []
    seen: dict[str, int] = {}
    fence = False

    def flush() -> None:
        body = "\n".join(lines).strip()
        if body:
            slug = _slug(title)
            seen[slug] = seen.get(slug, 0) + 1
            suffix = "" if seen[slug] == 1 else f"-{seen[slug]}"
            sections.append(Section(f"{prefix}#{slug}{suffix}", title, body))

    for line in text.splitlines():
        if line.lstrip().startswith("```"):
            fence = not fence
        heading = None if fence else _HEADING.match(line)
        if heading is not None:
            flush()
            title, lines = heading.group(2), []
        else:
            lines.append(line)
    flush()
    return sections


@lru_cache(maxsize=1)
def _load(repo_root: str) -> tuple[Section, ...]:
    root = Path(repo_root)
    sections: list[Section] = []
    for prefix, relative in _SOURCES:
        path = root / relative
        if path.is_file():
            sections.extend(_split(prefix, path.read_text(encoding="utf-8")))
    for path in sorted((root / _MANUAL_DIR).glob("*.md")):
        sections.extend(_split(f"manual/{path.stem}", path.read_text(encoding="utf-8")))
    return tuple(sections)


def search(repo_root: Path, query: str, limit: int = 12) -> list[dict[str, str | int]]:
    """Sections ranked by how often the query's words occur; a title hit counts most."""
    words = [w for w in re.findall(r"[a-z0-9_]+", query.lower()) if len(w) > 1]
    scored = []
    for section in _load(str(repo_root)):
        title, body = section.title.lower(), section.text.lower()
        hits = [w for w in words if w in title or w in body]
        if not hits:
            continue
        score = sum(10 * title.count(w) + min(body.count(w), 8) for w in hits) * len(hits)
        scored.append((score, section))
    scored.sort(key=lambda entry: -entry[0])
    results: list[dict[str, str | int]] = []
    for score, section in scored[:limit]:
        at = min((section.text.lower().find(w) for w in words if w in section.text.lower()), default=0)
        start = max(0, at - 80)
        results.append({
            "id": section.id,
            "title": section.title,
            "score": score,
            "excerpt": section.text[start:start + 240].replace("\n", " "),
        })
    return results


def read(repo_root: Path, section_id: str) -> dict[str, str | bool] | None:
    for section in _load(str(repo_root)):
        if section.id == section_id:
            cut = len(section.text) > MAX_SECTION_CHARS
            return {
                "id": section.id,
                "title": section.title,
                "text": section.text[:MAX_SECTION_CHARS],
                "truncated": cut,
            }
    return None


def contents(repo_root: Path, prefix: str | None = None) -> list[dict[str, str]]:
    return [
        {"id": s.id, "title": s.title}
        for s in _load(str(repo_root))
        if prefix is None or s.id.startswith(prefix)
    ]
