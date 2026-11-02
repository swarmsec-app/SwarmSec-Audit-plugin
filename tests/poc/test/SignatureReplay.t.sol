// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;

import {TestBase, TestToken} from "./TestBase.sol";
import {IERC20} from "fixtures/06-signature-replay/src/IERC20.sol";
import {RewardClaims} from "fixtures/06-signature-replay/src/RewardClaims.sol";
import {IERC20 as PIERC20} from "fixtures/06-signature-replay-patched/src/IERC20.sol";
import {RewardClaims as PatchedClaims} from "fixtures/06-signature-replay-patched/src/RewardClaims.sol";

contract SignatureReplayTest is TestBase {
    uint256 internal constant SIGNER_KEY = 0xA11CE5;
    address internal constant USER = address(0xC0FFEE);

    function _sig(bytes32 digest) internal returns (bytes memory) {
        (uint8 v, bytes32 r, bytes32 s) = vm.sign(SIGNER_KEY, digest);
        return abi.encodePacked(r, s, v);
    }

    function test_vulnerable_sameSignatureClaimedTwice() public {
        TestToken token = new TestToken();
        RewardClaims claims = new RewardClaims(IERC20(address(token)), vm.addr(SIGNER_KEY));
        token.mint(address(claims), 1_000e18);
        bytes32 digest = keccak256(
            abi.encodePacked("\x19Ethereum Signed Message:\n32", keccak256(abi.encodePacked(USER, uint256(100e18))))
        );
        bytes memory sig = _sig(digest);
        claims.claim(USER, 100e18, sig);
        claims.claim(USER, 100e18, sig);
        assertEq(token.balanceOf(USER), 200e18, "one approval paid twice");
    }

    function test_patched_replayRejected() public {
        vm.warp(1_000);
        TestToken token = new TestToken();
        PatchedClaims claims = new PatchedClaims(PIERC20(address(token)), vm.addr(SIGNER_KEY));
        token.mint(address(claims), 1_000e18);
        bytes32 structHash = keccak256(
            abi.encode(
                keccak256("Claim(address to,uint256 amount,uint256 nonce,uint256 deadline)"),
                USER, uint256(100e18), uint256(7), uint256(2_000)
            )
        );
        bytes memory sig = _sig(keccak256(abi.encodePacked("\x19\x01", claims.domainSeparator(), structHash)));
        claims.claim(USER, 100e18, 7, 2_000, sig);
        vm.expectRevert(bytes("nonce used"));
        claims.claim(USER, 100e18, 7, 2_000, sig);
        assertEq(token.balanceOf(USER), 100e18, "paid once");
    }
}
