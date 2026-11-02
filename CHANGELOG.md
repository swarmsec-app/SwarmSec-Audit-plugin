# Changelog

## 0.1.0 - 2026-11-02

First release.

### Commands and agents

- Skills: `audit`, `defi-audit`, `attack-surface`, `invariants`, `verify`, `diff-audit`, `report`.
- Agents: `audit-context`, `solidity-reviewer`, `defi-economics-reviewer`, `invariant-designer`,
  `finding-verifier`, `report-editor`. Only the last three can write files.

### Helper CLI (`scripts/swarmsec.py`, Python 3.11+, standard library only)

- Lexical inventory of contracts, storage, modifiers, entry points, external calls and flags; skips
  build artifacts, recognises cross-file contract types and calls with options, and caps its text
  output on large repositories with the least protected entry points first.
- Run workspaces under `.swarmsec-audit/runs/`, with `latest` accepted in paths.
- Finding validation: JSON schema, independent verification for published findings, recorded tool
  runs for reproductions, and cited file, line range and snippet checked against the checkout.
- Report rendering to Markdown and JSON with an overview table, source excerpts, deterministic order
  and redaction of credentials and local paths.
- A bounded tool runner: allowlisted tools only, no signing or broadcasting flags, Foundry offline
  with FFI disabled, secrets removed from the environment, fork URLs redacted.
- Diff summary: changed members, access and storage-layout changes, unchanged callers.
- Slither and ContractMap importers that produce leads, not findings.

### Tests and evaluation

- Finding and report JSON schemas, version 1.0.
- 23 Foundry fixture projects covering 16 cases, with ground truth in `tests/fixtures/manifest.json`
  and 21 Foundry tests proving it.
- 122 pytest tests; CI for Ubuntu and Windows.
- 14 `claude plugin eval` cases; results in `evals/RESULTS.md`.
- Unedited output from real sessions in `examples/`.
