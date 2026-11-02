// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;

/// @notice Push oracle. A keeper posts USD prices; consumers read them through getPrice.
contract PriceOracle {
    uint256 public constant MAX_AGE = 1 hours;

    address public immutable updater;
    mapping(address => uint256) private prices;
    mapping(address => uint256) public updatedAt;

    event PriceSet(address indexed token, uint256 price);

    constructor(address updater_) {
        updater = updater_;
    }

    /// @param price USD price with 8 decimals.
    function setPrice(address token, uint256 price) external {
        require(msg.sender == updater, "not updater");
        require(price > 0, "zero price");
        prices[token] = price;
        updatedAt[token] = block.timestamp;
        emit PriceSet(token, price);
    }

    /// @return USD price of one whole token, normalised to 18 decimals for the perps integration.
    function getPrice(address token) external view returns (uint256) {
        require(block.timestamp - updatedAt[token] <= MAX_AGE, "stale price");
        return prices[token] * 1e10;
    }
}
