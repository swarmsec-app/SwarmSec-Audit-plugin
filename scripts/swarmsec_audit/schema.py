"""Finding validation: a JSON Schema subset validator plus rules a schema cannot express.

The runtime stays standard-library only. tests/test_schema.py checks that the schema files are
valid Draft 2020-12 and that this validator agrees with the reference implementation on samples.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

SCHEMA_DIR = Path(__file__).resolve().parents[2] / "schemas"
PUBLISHED = {"reproduced", "supported"}

_TYPES = {
    "object": lambda v: isinstance(v, dict),
    "array": lambda v: isinstance(v, list),
    "string": lambda v: isinstance(v, str),
    "integer": lambda v: isinstance(v, int) and not isinstance(v, bool),
    "number": lambda v: isinstance(v, (int, float)) and not isinstance(v, bool),
    "boolean": lambda v: isinstance(v, bool),
    "null": lambda v: v is None,
}


def load_schema(name: str) -> dict:
    return json.loads((SCHEMA_DIR / name).read_text(encoding="utf-8"))


def validate(instance, schema: dict, root: dict | None = None, path: str = "$") -> list[str]:
    """Validate against the keywords the bundled schemas use. Unknown keywords are ignored."""
    root = root if root is not None else schema
    if "$ref" in schema:
        ref = schema["$ref"]
        if ref.startswith("#/$defs/"):
            return validate(instance, root["$defs"][ref.removeprefix("#/$defs/")], root, path)
        external = load_schema(ref)
        return validate(instance, external, external, path)
    if "anyOf" in schema:
        branches = [validate(instance, s, root, path) for s in schema["anyOf"]]
        if all(branches):
            return [f"{path}: does not match any allowed form ({'; '.join(b[0] for b in branches)})"]
        return []

    errors: list[str] = []
    if "const" in schema and instance != schema["const"]:
        return [f"{path}: must be {schema['const']!r}"]
    if "enum" in schema and instance not in schema["enum"]:
        return [f"{path}: {instance!r} is not one of {schema['enum']}"]
    if "type" in schema:
        types = schema["type"] if isinstance(schema["type"], list) else [schema["type"]]
        if not any(_TYPES[t](instance) for t in types):
            return [f"{path}: expected {' or '.join(types)}, got {type(instance).__name__}"]

    if isinstance(instance, str):
        if len(instance) < schema.get("minLength", 0):
            errors.append(f"{path}: shorter than {schema['minLength']} characters")
        if "maxLength" in schema and len(instance) > schema["maxLength"]:
            errors.append(f"{path}: longer than {schema['maxLength']} characters")
        if "pattern" in schema and not re.search(schema["pattern"], instance):
            errors.append(f"{path}: {instance!r} does not match {schema['pattern']}")
    if _TYPES["number"](instance) and "minimum" in schema and instance < schema["minimum"]:
        errors.append(f"{path}: below minimum {schema['minimum']}")
    if isinstance(instance, list):
        if len(instance) < schema.get("minItems", 0):
            errors.append(f"{path}: needs at least {schema['minItems']} item(s)")
        if "items" in schema:
            for i, item in enumerate(instance):
                errors += validate(item, schema["items"], root, f"{path}[{i}]")
    if isinstance(instance, dict):
        for key in schema.get("required", []):
            if key not in instance:
                errors.append(f"{path}: missing required field '{key}'")
        props = schema.get("properties", {})
        extra = schema.get("additionalProperties", True)
        for key, value in instance.items():
            if key in props:
                errors += validate(value, props[key], root, f"{path}.{key}")
            elif extra is False:
                errors.append(f"{path}: unexpected field '{key}'")
            elif isinstance(extra, dict):
                errors += validate(value, extra, root, f"{path}.{key}")
    return errors


def resolve_in_root(project_root: Path, rel: str) -> Path | None:
    """Resolve a project-relative path, refusing anything that escapes the project root."""
    rel = rel.replace("\\", "/")
    if re.match(r"^[A-Za-z]:|^/", rel):
        return None
    candidate = (project_root / rel).resolve()
    try:
        candidate.relative_to(project_root.resolve())
    except ValueError:
        return None
    return candidate


def _norm(text: str) -> str:
    return " ".join(text.split())


def check_evidence(finding: dict, project_root: Path) -> list[str]:
    """Each cited location must exist in the checkout, and a quoted snippet must match those lines."""
    errors = []
    for i, ev in enumerate(finding.get("evidence", [])):
        loc = ev.get("location")
        if not loc:
            if ev.get("kind") == "source":
                errors.append(f"evidence[{i}]: source evidence needs a location")
            continue
        path = resolve_in_root(project_root, loc["file"])
        where = f"evidence[{i}] {loc['file']}:{loc['start_line']}-{loc['end_line']}"
        if path is None:
            errors.append(f"{where}: path is outside the project root")
            continue
        if not path.is_file():
            errors.append(f"{where}: file not found")
            continue
        lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
        if loc["start_line"] > loc["end_line"] or loc["end_line"] > len(lines):
            errors.append(f"{where}: line range outside file ({len(lines)} lines)")
            continue
        snippet = ev.get("snippet")
        if snippet and _norm(snippet) not in _norm("\n".join(lines[loc["start_line"] - 1 : loc["end_line"]])):
            errors.append(f"{where}: snippet does not match the cited lines")
    for i, comp in enumerate(finding.get("affected_components", [])):
        path = resolve_in_root(project_root, comp["file"])
        if path is None or not path.is_file():
            errors.append(f"affected_components[{i}]: {comp['file']} not found in project")
    return errors


def actor(name: str) -> str:
    """Agent or skill identity behind a free-text name: 'swarmsec-audit:diff-audit (manual)' -> 'diff-audit'."""
    name = name.strip().lower().removeprefix("swarmsec-audit:")
    return re.match(r"[a-z0-9_-]*", name).group(0)


def check_rules(finding: dict, tool_runs: dict[str, dict]) -> tuple[list[str], list[str]]:
    """Cross-field rules. Returns (errors, warnings)."""
    errors, warnings = [], []
    status = finding["status"]
    repro = finding.get("reproduction")
    verification = finding.get("verification")

    # Publishing needs an independent check; dismissing your own hypothesis only lowers what is claimed.
    if status in PUBLISHED:
        if not verification:
            errors.append(f"status '{status}' needs a verification record")
        elif actor(verification["verifier"]) == actor(finding["discovered_by"]):
            errors.append("verifier is the same agent that discovered the finding; verification must be independent")
    if status == "reproduced":
        if not repro or repro["result"] != "demonstrated":
            errors.append("status 'reproduced' needs reproduction.result 'demonstrated'")
        elif repro["method"] != "manual-trace":
            run = tool_runs.get(repro.get("tool_run") or "")
            if run is None:
                errors.append("status 'reproduced' needs reproduction.tool_run pointing at a recorded tool run")
            elif run.get("exit_code") is None or run.get("timed_out"):
                errors.append(f"tool run {repro['tool_run']} did not complete")
        else:
            errors.append("a manual trace is not a reproduction; use status 'supported'")
        if repro and repro["environment"] == "fork-simulation":
            warnings.append(
                "reproduced on a fork simulation only; the report must not present it as a live-chain result"
            )
    if repro and repro.get("tool_run") and repro["tool_run"] not in tool_runs and repro["method"] != "manual-trace":
        errors.append(f"reproduction.tool_run {repro['tool_run']} has no record in tool-runs/")
    for i, ev in enumerate(finding["evidence"]):
        if ev.get("tool_run") and ev["tool_run"] not in tool_runs:
            errors.append(f"evidence[{i}].tool_run {ev['tool_run']} has no record in tool-runs/")
    if status in PUBLISHED:
        if not finding["remediation"].strip():
            errors.append("published findings need a remediation")
        if not any(ev["kind"] != "reasoning" for ev in finding["evidence"]):
            errors.append("published findings need evidence beyond reasoning (source, call path, test or tool)")
        if finding["severity"] in ("critical", "high") and finding["confidence"] == "low":
            warnings.append("high-impact finding with low confidence: consider status 'unresolved'")
    if status == "rejected" and not verification:
        errors.append("rejected hypotheses need the reason in verification.reason")
    return errors, warnings


def load_tool_runs(run_dir: Path) -> dict[str, dict]:
    runs = {}
    for p in sorted((run_dir / "tool-runs").glob("TR-*.json")):
        data = json.loads(p.read_text(encoding="utf-8"))
        runs[data["id"]] = data
    return runs


def validate_finding(
    finding: dict, project_root: Path | None, tool_runs: dict[str, dict]
) -> tuple[list[str], list[str]]:
    errors = validate(finding, load_schema("finding.schema.json"))
    if errors:
        return errors, []
    rule_errors, warnings = check_rules(finding, tool_runs)
    errors += rule_errors
    if project_root is not None:
        errors += check_evidence(finding, project_root)
    return errors, warnings


def load_findings(run_dir: Path) -> list[tuple[Path, dict | None, str | None]]:
    out = []
    for p in sorted((run_dir / "findings").glob("*.json")):
        try:
            out.append((p, json.loads(p.read_text(encoding="utf-8")), None))
        except json.JSONDecodeError as exc:
            out.append((p, None, f"invalid JSON: {exc}"))
    return out


def validate_run(run_dir: Path, project_root: Path | None) -> tuple[dict[str, list[str]], dict[str, list[str]]]:
    """Validate every finding in a run directory. Returns (errors, warnings) keyed by file name."""
    tool_runs = load_tool_runs(run_dir)
    errors: dict[str, list[str]] = {}
    warnings: dict[str, list[str]] = {}
    seen: dict[str, str] = {}
    for path, data, parse_error in load_findings(run_dir):
        if parse_error:
            errors[path.name] = [parse_error]
            continue
        errs, warns = validate_finding(data, project_root, tool_runs)
        fid = data.get("id") if isinstance(data, dict) else None
        if fid in seen:
            errs.append(f"duplicate id {fid} (also in {seen[fid]})")
        elif fid:
            seen[fid] = path.name
        if errs:
            errors[path.name] = errs
        if warns:
            warnings[path.name] = warns
    return errors, warnings
