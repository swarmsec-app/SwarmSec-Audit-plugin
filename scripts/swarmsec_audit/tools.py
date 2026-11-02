"""Optional tool detection and bounded, recorded execution."""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import time
from pathlib import Path

from .redact import redact_text

DETECT = {
    "forge": ["--version"],
    "cast": ["--version"],
    "anvil": ["--version"],
    "solc": ["--version"],
    "slither": ["--version"],
    "aderyn": ["--version"],
    "semgrep": ["--version"],
    "echidna": ["--version"],
    "medusa": ["--version"],
    "contractmap": ["--version"],
}
# forge subcommands that only compile, test or read. script/create/flatten-to-deploy paths are refused.
FORGE_ALLOWED = {"build", "test", "inspect", "coverage", "snapshot"}
RUNNABLE = {"forge", "slither", "aderyn", "semgrep", "echidna", "medusa", "contractmap"}
# Tools that compile through crytic-compile, which runs `npx hardhat compile` on Hardhat projects.
CRYTIC_TOOLS = {"slither", "echidna", "medusa"}
FORBIDDEN_ARGS = {
    "--private-key",
    "--mnemonic",
    "--broadcast",
    "--unlocked",
    "--ffi",
    "--keystore",
    "--ledger",
    "--trezor",
    "--aws",
}
FORK_ARGS = {"--fork-url", "-f", "--rpc-url"}
SECRET_ENV = re.compile(r"KEY|TOKEN|SECRET|PASSWORD|PASSPHRASE|MNEMONIC|PRIVATE|RPC|ETHERSCAN|CREDENTIAL", re.I)
DEFAULT_TIMEOUT = 600
OUTPUT_CAP = 2_000_000
SANDBOX_CAP = 300_000_000
SANDBOX_SKIP = {
    ".git",
    "out",
    "cache",
    "artifacts",
    "broadcast",
    "node_modules",
    ".swarmsec-audit",
    "crytic-export",
    "coverage",
}


class ToolError(Exception):
    pass


def detect(timeout: float = 10) -> dict[str, str | None]:
    """Map tool name to the first line of its version output, or None when absent or broken."""
    found: dict[str, str | None] = {}
    for name, args in DETECT.items():
        exe = shutil.which(name)
        if not exe:
            found[name] = None
            continue
        try:
            proc = subprocess.run(
                [exe, *args],
                capture_output=True,
                text=True,
                timeout=timeout,
                env=scrubbed_env(),
                stdin=subprocess.DEVNULL,
            )
        except (OSError, subprocess.TimeoutExpired) as exc:
            found[name] = f"present but version check failed: {type(exc).__name__}"
            continue
        lines = [ln.strip() for ln in (proc.stdout or proc.stderr).splitlines() if ln.strip()]
        version = next((ln for ln in lines if re.search(r"\d+\.\d+", ln)), lines[0] if lines else "unknown")
        found[name] = version
    return found


def short_version(text: str | None) -> str | None:
    """'forge Version: 1.5.1-stable' -> '1.5.1-stable'. Returns the input when it holds no version number."""
    if not text:
        return text
    m = re.search(r"\d+\.\d+(?:\.\d+)?(?:[-+][\w.+-]*)?", text)
    return m.group(0) if m else text


def scrubbed_env() -> dict[str, str]:
    env = {k: v for k, v in os.environ.items() if not SECRET_ENV.search(k)}
    env["FOUNDRY_FFI"] = "false"
    return env


def check_command(argv: list[str], project_root: Path, allow_fork: bool, allow_project_build: bool) -> list[str]:
    """Validate a tool command and return it with safety flags applied. Raises ToolError if refused."""
    if not argv:
        raise ToolError("no command given")
    tool = Path(argv[0]).name.lower().removesuffix(".exe")
    if tool not in RUNNABLE:
        raise ToolError(f"'{tool}' is not an allowed tool ({', '.join(sorted(RUNNABLE))})")
    args = list(argv[1:])
    for a in args:
        flag = a.split("=", 1)[0]
        if flag in FORBIDDEN_ARGS:
            raise ToolError(f"argument {flag} is never allowed: audits do not sign or broadcast")
    forks = [a for a in args if a.split("=", 1)[0] in FORK_ARGS]
    if forks and not allow_fork:
        raise ToolError("fork/RPC access needs --allow-fork, given only after the user approves a fork test")
    if tool == "forge":
        sub = next((a for a in args if not a.startswith("-")), None)
        if sub not in FORGE_ALLOWED:
            raise ToolError(f"forge {sub} is not allowed; permitted: {', '.join(sorted(FORGE_ALLOWED))}")
        if sub in ("build", "test", "coverage", "snapshot") and not forks and "--offline" not in args:
            args.append("--offline")
    if tool in CRYTIC_TOOLS and not allow_project_build:
        js = [
            n
            for n in ("hardhat.config.js", "hardhat.config.ts", "hardhat.config.cjs", "truffle-config.js")
            if (project_root / n).is_file()
        ]
        if js:
            raise ToolError(
                f"{tool} would compile through {js[0]}, which executes project JavaScript; "
                "pass --allow-project-build only after the user approves it"
            )
    return [argv[0], *args]


