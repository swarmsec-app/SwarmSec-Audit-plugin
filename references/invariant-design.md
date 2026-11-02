# Invariant design

A useful invariant is one that a real bug would break. Write it in the contract's own variables.

## Sources of good properties

| Kind | Example in contract terms |
|---|---|
| Conservation | `asset.balanceOf(vault) >= sum of convertToAssets(balanceOf[u])` |
| Totals equal sums | `totalSupply == sum(balanceOf[u])`, `distributor.totalShares == pool.totalStaked` |
| Cross-contract link | `distributor.shares[u] == pool.balances[u]` for every user |
| Solvency | for every account, `debt[a] <= borrowLimit(a)` after any non-liquidation action |
| Monotonic | `accRewardPerShare` never decreases; `nonce[u]` only increases |
| Round-trip | `deposit(x)` then `redeem(all)` returns at most `x` (plus accrued yield) |
| Authorization | only the owner changes `owner`, `minter`, `implementation` |
| Replay | each `(signer, nonce)` is consumed at most once |

## Preconditions and exclusions

State what the property does not cover: donations (allowed to break equality, not inequality), tokens
with fees or rebases, paused states, the moment before initialization, admin rescue functions. A
property that fails only in an excluded state is not a bug; one that fails in an included state is.

## Handler-based Foundry tests

- One handler contract exposes the actions users can take, with inputs bounded to sensible ranges
  (`amount % max + 1`, pick an actor from a small fixed set).
- The handler tracks ghost variables: what each actor deposited, total claimed, expected balances.
- The test contract deploys the system in `setUp`, deploys the handler, and returns only the handler
  from `targetContracts()` so the fuzzer does not call admin functions directly.
- Invariant functions are `invariant_*` and only read state.
- Add a handler action for anything an outsider can do that the code might not expect: direct token
  transfers to the contract, calls in unusual order, zero amounts.
- Keep `runs` and `depth` modest in CI (for example 64 and 32) and higher for a deliberate deep run.

A passing run means the fuzzer found no counterexample in that many calls. It is not a proof. When a
property fails, report the shrunk call sequence; that sequence is the reproduction.

## Properties that are useless

- Restating a `require` the function already enforces.
- Comparing a value with itself or with a variable only that same line writes.
- Properties over state the handler never changes.
- "No function reverts": reverts are often correct behaviour.
