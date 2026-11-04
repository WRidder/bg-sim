"""Assistant profiles: ``assistant.toml`` (machine specific, gitignored) or the committed
``assistant.example.toml``; ``BGSIM_ASSISTANT_CONFIG`` moves the file.

A profile names a runner (``claude-cli`` or ``openai-compatible``) and its limits. An unknown
key, a missing required key or a wrong type refuses the whole file: no silent defaults for
what the file spells out.
"""

from __future__ import annotations

import os
import tomllib
from dataclasses import dataclass, field, fields
from pathlib import Path
from typing import Any

CONFIG_ENV = "BGSIM_ASSISTANT_CONFIG"
RUNNERS = ("claude-cli", "openai-compatible")


class ProfileError(Exception):
    pass


@dataclass(frozen=True)
class Profile:
    name: str
    runner: str
    model: str
    max_turns: int
    timeout_s: float
    # claude-cli
    effort: str | None = None
    max_budget_usd: float | None = None
    # openai-compatible
    base_url: str | None = None
    api_key_env: str | None = None  # the variable that holds the key; the key is never in the file
    temperature: float | None = None
    top_k: int | None = None
    repeat_penalty: float | None = None
    one_tool_at_a_time: bool = False

    def public(self) -> dict[str, Any]:
        return {
            f.name: getattr(self, f.name)
            for f in fields(self)
            if getattr(self, f.name) is not None
        }


_SPEC: dict[str, tuple[Any, bool]] = {  # key -> (type, required)
    "runner": (str, True),
    "model": (str, True),
    "max_turns": (int, True),
    "timeout_s": ((int, float), True),
    "effort": (str, False),
    "max_budget_usd": ((int, float), False),
    "base_url": (str, False),
    "api_key_env": (str, False),
    "temperature": ((int, float), False),
    "top_k": (int, False),
    "repeat_penalty": ((int, float), False),
    "one_tool_at_a_time": (bool, False),
}
_ONLY = {
    "claude-cli": {"effort", "max_budget_usd"},
    "openai-compatible": {
        "base_url", "api_key_env", "temperature", "top_k", "repeat_penalty", "one_tool_at_a_time",
    },
}
_REQUIRED = {"claude-cli": {"effort", "max_budget_usd"}, "openai-compatible": {"base_url"}}


@dataclass(frozen=True)
class AssistantConfig:
    default: str
    profiles: dict[str, Profile]
    source: Path = field(default=Path("."), compare=False)


def config_path(repo_root: Path) -> Path:
    if CONFIG_ENV in os.environ:
        return Path(os.environ[CONFIG_ENV])
    own = repo_root / "assistant.toml"
    return own if own.is_file() else repo_root / "assistant.example.toml"


def parse(text: str, source: Path = Path("<string>")) -> AssistantConfig:
    try:
        doc = tomllib.loads(text)
    except tomllib.TOMLDecodeError as exc:
        raise ProfileError(f"{source}: {exc}") from None
    extra = set(doc) - {"default", "profiles"}
    if extra:
        raise ProfileError(f"{source}: unknown top-level keys {sorted(extra)}")
    raw = doc.get("profiles")
    if not isinstance(raw, dict) or not raw:
        raise ProfileError(f"{source}: no [profiles.*]")
    profiles: dict[str, Profile] = {}
    for name, entry in raw.items():
        if not isinstance(entry, dict):
            raise ProfileError(f"{source}: profiles.{name} is not a table")
        profiles[name] = _profile(name, entry, source)
    default = doc.get("default")
    if not isinstance(default, str) or default not in profiles:
        raise ProfileError(
            f"{source}: `default` must name a profile ({sorted(profiles)}), got {default!r}"
        )
    return AssistantConfig(default, profiles, source)


def _profile(name: str, entry: dict[str, Any], source: Path) -> Profile:
    where = f"{source}: profiles.{name}"
    unknown = set(entry) - set(_SPEC)
    if unknown:
        raise ProfileError(f"{where}: unknown keys {sorted(unknown)}")
    for key, (kind, required) in _SPEC.items():
        if key in entry:
            value = entry[key]
            wrong_bool = isinstance(value, bool) and kind is not bool
            if not isinstance(value, kind) or wrong_bool:
                raise ProfileError(f"{where}.{key}: wrong type ({type(value).__name__})")
        elif required:
            raise ProfileError(f"{where}: `{key}` is required")
    runner = entry["runner"]
    if runner not in RUNNERS:
        raise ProfileError(f"{where}.runner: {runner!r} is not one of {RUNNERS}")
    for other, keys in _ONLY.items():
        if other != runner and keys & set(entry):
            raise ProfileError(
                f"{where}: {sorted(keys & set(entry))} belong to runner {other}, not {runner}"
            )
    missing = _REQUIRED[runner] - set(entry)
    if missing:
        raise ProfileError(f"{where}: runner {runner} needs {sorted(missing)}")
    if entry["max_turns"] < 1 or entry["timeout_s"] <= 0:
        raise ProfileError(f"{where}: max_turns >= 1 and timeout_s > 0 are required")
    return Profile(name=name, **entry)


def load(path: Path) -> AssistantConfig:
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as exc:
        raise ProfileError(f"{path}: {exc.strerror or exc}") from None
    return parse(text, path)
