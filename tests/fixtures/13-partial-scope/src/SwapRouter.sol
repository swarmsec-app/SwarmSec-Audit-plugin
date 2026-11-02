// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;

import {IPriceModule} from "@periphery/interfaces/IPriceModule.sol";
import {IERC20} from "./IERC20.sol";
import {FeeCollector} from "./FeeCollector.sol";

/// @notice Swaps between listed tokens at the price module's quote, minus a protocol fee.
contract SwapRouter {
    uint256 public constant FEE_BPS = 30;

    address public owner;
    IPriceModule public priceModule;
    FeeCollector public immutable feeCollector;
    mapping(address => bool) public listed;

    event Swapped(address indexed account, address tokenIn, address tokenOut, uint256 amountIn, uint256 amountOut);
    event PriceModuleSet(address module);

    modifier onlyOwner() {
        require(msg.sender == owner, "not owner");
        _;
    }

    constructor(IPriceModule priceModule_, FeeCollector feeCollector_) {
        owner = msg.sender;
        priceModule = priceModule_;
        feeCollector = feeCollector_;
    }

    function setListed(address token, bool isListed) external onlyOwner {
        listed[token] = isListed;
    }

    function setPriceModule(IPriceModule module) external onlyOwner {
        priceModule = module;
        emit PriceModuleSet(address(module));
    }

    function swap(address tokenIn, address tokenOut, uint256 amountIn, uint256 minAmountOut)
        external
        returns (uint256 amountOut)
    {
        require(listed[tokenIn] && listed[tokenOut], "not listed");
        require(tokenIn != tokenOut, "same token");
        uint256 fee = amountIn * FEE_BPS / 10_000;
        uint256 quoted = priceModule.quote(tokenIn, tokenOut, amountIn - fee);
        require(quoted >= minAmountOut, "slippage");
        amountOut = quoted;
        require(IERC20(tokenIn).transferFrom(msg.sender, address(this), amountIn), "transfer in failed");
        require(IERC20(tokenIn).transfer(address(feeCollector), fee), "fee transfer failed");
        require(IERC20(tokenOut).transfer(msg.sender, amountOut), "transfer out failed");
        emit Swapped(msg.sender, tokenIn, tokenOut, amountIn, amountOut);
    }
}
