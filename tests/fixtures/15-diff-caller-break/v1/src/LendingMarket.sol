// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;

import {IERC20} from "./IERC20.sol";
import {PriceOracle} from "./PriceOracle.sol";

/// @notice Borrow a USD stablecoin (18 decimals) against one collateral token, up to 70% LTV.
contract LendingMarket {
    uint256 public constant LTV_BPS = 7_000;

    IERC20 public immutable collateralToken;
    uint8 public immutable collateralDecimals;
    IERC20 public immutable stable;
    PriceOracle public immutable oracle;

    mapping(address => uint256) public collateralOf;
    mapping(address => uint256) public debtOf;

    constructor(IERC20 collateralToken_, uint8 collateralDecimals_, IERC20 stable_, PriceOracle oracle_) {
        collateralToken = collateralToken_;
        collateralDecimals = collateralDecimals_;
        stable = stable_;
        oracle = oracle_;
    }

    function depositCollateral(uint256 amount) external {
        require(collateralToken.transferFrom(msg.sender, address(this), amount), "transfer failed");
        collateralOf[msg.sender] += amount;
    }

    function borrow(uint256 amount) external {
        debtOf[msg.sender] += amount;
        require(debtOf[msg.sender] <= maxDebt(msg.sender), "undercollateralised");
        require(stable.transfer(msg.sender, amount), "transfer failed");
    }

    function repay(uint256 amount) external {
        require(stable.transferFrom(msg.sender, address(this), amount), "transfer failed");
        debtOf[msg.sender] -= amount;
    }

    function withdrawCollateral(uint256 amount) external {
        collateralOf[msg.sender] -= amount;
        require(debtOf[msg.sender] <= maxDebt(msg.sender), "undercollateralised");
        require(collateralToken.transfer(msg.sender, amount), "transfer failed");
    }

    /// @return Maximum stablecoin debt (18 decimals) the account's collateral supports.
    function maxDebt(address account) public view returns (uint256) {
        // Oracle prices have 8 decimals; scale to the stablecoin's 18.
        uint256 value = collateralOf[account] * oracle.getPrice(address(collateralToken)) * 1e10
            / (10 ** collateralDecimals);
        return value * LTV_BPS / 10_000;
    }
}
