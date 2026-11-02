# Finding and evidence standard

Every hypothesis ends up as one JSON file, `findings/SWARM-NNN.json`, in the run directory. The schema
is `${CLAUDE_PLUGIN_ROOT}/schemas/finding.schema.json`; `swarmsec validate` enforces it plus the rules
below.

## Statuses

| Status | Meaning | Published? |
|---|---|---|
| `candidate` | Written by a reviewer, not yet verified | No; render refuses unless `--draft` |
| `reproduced` | An executed test demonstrated the broken property | Yes |
| `supported` | Traced end to end in source, nothing stops it, not executed | Yes |
| `unresolved` | Depends on something not visible (deployment, missing code) | Separate section |
| `rejected` | Disproved; the reason is kept in the audit log | Dismissed table only |

Rules the validator enforces:
- `evidence` is never empty, and a published finding needs evidence other than `reasoning`.
- `reproduced` and `supported` need a `verification` record whose `verifier` differs from
  `discovered_by`. Use bare agent or skill names (`solidity-reviewer`, `finding-verifier`, `audit`);
  the validator strips the `swarmsec-audit:` prefix and anything after the name before comparing. `rejected` needs a `verification` record with the reason; you may dismiss your own
  hypothesis.
- `reproduced` needs `reproduction.result = "demonstrated"` and a `tool_run` id that exists in
  `tool-runs/` and completed. A manual trace can never be a reproduction.
- Every `location` must exist in the checkout, inside the project, with the line range inside the
  file. A `snippet` must match those lines (whitespace is normalised).

## What counts as evidence

| kind | Use for | Must include |
|---|---|---|
| `source` | The line that is wrong, or the guard that is missing | `location`, preferably `snippet` |
| `call-path` | How the entry point reaches the effect | `location` of the key hop, the path in `description` |
| `test` | An executed test | `tool_run`, what it asserted |
| `tool` | Static-analysis output that points at the same code | `tool_run` or the tool name; never the only evidence |
| `state-delta` | Balances or storage before and after, from a trace | `tool_run` |
| `reasoning` | Arithmetic or an argument that ties the rest together | — |

Cite the narrowest line range that shows the point. Quote the code in `snippet` exactly as it appears.

## Writing a finding

```json
{
  "schema_version": "1.0",
  "id": "SWARM-001",
  "title": "setMinter has no access control, so anyone can mint",
  "category": "access-control",
  "severity": "critical",
  "confidence": "high",
  "status": "reproduced",
  "summary": "RewardToken.setMinter writes `minter` without checking the caller. Any account can make itself minter and call mint.",
  "impact": "Unlimited supply can be minted to the attacker, diluting every holder to zero.",
  "attacker": "unprivileged",
  "preconditions": [],
  "affected_components": [{"file": "src/RewardToken.sol", "contract": "RewardToken", "function": "setMinter"}],
  "evidence": [
    {"kind": "source", "description": "No modifier or sender check before the write.",
     "location": {"file": "src/RewardToken.sol", "start_line": 31, "end_line": 34},
     "snippet": "function setMinter(address newMinter) external {\n    minter = newMinter;"},
    {"kind": "test", "description": "Stranger calls setMinter then mint; balance asserted.", "tool_run": "TR-001"}
  ],
  "reproduction": {"method": "foundry-test", "command": "forge test --match-path test/swarmsec/Mint.t.sol",
                   "test_file": "test/swarmsec/Mint.t.sol", "tool_run": "TR-001", "result": "demonstrated",
                   "environment": "local", "assertions": ["minter == attacker", "balanceOf(attacker) == 1e24"]},
  "verification": {"verifier": "finding-verifier", "reason": "No guard on the path; test passes.",
                   "falsification_attempts": ["Checked for inherited access control: none.",
                                              "Checked whether minter is re-set elsewhere: only here."]},
  "discovered_by": "solidity-reviewer",
  "remediation": "Add onlyOwner to setMinter (RewardToken.sol:31).",
  "regression_test": "A non-owner calling setMinter reverts with 'not owner'; the minter is unchanged.",
  "limitations": []
}
```

Optional fields: `related` (other finding ids with the same root cause) and `diff_attribution`
(`introduced`, `worsened`, `preexisting`, `not-applicable`) for diff reviews.

## Rejecting well

A rejection names what stops the attack: "withdrawAll is `nonReentrant` (EtherVault.sol:27) and so is
every other function that reads `balances`", not "looks fine". Keep rejected hypotheses: the report's
dismissed table shows what was considered, which is how readers judge coverage.

## Proof-of-concept tests

- Minimal: deploy only what the path needs, perform the attack, assert the broken property.
- Assert the effect, not the absence of a revert: balances moved, owner changed, an invariant false.
- Add a control: the same sequence against a patched version, or the honest user's expected outcome.
- Run through `swarmsec run`, which records the command, version, exit code and output. The `TR-` id
  is what makes a reproduction checkable.
