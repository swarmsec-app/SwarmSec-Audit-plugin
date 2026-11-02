# Security review: benign

This report comes from an automated, model-assisted review. It is not a formal audit, and the absence of findings does not show that the code is safe.

| | |
|---|---|
| Run | `20261101T171945Z` (audit) |
| Revision | `2ece1d0ce9b3` |
| Generated | 2026-11-01T22:18:21+00:00 |
| Build | foundry, compiler 0.8.24, not-attempted |

## Summary

No substantiated findings in the reviewed scope.

No findings at any severity.

## Scope

- included: `.`

## Protocol context

**Purpose.** Custodial ledger for one immutable ERC-20 (`token`). Users `deposit` and `withdraw` 1:1; no yield, no fees, no shares.

**Assets.** The token balance held by `SavingsAccount`. Per-user claims in `balanceOf`, aggregate in `totalDeposits` (informational only, nothing reads it).

**Actors and powers.**
- Any account: `deposit(amount)`, `withdraw(amount, to)` against its own balance.
- `owner`: `setDepositsPaused` (blocks new deposits only), `transferOwnership` (two-step, `pendingOwner` must `acceptOwnership`). No function lets the owner move, freeze or sweep user funds; withdrawals ignore the pause flag.
- `pendingOwner`: can accept ownership.

**Trust assumptions.** The token is chosen by the deployer at construction and is trusted not to be malicious. Fee-on-transfer is handled by crediting the balance delta. Rebasing, blocklisting and hook (ERC-777 style) tokens are partially handled (`nonReentrant` on both entry points).

**External dependencies.** Only `token` (`transferFrom`, `transfer`, `balanceOf` via `SafeTransfer` and a staticcall). No oracles, no other protocols, no proxy/upgrade wiring.

**Attacker control.** Amounts, recipient `to`, call ordering, and any token hook the token itself exposes. Not the token address, owner or pending owner.

**Scope.** `src/SavingsAccount.sol`, `src/SafeTransfer.sol`. No tests, scripts, mocks or vendored libraries present. Not compiled; no artifacts used.

## Findings

None.

## Unresolved hypotheses

None.

## Dismissed hypotheses

None recorded.

## Tool runs

No tools were executed.

## Coverage gaps and limitations

- Not compiled and no tests executed; no solc/slither/echidna/medusa available, so no static-analysis or fuzzing coverage.
- The token's behaviour is unknown (constructor argument); rebasing, blocklist and hook semantics were reasoned about generically.
- Manual review by a single reviewer; hypotheses were all informational or lower and none was sent to an independent verifier.
- No proof-of-concept tests were run.
- Tools: anvil 1.5.1-stable, cast 1.5.1-stable, forge 1.5.1-stable; not installed: aderyn, contractmap, echidna, medusa, semgrep, slither, solc
