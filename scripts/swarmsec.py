#!/usr/bin/env python3
"""SwarmSec Audit helper CLI. Standard library only; Python 3.11+.

Run `python scripts/swarmsec.py <command> --help` for each command.
"""

from __future__ import annotations

import argparse
import json
import shutil
import sys
from pathlib import Path

if sys.version_info < (3, 11):  # noqa: UP036 - friendly message instead of a SyntaxError
    sys.exit("swarmsec.py needs Python 3.11 or newer")

sys.path.insert(0, str(Path(__file__).resolve().parent))

from swarmsec_audit import adapters, diffscan, report, schema, solscan, tools, workspace

KNOWN_ERRORS = (
    tools.ToolError,
    diffscan.DiffError,
    adapters.AdapterError,
    report.RenderError,
    FileNotFoundError,
    NotADirectoryError,
    ValueError,
)


def _print_json(data) -> None:
    print(json.dumps(data, indent=2, sort_keys=True, ensure_ascii=False))


def cmd_tools(args) -> int:
    found = tools.detect()
    if args.json:
        _print_json(found)
    else:
        for name, version in found.items():
            print(f"{name}: {version or 'absent'}")
    return 0


def cmd_inventory(args) -> int:
    target = Path(args.path)
    if not target.exists():
        raise FileNotFoundError(f"{args.path} does not exist")
    inv = solscan.inventory(target, args.include_vendored)
    if args.out:
        workspace.write_json(Path(args.out), inv)
    print(json.dumps(inv, indent=2) if args.json else solscan.format_text(inv))
    return 0


def cmd_init(args) -> int:
    project = Path(args.project).resolve()
    if not project.is_dir():
        raise NotADirectoryError(f"{args.project} is not a directory")
    target = Path(args.target)
    target_abs = (project / target).resolve() if not target.is_absolute() else target.resolve()
    if not target_abs.exists():
        raise FileNotFoundError(f"target {args.target} does not exist under {project}")
    try:
        rel_target = target_abs.relative_to(project).as_posix() or "."
    except ValueError:
        raise ValueError(f"target {args.target} is outside {project}") from None
    inv = solscan.inventory(target_abs, args.include_vendored, project)
    run_dir = workspace.create_run(project, rel_target, args.mode, args.diff, inv["build"], tools.detect())
    workspace.write_json(run_dir / "inventory.json", inv)
    if inv["unresolved_imports"] or inv["skipped"]:
        run = workspace.load_run(run_dir)
        run["coverage_gaps"] += [f"unresolved import {u}" for u in inv["unresolved_imports"]]
        run["coverage_gaps"] += [f"not scanned: {s['path']} ({s['reason']})" for s in inv["skipped"]]
        workspace.write_json(run_dir / "run.json", run)
    print(f"run directory: {run_dir.as_posix()}")
    print(solscan.format_text(inv))
    return 0


def cmd_validate(args) -> int:
    path = workspace.expand_latest(Path(args.path))
    if path.is_file():
        finding = json.loads(path.read_text(encoding="utf-8"))
        run_dir = path.parent.parent if path.parent.name == "findings" else path.parent
        tool_runs = schema.load_tool_runs(run_dir) if (run_dir / "tool-runs").is_dir() else {}
        root = Path(args.root) if args.root else _root_from_run(run_dir)
        errors, warnings = schema.validate_finding(finding, root, tool_runs)
        errors_by, warnings_by = ({path.name: errors} if errors else {}), ({path.name: warnings} if warnings else {})
        count = 1
    else:
        run_dir = workspace.resolve_run_dir(path)
        root = Path(args.root) if args.root else _root_from_run(run_dir)
        errors_by, warnings_by = schema.validate_run(run_dir, root)
        count = len(list((run_dir / "findings").glob("*.json")))
    for name, errs in sorted(errors_by.items()):
        for e in errs:
            print(f"ERROR {name}: {e}")
    for name, warns in sorted(warnings_by.items()):
        for w in warns:
            print(f"WARN  {name}: {w}")
    print(f"{count} finding file(s) checked, {sum(map(len, errors_by.values()))} error(s)")
    return 1 if errors_by else 0


def _root_from_run(run_dir: Path) -> Path | None:
    if (run_dir / "run.json").is_file():
        return Path(workspace.load_run(run_dir)["project_root"])
    return None


def cmd_render(args) -> int:
    run_dir = workspace.resolve_run_dir(Path(args.run_dir))
    md, js = report.render(run_dir, args.draft)
    data = json.loads(js.read_text(encoding="utf-8"))
    print(f"wrote {md.as_posix()}")
    print(f"wrote {js.as_posix()}")
    print(data["summary"]["statement"])
    return 0


def cmd_run(args) -> int:
    run_dir = workspace.resolve_run_dir(Path(args.run_dir))
    run = workspace.load_run(run_dir)
    project_root = Path(run["project_root"])
    cwd = Path(args.cwd).resolve() if args.cwd else None
    if not args.command:
        raise ValueError("give the tool command after --, e.g. run <run-dir> -- forge test")
    argv = args.command
    record = tools.run(
        run_dir, project_root, argv, cwd, args.timeout, args.allow_fork, args.allow_project_build, run.get("tools")
    )
    log = (run_dir / record["output_file"]).read_text(encoding="utf-8").splitlines()
    print("\n".join(log[-args.tail :]))
    status = "timed out" if record["timed_out"] else f"exit {record['exit_code']}"
    print(
        f"\n{record['id']}: {' '.join(record['argv'])} -> {status} in {record['duration_ms'] / 1000:.1f}s "
        f"(full output: {record['output_file']})"
    )
    return 0


