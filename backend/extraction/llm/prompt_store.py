"""Prompt files with a version number (plan WP4, rule 3).

Every prompt lives in its own file inside :data:`PROMPTS_DIR`. The file name
carries the version (``tier2_extractor_v1.txt``) and the file starts with two
metadata lines::

    # version: v1
    # chain: tier2_extractor

The version is stored with every LLM call (``llm_calls.prompt_version``) so a
result can always be traced back to the prompt that produced it.
"""

from __future__ import annotations

import re
from functools import lru_cache
from pathlib import Path

PROMPTS_DIR = Path(__file__).resolve().parent / "prompts"

_VERSION_RE = re.compile(r"^#\s*version\s*:\s*(?P<version>\S+)\s*$", re.MULTILINE)
_CHAIN_RE = re.compile(r"^#\s*chain\s*:\s*(?P<chain>\S+)\s*$", re.MULTILINE)
_NAME_RE = re.compile(r"^(?P<name>.+)_(?P<version>v(?P<number>\d+))$")


class PromptNotFoundError(FileNotFoundError):
    """Raised when a prompt file does not exist."""


def prompts_dir(prompts_dir_override: Path | str | None = None) -> Path:
    """Return the directory that holds the prompt files."""
    if prompts_dir_override is not None:
        return Path(prompts_dir_override)
    return PROMPTS_DIR


def _files(directory: Path, name: str) -> list[tuple[int, Path]]:
    """Return ``(version_number, path)`` for every version of ``name``."""
    found: list[tuple[int, Path]] = []
    for path in sorted(directory.glob(f"{name}_v*.txt")):
        match = _NAME_RE.match(path.stem)
        if match and match.group("name") == name:
            found.append((int(match.group("number")), path))
    return sorted(found)


def available_versions(name: str, directory: Path | str | None = None) -> list[str]:
    """Return the available versions of a prompt, oldest first."""
    base = prompts_dir(directory)
    return [f"v{number}" for number, _ in _files(base, name)]


def prompt_path(name: str, version: str | None = None, directory: Path | str | None = None) -> Path:
    """Return the path of a prompt file.

    ``version=None`` selects the highest available version.
    """
    base = prompts_dir(directory)
    versions = _files(base, name)
    if not versions:
        raise PromptNotFoundError(f"no prompt file for {name!r} in {base}")
    if version is None:
        return versions[-1][1]
    wanted = version.lstrip("v")
    for number, path in versions:
        if str(number) == wanted:
            return path
    raise PromptNotFoundError(
        f"prompt {name!r} has no version {version!r} (have {available_versions(name, base)})"
    )


def load_prompt(name: str, version: str | None = None, directory: Path | str | None = None) -> str:
    """Return the text of a prompt file."""
    return prompt_path(name, version, directory).read_text(encoding="utf-8")


def strip_metadata(text: str) -> str:
    """Return the prompt text without the leading ``#`` metadata lines."""
    lines = text.splitlines()
    while lines and lines[0].lstrip().startswith("#"):
        lines.pop(0)
    return "\n".join(lines).strip()


@lru_cache(maxsize=32)
def _cached_metadata(name: str, version: str | None) -> tuple[str, str]:
    text = load_prompt(name, version)
    version_match = _VERSION_RE.search(text)
    chain_match = _CHAIN_RE.search(text)
    if version_match is None:
        raise PromptNotFoundError(f"prompt {name!r} has no '# version:' header")
    if chain_match is None:
        raise PromptNotFoundError(f"prompt {name!r} has no '# chain:' header")
    return version_match.group("version"), chain_match.group("chain")


def prompt_version(
    name: str, version: str | None = None, directory: Path | str | None = None
) -> str:
    """Return the version string of a prompt file, e.g. ``"v1"``."""
    if directory is None:
        return _cached_metadata(name, version)[0]
    text = load_prompt(name, version, directory)
    match = _VERSION_RE.search(text)
    if match is None:
        raise PromptNotFoundError(f"prompt {name!r} has no '# version:' header")
    return match.group("version")


def prompt_chain(name: str, version: str | None = None, directory: Path | str | None = None) -> str:
    """Return the chain name declared in the prompt file."""
    if directory is None:
        return _cached_metadata(name, version)[1]
    text = load_prompt(name, version, directory)
    match = _CHAIN_RE.search(text)
    if match is None:
        raise PromptNotFoundError(f"prompt {name!r} has no '# chain:' header")
    return match.group("chain")


def list_prompts(directory: Path | str | None = None) -> list[str]:
    """Return the names of every known prompt."""
    base = prompts_dir(directory)
    names: list[str] = []
    for path in sorted(base.glob("*_v*.txt")):
        match = _NAME_RE.match(path.stem)
        if match and match.group("name") not in names:
            names.append(match.group("name"))
    return names


__all__ = [
    "PROMPTS_DIR",
    "PromptNotFoundError",
    "available_versions",
    "list_prompts",
    "load_prompt",
    "prompt_chain",
    "prompt_path",
    "prompt_version",
    "prompts_dir",
    "strip_metadata",
]
