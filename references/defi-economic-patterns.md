# DeFi economic patterns

For each mechanism: the properties that must hold, and the attack shapes that break them. Never assume
market data. State the market condition an attack needs ("a pool shallow enough that moving the price
by 2x costs less than the borrow").

## Vaults and share accounting (ERC-4626 style)

Properties:
- `convertToShares` rounds down and `convertToAssets` rounds down on redeem, up on mint/withdraw
  previews, so rounding always favours the vault.
- No sequence lets a depositor redeem more assets than they deposited plus their share of yield.
- `totalAssets()` cannot be moved cheaply by an outsider, or the share price tolerates it.

Attacks:
- First-depositor inflation: attacker mints 1 wei of shares, donates assets directly, and the next
  depositor's shares round to zero. Exploitable when `totalAssets` reads the live balance and there is
  neither a virtual offset nor a minimum first deposit nor a zero-share revert. A zero-share revert alone
  turns theft into griefing.
- Donation to manipulate the share price used by another protocol (collateral valuation).
- Rounding in the user's favour on `mint`/`withdraw`, repeated in a loop.
- Fee or yield accrual that can be triggered or skipped by the attacker around their own deposit.

## Lending, collateral and liquidation

Properties:
- After every action, each account's debt is within its borrow limit, or the action reverts.
- Liquidation is profitable for a liquidator whenever the account is unhealthy, and never possible while
  it is healthy.
- Interest accrues before any state that depends on it is read.
- Bad debt is recognised, not left as an unpayable balance that inflates `totalAssets`.

Attacks:
- Collateral valued from a manipulable source (spot price, `balanceOf` of a pool, vault share price).
- Decimal mismatches between token, oracle and debt unit.
- Withdrawing collateral or transferring it in a path that skips the health check.
- Self-liquidation for the bonus, liquidation at the boundary of rounding.
- Interest accrual skipped in one path, letting a user borrow against stale debt.

## Oracles

Check the source (Chainlink, TWAP, spot, custom keeper), the decimals of each feed, staleness
(`updatedAt` vs a heartbeat appropriate for that feed), round completeness, negative or zero answers,
L2 sequencer uptime where relevant, and what happens when the feed reverts (frozen protocol vs fallback).
Spot prices (`getReserves`, `slot0`) can be moved within one transaction; TWAPs only over their window.
A finding needs the path from the manipulated price to value leaving the protocol.

## AMMs and swaps

- Slippage limits set by the caller, not computed on-chain from the same manipulable state.
- Deadlines on user swaps.
- Reserve accounting vs actual balances (`sync`/`skim` style donations).
- Fee-on-transfer and rebasing tokens in pools.
- Rounding in invariant calculations that lets dust swaps extract value.

## Staking and rewards

Properties:
- Sum of user reward shares equals total shares; each user's shares equal their stake.
- Rewards accrued before any stake change (`updateReward` before balance changes).
- Reward debt reset whenever shares change, including in emergency and admin paths.

Attacks:
- A path that changes stake without notifying the reward accounting (emergency withdraw, direct
  transfer of receipt tokens, admin rescue).
- Staking just before a reward notification and leaving right after, when rewards are not streamed.
- Division by `totalShares == 0` or rewards notified with no stakers lost forever.
- Reward rate changes that apply retroactively.

## Governance and admin power

- Voting power measured at the current block (flash-loanable) rather than at a past snapshot.
- Proposal thresholds and quorum computed from manipulable supply.
- Timelock delays that can be set to zero by the role they constrain.
- Admin functions that can move user funds: report as trust assumptions unless the protocol claims
  otherwise.

## Cross-contract accounting

When two contracts keep books about the same thing (pool and distributor, vault and strategy, router
and pair), write the equality that should link them and find every path that changes one side. Each
path that skips the other side is a hypothesis. These bugs are invisible when each contract is reviewed
alone.

## Flash liquidity

A flash loan gives temporary capital within one transaction. It matters only when some state that
value depends on can be pushed and released within that transaction: spot prices, balances used as
prices, voting power without snapshots, share prices from live balances. Name that state.
