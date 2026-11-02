// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;

/// @notice ERC-20 transfers that accept tokens returning nothing and revert on `false` or a failed call.
library SafeTransfer {
    function safeTransfer(address token, address to, uint256 amount) internal {
        _call(token, abi.encodeWithSignature("transfer(address,uint256)", to, amount));
    }

    function safeTransferFrom(address token, address from, address to, uint256 amount) internal {
        _call(token, abi.encodeWithSignature("transferFrom(address,address,uint256)", from, to, amount));
    }

    function _call(address token, bytes memory payload) private {
        (bool ok, bytes memory data) = token.call(payload);
        require(ok && (data.length == 0 || abi.decode(data, (bool))), "token transfer failed");
        require(data.length > 0 || token.code.length > 0, "token has no code");
    }
}
