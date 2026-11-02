I wrote six invariants for the two contracts and ran them. Four pass and two fail. Both failures come from one cause: `StakingPool.emergencyWithdraw` never tells the distributor.

## Result of the run

The run is recorded as `TR-001` in `.swarmsec-audit/runs/20261101T172502Z/tool-runs/TR-001.log`. It ran offline with 256 runs of depth 500, which is 128,000 calls per invariant.

| Invariant | Result |
|---|---|
| `invariant_poolTotalEqualsSumOfBalances` | pass |
| `invariant_poolHoldsAllStakedTokens` | pass |
| `invariant_distributorTotalSharesEqualsSumOfShares` | pass |
| `invariant_rewardsAreCovered` | pass |
| `invariant_sharesMirrorPoolBalances` | **fail** |
| `invariant_totalSharesEqualsTotalStaked` | **fail** |

A pass means the fuzzer found no counterexample in those calls. It is not a proof.

**Counterexample, shrunk to two calls:** `stake(x)` and then `emergencyWithdraw()` by the same actor.
- The pool zeroes `balances[a]` and lowers `totalStaked` (`StakingPool.sol:51-52`).
- It never calls `distributor.onUnstake`, so `shares[a]` and `totalShares` stay at the old value.
- The staker has their tokens back but keeps a reward weight, which the distributor still counts in `totalShares`.

I did not write a proof of concept for the impact. By reading the code, rewards are split across `totalShares`, which includes these phantom shares. So a phantom holder keeps earning, and real stakers get a smaller share of each `notifyReward`. Rewards stay covered, which is why that invariant passes. What breaks is fairness. Running `swarmsec-audit:verify` on this would confirm the impact.

## Properties

| # | Statement | Domain | Excluded states | Catches | Test type |
|---|---|---|---|---|---|
| P1 | `distributor.shares(u) == pool.balances(u)` for every user | both contracts, all actors | after `setDistributor`; tokens without fees | Pool and distributor drifting apart. This is the `emergencyWithdraw` bug. | invariant (fails) |
| P2 | `distributor.totalShares == pool.totalStaked` | both contracts | same as P1 | Same root cause as P1, seen through the reward denominator | invariant (fails) |
| P3 | `pool.totalStaked == sum(pool.balances)` | pool | none | A stake or withdraw path that updates one side only | invariant (passes) |
| P4 | `stakingToken.balanceOf(pool) >= totalStaked` | pool | donations may only add a surplus | Principal not backed by tokens | invariant (passes) |
| P5 | `distributor.totalShares == sum(distributor.shares)` | distributor | none | Share bookkeeping errors in `onStake` or `onUnstake` | invariant (passes) |
| P6 | `rewardToken.balanceOf(distributor) >= sum(pending(u))` | distributor | donations may only add a surplus; reward token must not be the staking token | Rounding or accumulator errors that leave rewards unpaid | invariant (passes) |

**Rejected, because they cannot fail:**
- `accRewardPerShare` never decreases. It is only ever `+=`.
- `onStake` and `onUnstake` are callable only by the pool. That restates the `onlyPool` modifier, so a unit test is enough.
- `setDistributor` can be called only once, by the deployer. This also restates a `require`, so a unit test is enough.

**Not covered, because the mock token is a plain no-fee ERC20:**
- Fee-on-transfer, rebasing and hook tokens.
- Reentrancy through the reward token. `_harvest` sends the transfer before `rewardDebt` is updated (`RewardDistributor.sol:52-55`), so a hook token would need its own test.

## Files and caveats
- The new file is `test/invariants/StakingInvariants.t.sol`. It holds a mock token, a handler with seven actions (stake, withdraw, emergency withdraw, claim, notify reward and donate, with inputs bounded) and the invariant contract.
- `lib/forge-std` isn't installed, so it uses the local `Vm` interface. Nothing was installed.
- The mock token's `transferFrom` ignores allowances, since approvals aren't under test.
- The run directory and the test file are untracked in git. I haven't committed anything.