def next_id(directory: Path, prefix: str) -> str:
    nums = [
        int(m.group(1))
        for p in directory.glob(f"{prefix}-*.json")
        if (m := re.match(rf"{prefix}-(\d+)\.json$", p.name))
    ]
    return f"{prefix}-{max(nums, default=0) + 1:03d}"


def record_argv(argv: list[str]) -> list[str]:
    out, hide_next = [], False
    for a in argv:
        if hide_next:
            out.append("<redacted-rpc>")
            hide_next = False
            continue
        flag, eq, _ = a.partition("=")
        if flag in FORK_ARGS:
            if eq:
                out.append(f"{flag}=<redacted-rpc>")
            else:
                out.append(a)
                hide_next = True
            continue
        out.append(redact_text(a))
    return out


def run(
    run_dir: Path,
    project_root: Path,
    argv: list[str],
    cwd: Path | None = None,
    timeout: int = DEFAULT_TIMEOUT,
    allow_fork: bool = False,
    allow_project_build: bool = False,
    versions: dict[str, str | None] | None = None,
) -> dict:
    """Run one tool command with a timeout and record it under <run_dir>/tool-runs/."""
    cmd = check_command(argv, project_root, allow_fork, allow_project_build)
    exe = shutil.which(cmd[0])
    if exe is None:
        raise ToolError(f"{cmd[0]} is not installed; record this as a coverage gap")
    runs_dir = run_dir / "tool-runs"
    runs_dir.mkdir(parents=True, exist_ok=True)
    run_id = next_id(runs_dir, "TR")
    out_path = runs_dir / f"{run_id}.log"
    work = (cwd or project_root).resolve()
    start = time.monotonic()
    timed_out = False
    try:
        proc = subprocess.run(
            [exe, *cmd[1:]],
            cwd=work,
            capture_output=True,
            timeout=timeout,
            env=scrubbed_env(),
            stdin=subprocess.DEVNULL,
        )
        exit_code, stdout, stderr = proc.returncode, proc.stdout, proc.stderr
    except subprocess.TimeoutExpired as exc:
        timed_out, exit_code = True, None
        stdout, stderr = exc.stdout or b"", exc.stderr or b""
    duration = int((time.monotonic() - start) * 1000)
    text = (stdout or b"").decode("utf-8", "replace") + (stderr or b"").decode("utf-8", "replace")
    text = redact_text(text, project_root)
    truncated = len(text) > OUTPUT_CAP
    out_path.write_text(text[:OUTPUT_CAP], encoding="utf-8")
    tool = Path(cmd[0]).name.lower().removesuffix(".exe")
    sub = next((a for a in cmd[1:] if not a.startswith("-")), "") if tool == "forge" else ""
    fork = any(a.split("=", 1)[0] in FORK_ARGS for a in cmd)
    record = {
        "id": run_id,
        "tool": tool,
        "version": (versions or {}).get(tool),
        "command_class": f"{tool} {sub}".strip(),
        "argv": record_argv([tool, *cmd[1:]]),
        "cwd": _rel(work, project_root),
        "exit_code": exit_code,
        "timed_out": timed_out,
        "duration_ms": duration,
        # True unless the command was forced offline: other tools may fetch compilers or rules.
        "network": fork or not (tool == "forge" and "--offline" in cmd),
        "fork": fork,
        "output_file": f"tool-runs/{out_path.name}",
        "output_truncated": truncated,
    }
    (runs_dir / f"{run_id}.json").write_text(json.dumps(record, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return record


def _rel(path: Path, root: Path) -> str:
    try:
        return path.relative_to(root.resolve()).as_posix() or "."
    except ValueError:
        return "<outside-project>"


def make_sandbox(project_root: Path, run_dir: Path) -> Path:
    """Copy the project into the run directory so verification tests never touch the user's tree."""
    dest = run_dir / "sandbox"
    if dest.exists():
        return dest
    total = 0

    def ignore(directory: str, names: list[str]) -> set[str]:
        nonlocal total
        skipped = {n for n in names if n in SANDBOX_SKIP}
        for n in names:
            p = Path(directory) / n
            if n not in skipped and p.is_file():
                total += p.stat().st_size
        if total > SANDBOX_CAP:
            raise ToolError(f"project is larger than {SANDBOX_CAP // 1_000_000} MB; sandbox copy refused")
        return skipped

    try:
        shutil.copytree(project_root, dest, ignore=ignore, symlinks=True)
    except ToolError:
        shutil.rmtree(dest, ignore_errors=True)
        raise
    return dest
