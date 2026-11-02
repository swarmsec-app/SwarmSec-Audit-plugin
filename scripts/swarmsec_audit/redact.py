"""Remove credentials, authenticated endpoints and machine paths from text that leaves the run."""

from __future__ import annotations

import re
from pathlib import Path

_RULES = [
    # Credentials embedded in URLs: https://user:pass@host
    (re.compile(r"(https?|wss?)://[^/\s:@]+:[^/\s@]+@"), r"\1://<redacted>@"),
    # Provider endpoints that carry the API key in the path.
    (
        re.compile(
            r"(https?|wss?)://([\w.-]*(?:alchemy|infura|quiknode|quicknode|ankr|blastapi|drpc|chainstack|"
            r"getblock|nodereal|tenderly|blockpi|llamarpc|moralis)[\w.-]*)/[^\s\"'<>]+",
            re.I,
        ),
        r"\1://\2/<redacted>",
    ),
    (re.compile(r"([?&](?:api[-_]?key|apikey|key|token|access[-_]?token|auth)=)[^&\s\"'<>]+", re.I), r"\1<redacted>"),
    (
        re.compile(r"((?:PRIVATE_KEY|MNEMONIC|ETHERSCAN_API_KEY|API_KEY|SECRET|PASSWORD)\s*[=:]\s*)\S+", re.I),
        r"\1<redacted>",
    ),
    (re.compile(r"(--private-key|--mnemonic)(\s+|=)\S+"), r"\1\2<redacted>"),
    (re.compile(r"\bBearer\s+[A-Za-z0-9._~+/=-]{8,}"), "Bearer <redacted>"),
]


def _path_forms(path: Path) -> list[str]:
    """Native, forward-slash and Git Bash (/c/...) spellings of a path, longest first."""
    posix = path.resolve().as_posix()
    forms = {str(path.resolve()), posix}
    if len(posix) > 2 and posix[1] == ":":
        forms.add(f"/{posix[0].lower()}{posix[2:]}")
    return sorted(forms, key=len, reverse=True)


def redact_text(text: str, project_root: Path | None = None) -> str:
    for pattern, repl in _RULES:
        text = pattern.sub(repl, text)
    if project_root is not None:
        for form in _path_forms(project_root):
            text = text.replace(form, "<project>")
    for form in _path_forms(Path.home()):
        if len(form) > 3:
            text = text.replace(form, "~")
    return text


def redact_obj(value, project_root: Path | None = None):
    if isinstance(value, str):
        return redact_text(value, project_root)
    if isinstance(value, list):
        return [redact_obj(v, project_root) for v in value]
    if isinstance(value, dict):
        return {k: redact_obj(v, project_root) for k, v in value.items()}
    return value
