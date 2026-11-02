# Solidity threat model

Each section lists what to check, when it is exploitable, and the common reasons it is not. Use the
sections that apply to the code in front of you.

## Access control

Check: every state-changing entry point that moves value, sets a role, changes a parameter, pauses,
upgrades or initializes. Read the modifier body; a modifier named `onlyOwner` that does not compare
`msg.sender` protects nothing.

Exploitable when: the function is reachable by an account that should not reach it, directly or through
another contract that forwards calls (multicall, routers, `execute(target, data)` helpers), or when a
role can be granted by someone who should not grant it.

Not a finding when: the role is trusted by design and documented, the setter only affects the caller's
own position, or a second layer (timelock, multisig) is in the documented trust model.

Also check: two-step ownership transfer for critical roles, roles that can never be revoked, `tx.origin`
used for authorization, signature-based authorization (see Signatures).

## Reentrancy

Check every external call (low-level `call`, token transfers including ERC-777/ERC-1155/ERC-721 hooks,
calls to user-supplied addresses, callbacks such as flash-loan receivers). At the moment of the call,
list the state that is not yet updated.

Exploitable when: some function the callee can reach (the same one, another one, or another contract
that reads this state) behaves differently because of that stale state, and that difference moves value
or bypasses a check.

Not a finding when: every function that reads or writes the stale state shares a working guard, the
callee is fixed and trusted, the stale state is not used by anything reachable, or checked arithmetic
reverts the nested call before value moves.

Variants: cross-function (withdraw re-enters transfer), cross-contract (two contracts sharing
accounting), read-only (a view returns a stale price or share value that another protocol consumes).

## External calls and return values

- ERC-20 `transfer`/`transferFrom` that return `false` instead of reverting: is the return checked?
- Tokens that return nothing: a call through an interface declaring `returns (bool)` reverts, which is a
  denial of service for those tokens rather than theft.
- Low-level calls: is `success` checked? Is a call to an address with no code treated as success?
- Return data bombs and gas griefing: unbounded `returndatacopy` from untrusted callees.
- Calls to attacker-chosen targets with attacker-chosen data (`target.call(data)`): can they spend
  approvals the contract holds, or call the contract itself?

## delegatecall and arbitrary execution

`delegatecall` runs foreign code against this contract's storage and balance.
Exploitable when the target or the calldata is attacker-controlled, when the target's storage layout
differs, or when a self-`delegatecall` multicall lets `msg.value` be counted more than once in payable
functions.
Not a finding when the target is fixed (proxy implementation slot set by an authorized upgrade, or
`address(this)` in a contract with no payable functions).

## Initialization and upgrades

See `proxy-and-upgrade-review.md`. Short version: initializers must run once, on the proxy, in the same
transaction as deployment; implementations must not be initializable by strangers when that matters
(selfdestruct or delegatecall in the implementation); upgrades must be authorized and keep storage
layout.

## Arithmetic

- `unchecked` blocks: find the bound that makes each one safe. Loop counters and subtraction after an
  explicit `>=` check are fine.
- Casting down (`uint128(x)`) silently truncates in 0.8.x.
- Division before multiplication loses precision; check who benefits from the rounding.
- Decimals: values from tokens with 6, 8 and 18 decimals mixed in one formula; oracle answers with their
  own decimals.
- Solidity < 0.8: every unguarded `+ - *` is a candidate.

## Signatures

- The signed message must bind every field that matters: recipient, amount, nonce, deadline,
  `chainid`, verifying contract (EIP-712 domain).
- Replay: within the contract (no nonce or used-hash set), across chains (no `chainid`), across
  deployments (no contract address), across functions (same digest accepted by two functions).
- `ecrecover` returns `address(0)` for invalid signatures; compare against a signer that could be unset.
- Malleability only matters when the signature itself (not a nonce) is the replay key.
- `permit`: front-running a `permit` makes the victim's `permit` call revert; code that requires the
  `permit` call to succeed can be griefed.

## Denial of service

- Loops over arrays any user can grow.
- A single failing recipient blocking a batch payout (push vs pull).
- Reverting fallbacks of required recipients, blocklisted token recipients (USDC, USDT).
- State that an attacker can set to block others (front-running a unique key, dust that prevents
  closing a position, `require(balance == 0)` after a donation).

## Block context and time

- `block.timestamp` for deadlines is fine at the granularity of seconds to minutes.
- `blockhash`, `prevrandao`, timestamps as randomness: predictable or influenceable by validators.
- Epoch and accrual logic at boundaries: actions in the same block as an epoch change, zero elapsed time.

## Token assumptions

Ask which tokens the protocol accepts and what the docs promise. Then check behaviour with:
fee-on-transfer (credit the amount received), rebasing (stored balances drift), tokens with hooks
(reentrancy), tokens returning `false`, tokens with no return value, blocklists, pausable tokens,
upgradeable tokens, decimals other than 18, very large supplies.
