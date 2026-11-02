# Context

**Protocol.** A staking pool with an external reward accountant. `StakingPool` (src/StakingPool.sol) holds
`stakingToken` and keeps `balances`/`totalStaked`. `RewardDistributor` (src/RewardDistributor.sol) keeps a
MasterChef-style `accRewardPerShare` / `rewardDebt` ledger over its own `shares`/`totalShares`. The pool
must report every stake change to the distributor (`onStake` / `onUnstake`, `onlyPool`). Rewards are
instant, not streamed: `notifyReward` raises `accRewardPerShare` immediately.

**Assets.** Staked tokens in the pool; reward tokens in the distributor (funded by anyone via `notifyReward`).

**Actors.**
- `deployer` (pool immutable): one-shot `setDistributor`. No other privileges. No owner, pause or upgrade.
- Stakers: `stake`, `withdraw`, `emergencyWithdraw`, `claim`.
- Anyone: `notifyReward` (needs reward tokens and approval), `claim`.

**Key invariant.** For every account `distributor.shares[a] == pool.balances[a]` and
`distributor.totalShares == pool.totalStaked`. Rewards are only correct while this holds.

**Trust assumptions / dependencies.** Both tokens are unspecified `IERC20` (no SafeERC20, return value
checked). Reward and staking tokens are assumed standard; fee-on-transfer, rebasing or hook tokens are
not handled. The distributor's `pool` and the pool's `distributor` are wired by hand with no cross-check.

**Attacker controls.** Any account can stake, withdraw, emergency-withdraw and claim at any time, and
can fund `notifyReward` to time reward injection.

**Not reviewed.** Deployment scripts, the actual token addresses, off-chain keepers that call `notifyReward`.
