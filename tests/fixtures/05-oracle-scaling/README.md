# Isolated lending market

Borrowers post one of the listed collateral tokens and borrow the market's stablecoin up to 75% of
the collateral's USD value. The owner lists collateral by registering a Chainlink USD price feed
for it. Any Chainlink USD feed can be registered.

Liquidations are handled by a separate keeper contract that is out of scope for this review.
