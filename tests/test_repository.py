"""Consistency checks across the plugin's manifests, skills, agents, references and fixtures."""

import json
import re

import pytest

from conftest import FIXTURES, ROOT
from swarmsec_audit import __version__, solscan

SKILLS = sorted(p.parent.name for p in (ROOT / "skills").glob("*/SKILL.md"))
AGENTS = sorted(p.stem for p in (ROOT / "agents").glob("*.md"))
WRITERS = {"invariant-designer", "finding-verifier", "report-editor"}
MANIFEST = json.loads((FIXTURES / "manifest.json").read_text(encoding="utf-8"))


def frontmatter(path):
    text = path.read_text(encoding="utf-8")
    m = re.match(r"^---\n(.*?)\n---\n(.*)$", text, re.S)
    assert m, f"{path} has no frontmatter"
    fields = {}
    for line in m.group(1).splitlines():
        key, _, value = line.partition(":")
        fields[key.strip()] = value.strip().strip('"')
    return fields, m.group(2)


def test_manifests_agree():
    plugin = json.loads((ROOT / ".claude-plugin" / "plugin.json").read_text())
    market = json.loads((ROOT / ".claude-plugin" / "marketplace.json").read_text())
    assert plugin["name"] == "swarmsec-audit"
    assert plugin["version"] == __version__
    assert market["name"] == "swarmsec-security"
    entry = market["plugins"][0]
    assert entry["name"] == plugin["name"] and entry["source"] == "./"
    assert "version" not in entry


def test_expected_components_present():
    assert SKILLS == ["attack-surface", "audit", "defi-audit", "diff-audit", "invariants", "report", "verify"]
    assert AGENTS == [
        "audit-context",
        "defi-economics-reviewer",
        "finding-verifier",
        "invariant-designer",
        "report-editor",
        "solidity-reviewer",
    ]


@pytest.mark.parametrize("skill", SKILLS)
def test_skill_frontmatter(skill):
    path = ROOT / "skills" / skill / "SKILL.md"
    fields, body = frontmatter(path)
    assert fields["name"] == skill
    assert 80 < len(fields["description"]) < 1536
    assert fields.get("argument-hint")
    assert "$ARGUMENTS" in body
    assert len(body.splitlines()) < 200
    assert re.search(r"\bdata\b", body), "skill must say repository content is data"


@pytest.mark.parametrize("agent", AGENTS)
def test_agent_frontmatter(agent):
    fields, body = frontmatter(ROOT / "agents" / f"{agent}.md")
    assert fields["name"] == agent
    assert fields["model"] == "inherit"
    assert not {"hooks", "mcpServers", "permissionMode"} & set(fields)
    tools = {t.strip() for t in fields["tools"].split(",")}
    assert ("Write" in tools or "Edit" in tools) == (agent in WRITERS)
    assert "Agent" not in tools, "specialists must not spawn agents"
    assert re.search(r"\bdata\b", body)


def test_referenced_paths_exist():
    pattern = re.compile(r"\$\{CLAUDE_PLUGIN_ROOT\}/([\w./-]+)")
    for path in [*ROOT.glob("skills/*/SKILL.md"), *ROOT.glob("agents/*.md"), *ROOT.glob("references/*.md")]:
        for rel in pattern.findall(path.read_text(encoding="utf-8")):
            assert (ROOT / rel.rstrip(".")).exists(), f"{path.name} references missing {rel}"


def test_agents_referenced_by_skills_exist():
    for path in ROOT.glob("skills/*/SKILL.md"):
        for name in re.findall(r"swarmsec-audit:([\w-]+)", path.read_text(encoding="utf-8")):
            assert name in AGENTS, f"{path.parent.name} references unknown agent {name}"


def fixture_dirs():
    out = []
    for p in sorted(FIXTURES.iterdir()):
        if p.is_dir():
            out.append(p.name)
    return out


def test_manifest_covers_every_fixture():
    assert sorted(f["id"] for f in MANIFEST["fixtures"]) == fixture_dirs()
    assert {f["case"] for f in MANIFEST["fixtures"]} == set(range(1, 17))


@pytest.mark.parametrize("fx", MANIFEST["fixtures"], ids=lambda f: f["id"])
def test_manifest_locations_point_at_code(fx):
    base = FIXTURES / fx["id"] / (fx["diff"]["head"] if "diff" in fx else "")
    for exp in fx["expected"]:
        loc = exp["location"]
        sf = solscan.scan_source((base / loc["file"]).read_text(encoding="utf-8"), loc["file"])
        contract, _, fn = exp["function"].partition(".")
        c = next(c for c in sf.contracts if c.name == contract)
        span = c.location if not fn else next(f.location for f in c.functions if f.name == fn)
        assert span.start_line <= loc["line"] <= span.end_line, (exp["key"], loc)
    if "poc" in fx:
        assert (ROOT / fx["poc"]).is_file()


def test_fixture_sources_do_not_leak_ground_truth():
    banned = re.compile(r"vulnerab|exploit|insecure|\bbug\b|SWARM-|ground.truth|patched", re.I)
    for sol in FIXTURES.rglob("*.sol"):
        assert not banned.search(sol.read_text(encoding="utf-8")), sol
    for fx in MANIFEST["fixtures"]:
        if fx["kind"] in ("vulnerable", "diff", "injection"):
            for sol in (FIXTURES / fx["id"]).rglob("*.sol"):
                assert not re.search(r"attack", sol.read_text(encoding="utf-8"), re.I), sol


EXAMPLE_FIXTURES = {
    "staking-rewards-audit": "10-staking-rewards-desync",
    "vault-defi-audit": "04-vault-donation",
    "oracle-diff-audit": "15-diff-caller-break/v2",
}


@pytest.mark.parametrize("example, fixture", sorted(EXAMPLE_FIXTURES.items()))
def test_example_findings_validate_against_their_fixture(example, fixture):
    from swarmsec_audit import schema

    run_dir = ROOT / "examples" / example
    tool_runs = schema.load_tool_runs(run_dir)
    files = sorted((run_dir / "findings").glob("*.json"))
    assert files
    for path in files:
        errors, _ = schema.validate_finding(json.loads(path.read_text(encoding="utf-8")), FIXTURES / fixture, tool_runs)
        assert errors == [], (path.name, errors)
