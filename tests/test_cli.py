import json
import subprocess
import sys

from conftest import ROOT, write_finding

CLI = [sys.executable, str(ROOT / "scripts" / "swarmsec.py")]


def cli(*args, cwd=None):
    return subprocess.run([*CLI, *args], capture_output=True, text=True, cwd=cwd, encoding="utf-8")


def test_init_validate_render_end_to_end(project, finding, monkeypatch):
    out = cli("init", str(project), "--target", "src")
    assert out.returncode == 0, out.stderr
    assert "RewardToken.setMinter" in out.stdout
    run_dir = project / ".swarmsec-audit" / "runs"
    run = next(run_dir.iterdir())
    write_finding(run, finding)
    latest = str(project / ".swarmsec-audit" / "runs" / "latest" / "findings" / "SWARM-001.json")
    assert cli("validate", latest).returncode == 0
    rendered = cli("render", str(project / ".swarmsec-audit" / "runs" / "latest"))
    assert rendered.returncode == 0, rendered.stderr
    data = json.loads((run / "report.json").read_text(encoding="utf-8"))
    assert data["target"]["path"] == "src"
    assert [f["id"] for f in data["findings"]] == ["SWARM-001"]


def test_run_options_may_follow_run_dir(project, run_dir):
    # A refused command proves the tool command was split at `--` and not swallowed with the options.
    out = cli("run", str(run_dir), "--cwd", str(project), "--timeout", "5", "--", "forge", "script", "x")
    assert out.returncode == 2
    assert "forge script is not allowed" in out.stderr


def test_run_without_command_is_an_error(run_dir):
    out = cli("run", str(run_dir))
    assert out.returncode == 2 and "after --" in out.stderr


def test_missing_target_is_a_clear_error(tmp_path):
    out = cli("inventory", str(tmp_path / "nope"))
    assert out.returncode == 2 and "does not exist" in out.stderr
