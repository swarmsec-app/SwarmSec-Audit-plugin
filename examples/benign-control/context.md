# Context: SavingsAccount

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
