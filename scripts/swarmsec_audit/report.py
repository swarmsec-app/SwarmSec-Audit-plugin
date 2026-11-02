"""Render a run directory into report.json and report.md."""

from __future__ import annotations

import re
import textwrap
from pathlib import Path
from string import Template

from . import __version__
from .redact import redact_obj, redact_text
from .schema import PUBLISHED, load_findings, load_tool_runs, resolve_in_root, validate_finding
from .tools import short_version
from .workspace import load_run, now, write_json

TEMPLATE = Path(__file__).resolve().parents[2] / "templates" / "report.md"
SEVERITIES = ["critical", "high", "medium", "low", "informational"]
NO_FINDINGS = "No substantiated findings in the reviewed scope."
DISCLAIMER = (
    "This report comes from an automated, model-assisted review. It is not a formal audit, "
    "and the absence of findings does not show that the code is safe."
)
TOOL_GAPS = {
    "slither": "Slither not installed: no static-analysis cross-check.",
    "forge": "Foundry not installed: no local test execution or reproduction.",
}
SOURCE_EXCERPT_LINES = 14
TOOL_RUN_FIELDS = (
    "id",
    "tool",
    "version",
    "command_class",
    "argv",
    "exit_code",
    "timed_out",
    "duration_ms",
    "network",
    "fork",
    "output_file",
    "output_truncated",
)


class RenderError(Exception):
    pass


def _order(f: dict) -> tuple:
    return SEVERITIES.index(f["severity"]), f["id"]


def build_report(run_dir: Path, draft: bool = False) -> dict:
    run = load_run(run_dir)
    project_root = Path(run["project_root"])
    tool_runs = load_tool_runs(run_dir)
    published, unresolved, candidates, dismissed, problems = [], [], [], [], []
    for path, data, parse_error in load_findings(run_dir):
        if parse_error:
            problems.append(f"{path.name}: {parse_error}")
            continue
        errors, _ = validate_finding(data, project_root if project_root.is_dir() else None, tool_runs)
        if errors:
            problems.append(f"{path.name}: " + "; ".join(errors))
            continue
        status = data["status"]
        if status in PUBLISHED:
            published.append(data)
        elif status == "unresolved":
            unresolved.append(data)
        elif status == "rejected":
            dismissed.append({"id": data["id"], "title": data["title"], "reason": data["verification"]["reason"]})
        else:
            candidates.append(data)
    if problems:
        raise RenderError("findings failed validation:\n  " + "\n  ".join(problems))
    if candidates and not draft:
        raise RenderError(
            f"{len(candidates)} finding(s) still have status 'candidate'. Verify them, or "
            "render with --draft to produce a clearly marked unverified draft."
        )

    counts = {s: sum(1 for f in published if f["severity"] == s) for s in SEVERITIES}
    if published:
        parts = ", ".join(f"{n} {s}" for s, n in counts.items() if n)
        statement = f"{len(published)} substantiated finding(s) in the reviewed scope ({parts})."
    else:
        statement = NO_FINDINGS
    gaps = list(run.get("coverage_gaps", []))
    mentioned = " ".join(gaps + run.get("limitations", [])).lower()
    gaps += [msg for tool, msg in TOOL_GAPS.items() if not run.get("tools", {}).get(tool) and tool not in mentioned]
    limitations = list(run.get("limitations", []))
    if any((f.get("reproduction") or {}).get("environment") == "fork-simulation" for f in published):
        limitations.append("Some reproductions ran on a local fork simulation; they are not live-chain results.")

    report = {
        "schema_version": "1.0",
        "generator": {"name": "swarmsec-audit", "version": __version__},
        "generated_at": now().isoformat(timespec="seconds"),
        "run_id": run["run_id"],
        "mode": run["mode"],
        "target": {
            "name": project_root.name,
            "path": run["target"],
            "revision": run["revision"],
            "diff_range": run.get("diff_range"),
        },
        "scope": run["scope"],
        "build": run["build"],
        "summary": {"statement": statement, "counts": counts},
        "findings": sorted(published, key=_order),
        "unresolved": sorted(unresolved, key=_order),
        "candidates": sorted(candidates, key=_order),
        "dismissed": sorted(dismissed, key=lambda d: d["id"]),
        "tool_runs": [{k: r[k] for k in TOOL_RUN_FIELDS} for _, r in sorted(tool_runs.items())],
        "tools_detected": dict(sorted(run.get("tools", {}).items())),
        "coverage_gaps": gaps,
        "limitations": limitations,
        "disclaimer": DISCLAIMER,
    }
    return redact_obj(report, project_root)


