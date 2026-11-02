// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;

import {TestBase} from "./TestBase.sol";
import {RewardToken} from "fixtures/01-unauthorized-mint/src/RewardToken.sol";
import {RewardToken as PatchedToken} from "fixtures/01-unauthorized-mint-patched/src/RewardToken.sol";

contract UnauthorizedMintTest is TestBase {
    address internal constant BACKEND = address(0xB0B);
    address internal constant ATTACKER = address(0xBAD);

    function test_vulnerable_anyoneBecomesMinterAndMints() public {
        RewardToken token = new RewardToken(BACKEND);
        vm.startPrank(ATTACKER);
        token.setMinter(ATTACKER);
        token.mint(ATTACKER, 1_000_000e18);
        vm.stopPrank();
        assertTrue(token.minter() == ATTACKER, "attacker is minter");
        assertEq(token.balanceOf(ATTACKER), 1_000_000e18, "attacker minted supply");
    }

    function test_patched_setMinterRejectsStranger() public {
        PatchedToken token = new PatchedToken(BACKEND);
        vm.prank(ATTACKER);
        vm.expectRevert(bytes("not owner"));
        token.setMinter(ATTACKER);
    }
}
