# Security policy

## Reporting a problem in this plugin

Report vulnerabilities in SwarmSec Audit itself (the skills, agents, helper scripts or their safety
controls) privately to security@swarmsec.app, or through GitHub's "Report a vulnerability" form on
this repository. Please include the version, the command you ran and what happened. We aim to reply
within five working days.

In scope, for example:
- a way for content in an audited repository to make the plugin run commands, install packages,
  sign or send transactions, or write outside `.swarmsec-audit/`;
- `swarmsec.py run` accepting a command or flag it should refuse;
- credentials, RPC endpoints or local paths leaking into `report.md` or `report.json`;
- evidence validation accepting a location outside the project.

## Reporting a vulnerability you found with this plugin

Do not report third-party protocol vulnerabilities to us. Contact the affected project through its
own disclosure channel or bug bounty. Never test against live deployments you are not authorised to
test.

## What the plugin does not promise

The plugin's output is a model-assisted review, not a formal audit. "No substantiated findings" means
nothing in the reviewed scope survived verification; it does not mean the code is safe.