def _loc(loc: dict) -> str:
    start, end = loc["start_line"], loc["end_line"]
    return f"{loc['file']}:{start}" if start == end else f"{loc['file']}:{start}-{end}"


def _excerpt(ev: dict, project_root: Path | None) -> str | None:
    """The cited lines from the checkout, dedented. Falls back to the recorded snippet."""
    loc = ev.get("location")
    path = resolve_in_root(project_root, loc["file"]) if loc and project_root else None
    if path is not None and path.is_file():
        lines = path.read_text(encoding="utf-8", errors="replace").splitlines()[loc["start_line"] - 1 : loc["end_line"]]
        if len(lines) > SOURCE_EXCERPT_LINES:
            lines = [*lines[:SOURCE_EXCERPT_LINES], "// ..."]
        return textwrap.dedent("\n".join(lines)).strip("\n")
    return textwrap.dedent(ev["snippet"]).strip("\n") if ev.get("snippet") else None


def _first_location(f: dict) -> str:
    loc = next((ev["location"] for ev in f["evidence"] if ev.get("location")), None)
    return _loc(loc) if loc else f["affected_components"][0]["file"]


def _anchor(f: dict) -> str:
    """GitHub-style anchor of the '### SWARM-NNN: title' heading."""
    return re.sub(r"[^\w\- ]", "", f"{f['id']}: {f['title']}".lower()).replace(" ", "-")


def _finding_md(f: dict, project_root: Path | None) -> str:
    affected = ", ".join(
        f"`{c['contract']}.{c['function']}`" if c["function"] else f"`{c['contract']}`"
        for c in f["affected_components"]
    )
    meta = [
        f"**{f['severity'].capitalize()}**",
        f"{f['confidence']} confidence",
        f["status"],
        f["category"],
        f"attacker: {f['attacker']}",
    ]
    if f.get("diff_attribution") and f["diff_attribution"] != "not-applicable":
        meta.append(f"{f['diff_attribution']} by this change")
    out = [f"### {f['id']}: {f['title']}", "", " · ".join(meta), "", f"Affected: {affected}", "", f["summary"]]
    out += ["", f"**Impact.** {f['impact']}"]
    if f["preconditions"]:
        out += ["", "**Preconditions.**", *[f"- {p}" for p in f["preconditions"]]]
    out += ["", "**Evidence.**", ""]
    for i, ev in enumerate(f["evidence"], 1):
        where = f"`{_loc(ev['location'])}` " if ev.get("location") else ""
        run = f" (tool run {ev['tool_run']})" if ev.get("tool_run") else ""
        out.append(f"{i}. {where}*{ev['kind']}*: {ev['description']}{run}")
        code = _excerpt(ev, project_root)
        if code:
            out += ["", "   ```solidity", *[f"   {ln}" if ln else "" for ln in code.splitlines()], "   ```", ""]
    r = f.get("reproduction")
    if r and r["result"] != "not-run":
        run = f", tool run {r['tool_run']}" if r.get("tool_run") else ""
        out += ["", f"**Reproduction** ({r['method']}, {r['environment']}{run}): {r['result']}."]
        if r["command"]:
            out += ["", f"`{r['command']}`"]
        if r["assertions"]:
            out += ["", "Assertions:", *[f"- {a}" for a in r["assertions"]]]
    v = f.get("verification")
    if v:
        out += ["", f"**Verification** by {v['verifier']}: {v['reason']}"]
        if v["falsification_attempts"]:
            out += ["", "Attempts to falsify:", *[f"- {a}" for a in v["falsification_attempts"]]]
    out += ["", f"**Remediation.** {f['remediation']}"]
    if f["regression_test"]:
        out += ["", f"**Regression test.** {f['regression_test']}"]
    if f["limitations"]:
        out += ["", "**Limitations.**", *[f"- {x}" for x in f["limitations"]]]
    if f.get("related"):
        out += ["", f"Related: {', '.join(f['related'])}"]
    return re.sub(r"\n{3,}", "\n\n", "\n".join(out))


def _context(md: str) -> str:
    """Nest context.md under '## Protocol context': drop a leading title and demote other headings."""
    md = re.sub(r"\A#{1,3} [^\n]*\n+", "", md.strip())
    return re.sub(r"^(#{1,4}) ", lambda m: "#" * (len(m.group(1)) + 2) + " ", md, flags=re.M)


