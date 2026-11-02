# Examples

Unedited output from real runs on 1 November 2026. Each was a fresh, non-interactive session against a
copy of a bundled fixture:

```bash
claude -p --plugin-dir <plugin> --max-budget-usd 6 \
  --allowedTools Read Grep Glob Write Edit Agent "Bash(python:*)" "Bash(git:*)" -- "/swarmsec-audit:audit ."
```

Claude Code 2.1.312 on Windows 11, Foundry 1.5.1, no Slither. The session model was Claude Sonnet 5.5
(the CLI default in that environment); results from other models will differ. Each directory is one
sample, not an average. The rendered reports use the directory name of the copy (for example
`rewards`) as the project name.

| Example | Fixture | Command | Outcome | Cost |
|---|---|---|---|---|
| [staking-rewards-audit](staking-rewards-audit/) | `10-staking-rewards-desync` | `audit .`, then `verify` on SWARM-001 with test execution approved | SWARM-001 (high): `emergencyWithdraw` leaves reward shares behind. Reproduced by TR-001 with an attack test and a control test. Two extra issues kept as unresolved because they depend on the token | $0.68 + $0.34 |
| [benign-control](benign-control/) | `11-benign-savings` | `audit .` | "No substantiated findings in the reviewed scope", with five dismissed hypotheses and the coverage gaps | $0.25 |
| [vault-defi-audit](vault-defi-audit/) | `04-vault-donation` | `defi-audit .` | SWARM-001 (high): first-depositor donation makes later deposits mint zero shares. Two low-severity extras | $0.55 |
| [oracle-diff-audit](oracle-diff-audit/) | `15-diff-caller-break` (two commits) | `diff-audit HEAD~1..HEAD` | SWARM-001 (critical, introduced): `getPrice` now returns 18 decimals and the unchanged `LendingMarket.maxDebt` still scales by 1e10. Verified by `finding-verifier` from source | $0.44 |
| [treasury-attack-surface](treasury-attack-surface/) | `07-reinitializable-proxy` | `attack-surface .` | Entry-point table with `initialize` marked open with no one-time guard, owner-only `pay`, `setWithdrawLimit` and `upgradeTo`, and the UUPS/ERC-1967 wiring | $0.18 |
| [rewards-invariants](rewards-invariants/) | `10-staking-rewards-desync` | `invariants . --write-tests --dir test/invariants`, with writing and running approved | Six properties; four pass, two fail with the shrunk sequence `stake` then `emergencyWithdraw`. Three properties discarded because they cannot fail | $0.36 |

What to look at:

- `staking-rewards-audit/findings/SWARM-001.json`: status `reproduced`, the `reproduction` record
  pointing at `tool-runs/TR-001.json`, the assertions the test made, and the verifier's falsification
  attempts. `PhantomShares.t.sol` is the test the verifier wrote in the sandbox copy.
- `staking-rewards-audit/report.md`: findings, unresolved hypotheses, and the tool-run table.
- `benign-control/report.md`: what a clean result looks like, including what was not covered.
- `rewards-invariants/summary.md` and `StakingInvariants.t.sol`: the property table and the generated
  handler-based suite; `tool-runs/TR-001.log` is the raw Foundry output (exit code 1 because two
  invariants failed, which is the finding).

Every finding here validates against the fixture it came from (schema, independence, recorded tool
runs, and each cited line range and snippet); `tests/test_repository.py` re-checks this on every CI
run.
