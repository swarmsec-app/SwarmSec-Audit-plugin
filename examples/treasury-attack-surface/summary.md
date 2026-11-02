# Attack-surface map: `src/` (2 files, Solidity ^0.8.24)

I read both contracts in full. `contractmap` isn't installed, so the inventory and my own read are the only sources. The inventory's access guesses match the code, with one that matters (`initialize`). No compiler is available (`solc` is absent), so nothing here was compiled or run.

## Entry points

| Contract.function | Access | Writes | External calls | File:lines |
|---|---|---|---|---|
| `TreasuryProxy.constructor` | deploy time only | impl slot | `delegatecall(initData)` to the implementation | `TreasuryProxy.sol:9-17` |
| `TreasuryProxy.fallback` / `receive` | **open** | whatever the implementation does, in proxy storage | `delegatecall` to the implementation | `TreasuryProxy.sol:19-37` |
| `TreasuryV1.initialize(owner_)` | **open, no one-time guard** | `owner`, `withdrawLimit` (reset to 100 ether) | none | `TreasuryV1.sol:21-26` |
| `TreasuryV1.pay(to, amount)` | restricted: `onlyOwner` (`TreasuryV1.sol:16-19`) | none | `to.call{value: amount}("")`, with `to` chosen by the owner | `TreasuryV1.sol:28-33` |
| `TreasuryV1.setWithdrawLimit(limit)` | restricted: `onlyOwner` | `withdrawLimit` | none | `TreasuryV1.sol:35-37` |
| `TreasuryV1.upgradeTo(newImpl)` | restricted: `onlyOwner` | impl slot (inline assembly) | none | `TreasuryV1.sol:39-45` |
| `TreasuryV1.receive` | open | none | none | `TreasuryV1.sol:47` |

Called through the proxy, `receive` is reached via the proxy's own `receive`, which delegates to it. That call just accepts ETH.

## Privileged roles, worst case first

There is one role, `owner` (storage slot 0). The only places it is set are `initialize` (`TreasuryV1.sol:23`) and the proxy constructor's init call. There is no `transferOwnership`, no two-step transfer, no timelock and no pause.

1. **`upgradeTo`** can point the proxy at any contract with code, which gives full control of treasury storage and balance.
2. **`pay` plus `setWithdrawLimit`** can move the whole balance. The limit applies per call, not cumulatively, and the owner can raise it without bound. So `withdrawLimit` is not a real cap against a malicious or compromised owner.
3. **`initialize`** is documented as setting the owner to a multisig, but nothing restricts who can call it (see below).

## Upgrade and initialization wiring

- **Pattern:** UUPS-style ERC-1967. The proxy stores the implementation in the standard slot (`TreasuryProxy.sol:7`), and the implementation authorizes upgrades (`upgradeTo`, owner-only). Both contracts use the same slot constant.
- **Storage layout:** the proxy declares no state variables. `owner` and `withdrawLimit` take slots 0 and 1 of the proxy, so they don't collide with the ERC-1967 slot. This was read from the declarations, not confirmed with `forge inspect`.
- **Initialization:** the doc comment says the proxy is initialized in the constructor, which avoids front-running at deployment. **But `initialize` has no initialized flag, no `initializer` modifier and no owner check.** It stays callable by anyone on the proxy forever, and it overwrites `owner` and resets `withdrawLimit`. This is the biggest issue on the surface.
- **Implementation not locked:** there is no constructor or `_disableInitializers`, so anyone can also call `initialize` on the bare implementation. I infer this has little impact today, because that contract has no `selfdestruct` or `delegatecall` and `upgradeTo` only writes its own slot. It matters if a later version adds either.
- **`upgradeTo` checks:** it only requires `code.length > 0`. There is no UUPS compatibility check (`proxiableUUID`-style), so upgrading to an implementation without an `upgradeTo` bricks future upgrades. Nothing in the tree prevents that.
- **Proxy constructor:** it doesn't check that `implementation` has code. A `delegatecall` to an address without code returns success, so a wrong address would skip initialization silently. This is moot given the open `initialize`.
- **No `upgradeToAndCall`:** a migration can't initialize in the same transaction as the upgrade.

## External calls by trust level

- **Fixed or trusted:** none.
- **Admin-configurable:** the implementation address in the slot (owner-controlled via `upgradeTo`). The proxy `delegatecall`s it on every call, so it is fully trusted.
- **Caller-supplied:** `pay`'s `to` is chosen by the owner. It is an arbitrary address with all gas forwarded, so it can re-enter. Re-entry would need `onlyOwner` to pass, and `pay` writes no state after the call. Reentrancy risk is therefore low unless the owner is a contract that calls `pay` again.
- **Callbacks:** none defined. The only inbound callback is ETH arriving in `receive`.

## Assumptions the source can't settle

- Who `owner` is (the comment says a multisig) and how that multisig is configured.
- Whether the real deployment initialized atomically through the constructor, as the comment says.
- The deployed implementation address and whether anything was initialized on it directly.
- Compiler settings and the exact storage layout, since neither is verified here.
- Whether any later `TreasuryV2` exists. There is none in this tree, so an upgrade review has nothing to compare against.

## Suggested follow-up

`TreasuryV1.initialize` looks directly exploitable. Anyone calls `initialize(attacker)`, becomes owner, raises the limit, and drains the balance with `pay` or upgrades to a malicious implementation. I haven't reproduced it. Run the `swarmsec-audit:audit` skill on `src/`, or `swarmsec-audit:verify` on this path, to confirm it. I wrote no findings here and no files.