def _overview(report: dict) -> str:
    rows = [(f, "") for f in report["findings"] + report["unresolved"]]
    rows += [(f, " (unverified draft)") for f in report["candidates"]]
    if not rows:
        return ""
    lines = ["| ID | Severity | Status | Title | Location |", "|---|---|---|---|---|"]
    lines += [
        f"| [{f['id']}](#{_anchor(f)}) | {f['severity']} | {f['status']}{tag} | {f['title']} | `{_first_location(f)}` |"
        for f, tag in rows
    ]
    return "\n".join(lines)


def _tool_runs_md(runs: list[dict]) -> str:
    if not runs:
        return "No tools were executed."
    lines = ["| ID | Command | Version | Result | Time | Network |", "|---|---|---|---|---|---|"]
    for r in runs:
        result = "timed out" if r["timed_out"] else f"exit {r['exit_code']}"
        network = "fork" if r["fork"] else "possible" if r["network"] else "offline"
        lines.append(
            f"| {r['id']} | `{' '.join(r['argv'])}` | {short_version(r['version']) or 'unknown'} | {result} | "
            f"{r['duration_ms'] / 1000:.1f}s | {network} |"
        )
    return "\n".join(lines)


def render_markdown(report: dict, context_md: str, project_root: Path | None = None) -> str:
    t = report["target"]
    rev = t["revision"]
    revision = (
        f"`{rev['commit'][:12]}`" + (" (uncommitted changes)" if rev["dirty"] else "")
        if rev["commit"]
        else "not a git checkout"
    )
    if t["diff_range"]:
        revision += f", diff `{t['diff_range']}`"
    b = report["build"]
    counts = " · ".join(f"{n} {s}" for s, n in report["summary"]["counts"].items() if n)
    scope = [f"- included: `{p}`" for p in report["scope"]["included"]]
    scope += [f"- excluded: `{e['path']}` ({e['reason']})" for e in report["scope"]["excluded"]]
    findings = "\n\n".join(_finding_md(f, project_root) for f in report["findings"]) or "None."
    if report["candidates"]:
        findings += "\n\n### Unverified candidates (draft)\n\nThese have not been verified and are not findings.\n\n"
        findings += "\n\n".join(_finding_md(f, project_root) for f in report["candidates"])
    unresolved = "\n\n".join(_finding_md(f, project_root) for f in report["unresolved"]) or "None."
    dismissed = "None recorded."
    if report["dismissed"]:
        dismissed = "| ID | Hypothesis | Why it was dismissed |\n|---|---|---|\n" + "\n".join(
            f"| {d['id']} | {d['title']} | {d['reason']} |" for d in report["dismissed"]
        )
    found = [f"{k} {short_version(v)}" for k, v in report["tools_detected"].items() if v]
    absent = [k for k, v in report["tools_detected"].items() if not v]
    tools = (
        "Tools: " + (", ".join(found) or "none detected") + (f"; not installed: {', '.join(absent)}" if absent else "")
    )
    coverage = [f"- {g}" for g in report["coverage_gaps"]] + [f"- {x}" for x in report["limitations"]]
    coverage.append(f"- {tools}" if report["tools_detected"] else "- Tools: not recorded")
    md = Template(TEMPLATE.read_text(encoding="utf-8")).substitute(
        name=t["name"],
        disclaimer=report["disclaimer"],
        run_id=report["run_id"],
        mode=report["mode"],
        revision=revision,
        generated_at=report["generated_at"],
        build=f"{b['system'] or 'unknown'}, compiler {b['compiler'] or 'unknown'}, {b['status']}",
        statement=report["summary"]["statement"],
        counts=counts or "No findings at any severity.",
        overview=_overview(report),
        scope="\n".join(scope),
        context=_context(context_md) or "Not recorded.",
        findings=findings,
        unresolved=unresolved,
        dismissed=dismissed,
        tool_runs=_tool_runs_md(report["tool_runs"]),
        coverage="\n".join(coverage),
    )
    return re.sub(r"\n{3,}", "\n\n", md)


def render(run_dir: Path, draft: bool = False) -> tuple[Path, Path]:
    report = build_report(run_dir, draft)
    context_path = run_dir / "context.md"
    context_md = context_path.read_text(encoding="utf-8") if context_path.is_file() else ""
    project_root = Path(load_run(run_dir)["project_root"])
    md = render_markdown(report, context_md, project_root if project_root.is_dir() else None)
    write_json(run_dir / "report.json", report)
    (run_dir / "report.md").write_text(redact_text(md, project_root), encoding="utf-8")
    return run_dir / "report.md", run_dir / "report.json"
