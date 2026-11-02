# Severity and confidence

Severity says how bad the outcome is if the attack works. Confidence says how sure we are that it
works. Rate them separately: a reproduced bug that leaks dust is low severity, high confidence; an
untested path to draining the vault is high severity, maybe low confidence.

## Severity

Start from the impact, then move down for each constraint the attack needs.

| Severity | Impact | Typical constraints |
|---|---|---|
| critical | Direct loss or theft of user or protocol funds, unlimited minting, or permanent takeover of a privileged role | Unprivileged attacker, no unusual state, works now |
| high | Loss of funds that needs a plausible precondition, permanent freezing of funds, insolvency, takeover of an admin path | Some setup, a common token type, a reachable state |
| medium | Loss limited in size or time, temporary freezing, broken core accounting without direct theft, griefing that costs the attacker little | Specific configuration, privileged mistake, market condition |
| low | Small or bounded loss, recoverable errors, missing checks with a narrow impact | Unlikely configuration, admin action against their own interest |
| informational | No direct impact: hardening, clarity, events, defensive checks | — |

Move a level down when the attack needs:
- a privileged role to act maliciously or carelessly (unless the finding is that the role is
  reachable by someone it should not be);
- a deployment or configuration the project documents against;
- market conditions the protocol does not control and that are expensive to create;
- a victim to take an unusual action.

Do not move down because an attack is "complicated". Complexity costs an attacker time, not money.

Some rules that come up often:
- Anyone can call a function that moves funds or roles with no check: critical or high.
- An admin can rug users: report as a trust assumption (informational or low) unless the protocol
  claims admins cannot do it, then medium or higher.
- Reentrancy that only re-reads a stale view used by nobody: informational at most.
- External call before the state update (checks-effects-interactions not followed) where every function
  that could observe the stale state shares a working guard: informational. It becomes a finding only
  when you can name a reachable path the guard does not cover.
- Missing event, missing zero-address check on an admin setter: informational or low.
- Front-running that only changes who wins a fair race: not a finding.

## Confidence

| Confidence | Meaning |
|---|---|
| high | Reproduced by an executed test, or the path is short and every hop was read with no guard possible |
| medium | Traced end to end in source; depends on an assumption that is plausible but not checked (token type, deployment value) |
| low | Plausible but parts of the path are outside the reviewed code or depend on runtime state not seen |

A high or critical finding with low confidence should usually be `unresolved` rather than published.

## Status is not confidence

`reproduced`, `supported`, `unresolved` and `rejected` record what verification did. A `supported`
finding can have high confidence when the path is trivial; a `reproduced` finding normally has high
confidence unless the test modelled the environment loosely (then say so in `limitations`).
