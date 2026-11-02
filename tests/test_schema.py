import json

import pytest

from conftest import ROOT, write_finding
from swarmsec_audit import schema


def errors_for(finding, project=None, tool_runs=None):
    return schema.validate_finding(finding, project, tool_runs or {})[0]


def test_valid_finding_passes(finding, project):
    assert errors_for(finding, project) == []


def test_empty_evidence_rejected(finding):
    finding["evidence"] = []
    assert any("at least 1" in e for e in errors_for(finding))


def test_reasoning_only_evidence_cannot_be_published(finding):
    finding["evidence"] = [{"kind": "reasoning", "description": "It looks unsafe to me."}]
    assert any("beyond reasoning" in e for e in errors_for(finding))


def test_self_verification_rejected(finding):
    finding["verification"]["verifier"] = finding["discovered_by"]
    assert any("independent" in e for e in errors_for(finding))


def test_reproduced_needs_recorded_tool_run(finding):
    finding["status"] = "reproduced"
    finding["reproduction"] = {
        "method": "foundry-test",
        "command": "forge test",
        "test_file": None,
        "tool_run": "TR-001",
        "result": "demonstrated",
        "environment": "local",
        "assertions": ["attacker balance == 1e24"],
    }
    assert any("no record" in e or "recorded tool run" in e for e in errors_for(finding))
    ok_run = {"TR-001": {"id": "TR-001", "exit_code": 0, "timed_out": False}}
    assert errors_for(finding, tool_runs=ok_run) == []
    timed_out = {"TR-001": {"id": "TR-001", "exit_code": None, "timed_out": True}}
    assert any("did not complete" in e for e in errors_for(finding, tool_runs=timed_out))


def test_manual_trace_is_not_a_reproduction(finding):
    finding["status"] = "reproduced"
    finding["reproduction"] = {
        "method": "manual-trace",
        "command": "",
        "test_file": None,
        "tool_run": None,
        "result": "demonstrated",
        "environment": "none",
        "assertions": [],
    }
    assert any("manual trace" in e for e in errors_for(finding))


def test_fork_reproduction_warns(finding):
    finding["status"] = "reproduced"
    finding["reproduction"] = {
        "method": "fork-test",
        "command": "forge test --fork-url <rpc>",
        "test_file": None,
        "tool_run": "TR-001",
        "result": "demonstrated",
        "environment": "fork-simulation",
        "assertions": ["x"],
    }
    _, warnings = schema.validate_finding(finding, None, {"TR-001": {"exit_code": 0, "timed_out": False}})
    assert any("fork" in w for w in warnings)


def test_rejected_needs_reason_but_not_independence(finding):
    finding["status"] = "rejected"
    finding["verification"] = None
    assert errors_for(finding)
    finding["verification"] = {
        "verifier": "solidity-reviewer",
        "reason": "Guarded by onlyOwner at line 31.",
        "falsification_attempts": [],
    }
    assert errors_for(finding) == []


def test_evidence_lines_and_snippet_checked(finding, project):
    finding["evidence"][0]["location"]["end_line"] = 9999
    assert any("outside file" in e for e in errors_for(finding, project))
    finding["evidence"][0]["location"]["end_line"] = 34
    finding["evidence"][0]["snippet"] = "function setMinter(address newMinter) external onlyOwner {"
    assert any("snippet does not match" in e for e in errors_for(finding, project))


@pytest.mark.parametrize("bad", ["../../etc/passwd", "C:/Windows/win.ini", "/etc/passwd", "..\\..\\secret.sol"])
def test_evidence_cannot_escape_project(finding, project, bad):
    finding["evidence"][0]["location"]["file"] = bad
    assert any("outside the project" in e for e in errors_for(finding, project))


def test_windows_separators_accepted(finding, project):
    finding["evidence"][0]["location"]["file"] = "src\\RewardToken.sol"
    assert errors_for(finding, project) == []


def test_run_validation_reports_bad_json_and_duplicates(run_dir, finding):
    write_finding(run_dir, finding)
    (run_dir / "findings" / "broken.json").write_text("{not json", encoding="utf-8")
    dup = dict(finding)
    (run_dir / "findings" / "copy.json").write_text(json.dumps(dup), encoding="utf-8")
    errors, _ = schema.validate_run(run_dir, None)
    assert "invalid JSON" in errors["broken.json"][0]
    assert any("duplicate id" in e for e in errors.get("copy.json", []) + errors.get("SWARM-001.json", []))


def test_schema_files_agree_with_reference_validator(finding):
    jsonschema = pytest.importorskip("jsonschema")
    referencing = pytest.importorskip("referencing")
    finding_schema = json.loads((ROOT / "schemas" / "finding.schema.json").read_text())
    report_schema = json.loads((ROOT / "schemas" / "report.schema.json").read_text())
    jsonschema.Draft202012Validator.check_schema(finding_schema)
    jsonschema.Draft202012Validator.check_schema(report_schema)
    validator = jsonschema.Draft202012Validator(finding_schema)
    samples = [finding]
    for mutate in (
        lambda f: f.update(severity="severe"),
        lambda f: f.update(evidence=[]),
        lambda f: f.update(id="BUG-1"),
        lambda f: f.update(extra=1),
        lambda f: f.update(reproduction={"method": "foundry-test"}),
        lambda f: f.pop("impact"),
    ):
        bad = json.loads(json.dumps(finding))
        mutate(bad)
        samples.append(bad)
    for sample in samples:
        assert validator.is_valid(sample) == (schema.validate(sample, finding_schema) == []), sample
    registry = referencing.Registry().with_resource(
        "finding.schema.json", referencing.Resource.from_contents(finding_schema)
    )
    jsonschema.Draft202012Validator(report_schema, registry=registry)


def test_self_verification_detected_through_name_variants(finding):
    finding["discovered_by"] = "swarmsec-audit:diff-audit"
    finding["verification"]["verifier"] = "swarmsec-audit:diff-audit (manual trace, no Foundry test run)"
    assert any("independent" in e for e in errors_for(finding))
    finding["verification"]["verifier"] = "finding-verifier"
    assert errors_for(finding) == []
