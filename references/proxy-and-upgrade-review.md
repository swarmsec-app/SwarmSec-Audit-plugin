# Proxy and upgrade review

## Identify the pattern

| Pattern | Implementation stored | Upgrade authorized in |
|---|---|---|
| Transparent (ERC-1967) | slot `0x3608...2bbc` | ProxyAdmin, via the proxy |
| UUPS (ERC-1967) | slot `0x3608...2bbc` | the implementation (`upgradeTo`, `_authorizeUpgrade`) |
| Beacon | beacon slot `0xa3f0...3d50`, then `beacon.implementation()` | the beacon owner |
| Diamond (EIP-2535) | per-selector facet mapping | `diamondCut`, usually owner |
| Minimal clone (EIP-1167) | bytecode, immutable | not upgradeable |
| Custom | wherever the code says | read it |

The scanner flags `erc1967-slot`, `delegating-fallback`, `upgrade-function:*` and `initializer:*`
hints. Confirm each by reading the code.

## Initialization

- Every initializer must be callable once on the proxy. Look for a working one-time flag (OpenZeppelin
  `initializer`, or a custom boolean that is set and checked).
- The proxy should be initialized in the deployment transaction (constructor data). If deployment and
  initialization are separate transactions, someone can front-run initialization.
- The implementation itself should be locked (`_disableInitializers()` or a constructor that sets the
  flag). This matters most when the implementation contains `selfdestruct` or `delegatecall`, or when
  UUPS `upgradeTo` on the implementation could be called by whoever initializes it.
- Reinitializers (`reinitializer(n)`) for new versions: check the version number increases and that
  new initialization cannot reset existing roles.

## Upgrade authorization

- UUPS: `_authorizeUpgrade` must be restricted. An implementation missing it (or `upgradeTo` without a
  check) lets anyone upgrade. A new implementation without the upgrade function bricks upgrades.
- Transparent: admin functions only through ProxyAdmin; the admin cannot also be a user of the proxy.
- Check what the upgrade role can do in one step versus through a timelock.

## Storage layout

When comparing two versions:
- Existing variables must keep their order, types and slot positions, across the whole inheritance
  chain (C3 linearisation order). Inserting a variable before existing ones, changing a type's size,
  reordering base contracts or removing a variable shifts every later slot.
- Appending at the end of the most derived contract is safe only if no child contract and no gap
  occupies those slots.
- `__gap` arrays in base contracts must shrink by exactly the number of slots added.
- Packed variables (`bool`, `uint8`, `address` sharing a slot) change position when neighbours change.
- Constants and immutables use no storage; moving them is harmless.
- A shifted one-time initialization flag reads as false after upgrade, so the initializer can be called
  again. Check this specifically.

`swarmsec diff` compares declaration order per contract lexically. When Foundry is available and the
user approved compiling, `forge inspect <Contract> storage-layout` gives exact slots for both versions.

## Diamonds

- Facets sharing storage must use namespaced storage (EIP-7201 or diamond storage structs) that do not
  overlap.
- `diamondCut` authorization, selector clashes, and initialization delegatecalls passed with cuts.
