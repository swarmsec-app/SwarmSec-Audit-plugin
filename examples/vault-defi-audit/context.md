# Context and accounting model: ShareVault

Scope: `src/ShareVault.sol` (50 lines, production), `src/IERC20.sol` (interface). No tests, no README or spec. The
only description is the NatSpec on the contract: "Single-asset yield vault. Shares track a pro-rata claim on every
asset the vault holds, including yield that a strategy keeper sends back to the vault."

## Mechanism
ERC-4626-like single-asset share vault, hand-rolled. Not a token: shares are `balanceOf` / `totalSupply`, with no
transfer or approval. No owner, no roles, no admin parameters, no fees, no oracle, no upgrade path.

## Assets and claims
| Asset | Who holds claims | Storage |
|---|---|---|
| `asset` (immutable ERC20, unknown token) held by the vault | share holders, pro rata | `balanceOf[user]`, `totalSupply` |

## Price and rate inputs
- Only one: `totalAssets() = asset.balanceOf(address(this))`, a **live balance**. Anyone can raise it by transferring
  the token directly to the vault. The "keeper yield" described in the NatSpec reaches the vault the same way (a plain
  transfer), so yield and donation are indistinguishable.
- No strategy or keeper code exists in this repo. How assets leave the vault for a strategy is not visible.

## Conversions
| Function | Formula | Rounding | Beneficiary |
|---|---|---|---|
| `convertToShares` (deposit) | `assets * supply / totalAssets()`, `supply == 0 ? assets` | down | vault (good) |
| `convertToAssets` (redeem) | `shares * totalAssets() / supply`, `supply == 0 ? shares` | down | vault (good) |

No virtual shares or offset, no minimum first deposit, no zero-share revert on deposit.

## State-changing functions
- `deposit(assets, receiver)`: shares computed, then `transferFrom`, then `totalSupply += shares`,
  `balanceOf[receiver] += shares`. Shares are computed before the transfer (correct against pre-deposit balance).
- `redeem(shares, receiver)`: shares > 0 required, assets computed, balances reduced, then `transfer`.
  Checks-effects-interactions respected. `receiver` can be anyone; `msg.sender` must own the shares.

## Properties (P)
- P1 Solvency: `asset.balanceOf(vault) >= sum of convertToAssets(balanceOf[u])` for all users. Holds by construction
  (redeem pays a pro rata share of the live balance, so the last redeemer never hits a shortfall revert). With a
  fee-on-transfer token the loss is a lower share price (dilution), not insolvency (SWARM-003).
- P2 `totalSupply == sum(balanceOf)`. Holds: both updated by the same amounts in each path; no other writer.
- P3 No round trip profit: `redeem(deposit(x))` returns <= x. Holds absent outside balance changes (rounding is down both ways).
- P4 A depositor's shares are worth at least `assets - 1 share-unit` of what they paid, regardless of other users'
  actions. **Does not hold**: a donation can raise the price per share arbitrarily, so a deposit can mint 0 or few
  shares (SWARM-001).
- P5 Value arriving as yield accrues to those who were exposed to the vault before it arrived. **Does not hold**:
  no lockup, no streaming, price jumps in one transfer (SWARM-002).
- P6 Share price is finite and defined when `totalSupply > 0`. Holds with a plain token; `totalAssets() == 0` with
  `supply > 0` would make `deposit` divide by zero (needs the vault's balance to hit zero while shares exist; no path in
  this code does it).

## Boring paths checked
- Zero amounts: `deposit(0)` mints 0 shares, no effect; `redeem(0)` reverts. Max amounts: `assets * supply` overflow
  reverts under 0.8 checked math (DoS at ~2^128 magnitudes only).
- First depositor with `supply == 0` and a pre-existing balance: gets 1:1 shares and therefore the stray balance. The loser
  is whoever donated, no third-party harm.
- Last redeemer: leaves rounding dust (stays in vault, picked up by the next first depositor).
- No emergency withdraw, no admin parameter, no epochs in this code.
- Token behaviour: fee-on-transfer, rebasing, hooks, missing return value (see SWARM-003 and the rejected list).
