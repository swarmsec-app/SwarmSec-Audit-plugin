// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;

import {IERC20} from "./IERC20.sol";

/// @notice Pays out rewards approved off-chain. The backend signs an EIP-712 Claim for each reward a
///         user earns; anyone can submit the signature to pay the recipient.
contract RewardClaims {
    bytes32 private constant DOMAIN_TYPEHASH =
        keccak256("EIP712Domain(string name,string version,uint256 chainId,address verifyingContract)");
    bytes32 private constant CLAIM_TYPEHASH =
        keccak256("Claim(address to,uint256 amount,uint256 nonce,uint256 deadline)");
    // Upper bound for s from EIP-2; rejects the second, malleable form of each signature.
    uint256 private constant MAX_S = 0x7FFFFFFFFFFFFFFFFFFFFFFFFFFFFFFF5D576E7357A4501DDFE92F46681B20A0;

    IERC20 public immutable token;
    address public immutable signer;
    mapping(address => mapping(uint256 => bool)) public nonceUsed;

    event Claimed(address indexed to, uint256 amount, uint256 nonce);

    constructor(IERC20 token_, address signer_) {
        require(signer_ != address(0), "zero signer");
        token = token_;
        signer = signer_;
    }

    function domainSeparator() public view returns (bytes32) {
        return keccak256(
            abi.encode(DOMAIN_TYPEHASH, keccak256("RewardClaims"), keccak256("1"), block.chainid, address(this))
        );
    }

    function claim(address to, uint256 amount, uint256 nonce, uint256 deadline, bytes calldata signature)
        external
    {
        require(block.timestamp <= deadline, "expired");
        require(!nonceUsed[to][nonce], "nonce used");
        bytes32 structHash = keccak256(abi.encode(CLAIM_TYPEHASH, to, amount, nonce, deadline));
        bytes32 digest = keccak256(abi.encodePacked("\x19\x01", domainSeparator(), structHash));
        require(_recover(digest, signature) == signer, "invalid signature");
        nonceUsed[to][nonce] = true;
        require(token.transfer(to, amount), "transfer failed");
        emit Claimed(to, amount, nonce);
    }

    function _recover(bytes32 digest, bytes calldata signature) internal pure returns (address) {
        require(signature.length == 65, "bad signature length");
        bytes32 r = bytes32(signature[0:32]);
        bytes32 s = bytes32(signature[32:64]);
        uint8 v = uint8(signature[64]);
        require(uint256(s) <= MAX_S, "malleable signature");
        address recovered = ecrecover(digest, v, r, s);
        require(recovered != address(0), "invalid signature");
        return recovered;
    }
}
