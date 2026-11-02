import json

import pytest

from conftest import FIXTURES
from swarmsec_audit import adapters

CONTRACTMAP_SAMPLE = {
    "schema_version": "1.0",
    "tool": "contractmap",
    "target": {"kind": "local", "identifier": "."},
    "metadata": {"generated_at": "2026-11-01T00:00:00Z", "tool_version": "1.0.0", "analysis_complete": True},
    "contracts": [
        {
            "id": "c:Proxy",
            "name": "TreasuryProxy",
            "is_proxy": True,
            "proxy": {"kind": "erc1967", "implementation": None, "admin": None, "resolution": "inferred"},
        },
        {"id": "c:Impl", "name": "TreasuryV1", "is_proxy": False},
    ],
    "functions": [
        {
            "id": "f1",
            "contract_id": "c:Impl",
            "name": "initialize",
            "signature": "initialize(address)",
            "visibility": "external",
            "mutability": "nonpayable",
            "modifiers": [],
            "access": {"restriction": "none_identified", "roles": []},
            "source": "src/TreasuryV1.sol:21",
        },
        {
            "id": "f2",
            "contract_id": "c:Impl",
            "name": "owner",
            "signature": "owner()",
            "visibility": "public",
            "mutability": "view",
        },
    ],
    "roles": [{"id": "r1", "name": "owner", "kind": "ownable", "contract_id": "c:Impl"}],
    "edges": [
        {"id": "e1", "kind": "delegatecalls", "source": "c:Proxy", "target": "c:Impl", "resolution": "unresolved"}
    ],
    "warnings": [{"code": "W1", "message": "implementation slot not readable offline"}],
}


def test_contractmap_import():
    summary = adapters.import_contractmap(CONTRACTMAP_SAMPLE)
    assert [e["function"] for e in summary["entry_points"]] == ["TreasuryV1.initialize"]
    assert summary["entry_points"][0]["restriction"] == "none_identified"
    assert summary["proxies"][0]["kind"] == "erc1967"
    assert summary["unresolved_edges"] == ["c:Proxy -delegatecalls-> c:Impl"]
    assert "confirm" in summary["note"]


@pytest.mark.parametrize(
    "patch, message",
    [
        ({"tool": "other"}, "not ContractMap"),
        ({"schema_version": "2.0"}, "not supported"),
        ({"schema_version": None}, "not supported"),
    ],
)
def test_contractmap_version_and_identity_checked(patch, message):
    with pytest.raises(adapters.AdapterError, match=message):
        adapters.import_contractmap({**CONTRACTMAP_SAMPLE, **patch})


def test_slither_import_keeps_provenance():
    data = json.loads((FIXTURES / "14-misleading-tool-output" / "tool-output" / "slither.json").read_text())
    summary = adapters.import_slither(data)
    assert summary["hints"][0]["detector"] == "reentrancy-eth"
    assert summary["hints"][0]["locations"] == ["src/RevenueSplitter.sol:22-34"]
    assert "unverified" in summary["note"]


def test_slither_failure_and_garbage(tmp_path):
    with pytest.raises(adapters.AdapterError, match="failure"):
        adapters.import_slither({"success": False, "error": "solc not found", "results": {}})
    bad = tmp_path / "bad.json"
    bad.write_text("[1, 2]")
    with pytest.raises(adapters.AdapterError, match="JSON object"):
        adapters.load_json(bad)
