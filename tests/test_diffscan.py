import pytest

from conftest import git, make_diff_repo
from swarmsec_audit import diffscan


def test_storage_insertion_detected(tmp_path):
    repo = make_diff_repo(tmp_path, "08-storage-layout-upgrade")
    summary = diffscan.diff_summary(repo, "HEAD~1..HEAD")
    staking = next(f for f in summary["files"] if f["file"] == "src/StakingRewards.sol")
    assert any("IERC20 stakingToken replaced by uint256 rewardRate" in s for s in staking["storage_layout"])
    assert "StakingRewards.setPaused" in staking["functions_added"]
    assert any(a.startswith("StakingRewards.stake:") and "whenNotPaused" in a for a in staking["access_changes"])


def test_unchanged_caller_of_changed_function_found(tmp_path):
    repo = make_diff_repo(tmp_path, "15-diff-caller-break")
    summary = diffscan.diff_summary(repo, "HEAD~1...HEAD")
    assert [f["file"] for f in summary["files"]] == ["src/PriceOracle.sol"]
    assert summary["files"][0]["changed_members"] == ["PriceOracle.getPrice"]
    callers = {c["function"]: c for c in summary["unchanged_callers"]}
    assert callers["LendingMarket.maxDebt"]["location"] == "src/LendingMarket.sol:49-54"


def test_single_commit_and_working_tree(tmp_path):
    repo = make_diff_repo(tmp_path, "15-diff-caller-break")
    assert diffscan.diff_summary(repo, "HEAD")["files"][0]["file"] == "src/PriceOracle.sol"
    (repo / "src" / "PriceOracle.sol").write_text(
        (repo / "src" / "PriceOracle.sol").read_text().replace("1 hours", "1 days")
    )
    work = diffscan.diff_summary(repo, None)
    assert work["head"] == "working-tree"
    assert work["files"][0]["changed_members"] == ["PriceOracle.<state>"]


@pytest.mark.parametrize("spec", ["--output=/tmp/x", "main;rm -rf /", "-p", "nosuchbranch...HEAD"])
def test_bad_ranges_rejected(tmp_path, spec):
    repo = make_diff_repo(tmp_path, "15-diff-caller-break")
    with pytest.raises(diffscan.DiffError):
        diffscan.diff_summary(repo, spec)


def test_root_commit_needs_explicit_range(tmp_path):
    repo = make_diff_repo(tmp_path, "15-diff-caller-break")
    root = git(repo, "rev-list", "--max-parents=0", "HEAD").strip()
    with pytest.raises(diffscan.DiffError, match="no parent"):
        diffscan.diff_summary(repo, root)
