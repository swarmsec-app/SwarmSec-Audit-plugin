# Security review: vault

This report comes from an automated, model-assisted review. It is not a formal audit, and the absence of findings does not show that the code is safe.

| | |
|---|---|
| Run | `20261101T172346Z` (defi-audit) |
| Revision | `98d69f4efe05` |
| Generated | 2026-11-01T22:18:22+00:00 |
| Build | foundry, compiler 0.8.24, not-attempted |

## Summary

3 substantiated finding(s) in the reviewed scope (1 high, 2 low).

1 high · 2 low

| ID | Severity | Status | Title | Location |
|---|---|---|---|---|
| [SWARM-001](#swarm-001-donation-inflation-deposit-can-mint-zero-shares-and-take-the-depositors-assets) | high | supported | Donation inflation: deposit can mint zero shares and take the depositor's assets | `src/ShareVault.sol:20-22` |
| [SWARM-002](#swarm-002-keeper-yield-arrives-as-a-lump-sum-balance-increase-so-just-in-time-depositors-capture-it) | low | supported | Keeper yield arrives as a lump-sum balance increase, so just-in-time depositors capture it | `src/ShareVault.sol:6-7` |
| [SWARM-003](#swarm-003-vault-assumes-a-plain-erc20-fee-on-transfer-dilutes-holders-no-return-tokens-brick-it) | low | supported | Vault assumes a plain ERC20: fee-on-transfer dilutes holders, no-return tokens brick it | `src/ShareVault.sol:35-38` |

## Scope

- included: `.`

## Protocol context

Scope: `src/ShareVault.sol` (50 lines, production), `src/IERC20.sol` (interface). No tests, no README or spec. The
only description is the NatSpec on the contract: "Single-asset yield vault. Shares track a pro-rata claim on every
asset the vault holds, including yield that a strategy keeper sends back to the vault."

#### Mechanism
ERC-4626-like single-asset share vault, hand-rolled. Not a token: shares are `balanceOf` / `totalSupply`, with no
transfer or approval. No owner, no roles, no admin parameters, no fees, no oracle, no upgrade path.

#### Assets and claims
| Asset | Who holds claims | Storage |
|---|---|---|
| `asset` (immutable ERC20, unknown token) held by the vault | share holders, pro rata | `balanceOf[user]`, `totalSupply` |

#### Price and rate inputs
- Only one: `totalAssets() = asset.balanceOf(address(this))`, a **live balance**. Anyone can raise it by transferring
  the token directly to the vault. The "keeper yield" described in the NatSpec reaches the vault the same way (a plain
  transfer), so yield and donation are indistinguishable.
- No strategy or keeper code exists in this repo. How assets leave the vault for a strategy is not visible.

#### Conversions
| Function | Formula | Rounding | Beneficiary |
|---|---|---|---|
| `convertToShares` (deposit) | `assets * supply / totalAssets()`, `supply == 0 ? assets` | down | vault (good) |
| `convertToAssets` (redeem) | `shares * totalAssets() / supply`, `supply == 0 ? shares` | down | vault (good) |

No virtual shares or offset, no minimum first deposit, no zero-share revert on deposit.

#### State-changing functions
- `deposit(assets, receiver)`: shares computed, then `transferFrom`, then `totalSupply += shares`,
  `balanceOf[receiver] += shares`. Shares are computed before the transfer (correct against pre-deposit balance).
- `redeem(shares, receiver)`: shares > 0 required, assets computed, balances reduced, then `transfer`.
  Checks-effects-interactions respected. `receiver` can be anyone; `msg.sender` must own the shares.

#### Properties (P)
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

#### Boring paths checked
- Zero amounts: `deposit(0)` mints 0 shares, no effect; `redeem(0)` reverts. Max amounts: `assets * supply` overflow
  reverts under 0.8 checked math (DoS at ~2^128 magnitudes only).
- First depositor with `supply == 0` and a pre-existing balance: gets 1:1 shares and therefore the stray balance. The loser
  is whoever donated, no third-party harm.
- Last redeemer: leaves rounding dust (stays in vault, picked up by the next first depositor).
- No emergency withdraw, no admin parameter, no epochs in this code.
- Token behaviour: fee-on-transfer, rebasing, hooks, missing return value (see SWARM-003 and the rejected list).

## Findings

### SWARM-001: Donation inflation: deposit can mint zero shares and take the depositor's assets

**High** · medium confidence · supported · rounding · attacker: unprivileged

Affected: `ShareVault.deposit`, `ShareVault.convertToShares`, `ShareVault.totalAssets`

Share price comes from the live token balance and shares round down, with no virtual offset, minimum first deposit or zero-share check. After a 1 wei first deposit, a direct token transfer raises the price so a later deposit of V mints 0 shares (or 1) while the vault still keeps all V.

**Impact.** A victim who deposits after the attacker's setup loses all (or a large part) of their deposit to the attacker, who redeems their share for the whole balance. With X = V = 1e18 the attacker spends 1e18+1 and receives 2e18+1.

**Preconditions.**
- totalSupply is tiny when the victim deposits (vault empty or just launched, or all other holders have redeemed); with supply S the donation needed is about V*S - totalAssets, so a seeded vault makes it uneconomic
- The asset is a standard ERC20 whose balanceOf rises on a direct transfer
- The attacker's deposit and donation land before the victim's deposit (bundling, or front-running a pending deposit)

**Evidence.**

1. `src/ShareVault.sol:20-22` *source*: totalAssets is the live token balance, so a plain transfer moves the share price.

   ```solidity
   function totalAssets() public view returns (uint256) {
       return asset.balanceOf(address(this));
   }
   ```

2. `src/ShareVault.sol:26` *source*: Shares round down with no offset or minimum, so a large totalAssets gives 0.

   ```solidity
   return supply == 0 ? assets : assets * supply / totalAssets();
   ```

3. `src/ShareVault.sol:35-38` *call-path*: deposit mints the computed shares even when zero and still pulls the full `assets`; there is no minShares argument.

   ```solidity
   shares = convertToShares(assets);
   require(asset.transferFrom(msg.sender, address(this), assets), "transfer failed");
   totalSupply += shares;
   balanceOf[receiver] += shares;
   ```

4. *reasoning*: Hand-computed: attacker deposits 1 (1 share), transfers X=1e18, victim deposits V=1e18: shares = floor(1e18*1/(1e18+1)) = 0. Attacker redeems 1 share for (X+1+V) = 2e18+1. Partial case X=1000, V=1500: victim gets 1 share, redeems 1250 of 1500; attacker spends 1001 and receives 1250.

**Verification** by finding-verifier: Path traced end to end in source; no zero-share revert, no minimum, no redeem guard stops the attacker's 1 share (redeem only requires shares > 0). Not executed: the user has not approved running tests.

Attempts to falsify:
- Looked for a zero-share revert or minShares in deposit: none.
- Checked redeem's `require(shares > 0)`: it only blocks redeeming 0 shares, not the attacker's 1.
- Checked checked-arithmetic overflow at these magnitudes: none.
- Checked a pre-seeded vault: the attack cost scales with totalSupply, so it needs tiny supply; that is recorded as a precondition.

**Remediation.** Add virtual shares and assets in the conversions (ERC-4626 decimals offset of 6 or more), or burn a minimum amount of shares on the first deposit, or both. Also revert in deposit when shares == 0 and add a minShares parameter. Track assets with an internal counter if donations must not move the price.

**Regression test.** Deposit 1 wei, donate 1e18 directly, then deposit 1e18 as a second user: the call reverts (or the victim can redeem at least 99.99% of 1e18); the attacker's redeem returns at most their own 1e18+1 less nothing from the victim.

**Limitations.**
- Not executed; hand-computed only.
- Deployment state is unknown: whether the vault is seeded at deploy, and who deposits first.

### SWARM-002: Keeper yield arrives as a lump-sum balance increase, so just-in-time depositors capture it

**Low** · medium confidence · supported · economic · attacker: unprivileged

Affected: `ShareVault.deposit`, `ShareVault.redeem`

Yield is a plain token transfer to the vault, which steps the share price up at once. There is no lockup, deposit fee, streaming or same-block guard, so an account that deposits before the keeper transfer and redeems after it takes yield pro rata to its capital without being exposed for any time.

**Impact.** Long-term holders are diluted. Example: honest holder has 1000 shares on 1000 assets; attacker deposits 1000, keeper sends 100, attacker redeems 1000 shares for 1050 and takes 50 of the 100 yield. In general the attacker captures Y*d/(A+d) of yield Y for a deposit d. No principal is lost.

**Preconditions.**
- The keeper transfers yield to the vault in discrete lumps (per NatSpec); the keeper code is not in this repo
- The attacker can order a deposit before and a redeem after the keeper transfer (sees it in the mempool, or knows the schedule)
- Profit exceeds the attacker's funding cost; capital can be borrowed for the transaction, but only if the loan fee is below the captured yield

**Evidence.**

1. `src/ShareVault.sol:6-7` *source*: NatSpec states the yield mechanism: it is sent to the vault and reflected through the pro-rata claim.

   ```solidity
   /// @notice Single-asset yield vault. Shares track a pro-rata claim on every asset the vault holds,
   ///         including yield that a strategy keeper sends back to the vault.
   ```

2. `src/ShareVault.sol:42-49` *call-path*: deposit mints at the pre-yield balance price and redeem pays at the post-yield price, with nothing between them and no restriction on either caller.

   ```solidity
   function redeem(uint256 shares, address receiver) external returns (uint256 assets) {
       require(shares > 0, "zero shares");
       assets = convertToAssets(shares);
       balanceOf[msg.sender] -= shares;
       totalSupply -= shares;
       require(asset.transfer(receiver, assets), "transfer failed");
       emit Withdraw(msg.sender, receiver, assets, shares);
   }
   ```

3. *reasoning*: Arithmetic above (1000/1000 holder, attacker 1000, yield 100): assets 2100 over 2000 shares, attacker redeems 1000 shares for 1050.

**Verification** by finding-verifier: Traced in source and hand-computed. No lockup, fee, streaming or access control exists in the 50 lines, and no keeper code is in the repo. Severity lowered by the verifier because only yield moves, never principal, and discrete-harvest vaults share this property.

Attempts to falsify:
- Searched for lockup, delay, fee, streaming and same-block guards: none.
- Searched for access control on deposit and redeem: none.
- Grepped for any keeper or strategy transfer in the repo: only the vault's own transfer calls at lines 36 and 47.

**Remediation.** Stream yield over a period (rewardRate style) instead of transferring it as a lump, or charge an entry/exit fee that stays in the vault, or enforce a minimum holding time. If the keeper submits through a private mempool and the amounts are small, document it as accepted.

**Regression test.** Second user deposits, the keeper transfers yield, the second user redeems in the same block: the second user's profit is at most the streamed share for zero elapsed time (zero), and the long-term holder keeps the full yield.

**Limitations.**
- Keeper size, cadence and submission method are unknown, so profitability is not quantified.
- Whether the behaviour is intended is unknown; the NatSpec does not promise yield to long-term holders only.
- Not executed; hand-computed only.

### SWARM-003: Vault assumes a plain ERC20: fee-on-transfer dilutes holders, no-return tokens brick it

**Low** · medium confidence · supported · token-integration · attacker: external-dependency

Affected: `ShareVault.deposit`, `ShareVault.redeem`

deposit credits shares for the nominal `assets` argument instead of the balance actually received, and both transfer calls are declared to return bool. The asset is an unknown immutable constructor argument, so behaviour depends on the token chosen.

**Impact.** With a 1% fee-on-transfer token, Bob's 1000 deposit (990 received) mints 1010 shares against Alice's 1000 for 990, shifting about 4.9 of value from Alice to Bob; the vault stays pro-rata solvent because redeem pays from the live balance, so the loss is dilution, not a failing last redemption. With a token that returns no data (USDT-style) every deposit and redeem reverts, so the vault is unusable (deposits revert before minting, so no funds are lost; direct transfers sent to it are stuck). A token whose balance reaches 0 while shares exist makes deposit divide by zero.

**Preconditions.**
- The vault is deployed with a fee-on-transfer, no-return-data, or balance-zeroing token as `asset`

**Evidence.**

1. `src/ShareVault.sol:35-38` *source*: Shares are computed from the nominal amount and the received amount is never measured.

   ```solidity
   shares = convertToShares(assets);
   require(asset.transferFrom(msg.sender, address(this), assets), "transfer failed");
   totalSupply += shares;
   balanceOf[receiver] += shares;
   ```

2. `src/IERC20.sol:6-7` *source*: The interface declares bool returns, so empty returndata fails ABI decoding.

   ```solidity
   function transfer(address to, uint256 amount) external returns (bool);
   function transferFrom(address from, address to, uint256 amount) external returns (bool);
   ```

3. *reasoning*: 1% fee: Alice 1000 in, vault +990, 1000 shares. Bob 1000 in, vault +990, floor(1000*1000/990) = 1010 shares. Assets 1980 over 2010 shares: Alice redeems 985, last holder gets 995 for 1010 shares. A round-trip attacker pays about 2% fees for about 0.5% gain, so it is not extractable.

**Verification** by finding-verifier: Traced in source and hand-computed. The claim that the last redeemer cannot withdraw was rejected: redeem pays shares*liveBalance/supply, which never exceeds the balance.

Attempts to falsify:
- Checked whether the last redeemer's transfer can fail for lack of balance: no, the payout is capped by the live balance.
- Checked whether a round-trip attacker profits from the fee-induced dilution: no, about 2% in fees for about 0.5% gained.
- Checked an ERC777 sender hook re-entering deposit or redeem: share price stays consistent apart from rounding, redeem follows checks-effects-interactions; nothing exploitable.

**Remediation.** Document that the asset must be a plain ERC20, or measure the balance before and after transferFrom and mint shares from the received amount. Use a safeTransfer/safeTransferFrom wrapper for tokens that return nothing.

**Regression test.** With a mock 1% fee token, two equal deposits mint equal shares and each can redeem within rounding of what the vault received; with a no-return-data mock token, deposit and redeem succeed.

**Limitations.**
- The asset address is not in the repo; the finding is conditional on the token chosen at deployment.
- Not executed; hand-computed only.

## Unresolved hypotheses

None.

## Dismissed hypotheses

None recorded.

## Tool runs

No tools were executed.

## Coverage gaps and limitations

- Slither not installed: no static-analysis cross-check.
- Tools: anvil 1.5.1-stable, cast 1.5.1-stable, forge 1.5.1-stable; not installed: aderyn, contractmap, echidna, medusa, semgrep, slither, solc
