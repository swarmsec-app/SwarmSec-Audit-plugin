// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;

import {TestBase, TestToken} from "./TestBase.sol";
import {StakingProxy} from "fixtures/08-storage-layout-upgrade/v1/src/StakingProxy.sol";
import {StakingRewards as StakingV1} from "fixtures/08-storage-layout-upgrade/v1/src/StakingRewards.sol";
import {StakingRewards as StakingV2} from "fixtures/08-storage-layout-upgrade/v2/src/StakingRewards.sol";

interface IStaking {
    function initialize(address owner_, address stakingToken_) external;
    function stake(uint256 amount) external;
    function stakes(address account) external view returns (uint256);
    function totalStaked() external view returns (uint256);
    function stakingToken() external view returns (address);
    function owner() external view returns (address);
    function upgradeTo(address impl) external;
}

contract StorageLayoutTest is TestBase {
    address internal constant OWNER = address(0x5AFE);
    address internal constant USER = address(0xA11CE);
    address internal constant ATTACKER = address(0xBAD);

    function test_upgradeToV2_shiftsStorage() public {
        TestToken token = new TestToken();
        IStaking staking = IStaking(address(new StakingProxy(
            address(new StakingV1()), abi.encodeCall(IStaking.initialize, (OWNER, address(token)))
        )));
        token.mint(USER, 100e18);
        vm.startPrank(USER);
        token.approve(address(staking), 100e18);
        staking.stake(100e18);
        vm.stopPrank();
        assertEq(staking.stakes(USER), 100e18, "staked under v1");

        address v2 = address(new StakingV2());
        vm.prank(OWNER);
        staking.upgradeTo(v2);

        assertEq(staking.stakes(USER), 0, "user stake reads as zero after upgrade");
        assertEq(staking.totalStaked(), 0, "totalStaked reads the old mapping slot");
        assertTrue(staking.stakingToken() == address(uint160(100e18)), "stakingToken reads old totalStaked");
        vm.prank(ATTACKER);
        staking.initialize(ATTACKER, address(token));
        assertTrue(staking.owner() == ATTACKER, "initialized flag moved; anyone can re-initialize");
    }
}
