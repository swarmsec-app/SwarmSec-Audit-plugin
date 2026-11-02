// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;

import {TestBase, TestToken} from "./TestBase.sol";
import {IERC20 as IERC20V1} from "fixtures/15-diff-caller-break/v1/src/IERC20.sol";
import {PriceOracle as OracleV1} from "fixtures/15-diff-caller-break/v1/src/PriceOracle.sol";
import {LendingMarket as MarketV1} from "fixtures/15-diff-caller-break/v1/src/LendingMarket.sol";
import {IERC20 as IERC20V2} from "fixtures/15-diff-caller-break/v2/src/IERC20.sol";
import {PriceOracle as OracleV2} from "fixtures/15-diff-caller-break/v2/src/PriceOracle.sol";
import {LendingMarket as MarketV2} from "fixtures/15-diff-caller-break/v2/src/LendingMarket.sol";

interface IMarket {
    function depositCollateral(uint256 amount) external;
    function borrow(uint256 amount) external;
    function maxDebt(address account) external view returns (uint256);
}

contract DiffCallerBreakTest is TestBase {
    address internal constant BORROWER = address(0xB0B);

    function _setup(address oracle, address market, TestToken collateral, TestToken stable) internal {
        OracleV1(oracle).setPrice(address(collateral), 2e8);
        stable.mint(market, 1_000_000e18);
        collateral.mint(BORROWER, 1e18);
        vm.startPrank(BORROWER);
        collateral.approve(market, 1e18);
        IMarket(market).depositCollateral(1e18);
        vm.stopPrank();
    }

    function test_v1_limitIsSeventyPercentOfTwoDollars() public {
        TestToken collateral = new TestToken();
        TestToken stable = new TestToken();
        OracleV1 oracle = new OracleV1(address(this));
        MarketV1 market = new MarketV1(IERC20V1(address(collateral)), 18, IERC20V1(address(stable)), oracle);
        _setup(address(oracle), address(market), collateral, stable);
        assertEq(market.maxDebt(BORROWER), 1.4e18, "1 token at $2, 70% LTV");
    }

    function test_v2_unchangedMarketOvervaluesAndIsDrained() public {
        TestToken collateral = new TestToken();
        TestToken stable = new TestToken();
        OracleV2 oracle = new OracleV2(address(this));
        MarketV2 market = new MarketV2(IERC20V2(address(collateral)), 18, IERC20V2(address(stable)), oracle);
        _setup(address(oracle), address(market), collateral, stable);
        assertEq(market.maxDebt(BORROWER), 1.4e28, "limit inflated by 1e10");
        vm.prank(BORROWER);
        market.borrow(1_000_000e18);
        assertEq(stable.balanceOf(BORROWER), 1_000_000e18, "whole reserve borrowed against $2 of collateral");
    }
}
