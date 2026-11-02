// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;

import {TestBase, TestToken} from "./TestBase.sol";
import {StakingPool, IERC20} from "fixtures/09-nonstandard-token/src/StakingPool.sol";

/// @dev Burns 1% of every transfer.
contract FeeToken is TestToken {
    function transfer(address to, uint256 amount) public override returns (bool) {
        uint256 fee = amount / 100;
        balanceOf[msg.sender] -= amount;
        balanceOf[to] += amount - fee;
        return true;
    }

    function transferFrom(address from, address to, uint256 amount) public override returns (bool) {
        uint256 fee = amount / 100;
        allowance[from][msg.sender] -= amount;
        balanceOf[from] -= amount;
        balanceOf[to] += amount - fee;
        return true;
    }
}

/// @dev Returns false instead of reverting when a transfer cannot be made.
contract FalseReturningToken is TestToken {
    function transferFrom(address from, address to, uint256 amount) public override returns (bool) {
        if (balanceOf[from] < amount || allowance[from][msg.sender] < amount) return false;
        return super.transferFrom(from, to, amount);
    }
}

contract NonstandardTokenTest is TestBase {
    address internal constant ALICE = address(0xA11CE);
    address internal constant BOB = address(0xB0B);
    address internal constant ATTACKER = address(0xBAD);

    function _stake(TestToken token, StakingPool pool, address who, uint256 amount) internal {
        token.mint(who, amount);
        vm.startPrank(who);
        token.approve(address(pool), amount);
        pool.stake(amount);
        vm.stopPrank();
    }

    function test_feeOnTransfer_lastStakerCannotUnstake() public {
        FeeToken token = new FeeToken();
        StakingPool pool = new StakingPool(IERC20(address(token)));
        _stake(token, pool, ALICE, 100e18);
        _stake(token, pool, BOB, 100e18);
        assertEq(pool.totalStaked(), 200e18, "credited 200");
        assertEq(token.balanceOf(address(pool)), 198e18, "received 198");
        vm.prank(ALICE);
        pool.unstake(100e18);
        vm.prank(BOB);
        vm.expectRevert();
        pool.unstake(100e18);
    }

    function test_falseReturn_stakeCreditedWithoutTransfer() public {
        FalseReturningToken token = new FalseReturningToken();
        StakingPool pool = new StakingPool(IERC20(address(token)));
        _stake(token, pool, ALICE, 1_000e18);
        vm.startPrank(ATTACKER);
        pool.stake(1_000e18);
        pool.unstake(1_000e18);
        vm.stopPrank();
        assertEq(token.balanceOf(ATTACKER), 1_000e18, "attacker withdrew Alice's tokens");
        assertEq(token.balanceOf(address(pool)), 0, "pool empty while Alice is still credited");
    }
}
