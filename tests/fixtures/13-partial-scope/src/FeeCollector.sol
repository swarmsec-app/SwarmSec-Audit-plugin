// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;

import {IERC20} from "./IERC20.sol";

/// @notice Accumulates protocol fees; the treasury sweeps them.
contract FeeCollector {
    address public immutable treasury;

    event Swept(address indexed token, uint256 amount);

    constructor(address treasury_) {
        require(treasury_ != address(0), "zero treasury");
        treasury = treasury_;
    }

    function sweep(address token) external {
        require(msg.sender == treasury, "not treasury");
        uint256 amount = IERC20(token).balanceOf(address(this));
        require(IERC20(token).transfer(treasury, amount), "transfer failed");
        emit Swept(token, amount);
    }
}