def cmd_sandbox(args) -> int:
    run_dir = workspace.resolve_run_dir(Path(args.run_dir))
    dest = tools.make_sandbox(Path(workspace.load_run(run_dir)["project_root"]), run_dir)
    print(dest.as_posix())
    return 0


def cmd_diff(args) -> int:
    summary = diffscan.diff_summary(Path(args.root), args.range)
    if args.out:
        workspace.write_json(Path(args.out), summary)
    print(json.dumps(summary, indent=2) if args.json else diffscan.format_text(summary))
    return 0


def cmd_import(args) -> int:
    run_dir = workspace.resolve_run_dir(Path(args.run_dir))
    data = adapters.load_json(Path(args.file))
    summary = adapters.import_contractmap(data) if args.kind == "contractmap" else adapters.import_slither(data)
    hints_dir = run_dir / "tool-hints"
    hints_dir.mkdir(exist_ok=True)
    workspace.write_json(hints_dir / f"{args.kind}.json", summary)
    print(adapters.format_hints(summary))
    return 0


def cmd_contractmap(args) -> int:
    run_dir = workspace.resolve_run_dir(Path(args.run_dir))
    if shutil.which("contractmap") is None:
        print("contractmap is not installed; continuing without it (see references/tool-integration.md).")
        return 0
    run = workspace.load_run(run_dir)
    out = run_dir / "tool-hints" / "contractmap-raw.json"
    out.parent.mkdir(exist_ok=True)
    record = tools.run(
        run_dir,
        Path(run["project_root"]),
        ["contractmap", "scan", run["target"], "--format", "json", "--output", str(out)],
        versions=run.get("tools"),
    )
    if record["exit_code"] != 0 or not out.is_file():
        print(f"contractmap run {record['id']} did not produce output; continuing without it.")
        return 0
    summary = adapters.import_contractmap(adapters.load_json(out))
    workspace.write_json(run_dir / "tool-hints" / "contractmap.json", summary)
    print(adapters.format_hints(summary))
    return 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="swarmsec.py", description=__doc__.splitlines()[0])
    sub = p.add_subparsers(dest="cmd", required=True)

    s = sub.add_parser("tools", help="detect optional security tools")
    s.add_argument("--json", action="store_true")
    s.set_defaults(func=cmd_tools)

    s = sub.add_parser("inventory", help="scan Solidity sources (lexical, read-only)")
    s.add_argument("path")
    s.add_argument("--json", action="store_true")
    s.add_argument("--include-vendored", action="store_true", help="also scan lib/ and node_modules/")
    s.add_argument("--out", help="write the JSON inventory to this file")
    s.set_defaults(func=cmd_inventory)

    s = sub.add_parser("init", help="create a run directory under <project>/.swarmsec-audit/runs/")
    s.add_argument("project")
    s.add_argument("--target", default=".", help="file or directory to audit, relative to the project")
    s.add_argument("--mode", default="audit", choices=workspace.MODES)
    s.add_argument("--diff", help="git range for diff-audit runs")
    s.add_argument("--include-vendored", action="store_true")
    s.set_defaults(func=cmd_init)

    s = sub.add_parser("validate", help="check findings against the schema and the source tree")
    s.add_argument("path", help="run directory, 'latest', or a single finding JSON file")
    s.add_argument("--root", help="project root used to check evidence locations")
    s.set_defaults(func=cmd_validate)

    s = sub.add_parser("render", help="write report.md and report.json for a run")
    s.add_argument("run_dir")
    s.add_argument("--draft", action="store_true", help="allow unverified candidates, clearly marked")
    s.set_defaults(func=cmd_render)

    s = sub.add_parser("run", help="run an allowed tool with a timeout and record the result")
    s.add_argument("run_dir")
    s.add_argument("--timeout", type=int, default=tools.DEFAULT_TIMEOUT)
    s.add_argument("--cwd", help="working directory (default: project root)")
    s.add_argument("--allow-fork", action="store_true", help="permit --fork-url; only with user approval")
    s.add_argument(
        "--allow-project-build",
        action="store_true",
        help="permit compiling through Hardhat/Truffle JS config; only with user approval",
    )
    s.add_argument("--tail", type=int, default=60, help="lines of output to print")
    s.set_defaults(func=cmd_run)

    s = sub.add_parser("sandbox", help="copy the project into the run directory for verification tests")
    s.add_argument("run_dir")
    s.set_defaults(func=cmd_sandbox)

    s = sub.add_parser("diff", help="security summary of a git diff over .sol files")
    s.add_argument("range", nargs="?", help="A...B, A..B, a commit, or empty for uncommitted changes")
    s.add_argument("--root", default=".")
    s.add_argument("--json", action="store_true")
    s.add_argument("--out")
    s.set_defaults(func=cmd_diff)

    s = sub.add_parser("import", help="import optional tool output as hints")
    s.add_argument("run_dir")
    s.add_argument("kind", choices=["contractmap", "slither"])
    s.add_argument("file")
    s.set_defaults(func=cmd_import)

    s = sub.add_parser("contractmap", help="run ContractMap if installed and import its map")
    s.add_argument("run_dir")
    s.set_defaults(func=cmd_contractmap)
    return p


def main(argv: list[str] | None = None) -> int:
    for stream in (sys.stdout, sys.stderr):
        stream.reconfigure(encoding="utf-8", errors="replace")
    argv = list(sys.argv[1:] if argv is None else argv)
    # Everything after the first `--` is the tool command for `run`, so options may come in any order.
    command: list[str] = []
    if "--" in argv:
        i = argv.index("--")
        argv, command = argv[:i], argv[i + 1 :]
    args = build_parser().parse_args(argv)
    args.command = command
    try:
        return args.func(args)
    except KNOWN_ERRORS as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
