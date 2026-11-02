# Single-token staking pool

A pool is deployed once per token. Users stake the token and can unstake their full stake at any
time. The deployment script is used for any ERC-20 a partner protocol requests, including tokens
that charge a fee on transfer and older tokens that signal failure by returning `false`.
