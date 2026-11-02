import json

import pytest

from conftest import ROOT, write_finding
from swarmsec_audit import report, workspace
from swarmsec_audit.redact import redact_text


def test_no_findings_statement_and_tool_gap(run_dir, monkeypatch):
    monkeypatch.setenv("SOURCE_DATE_EPOCH", "1767225600")
    md, js = report.render(run_dir)
    data = json.loads(js.read_text())
    assert data["summary"]["statement"] == report.NO_FINDINGS
    assert any("Slither not installed" in g for g in data["coverage_gaps"])
    text = md.read_text()
    assert "No substantiated findings in the reviewed scope." in text
    assert "not a formal audit" in text
    assert "secure" not in text.lower()


def test_rendering_is_deterministic(run_dir, finding, monkeypatch):
    monkeypatch.setenv("SOURCE_DATE_EPOCH", "1767225600")
    write_finding(run_dir, finding)
    first = [p.read_bytes() for p in report.render(run_dir)]
    second = [p.read_bytes() for p in report.render(run_dir)]
    assert first == second


def test_status_routing_and_ordering(run_dir, finding):
    low = dict(finding, id="SWARM-002", severity="low", title="Low severity ordering check")
    rejected = dict(finding, id="SWARM-003", status="rejected", title="Rejected hypothesis example")
    unresolved = dict(
        finding, id="SWARM-004", status="unresolved", verification=None, title="Unresolved hypothesis example"
    )
    for f in (low, finding, rejected, unresolved):
        write_finding(run_dir, f)
    data = report.build_report(run_dir)
    assert [f["id"] for f in data["findings"]] == ["SWARM-001", "SWARM-002"]
    assert [d["id"] for d in data["dismissed"]] == ["SWARM-003"]
    assert [f["id"] for f in data["unresolved"]] == ["SWARM-004"]
    assert data["summary"]["counts"]["high"] == 1


def test_candidates_block_final_report(run_dir, finding):
    write_finding(run_dir, dict(finding, status="candidate", verification=None))
    with pytest.raises(report.RenderError, match="candidate"):
        report.build_report(run_dir)
    md, _ = report.render(run_dir, draft=True)
    assert "Unverified candidates (draft)" in md.read_text()


def test_invalid_findings_block_report(run_dir, finding):
    write_finding(run_dir, dict(finding, evidence=[]))
    with pytest.raises(report.RenderError, match="validation"):
        report.build_report(run_dir)


def test_report_json_matches_schema(run_dir, finding):
    jsonschema = pytest.importorskip("jsonschema")
    referencing = pytest.importorskip("referencing")
    write_finding(run_dir, finding)
    _, js = report.render(run_dir)
    finding_schema = json.loads((ROOT / "schemas" / "finding.schema.json").read_text())
    report_schema = json.loads((ROOT / "schemas" / "report.schema.json").read_text())
    registry = referencing.Registry().with_resource(
        "finding.schema.json", referencing.Resource.from_contents(finding_schema)
    )
    jsonschema.Draft202012Validator(report_schema, registry=registry).validate(json.loads(js.read_text()))


def test_secrets_and_paths_redacted(run_dir, finding):
    run = workspace.load_run(run_dir)
    run["limitations"] = [
        "fork via https://eth-mainnet.g.alchemy.com/v2/abcDEF123456 failed",
        f"see {run['project_root']}/src/RewardToken.sol",
        "PRIVATE_KEY=0xdeadbeef in .env was ignored",
    ]
    workspace.write_json(run_dir / "run.json", run)
    write_finding(run_dir, finding)
    md, js = report.render(run_dir)
    for text in (md.read_text(), js.read_text()):
        assert "abcDEF123456" not in text
        assert "0xdeadbeef" not in text
        assert run["project_root"] not in text
        assert "<project>/src/RewardToken.sol" in text


@pytest.mark.parametrize(
    "raw, leaked",
    [
        ("https://user:hunter2@rpc.example.org", "hunter2"),
        ("https://mainnet.infura.io/v3/0123456789abcdef", "0123456789abcdef"),
        ("https://rpc.example.org/?apikey=SECRETVALUE", "SECRETVALUE"),
        ("--private-key 0xac0974bec39a17e36ba4a6b4d238ff944bacb478cbed5efcae784d7bf4f2ff80", "0xac0974bec"),
        ("Authorization: Bearer abcdefghijklmnop", "abcdefghijklmnop"),
    ],
)
def test_redaction_rules(raw, leaked):
    assert leaked not in redact_text(raw)


def test_latest_resolution(run_dir):
    assert workspace.resolve_run_dir(run_dir.parent / "latest") == run_dir
    assert workspace.resolve_run_dir(run_dir.parents[2]) == run_dir
