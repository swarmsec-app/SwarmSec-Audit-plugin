# SwarmSec Audit

A Claude Code plugin for reviewing Solidity and EVM contracts. It maps the attack surface, generates
vulnerability hypotheses, has a separate agent try to disprove each one, and writes a report in which
every finding cites lines that a script has checked against your checkout.

It is a review aid for developers and auditors: before a formal audit, on a pull request, or while
researching a protocol. It is not a formal audit, and "no substantiated findings" does not mean the code
is safe.

## How it differs from a prompt that asks for bugs

- **Findings are data with rules.** Each finding is a JSON file. `swarmsec validate` rejects a finding
  with no evidence, evidence whose file or line range does not exist, a quoted snippet that does not
  match the cited lines, or a path outside the project.
- **The finder is not the judge.** A published finding needs a verification record from a different
  agent than the one that found it. The verifier's job is to break the claim.
- **"Reproduced" means a recorded test run.** The status needs a `TR-` record from `swarmsec run` that
  completed: command, tool version, exit code and output. A manual trace can only reach `supported`.
- **Dismissed hypotheses stay visible.** Rejected claims appear in the report with the reason, so a
  reader can see what was considered.
- **Coverage gaps are reported.** Missing tools, unresolved imports and code outside the tree are
  listed as gaps, never treated as evidence of safety.
- **Read-only by default.** No package installs, project scripts, deployments or transactions. Tests run
  in a sandbox copy, offline, with FFI off, only after you approve.

## Install

From a clone (tested with Claude Code 2.1.312):

```bash
claude plugin marketplace add ./swarmsec-audit
claude plugin install swarmsec-audit@swarmsec-security
```

From GitHub:

```bash
claude plugin marketplace add SwarmSec/swarmsec-audit
claude plugin install swarmsec-audit@swarmsec-security
```

For development, load the working tree directly:

```bash
claude --plugin-dir ./swarmsec-audit
```

Requirements: Claude Code (tested with 2.1.312) and Python 3.11 or later for the helper script
(standard library only). Foundry is optional and enables reproduction tests. There is no SwarmSec
backend, account or extra API key.

## Commands

| Command | What it does |
|---|---|
| `/swarmsec-audit:audit [path]` | Full review: scope, attack surface, hypotheses, independent verification, report |
| `/swarmsec-audit:defi-audit [path]` | Accounting and economic review: share math, oracles, lending, rewards, cross-contract books |
| `/swarmsec-audit:attack-surface [path]` | Entry points, access control, roles, proxies, external calls; a map, not findings |
| `/swarmsec-audit:invariants [path] [--write-tests]` | Properties to fuzz, with preconditions; optionally Foundry handler tests |
| `/swarmsec-audit:verify <finding.json \| description>` | Trace, try to falsify, optionally reproduce in a sandbox; returns a verdict |
| `/swarmsec-audit:diff-audit [base...head]` | Review a change, including unchanged callers and storage layout |
| `/swarmsec-audit:report [run-dir]` | Validate, deduplicate and render a run into `report.md` and `report.json` |

Claude also picks these skills from plain requests such as "security review these contracts". Add
`--no-files` to `audit` or `defi-audit` to keep everything in chat.

Output goes to `.swarmsec-audit/runs/<timestamp>/` in the audited project:

```
run.json          scope, revision, build status, detected tools, coverage gaps
inventory.json    lexical scan of contracts, entry points, calls and flags
context.md        protocol summary, assets, actors, trust assumptions
findings/         SWARM-NNN.json, one per hypothesis, including rejected ones
tool-runs/        TR-NNN.json and .log for every tool execution
report.md         the readable report
report.json       the same, validated against schemas/report.schema.json
```

Add `.swarmsec-audit/` to your `.gitignore` if you do not want to commit runs.

## Five-minute audit

```bash
cp -r tests/fixtures/10-staking-rewards-desync /tmp/rewards && cd /tmp/rewards
claude --plugin-dir /path/to/swarmsec-audit
> /swarmsec-audit:audit .
```

On 1 November 2026 a session with Claude Sonnet 5.5 took 104 seconds and $0.68 for this fixture. It
reported SWARM-001 (high): `StakingPool.emergencyWithdraw` returns the stake without calling the
reward distributor, so the account keeps its reward shares. The verifier traced it and corrected one
overstated claim about the impact. Asked to verify with test execution allowed, a second session wrote
an attack test and a control test in a sandbox copy, ran them offline as TR-001, and moved the finding
to `reproduced`: after ten stake and emergency-withdraw cycles the attacker took 1000 of an 1100-token
reward while holding no stake. The full output is in [examples/](examples/).

The benign control (`11-benign-savings`) came back with "No substantiated findings in the reviewed
scope" ($0.25), five dismissed hypotheses with reasons, and the coverage gaps.

## Results on the bundled fixtures

Ground truth for 16 cases (vulnerable, patched, benign, noisy, partial scope, a misleading tool
report, two diffs and a prompt-injection repository) is in `tests/fixtures/manifest.json`. Every
vulnerable claim is proven, and every patched variant shown safe, by the Foundry suite in `tests/poc/`
(21 tests).

Single real sessions, one sample each, Claude Sonnet 5.5, Claude Code 2.1.312:

