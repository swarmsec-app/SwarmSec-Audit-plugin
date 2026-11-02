// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;

import {TestBase, TestToken} from "./TestBase.sol";
import {LendingMarket, IERC20, AggregatorV3Interface} from "fixtures/05-oracle-scaling/src/LendingMarket.sol";

contract MockFeed {
    uint8 public decimals;
    int256 public answer;
    uint256 public updatedAt;

    constructor(uint8 decimals_, int256 answer_, uint256 updatedAt_) {
        decimals = decimals_;
        answer = answer_;
        updatedAt = updatedAt_;
    }

    function latestRoundData() external view returns (uint80, int256, uint256, uint256, uint80) {
        return (1, answer, updatedAt, updatedAt, 1);
    }
}

contract OracleScalingTest is TestBase {
    TestToken internal stable;
    TestToken internal collateral;
    LendingMarket internal market;

    function setUp() public {
        vm.warp(30 days);
        stable = new TestToken();
        collateral = new TestToken();
        market = new LendingMarket(IERC20(address(stable)));
    }

    function test_vulnerable_eighteenDecimalFeedInflatesValue() public {
        // A $2 asset quoted by an 18-decimal USD feed.
        MockFeed feed = new MockFeed(18, 2e18, block.timestamp);
        market.setFeed(address(collateral), AggregatorV3Interface(address(feed)));
        assertEq(market.usdValue(address(collateral), 1e18), 2e28, "1 token valued at $2e10");
    }

    function test_vulnerable_staleAnswerAccepted() public {
        MockFeed feed = new MockFeed(8, 2e8, block.timestamp - 7 days);
        market.setFeed(address(collateral), AggregatorV3Interface(address(feed)));
        assertEq(market.usdValue(address(collateral), 1e18), 2e18, "week-old price still used");
    }
}
