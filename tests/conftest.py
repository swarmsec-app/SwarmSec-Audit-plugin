import copy
import json
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
FIXTURES = ROOT / "tests" / "fixtures"
sys.path.insert(0, str(ROOT / "scripts"))

from swarmsec_audit import workspace  # noqa: E402

BASE_FINDING = {
    "schema_version": "1.0",
    "id": "SWARM-001",
    "title": "Anyone can become minter",
    "category": "access-control",
    "severity": "high",
    "confidence": "high",
    "status": "supported",
    "summary": "setMinter has no caller check, so any account can make itself the minter.",
    "impact": "Unlimited minting dilutes every holder.",
    "attacker": "unprivileged",
    "preconditions": [],
    "affected_components": [{"file": "src/RewardToken.sol", "contract": "RewardToken", "function": "setMinter"}],
    "evidence": [
        {
            "kind": "source",
            "description": "setMinter writes minter without checking msg.sender.",
            "location": {"file": "src/RewardToken.sol", "start_line": 31, "end_line": 34},
            "snippet": "function setMinter(address newMinter) external {\n        minter = newMinter;",
        }
    ],
    "reproduction": None,
    "verification": {
        "verifier": "finding-verifier",
        "reason": "No modifier or sender check on the path.",
        "falsification_attempts": ["Looked for an inherited guard; there is none."],
    },
    "discovered_by": "solidity-reviewer",
    "remediation": "Add onlyOwner to setMinter.",
    "regression_test": "A stranger calling setMinter must revert with 'not owner'.",
    "limitations": [],
}


@pytest.fixture
def finding():
    return copy.deepcopy(BASE_FINDING)


@pytest.fixture
def project(tmp_path):
    """Copy of fixture 01 in a temp dir, so tests can write run directories into it."""
    dest = tmp_path / "project"
    shutil.copytree(FIXTURES / "01-unauthorized-mint", dest)
    return dest


@pytest.fixture
def run_dir(project):
    return workspace.create_run(
        project,
        ".",
        "audit",
        None,
        {"system": "foundry", "compiler": "0.8.24"},
        {"forge": "forge 1.0", "slither": None},
    )


def write_finding(run_dir: Path, data: dict) -> Path:
    path = run_dir / "findings" / f"{data['id']}.json"
    path.write_text(json.dumps(data), encoding="utf-8")
    return path


def git(cwd: Path, *args: str) -> str:
    return subprocess.run(
        ["git", "-c", "user.name=t", "-c", "user.email=t@t", "-c", "commit.gpgsign=false", *args],
        cwd=cwd,
        check=True,
        capture_output=True,
        text=True,
    ).stdout


def make_diff_repo(tmp_path: Path, fixture: str) -> Path:
    """A git repo whose first commit is <fixture>/v1 and second is <fixture>/v2."""
    repo = tmp_path / "repo"
    shutil.copytree(FIXTURES / fixture / "v1", repo)
    git(repo, "init", "-q", "-b", "main")
    git(repo, "add", "-A")
    git(repo, "commit", "-q", "-m", "v1")
    for p in (FIXTURES / fixture / "v2").rglob("*"):
        if p.is_file():
            target = repo / p.relative_to(FIXTURES / fixture / "v2")
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(p, target)
    git(repo, "add", "-A")
    git(repo, "commit", "-q", "-m", "v2")
    return repo