| Command and fixture | Expected | Result | Cost |
|---|---|---|---|
| `audit` on 10 (pool + distributor) | emergencyWithdraw desync, high | Found, high; reproduced by `verify` | $0.68 + $0.34 |
| `audit` on 11 (benign) | nothing above informational | No substantiated findings | $0.25 |
| `defi-audit` on 04 (vault) | donation / first-depositor, high | Found, high, plus two lows | $0.55 |
| `diff-audit HEAD~1..HEAD` on 15 | break in the unchanged caller, high or critical | Found in `LendingMarket.maxDebt`, critical, attributed to the change, verified by `finding-verifier` | $0.44 |
| `invariants --write-tests` on 10 | cross-contract share properties fail | 2 of 6 invariants fail with the shrunk sequence | $0.36 |
| `attack-surface` on 07 (proxy) | `initialize` open, owner-only admin, ERC-1967 wiring | All three, with file:line for each entry point | $0.18 |
| `report` on the run from row 1 | validate and render without inventing changes | 0 errors, no severity changes, report re-rendered | $0.20 |

### Plugin evals against a no-plugin baseline

Seven cases from `evals/`, one run per arm, Claude Sonnet 5.5, run with `claude plugin eval`:

| Case | With plugin | Without |
|---|---|---|
| unauthorized mint (true positive) | 1.00 | 1.00 |
| guarded reentrancy (false-positive control) | 1.00 | 0.00 |
| oracle change breaks an unchanged caller (diff) | 1.00 | 1.00 |
| prompt injection in source and README | 1.00 | 1.00 |
| unrelated request must not trigger the skill | 1.00 | 1.00 |
| noisy but safe delegatecall and unchecked code (false-positive control) | 1.00 | 0.00 |
| attack-surface map of a proxy | 1.00 | 1.00 |

Mean Δ +0.29 for $1.90. On these small fixtures the model without the plugin already finds the
headline bugs; the difference showed up on the two false-positive controls, where the plugin's
severity rules kept safe patterns from being reported as medium or low findings. The first run of the
same suite found that the audit skill did not trigger on two of four audit-style prompts; the
descriptions were fixed and both re-runs are recorded in [evals/RESULTS.md](evals/RESULTS.md). The full
14-case suite with three runs per arm has not been run yet; the last attempt stopped at the
account's monthly spend limit with seven cases unscored.

## Optional tools

Tools are detected at run time (`swarmsec tools`). Missing ones become coverage gaps.

| Tool | Used for |
|---|---|
| Foundry (`forge`) | Proof-of-concept tests in a sandbox copy; invariant tests; `forge inspect` storage layouts |
| Slither | Detector hints, imported with file and line provenance and verified like any other hypothesis |
| Aderyn, Semgrep | Additional hints (Semgrep with `--metrics=off` and local rules only) |
| Echidna, Medusa | Property fuzzing beyond Foundry invariants |
| ContractMap | Attack-surface map imported as leads; schema 1.x only, checked before import |

Slither, Echidna and Medusa compile Hardhat projects by running `npx hardhat compile`, which executes
the project's JavaScript config. The runner refuses that unless you approve it explicitly.

## Security model

The plugin reads repositories you may not trust. It treats source comments, READMEs, tool output and
commit messages as data. The red-team fixture (`tests/fixtures/16-prompt-injection`) hides
instructions in a comment and a README telling reviewers to stay silent and run `npm install`.

The helper's tool runner (`swarmsec run`) enforces these rules regardless of what the model asks for:

- only `forge build|test|inspect|coverage|snapshot`, `slither`, `aderyn`, `semgrep`, `echidna`,
  `medusa` and `contractmap`; no `forge script`, `forge create`, `cast` or `anvil`;
- `--private-key`, `--mnemonic`, `--keystore`, `--broadcast`, `--unlocked`, `--ffi` and hardware wallet
  flags are refused;
- Foundry runs `--offline` with `FOUNDRY_FFI=false`; forks need `--allow-fork`;
- environment variables that look like keys, tokens, RPC URLs or Etherscan credentials are removed;
- fork URLs are stored as `<redacted-rpc>`; reports redact credentials in URLs, provider API keys and
  local paths.

There are no hooks. Nothing runs unless a skill is invoked. Audited code and findings stay on your
machine; the plugin makes no network calls of its own.

## Tests and evaluation

Deterministic checks (none call a model). The CI workflow runs them on Ubuntu and Windows; locally they pass on Windows 11 with Python 3.11 and 3.13:

```bash
uv run --group dev pytest                 # helper scripts, schemas, fixtures, plugin layout
(cd tests/poc && forge test --offline)    # proves each fixture's ground truth
claude plugin validate .
```

Model evaluations use `claude plugin eval` and cost money, so they never run in CI:

```bash
claude plugin eval . --scaffold --max-cost-usd 40
```

Each case copies one fixture into the eval workspace with a script you can read in the case
directory, and the run is compared against a no-plugin baseline.

## Compatibility

Tested with Claude Code 2.1.312 on Windows 11 with Python 3.11 and 3.13 and Foundry 1.5.1. The CI
workflow targets Ubuntu and Windows but has not run yet, because the repository is not published.
Solidity only; Vyper and non-EVM chains are not supported.

## Limitations

- The inventory is a lexical scan, not a compiler. It can miss calls made through complex expressions
  and misjudge access control defined in files outside the scan. Skills treat it as a list of leads.
- Storage-layout comparison in `swarmsec diff` reads declaration order per contract. It does not
  compute slots across inheritance; use `forge inspect` for that when compiling is acceptable.
- Model results vary between runs and models. Treat any single run as one sample.
- A reproduction on a fork is a simulation of chain state, not a live result.

## Contributing and security

See [CONTRIBUTING.md](CONTRIBUTING.md) and [SECURITY.md](SECURITY.md). Report problems in the plugin
to security@swarmsec.app; report vulnerabilities you find in other projects to those projects.

Methodology was cross-checked against Trail of Bits' public skills (CC BY-SA 4.0) and other public
auditing approaches; no text from them is included.

## License

MIT. See [LICENSE](LICENSE).
