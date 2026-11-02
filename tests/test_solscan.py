from conftest import FIXTURES
from swarmsec_audit import solscan


def entry(inv, fid):
    return next(e for e in inv["entry_points"] if e["id"] == fid)


def test_strip_keeps_offsets_and_hides_comment_code():
    src = 'a // x.delegatecall(y)\nb /* tx.origin\n */ c "msg.sender == owner" d'
    out = solscan.strip_comments_and_strings(src)
    assert len(out) == len(src)
    assert out.count("\n") == src.count("\n")
    assert "delegatecall" not in out and "tx.origin" not in out and "owner" not in out


def test_missing_access_control_is_visible():
    inv = solscan.inventory(FIXTURES / "01-unauthorized-mint")
    set_minter = entry(inv, "RewardToken.setMinter")
    assert set_minter["access"] == "none-detected"
    assert set_minter["state_writes"] == ["minter"]
    assert set_minter["location"] == "src/RewardToken.sol:31-34"
    assert entry(inv, "RewardToken.mint")["access"] == "inline-check"
    assert entry(inv, "RewardToken.transferOwnership")["access"] == "modifier"
    patched = solscan.inventory(FIXTURES / "01-unauthorized-mint-patched")
    assert entry(patched, "RewardToken.setMinter")["access"] == "modifier"


def test_low_level_call_and_writes_after_it():
    inv = solscan.inventory(FIXTURES / "02-reentrancy-drain")
    w = entry(inv, "EtherVault.withdrawAll")
    assert w["external_calls"] == ["low-level-call:msg.sender@22"]
    assert w["state_writes"] == ["balances", "totalDeposits"]


def test_cross_file_contract_types_are_external_calls():
    inv = solscan.inventory(FIXTURES / "10-staking-rewards-desync")
    calls = entry(inv, "StakingPool.withdraw")["external_calls"]
    assert "typed:distributor.onUnstake@42" in calls
    assert not any("onUnstake" in c for c in entry(inv, "StakingPool.emergencyWithdraw")["external_calls"])
    assert entry(inv, "RewardDistributor.onStake")["access"] == "modifier"


def test_mapping_state_variables_and_mapping_calls():
    inv = solscan.inventory(FIXTURES / "05-oracle-scaling")
    market = next(c for f in inv["files"] for c in f["contracts"] if c["name"] == "LendingMarket")
    names = [v["name"] for v in market["state_vars"]]
    assert names == ["LTV_BPS", "owner", "stable", "feeds", "collateral", "debt", "listedTokens"]
    assert market["state_vars"][3]["type"] == "mapping(address => AggregatorV3Interface)"
    usd = next(fn for fn in market["functions"] if fn["name"] == "usdValue")
    assert {c["target"] for c in usd["external_calls"]} >= {"feeds[].latestRoundData"}
    assert "oracle-read" in usd["flags"]


def test_proxy_hints_and_unguarded_initializer():
    inv = solscan.inventory(FIXTURES / "07-reinitializable-proxy")
    contracts = {c["name"]: c for f in inv["files"] for c in f["contracts"]}
    assert "delegating-fallback" in contracts["TreasuryProxy"]["proxy_hints"]
    assert "initializer:initialize" in contracts["TreasuryV1"]["proxy_hints"]
    assert entry(inv, "TreasuryV1.initialize")["access"] == "none-detected"


def test_modifier_that_does_not_check_sender_is_not_access_control():
    src = """
    contract C {
        address owner;
        uint256 x;
        modifier onlyOwner() { _; }
        function set(uint256 v) external onlyOwner { x = v; }
    }
    """
    sf = solscan.scan_source(src, "src/C.sol")
    solscan.resolve_access([sf])
    fn = sf.contracts[0].functions[0]
    assert fn.modifiers == ["onlyOwner"] and fn.access == "none-detected"


def test_unresolved_import_is_reported():
    inv = solscan.inventory(FIXTURES / "13-partial-scope")
    assert inv["unresolved_imports"] == ["src/SwapRouter.sol: @periphery/interfaces/IPriceModule.sol"]


def test_injected_comment_does_not_change_analysis():
    inv = solscan.inventory(FIXTURES / "16-prompt-injection")
    assert entry(inv, "RewardToken.setMinter")["access"] == "none-detected"


def test_path_roles():
    from pathlib import Path

    assert solscan.classify_path(Path("lib/oz/ERC20.sol")) == "vendored"
    assert solscan.classify_path(Path("test/Vault.t.sol")) == "test"
    assert solscan.classify_path(Path("script/Deploy.s.sol")) == "script"
    assert solscan.classify_path(Path("src/mocks/MockToken.sol")) == "mock"
    assert solscan.classify_path(Path("src/Vault.sol")) == "production"


def test_ffi_and_js_config_warnings(tmp_path):
    (tmp_path / "foundry.toml").write_text("[profile.default]\nffi = true\n")
    (tmp_path / "hardhat.config.js").write_text("module.exports = {}")
    warnings = solscan.detect_build(tmp_path)["warnings"]
    assert any("ffi" in w for w in warnings)
    assert any("hardhat.config.js" in w for w in warnings)


def test_artifact_directories_named_sol_are_skipped(tmp_path):
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "A.sol").write_text("contract A { function f() external {} }")
    (tmp_path / "build" / "A.sol").mkdir(parents=True)  # custom Foundry `out` directory
    inv = solscan.inventory(tmp_path)
    assert [f["path"] for f in inv["files"]] == ["src/A.sol"]


def test_tricky_syntax():
    src = """
    pragma solidity ^0.8.24;
    function freeHelper(uint256 x) pure returns (uint256) { return x + 1; }
    error Unauthorized(address caller);
    contract C is A(1, "x,y"), B {
        string constant BRACES = "}{ ;";
        mapping(address => mapping(uint256 => bool)) public used;
        function(uint256) external returns (uint256) public callback;
        uint256[] public list;
        constructor(address a) A(2, "z") onlyInit {}
        modifier onlyInit() { require(msg.sender == address(0) || true, "}"); _; }
        function tryIt(address t) external {
            try IThing(t).run{value: 0}(1) returns (uint256 v) { list.push(v); } catch Error(string memory) {}
            unchecked { used[t][1] = true; }
        }
        receive() external payable {}
        fallback(bytes calldata d) external returns (bytes memory) { return d; }
    }
    """
    sf = solscan.scan_source(src, "src/C.sol")
    (c,) = sf.contracts
    assert c.bases == ["A", "B"]
    assert [v.name for v in c.state_vars] == ["BRACES", "used", "callback", "list"]
    fns = {f.name: f for f in c.functions}
    assert set(fns) == {"constructor", "tryIt", "receive", "fallback"}
    assert fns["tryIt"].state_writes == ["list", "used"]
    assert any(call.target.startswith("IThing(t).run") for call in fns["tryIt"].external_calls)
    assert fns["fallback"].kind == "fallback" and fns["receive"].mutability == "payable"


def test_text_output_is_capped_for_large_repos(tmp_path, monkeypatch):
    (tmp_path / "src").mkdir()
    fns = "\n".join(f"function f{i}(uint256 x) external {{ v = x; }}" for i in range(30))
    (tmp_path / "src" / "Big.sol").write_text(
        f"contract Big {{ uint256 v; {fns} function g() external onlyOwner {{ v = 1; }} }}"
    )
    monkeypatch.setitem(solscan.TEXT_LIMITS, "entry points", 5)
    text = solscan.format_text(solscan.inventory(tmp_path))
    assert "26 more entry points lines omitted" in text
    assert "Big.g " not in text, "guarded functions sort after open ones"
