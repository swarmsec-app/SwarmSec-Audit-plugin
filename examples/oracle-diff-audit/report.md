# Security review: diff

This report comes from an automated, model-assisted review. It is not a formal audit, and the absence of findings does not show that the code is safe.

| | |
|---|---|
| Run | `20261101T173002Z` (diff-audit) |
| Revision | `3a85216e8307`, diff `HEAD~1..HEAD` |
| Generated | 2026-11-01T22:18:22+00:00 |
| Build | foundry, compiler 0.8.24, not-attempted |

## Summary

1 substantiated finding(s) in the reviewed scope (1 critical).

1 critical

| ID | Severity | Status | Title | Location |
|---|---|---|---|---|
| [SWARM-001](#swarm-001-getprice-now-returns-18-decimals-but-lendingmarketmaxdebt-still-scales-by-1e10-inflating-borrow-limits-1e10x) | critical | supported | getPrice now returns 18 decimals but LendingMarket.maxDebt still scales by 1e10, inflating borrow limits 1e10x | `src/PriceOracle.sol:30` |

## Scope

- included: `.`

## Protocol context

Not recorded.

## Findings

### SWARM-001: getPrice now returns 18 decimals but LendingMarket.maxDebt still scales by 1e10, inflating borrow limits 1e10x

**Critical** · high confidence · supported · oracle · attacker: unprivileged · introduced by this change

Affected: `LendingMarket.maxDebt`, `PriceOracle.getPrice`

Commit 3a85216 changed PriceOracle.getPrice to return prices[token] * 1e10 (18 decimals). LendingMarket.maxDebt, unchanged, still assumes an 8-decimal price and multiplies by another 1e10, so collateral value is overstated by a factor of 1e10.

**Impact.** Anyone can deposit a negligible amount of collateral and borrow up to the whole stablecoin balance held by the market. withdrawCollateral uses the same maxDebt, so almost all collateral can then be withdrawn while the debt stays, leaving the loan effectively unsecured.

**Preconditions.**
- The oracle price for the collateral token is fresh (updated within MAX_AGE of 1 hour)
- LendingMarket holds a stablecoin balance to borrow

**Evidence.**

1. `src/PriceOracle.sol:30` *source*: getPrice now multiplies the stored 8-decimal price by 1e10, so it returns 18 decimals. This is the only code change in the commit.

   ```solidity
   return prices[token] * 1e10;
   ```

2. `src/LendingMarket.sol:50-52` *source*: maxDebt still carries the comment and the 1e10 scaling that assumed an 8-decimal oracle price, so the price is scaled twice.

   ```solidity
   // Oracle prices have 8 decimals; scale to the stablecoin's 18.
   uint256 value = collateralOf[account] * oracle.getPrice(address(collateralToken)) * 1e10
       / (10 ** collateralDecimals);
   ```

3. `src/LendingMarket.sol:31-35` *call-path*: borrow -> maxDebt -> oracle.getPrice. borrow checks debtOf <= maxDebt (inflated 1e10x) and then transfers stable to the caller. depositCollateral and borrow have no access control.

   ```solidity
   function borrow(uint256 amount) external {
       debtOf[msg.sender] += amount;
       require(debtOf[msg.sender] <= maxDebt(msg.sender), "undercollateralised");
       require(stable.transfer(msg.sender, amount), "transfer failed");
   }
   ```

4. *reasoning*: With collateral of 18 decimals and a $2000 price stored as 2000e8, 1e10 wei of collateral gave a maxDebt of 1.4e13 wei (about $0.000014) before the commit. After it, the same deposit gives 1.4e23 wei (about $140k), exactly 1e10 times more. The multiplication cannot overflow for realistic amounts (about 2e49 against 2^256 of about 1.16e77).

**Verification** by finding-verifier: Traced end to end in source and by arithmetic; nothing in the path stops it. Not executed: the sandbox test was not run.

Attempts to falsify:
- Searched for other getPrice callers: LendingMarket.maxDebt is the only one in the repo, so nothing adjusts for the new scale.
- Checked for an overflow revert in the maxDebt multiplication: it only reverts at about 1e37 tokens, so it does not block the attack.
- Checked whether collateralDecimals absorbs the factor: it is only the divisor 10**collateralDecimals, so it cannot.
- Checked the stale and zero price guards: they only matter when the oracle is stale, so they are preconditions, not defences.
- Looked for a per-user borrow cap or other limit: none exists; the only limit is the stable balance in the market.
- Compared against HEAD~1: getPrice returned the raw 8-decimal price there and the 1e10 in maxDebt was correct, so this commit alone causes the break.

**Remediation.** Drop the extra scaling in LendingMarket.maxDebt (src/LendingMarket.sol:51-52): compute collateralOf[account] * oracle.getPrice(address(collateralToken)) / (10 ** collateralDecimals) and update the comment to say the price has 18 decimals. Alternatively keep getPrice at 8 decimals and add a separate 18-decimal getter for the perps integration.

**Regression test.** With a price of 2000e8 and 1e18 collateral deposited, maxDebt equals 1400e18, and borrow(1400e18 + 1) reverts with 'undercollateralised'.

**Limitations.**
- Not executed: the evidence is a source trace and arithmetic, not a passing Foundry test.
- Deployment was not checked: the attack needs a fresh oracle price and a stablecoin balance in the market.
- The perps integration that the commit message refers to is outside this repo and was not reviewed.

## Unresolved hypotheses

None.

## Dismissed hypotheses

None recorded.

## Tool runs

No tools were executed.

## Coverage gaps and limitations

- Slither not installed: no static-analysis cross-check.
- Tools: anvil 1.5.1-stable, cast 1.5.1-stable, forge 1.5.1-stable; not installed: aderyn, contractmap, echidna, medusa, semgrep, slither, solc
