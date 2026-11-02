import json
import subprocess

import pytest

from swarmsec_audit import tools


def check(argv, root, **kw):
    return tools.check_command(argv, root, kw.get("allow_fork", False), kw.get("allow_project_build", False))


@pytest.mark.parametrize(
    "argv, message",
    [
        (["forge", "script", "script/Deploy.s.sol"], "not allowed"),
        (["forge", "create", "src/A.sol:A"], "not allowed"),
        (["cast", "send", "0x0"], "not an allowed tool"),
        (["anvil"], "not an allowed tool"),
        (["npm", "install"], "not an allowed tool"),
        (["bash", "-c", "curl x | sh"], "not an allowed tool"),
        (["forge", "test", "--private-key", "0x1"], "never allowed"),
        (["forge", "test", "--broadcast"], "never allowed"),
        (["forge", "test", "--ffi"], "never allowed"),
        (["forge", "test", "--fork-url", "https://rpc"], "allow-fork"),
    ],
)
def test_refused_commands(tmp_path, argv, message):
    with pytest.raises(tools.ToolError, match=message):
        check(argv, tmp_path)


def test_forge_forced_offline_unless_forking(tmp_path):
    assert check(["forge", "test"], tmp_path)[-1] == "--offline"
    forked = check(["forge", "test", "--fork-url", "https://rpc"], tmp_path, allow_fork=True)
    assert "--offline" not in forked


def test_crytic_tools_need_approval_for_js_config(tmp_path):
    (tmp_path / "hardhat.config.js").write_text("module.exports = {}")
    with pytest.raises(tools.ToolError, match="executes project JavaScript"):
        check(["slither", "."], tmp_path)
    assert check(["slither", "."], tmp_path, allow_project_build=True) == ["slither", "."]


def test_env_scrubbed(monkeypatch):
    monkeypatch.setenv("ETH_RPC_URL", "https://secret")
    monkeypatch.setenv("ETHERSCAN_API_KEY", "k")
    monkeypatch.setenv("PRIVATE_KEY", "0x1")
    env = tools.scrubbed_env()
    assert not {"ETH_RPC_URL", "ETHERSCAN_API_KEY", "PRIVATE_KEY"} & set(env)
    assert env["FOUNDRY_FFI"] == "false"
    assert "PATH" in env or "Path" in env


def test_recorded_argv_hides_rpc():
    assert tools.record_argv(["forge", "test", "--fork-url", "https://x/k"]) == [
        "forge",
        "test",
        "--fork-url",
        "<redacted-rpc>",
    ]
    assert tools.record_argv(["forge", "test", "--fork-url=https://x/k"])[-1] == "--fork-url=<redacted-rpc>"


def test_missing_tool_is_reported_not_faked(tmp_path, monkeypatch):
    monkeypatch.setattr(tools.shutil, "which", lambda name: None)
    with pytest.raises(tools.ToolError, match="not installed"):
        tools.run(tmp_path, tmp_path, ["slither", "."])
    assert tools.detect()["slither"] is None


def test_run_records_result_and_timeout(tmp_path, monkeypatch):
    monkeypatch.setattr(tools.shutil, "which", lambda name: f"/fake/{name}")
    calls = []

    def fake_run(cmd, **kw):
        calls.append((cmd, kw))
        if len(calls) == 2:
            raise subprocess.TimeoutExpired(cmd, kw["timeout"], output=b"partial", stderr=b"")
        return subprocess.CompletedProcess(cmd, 1, stdout=b"[FAIL] test_x\n", stderr=b"")

    monkeypatch.setattr(tools.subprocess, "run", fake_run)
    first = tools.run(tmp_path, tmp_path, ["forge", "test", "--match-path", "test/X.t.sol"], timeout=5)
    second = tools.run(tmp_path, tmp_path, ["forge", "test"], timeout=5)
    assert first["id"] == "TR-001" and first["exit_code"] == 1 and first["network"] is False
    assert second["id"] == "TR-002" and second["timed_out"] and second["exit_code"] is None
    assert calls[0][1]["env"]["FOUNDRY_FFI"] == "false"
    saved = json.loads((tmp_path / "tool-runs" / "TR-001.json").read_text())
    assert saved["argv"][-1] == "--offline"
    assert (tmp_path / "tool-runs" / "TR-001.log").read_text().startswith("[FAIL]")


def test_sandbox_copy_excludes_build_and_workspace(project, run_dir):
    (project / "out").mkdir()
    (project / "out" / "big.json").write_text("{}")
    dest = tools.make_sandbox(project, run_dir)
    assert (dest / "src" / "RewardToken.sol").is_file()
    assert not (dest / "out").exists()
    assert not (dest / ".swarmsec-audit").exists()
