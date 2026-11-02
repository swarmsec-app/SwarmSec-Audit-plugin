// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;

import {IERC20} from "./IERC20.sol";
import {RewardDistributor} from "./RewardDistributor.sol";

/// @notice Holds staked tokens. Rewards are accounted by the RewardDistributor wired in at setup.
contract StakingPool {
    IERC20 public immutable stakingToken;
    address public immutable deployer;
    RewardDistributor public distributor;
    uint256 public totalStaked;
    mapping(address => uint256) public balances;

    event Staked(address indexed account, uint256 amount);
    event Withdrawn(address indexed account, uint256 amount);
    event EmergencyWithdrawn(address indexed account, uint256 amount);

    constructor(IERC20 stakingToken_) {
        stakingToken = stakingToken_;
        deployer = msg.sender;
    }

    function setDistributor(RewardDistributor distributor_) external {
        require(msg.sender == deployer, "not deployer");
        require(address(distributor) == address(0), "already set");
        distributor = distributor_;
    }

    function stake(uint256 amount) external {
        require(amount > 0, "zero amount");
        require(stakingToken.transferFrom(msg.sender, address(this), amount), "transfer failed");
        balances[msg.sender] += amount;
        totalStaked += amount;
        distributor.onStake(msg.sender, amount);
        emit Staked(msg.sender, amount);
    }

    function withdraw(uint256 amount) external {
        balances[msg.sender] -= amount;
        totalStaked -= amount;
        distributor.onUnstake(msg.sender, amount);
        require(stakingToken.transfer(msg.sender, amount), "transfer failed");
        emit Withdrawn(msg.sender, amount);
    }

    /// @notice Withdraw without touching rewards, for use if the distributor is ever stuck.
    function emergencyWithdraw() external {
        uint256 amount = balances[msg.sender];
        require(amount > 0, "nothing staked");
        balances[msg.sender] = 0;
        totalStaked -= amount;
        require(stakingToken.transfer(msg.sender, amount), "transfer failed");
        emit EmergencyWithdrawn(msg.sender, amount);
    }
}
