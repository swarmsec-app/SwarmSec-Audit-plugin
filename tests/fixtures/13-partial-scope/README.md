# Swap router

`SwapRouter` quotes swaps through a pluggable price module from the `periphery` package and settles
them from a liquidity reserve. `FeeCollector` receives protocol fees.

The `periphery` package is installed with `forge install` into `lib/periphery` and is not vendored in
this repository. `foundry.toml` maps `@periphery/` to it.
