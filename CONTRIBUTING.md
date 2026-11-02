# Contributing

## Layout

| Path | What lives there |
|---|---|
| `skills/<name>/SKILL.md` | The seven commands. Keep each under 200 lines; put checklists in `references/` |
| `agents/*.md` | Specialist subagents. Only `invariant-designer`, `finding-verifier` and `report-editor` may have Write or Edit |
| `references/` | Methodology loaded on demand |
| `scripts/swarmsec.py`, `scripts/swarmsec_audit/` | Helper CLI. Python 3.11+, standard library only |
| `schemas/` | Finding and report JSON schemas (Draft 2020-12) |
| `tests/fixtures/` | Small Foundry projects; ground truth in `tests/fixtures/manifest.json` |
| `tests/poc/` | Foundry tests that prove each fixture's ground truth |
| `evals/` | `claude plugin eval` cases |

## Checks

```bash
uv run --group dev pytest
uv run --group dev ruff check .
uv run --group dev ruff format --check .
(cd tests/poc && forge test --offline)
claude plugin validate .
```

All of these run in CI on Linux and Windows except the Foundry suite, which runs on Linux. None of
them call a model.

## Model evaluations

`claude plugin eval` calls the model on your account and costs money. CI never runs it. Run it
deliberately:

```bash
claude plugin eval . --scaffold --runs 1 --ablation none --case audit-unauthorized-mint   # cheap iteration
claude plugin eval . --scaffold --max-cost-usd 40                                         # full suite with baseline
```

`--scaffold` is required: each case copies its fixture into the empty eval workspace with a short bash
script you can read in the case directory. Record results you cite in `evals/RESULTS.md` with the
date, Claude Code version, model and cost.

## Adding a fixture

1. Add a minimal Foundry project under `tests/fixtures/NN-name/` with `foundry.toml` pinned to
   `solc_version = "0.8.24"` and no external dependencies.
2. Keep the source realistic. No comments that point at the flaw; `tests/test_repository.py` rejects
   words such as "vulnerable", "exploit" or "attack" in vulnerable fixtures.
3. Add the ground truth to `tests/fixtures/manifest.json`: expected findings with location and
   severity band, or `max_severity` for controls.
4. Add a Foundry test in `tests/poc/test/` that demonstrates the issue (and its absence in a patched
   variant), using the local `Vm` interface in `TestBase.sol`.
5. Optionally add an eval case under `evals/`.

## Writing style

Skills, references and reports are read by people and models. Say what to check and when it matters,
with concrete conditions. No filler, no marketing words, no claims the code cannot back up.

## Attribution

Methodology was cross-checked against Trail of Bits' public skills (CC BY-SA 4.0) and other public
auditing approaches. No text was copied. Do not paste text from those sources; describe the idea in
your own words and add attribution here if a contribution adapts a specific technique.
