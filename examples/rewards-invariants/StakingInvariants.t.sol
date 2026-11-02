// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;

import {IERC20} from "../../src/IERC20.sol";
import {StakingPool} from "../../src/StakingPool.sol";
import {RewardDistributor} from "../../src/RewardDistributor.sol";

interface Vm {
    function prank(address sender) external;
}

/// @dev Plain no-fee token. transferFrom ignores allowances: approvals are not under test.
contract MockToken is IERC20 {
    mapping(address => uint256) public balanceOf;

    function mint(address to, uint256 amount) external {
        balanceOf[to] += amount;
    }

    function transfer(address to, uint256 amount) external returns (bool) {
        balanceOf[msg.sender] -= amount;
        balanceOf[to] += amount;
        return true;
    }

    function transferFrom(address from, address to, uint256 amount) external returns (bool) {
        balanceOf[from] -= amount;
        balanceOf[to] += amount;
        return true;
    }
}

/// @dev The fuzzer calls only this contract. Reverting calls are ignored by the fuzzer, so inputs are
///      bounded to keep each action valid.
contract Handler {
    Vm internal constant vm = Vm(address(uint160(uint256(keccak256("hevm cheat code")))));

    address[3] public actors = [address(0xA1), address(0xA2), address(0xA3)];
    MockToken public immutable stakingToken;
    MockToken public immutable rewardToken;
    StakingPool public immutable pool;
    RewardDistributor public immutable distributor;

    constructor(MockToken s, MockToken r, StakingPool p, RewardDistributor d) {
        stakingToken = s;
        rewardToken = r;
        pool = p;
        distributor = d;
    }

    function _actor(uint256 seed) internal view returns (address) {
        return actors[seed % actors.length];
    }

    function stake(uint256 seed, uint256 amount) external {
        address a = _actor(seed);
        amount = amount % 1e24 + 1;
        stakingToken.mint(a, amount);
        vm.prank(a);
        pool.stake(amount);
    }

    function withdraw(uint256 seed, uint256 amount) external {
        address a = _actor(seed);
        uint256 bal = pool.balances(a);
        if (bal == 0) return;
        vm.prank(a);
        pool.withdraw(amount % bal + 1);
    }

    function emergencyWithdraw(uint256 seed) external {
        address a = _actor(seed);
        if (pool.balances(a) == 0) return;
        vm.prank(a);
        pool.emergencyWithdraw();
    }

    function claim(uint256 seed) external {
        vm.prank(_actor(seed));
        distributor.claim();
    }

    function notifyReward(uint256 amount) external {
        if (distributor.totalShares() == 0) return;
        amount = amount % 1e24 + 1;
        rewardToken.mint(address(this), amount);
        distributor.notifyReward(amount);
    }

    /// @dev Outsider sends tokens straight to the contracts; may break equalities, never inequalities.
    function donate(uint256 amount) external {
        amount = amount % 1e24 + 1;
        stakingToken.mint(address(pool), amount);
        rewardToken.mint(address(distributor), amount);
    }
}

contract StakingInvariants {
    MockToken internal stakingToken;
    MockToken internal rewardToken;
    StakingPool internal pool;
    RewardDistributor internal distributor;
    Handler internal handler;

    function setUp() public {
        stakingToken = new MockToken();
        rewardToken = new MockToken();
        pool = new StakingPool(stakingToken);
        distributor = new RewardDistributor(address(pool), rewardToken);
        pool.setDistributor(distributor);
        handler = new Handler(stakingToken, rewardToken, pool, distributor);
    }

    /// @dev Foundry reads this to restrict fuzzing to the handler.
    function targetContracts() public view returns (address[] memory targets) {
        targets = new address[](1);
        targets[0] = address(handler);
    }

    // Pool-local: totalStaked is the sum of balances.
    function invariant_poolTotalEqualsSumOfBalances() public view {
        uint256 sum;
        for (uint256 i; i < 3; i++) sum += pool.balances(handler.actors(i));
        require(sum == pool.totalStaked(), "totalStaked != sum(balances)");
    }

    // Pool-local: staked principal is always backed by tokens (donations may add surplus).
    function invariant_poolHoldsAllStakedTokens() public view {
        require(stakingToken.balanceOf(address(pool)) >= pool.totalStaked(), "pool insolvent");
    }

    // Distributor-local: totalShares is the sum of shares.
    function invariant_distributorTotalSharesEqualsSumOfShares() public view {
        uint256 sum;
        for (uint256 i; i < 3; i++) sum += distributor.shares(handler.actors(i));
        require(sum == distributor.totalShares(), "totalShares != sum(shares)");
    }

    // Cross-contract: every account's reward weight equals what it has staked.
    function invariant_sharesMirrorPoolBalances() public view {
        for (uint256 i; i < 3; i++) {
            address a = handler.actors(i);
            require(distributor.shares(a) == pool.balances(a), "shares != pool balance");
        }
    }

    // Cross-contract: reward denominators match the pool's total.
    function invariant_totalSharesEqualsTotalStaked() public view {
        require(distributor.totalShares() == pool.totalStaked(), "totalShares != totalStaked");
    }

    // Reward solvency: the distributor can pay everything currently pending.
    function invariant_rewardsAreCovered() public view {
        uint256 owed;
        for (uint256 i; i < 3; i++) owed += distributor.pending(handler.actors(i));
        require(rewardToken.balanceOf(address(distributor)) >= owed, "rewards insolvent");
    }
}
