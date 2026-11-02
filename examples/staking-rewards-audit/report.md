# Security review: rewards

This report comes from an automated, model-assisted review. It is not a formal audit, and the absence of findings does not show that the code is safe.

| | |
|---|---|
| Run | `20261101T171953Z` (audit) |
| Revision | `b2c1666c771f` |
| Generated | 2026-11-01T22:18:21+00:00 |
| Build | foundry, compiler 0.8.24, not-attempted |

## Summary

2 substantiated finding(s) in the reviewed scope (1 high, 1 low).

1 high · 1 low

| ID | Severity | Status | Title | Location |
|---|---|---|---|---|
| [SWARM-001](#swarm-001-emergencywithdraw-leaves-phantom-shares-in-rewarddistributor-letting-anyone-farm-rewards-with-no-stake) | high | reproduced | emergencyWithdraw leaves phantom shares in RewardDistributor, letting anyone farm rewards with no stake | `src/StakingPool.sol:51-53` |
| [SWARM-003](#swarm-003-rewards-are-paid-instantly-to-current-shares-so-just-in-time-stakers-capture-third-party-notifyreward-batches) | low | supported | Rewards are paid instantly to current shares, so just-in-time stakers capture third-party notifyReward batches | `src/RewardDistributor.sol:31-35` |
| [SWARM-002](#swarm-002-reward-transfer-happens-before-rewarddebt-is-updated-so-a-hook-capable-reward-token-allows-re-entrant-double-claims) | low | unresolved | Reward transfer happens before rewardDebt is updated, so a hook-capable reward token allows re-entrant double claims | `src/RewardDistributor.sol:62-64` |
| [SWARM-004](#swarm-004-pool-and-distributor-wiring-is-not-cross-checked-and-rewardtoken-may-equal-stakingtoken) | informational | unresolved | Pool and distributor wiring is not cross-checked, and rewardToken may equal stakingToken | `src/StakingPool.sol:24-28` |

## Scope

- included: `.`

## Protocol context

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

## Findings

### SWARM-001: emergencyWithdraw leaves phantom shares in RewardDistributor, letting anyone farm rewards with no stake

**High** · high confidence · reproduced · rewards · attacker: unprivileged

Affected: `StakingPool.emergencyWithdraw`, `RewardDistributor.onStake`, `RewardDistributor.claim`

StakingPool.emergencyWithdraw zeroes the caller's balance and returns the tokens but never calls distributor.onUnstake, so RewardDistributor.shares[user] and totalShares keep the old stake. The user can stake again and repeat, growing shares by the stake size each loop while the capital is returned every time.

**Impact.** An attacker with a small amount of capital (or a flash loan) inflates their shares without bound and captures almost all later notifyReward distributions, while holding no stake. Honest stakers are diluted toward zero (with 1000 honest and 1000 attacker stake, a reward of 100 splits 50/50 at one cycle, about 91/9 at ten cycles, 99/1 at one hundred). Principal is not at risk, and the loss is limited to rewards. Rewards can also accrue to phantom holders only if totalStaked reaches 0.

**Preconditions.**
- RewardDistributor is wired in and rewards are being notified (notifyReward) while the attacker holds phantom shares
- Attacker holds or can borrow some staking token

**Evidence.**

1. `src/StakingPool.sol:51-53` *source*: emergencyWithdraw clears pool balances and returns tokens but makes no call to distributor.onUnstake, so the distributor ledger is not reduced.

   ```solidity
   balances[msg.sender] = 0;
   totalStaked -= amount;
   require(stakingToken.transfer(msg.sender, amount), "transfer failed");
   ```

2. `src/RewardDistributor.sol:40-41` *source*: stake reports the amount to the distributor, which only ever adds to shares and totalShares; nothing compares shares to pool balances.

   ```solidity
   shares[account] += amount;
   totalShares += amount;
   ```

3. `src/RewardDistributor.sol:52-55` *source*: claim pays out on distributor shares alone, with no check that the caller still has a pool balance.

   ```solidity
   function claim() external {
       _harvest(msg.sender);
       rewardDebt[msg.sender] = shares[msg.sender] * accRewardPerShare / PRECISION;
   }
   ```

4. `src/RewardDistributor.sol:34` *call-path*: stake(C) -> onStake adds C shares; emergencyWithdraw returns C tokens, shares unchanged; stake(C) again -> shares 2C; repeat N times. notifyReward divides by the inflated totalShares and claim pays on the inflated shares.

   ```solidity
   accRewardPerShare += amount * PRECISION / totalShares;
   ```

5. *test*: test_phantomSharesCaptureRewards: 10 stake/emergencyWithdraw cycles of 1000 leave the attacker with 0 pool balance, all 1000 tokens back, shares == 10000 and totalShares == 11000 against totalStaked == 1000. After notifyReward(1100) the attacker claims 1000 and the honest staker 100. Control test_control_withdrawLoopEarnsNothing: the same loop through withdraw() leaves shares == 0, totalShares == totalStaked, attacker reward 0, honest reward 1100. Both pass. (tool run TR-001)
6. *reasoning*: No revert blocks the loop: rewardDebt is always set to floor(shares*acc/1e18) at the current acc, and acc never decreases, so pending never underflows. withdraw after an emergencyWithdraw reverts on the balances underflow, which only stops the attacker taking extra tokens.

**Reproduction** (foundry-test, local, tool run TR-001): demonstrated.

`forge test --match-path test/swarmsec/PhantomShares.t.sol -vvv`

Assertions:
- pool.balances(attacker) == 0 and stakeToken.balanceOf(attacker) == 1000 after 10 cycles
- distributor.shares(attacker) == 10000 and distributor.totalShares() == 11000 while pool.totalStaked() == 1000
- after notifyReward(1100): attacker reward == 1000, honest reward == 100
- control (withdraw loop): shares(attacker) == 0, totalShares == totalStaked, attacker reward == 0, honest reward == 1100

**Verification** by finding-verifier: Traced end to end in source with no guard on the stake/emergencyWithdraw loop, then executed in a sandbox copy with plain mock ERC20s (TR-001): the attacker holds no stake yet captures 10/11 of the reward, while the withdraw() control leaves the ledger in sync.

Attempts to falsify:
- Looked for a revert when shares exceed balances in onStake, _harvest and pending: none, pending cannot underflow.
- Checked whether withdraw after emergencyWithdraw breaks honest users: it reverts only for the attacker (balances underflow); shares >= balances always holds so honest onUnstake cannot underflow.
- Checked for an overflow bound on shares: uint256, unreachable.
- Checked whether the attacker can push the reward balance below honest pending: the ledger stays solvent, so honest withdraw reverting after a drain was not supported and was dropped from the impact.

**Remediation.** Call distributor.onUnstake(msg.sender, amount) in emergencyWithdraw (StakingPool.sol:48-55) so the ledger stays equal to the pool. If the exit must work when the reward-token transfer can revert, give the distributor a forced-exit function that burns shares without calling _harvest, and call that instead.

**Regression test.** stake(C), emergencyWithdraw(), then assert distributor.shares(user) == 0 and distributor.totalShares() == pool.totalStaked(). Also: after three stake/emergencyWithdraw loops, notifyReward(R) and claim() pay the user nothing.

**Limitations.**
- Test uses plain mock tokens (no fee-on-transfer, hooks or blocklists) and no fork; the real staking and reward tokens were not exercised.
- The 10/11 split is for 10 cycles against 1000 honest stake; it scales with cycles and honest stake, and the attacker needs no stake at claim time.
- The single-transaction flash-loan variant and the real size of the loss depend on the actual staking token and the reward amounts.

### SWARM-003: Rewards are paid instantly to current shares, so just-in-time stakers capture third-party notifyReward batches

**Low** · medium confidence · supported · economic · attacker: unprivileged

Affected: `RewardDistributor.notifyReward`

notifyReward is permissionless and raises accRewardPerShare immediately, with no vesting or time weighting. A staker can stake a large amount just before someone else's notifyReward, claim a pro-rata share and withdraw straight after. The contract comment says rewards 'stream' to stakers, but no streaming exists.

**Impact.** Reward value moves from long-term stakers to the just-in-time staker, in proportion to C/(C+H). Principal is not at risk and the capital is returned, so the cost is gas and opportunity cost. The attacker must hold capital across the victim's notifyReward transaction (MEV bundle or a predictable keeper schedule); a flash loan alone does not work.

**Preconditions.**
- A third party funds notifyReward at a time the attacker can predict or sandwich
- Attacker holds enough staking token to be a large share of totalShares

**Evidence.**

1. `src/RewardDistributor.sol:31-35` *source*: The full reward is added to accRewardPerShare at once, split over the shares present at that moment.

   ```solidity
   function notifyReward(uint256 amount) external {
       require(totalShares > 0, "no stakers");
       require(rewardToken.transferFrom(msg.sender, address(this), amount), "transfer failed");
       accRewardPerShare += amount * PRECISION / totalShares;
       emit RewardAdded(amount);
   ```

2. `src/RewardDistributor.sol:6` *source*: The NatSpec promises a stream, but nothing implements one.

   ```solidity
   /// @notice Streams reward tokens to stakers of a StakingPool, pro rata to their stake.
   ```

**Verification** by finding-verifier: Mechanism holds in source and there is no lock or delay. It is a recognised weakness of instant-distribution pools rather than an accounting bug, so severity stays low.

Attempts to falsify:
- Looked for vesting, lock or delay on stake/withdraw: none.
- Checked whether a flash loan suffices: no, the attacker must be staked across the victim's transaction.
- Checked whether the attacker gains by calling notifyReward itself: no, it pays R and gets back R*C/(C+H).

**Remediation.** Stream the reward over a period (rewardRate and periodFinish, updating accRewardPerShare with elapsed time), or document that rewards are instant and fund them in a way that cannot be front-run (private mempool or minimum stake duration).

**Regression test.** Stake H, notifyReward(R), then a second account stakes C, claims and withdraws in the same block as a later notifyReward: the second account's reward must be near zero.

**Limitations.**
- Who calls notifyReward and how predictably is outside the reviewed code.
- Not executed.

## Unresolved hypotheses

### SWARM-002: Reward transfer happens before rewardDebt is updated, so a hook-capable reward token allows re-entrant double claims

**Low** · low confidence · unresolved · reentrancy · attacker: external-dependency

Affected: `RewardDistributor._harvest`, `RewardDistributor.claim`

_harvest sends the reward token before its callers (claim, onStake, onUnstake) reset rewardDebt, and the contract has no reentrancy guard. If the reward token calls back into the recipient on transfer, the recipient can re-enter claim() and be paid the same pending amount repeatedly.

**Impact.** If the reward token has recipient hooks (ERC777-style), an attacker can drain the distributor's whole reward balance. With a plain ERC20 there is no impact. Severity is rated low until the token is known; it would be critical for a hook token.

**Preconditions.**
- rewardToken invokes a callback on the recipient during transfer
- Distributor holds a reward balance larger than the attacker's pending amount

**Evidence.**

1. `src/RewardDistributor.sol:62-64` *source*: The reward transfer is an external call made while rewardDebt and pending are still unchanged.

   ```solidity
   uint256 amount = pending(account);
   if (amount > 0) {
       require(rewardToken.transfer(account, amount), "transfer failed");
   ```

2. `src/RewardDistributor.sol:52-55` *call-path*: claim() -> _harvest (transfer, hook re-enters claim()) -> _harvest pays the same pending again; rewardDebt is only reset after _harvest returns.

   ```solidity
   function claim() external {
       _harvest(msg.sender);
       rewardDebt[msg.sender] = shares[msg.sender] * accRewardPerShare / PRECISION;
   }
   ```

**Verification** by finding-verifier: The ordering is real and unguarded, but exploitability depends on the reward token, which is not in the repository.

Attempts to falsify:
- Looked for a guard or checks-effects-interactions ordering in claim, onStake and onUnstake: none.
- Checked whether a plain IERC20.transfer can call back into the recipient: no, only hook tokens do.
- Checked the staking-token side: withdraw and emergencyWithdraw update state before transferring; stake has no exploitable stale state.

**Remediation.** In _harvest callers (or inside _harvest), set rewardDebt to the new value before the transfer, or add a nonReentrant guard to claim, onStake and onUnstake. Use SafeERC20 as well.

**Regression test.** With a mock reward token whose transfer calls claim() on the recipient, a single claim pays out exactly pending(account) once, and the distributor balance falls by that amount only.

**Limitations.**
- Reward token implementation is not part of the reviewed scope.
- Not executed.

### SWARM-004: Pool and distributor wiring is not cross-checked, and rewardToken may equal stakingToken

**Informational** · low confidence · unresolved · input-validation · attacker: admin

Affected: `StakingPool.setDistributor`, `RewardDistributor.constructor`

setDistributor is one-shot and does not check that the distributor's pool is this pool or that its reward token differs from stakingToken. The RewardDistributor constructor takes pool and rewardToken without validation. A wrong value is permanent because setDistributor cannot be called twice. Nothing stops rewardToken and stakingToken being the same token, which the accounting does not anticipate.

**Impact.** A deployment mistake bricks the pool (setDistributor cannot be repeated) or ties the distributor to the wrong pool. No attacker-triggerable loss was found; this is hardening.

**Preconditions.**
- The deployer sets a mismatched distributor, or deploys the distributor with a wrong pool or reward token

**Evidence.**

1. `src/StakingPool.sol:24-28` *source*: setDistributor stores any address once; it does not call distributor.pool() or check the reward token.

   ```solidity
   function setDistributor(RewardDistributor distributor_) external {
       require(msg.sender == deployer, "not deployer");
       require(address(distributor) == address(0), "already set");
       distributor = distributor_;
   }
   ```

**Verification** by finding-verifier: Raised by the verifier as a new, unverified observation; impact depends on deployment values not in the repository.

**Remediation.** In setDistributor require distributor_.pool() == address(this) and address(distributor_.rewardToken()) != address(stakingToken). Reject the zero address in the RewardDistributor constructor.

**Regression test.** setDistributor with a distributor built for another pool reverts; setDistributor with matching wiring succeeds once.

**Limitations.**
- Deployment script and token addresses are not part of the reviewed scope.
- The verifier did not examine this one in depth.

## Dismissed hypotheses

None recorded.

## Tool runs

| ID | Command | Version | Result | Time | Network |
|---|---|---|---|---|---|
| TR-001 | `forge test --match-path test/swarmsec/PhantomShares.t.sol -vvv --offline` | 1.5.1-stable | exit 0 | 1.1s | offline |

## Coverage gaps and limitations

- Staking and reward token implementations unknown; token-dependent hypotheses left unresolved.
- Deployment wiring and keeper behaviour for notifyReward not visible.
- Slither not installed: no static-analysis cross-check.
- Tools: anvil 1.5.1-stable, cast 1.5.1-stable, forge 1.5.1-stable; not installed: aderyn, contractmap, echidna, medusa, semgrep, slither, solc
