// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;

import {IERC20} from "./IERC20.sol";

/// @notice Streams reward tokens to stakers of a StakingPool, pro rata to their stake.
///         The pool reports every stake change through onStake/onUnstake.
contract RewardDistributor {
    uint256 private constant PRECISION = 1e18;

    address public immutable pool;
    IERC20 public immutable rewardToken;
    uint256 public totalShares;
    uint256 public accRewardPerShare;
    mapping(address => uint256) public shares;
    mapping(address => uint256) public rewardDebt;

    event RewardAdded(uint256 amount);
    event RewardPaid(address indexed account, uint256 amount);

    modifier onlyPool() {
        require(msg.sender == pool, "only pool");
        _;
    }

    constructor(address pool_, IERC20 rewardToken_) {
        pool = pool_;
        rewardToken = rewardToken_;
    }

    function notifyReward(uint256 amount) external {
        require(totalShares > 0, "no stakers");
        require(rewardToken.transferFrom(msg.sender, address(this), amount), "transfer failed");
        accRewardPerShare += amount * PRECISION / totalShares;
        emit RewardAdded(amount);
    }

    function onStake(address account, uint256 amount) external onlyPool {
        _harvest(account);
        shares[account] += amount;
        totalShares += amount;
        rewardDebt[account] = shares[account] * accRewardPerShare / PRECISION;
    }

    function onUnstake(address account, uint256 amount) external onlyPool {
        _harvest(account);
        shares[account] -= amount;
        totalShares -= amount;
        rewardDebt[account] = shares[account] * accRewardPerShare / PRECISION;
    }

    function claim() external {
        _harvest(msg.sender);
        rewardDebt[msg.sender] = shares[msg.sender] * accRewardPerShare / PRECISION;
    }

    function pending(address account) public view returns (uint256) {
        return shares[account] * accRewardPerShare / PRECISION - rewardDebt[account];
    }

    function _harvest(address account) private {
        uint256 amount = pending(account);
        if (amount > 0) {
            require(rewardToken.transfer(account, amount), "transfer failed");
            emit RewardPaid(account, amount);
        }
    }
}
