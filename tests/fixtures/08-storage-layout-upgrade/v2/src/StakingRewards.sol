// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;

import {IERC20} from "./IERC20.sol";

/// @notice Upgradeable staking contract (UUPS) deployed behind StakingProxy.
///         V2 adds an emergency pause and a configurable reward rate.
contract StakingRewards {
    bytes32 internal constant IMPLEMENTATION_SLOT = 0x360894a13ba1a3210667c828492db98dca3e2076cc3735a920a3ca505d382bbc;

    address public owner;
    uint256 public rewardRate;
    IERC20 public stakingToken;
    uint256 public totalStaked;
    mapping(address => uint256) public stakes;
    bool private initialized;
    bool public paused;

    event Staked(address indexed account, uint256 amount);
    event Unstaked(address indexed account, uint256 amount);
    event Upgraded(address indexed implementation);
    event RewardRateSet(uint256 rate);

    modifier onlyOwner() {
        require(msg.sender == owner, "not owner");
        _;
    }

    modifier whenNotPaused() {
        require(!paused, "paused");
        _;
    }

    constructor() {
        initialized = true;
    }

    function initialize(address owner_, IERC20 stakingToken_) external {
        require(!initialized, "already initialized");
        initialized = true;
        owner = owner_;
        stakingToken = stakingToken_;
    }

    function stake(uint256 amount) external whenNotPaused {
        require(amount > 0, "zero amount");
        require(stakingToken.transferFrom(msg.sender, address(this), amount), "transfer failed");
        stakes[msg.sender] += amount;
        totalStaked += amount;
        emit Staked(msg.sender, amount);
    }

    function unstake(uint256 amount) external {
        stakes[msg.sender] -= amount;
        totalStaked -= amount;
        require(stakingToken.transfer(msg.sender, amount), "transfer failed");
        emit Unstaked(msg.sender, amount);
    }

    function setPaused(bool paused_) external onlyOwner {
        paused = paused_;
    }

    function setRewardRate(uint256 rate) external onlyOwner {
        rewardRate = rate;
        emit RewardRateSet(rate);
    }

    function upgradeTo(address newImplementation) external onlyOwner {
        require(newImplementation.code.length > 0, "not a contract");
        assembly {
            sstore(IMPLEMENTATION_SLOT, newImplementation)
        }
        emit Upgraded(newImplementation);
    }
}
