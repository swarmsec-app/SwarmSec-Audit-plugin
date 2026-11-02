# Tools and delegation

## Helper CLI

`python3 "${CLAUDE_PLUGIN_ROOT}/scripts/swarmsec.py" <command>` (Python 3.11+, standard library only).
On Windows `python3` is often a Store stub; use `python`.

| Command | What it does | Writes |
|---|---|---|
| `tools` | Detects forge, cast, anvil, solc, slither, aderyn, semgrep, echidna, medusa, contractmap | nothing |
| `inventory <path>` | Lexical scan: contracts, storage, modifiers, entry points, calls, flags, unresolved imports | nothing (`--out` optional) |
| `init <root> --target <path> [--mode M] [--diff R]` | Creates `.swarmsec-audit/runs/<id>/` with `run.json` and `inventory.json` | run dir |
| `diff <range> --root <repo>` | Changed members, access and storage-layout changes, unchanged callers | nothing |
| `validate <run-dir \| finding.json>` | Schema, cross-field rules, evidence locations and snippets | nothing |
| `render <run-dir> [--draft]` | `report.md` and `report.json`, redacted, deterministic order | run dir |
| `sandbox <run-dir>` | Copies the project into `<run-dir>/sandbox/` for tests | run dir |
| `run <run-dir> [--cwd D] [--timeout S] -- <tool> ...` | Runs an allowed tool and records `tool-runs/TR-NNN.json` + log | run dir |
| `import <run-dir> slither\|contractmap <file>` | Converts tool JSON into hints | run dir |
| `contractmap <run-dir>` | Runs ContractMap if installed and imports its map | run dir |

The inventory is lexical. It can miss calls through complex expressions and misjudge access control
defined outside the scanned files. Confirm everything it reports by reading the code.

## What `run` allows

- Tools: `forge` (`build`, `test`, `inspect`, `coverage`, `snapshot`), `slither`, `aderyn`, `semgrep`,
  `echidna`, `medusa`, `contractmap`. Everything else is refused, including `forge script`,
  `forge create`, `cast` and `anvil`.
- Never allowed: `--private-key`, `--mnemonic`, `--keystore`, `--broadcast`, `--unlocked`, `--ffi`,
  hardware wallet flags.
- `forge build/test/coverage/snapshot` get `--offline` unless a fork URL is given, and every run has
  `FOUNDRY_FFI=false`.
- Environment variables whose names contain KEY, TOKEN, SECRET, PASSWORD, MNEMONIC, PRIVATE, RPC,
  ETHERSCAN or CREDENTIAL are removed.
- `--fork-url`/`--rpc-url` need `--allow-fork`; pass it only after the user approved that endpoint.
  The URL is stored as `<redacted-rpc>`.
- Slither, Echidna and Medusa compile through crytic-compile, which runs `npx hardhat compile` for
  Hardhat projects. With a JavaScript config present, `run` refuses unless `--allow-project-build` is
  given, which needs the user's approval.
- Default timeout 600 s; output capped at 2 MB per run.

## Optional tools

| Tool | Use it for | If absent |
|---|---|---|
| Foundry | Reproducing hypotheses, invariant tests, `forge inspect` storage layouts | No reproduction; findings at most `supported` |
| Slither | Detector hints and a second opinion on call graphs | Record "no static-analysis cross-check" |
| Aderyn, Semgrep | More detector hints | Nothing to record unless the user asked |
| Echidna, Medusa | Property fuzzing beyond Foundry | Use Foundry invariants |
| ContractMap | Attack-surface map, proxies, roles | Use the inventory and reading |

Run Slither as `swarmsec run <run-dir> -- slither . --json <run-dir>/slither.json`, then
`swarmsec import <run-dir> slither <run-dir>/slither.json`. Its detectors are hints: each one needs the
same tracing as any other hypothesis, and many are false positives.
Run Semgrep with `--metrics=off` and local rule files only.

ContractMap output (schema 1.x) is imported as leads. The adapter checks `tool` and `schema_version`
and refuses other versions. Confirm proxies, roles and unresolved edges in source before relying on
them.

## Delegation

Delegate only when the agent has a distinct job:

| Codebase | Plan |
|---|---|
| 1-2 small contracts | Review yourself, then one `finding-verifier` pass |
| Multi-contract protocol | `audit-context` first; then `solidity-reviewer` and `defi-economics-reviewer` in parallel on their paths; then `finding-verifier` |
| Large repository | Split by trust boundary or component (not by file count); at most three reviewers at once |

- Parallel work is read-only review only. Verification and report writing happen after hypotheses are
  collected.
- Give each agent the run directory, `context.md`, the paths it owns and what is out of scope.
- A reviewer never verifies its own hypotheses.
- Six agent launches per audit is a sensible ceiling unless the user asks for more depth.

## Trail of Bits and other skills

If the user has other audit skills installed (for example Trail of Bits `entry-point-analyzer`,
`differential-review` or `fp-check`), they can be used as a cross-check. SwarmSec does not depend on
them.
