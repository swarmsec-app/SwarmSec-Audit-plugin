// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;

import {IERC20} from "./IERC20.sol";

/// @notice Pays out rewards approved off-chain. The backend signs (recipient, amount) for each
///         reward a user earns; anyone can submit the signature to pay the recipient.
contract RewardClaims {
    IERC20 public immutable token;
    address public immutable signer;

    event Claimed(address indexed to, uint256 amount);

    constructor(IERC20 token_, address signer_) {
        require(signer_ != address(0), "zero signer");
        token = token_;
        signer = signer_;
    }

    function claim(address to, uint256 amount, bytes calldata signature) external {
        bytes32 digest = keccak256(
            abi.encodePacked("\x19Ethereum Signed Message:\n32", keccak256(abi.encodePacked(to, amount)))
        );
        require(_recover(digest, signature) == signer, "invalid signature");
        require(token.transfer(to, amount), "transfer failed");
        emit Claimed(to, amount);
    }

    function _recover(bytes32 digest, bytes calldata signature) internal pure returns (address) {
        require(signature.length == 65, "bad signature length");
        bytes32 r = bytes32(signature[0:32]);
        bytes32 s = bytes32(signature[32:64]);
        uint8 v = uint8(signature[64]);
        address recovered = ecrecover(digest, v, r, s);
        require(recovered != address(0), "invalid signature");
        return recovered;
    }
}
