"""The assistant's system prompt."""

from __future__ import annotations

from pathlib import Path

from ..profiles import Profile

_SYSTEM = Path(__file__).with_name("system.md")
_HOME = Path(__file__).with_name("home.md")
_ONE_TOOL = "\nCall one tool at a time and wait for its result."


def system_prompt(profile: Profile, project: str | None) -> str:
    text = _SYSTEM.read_text(encoding="utf-8").replace("{project}", project or "(none yet)")
    if project is None:
        text += _HOME.read_text(encoding="utf-8")
    return text + (_ONE_TOOL if profile.one_tool_at_a_time else "")
