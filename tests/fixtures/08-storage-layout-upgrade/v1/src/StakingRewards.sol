// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;

import {IERC20} from "./IERC20.sol";

/// @notice Upgradeable staking contract (UUPS) deployed behind StakingProxy.
contract StakingRewards {
    bytes32 internal constant IMPLEMENTATION_SLOT = 0x360894a13ba1a3210667c828492db98dca3e2076cc3735a920a3ca505d382bbc;

    address public owner;
    IERC20 public stakingToken;
    uint256 public totalStaked;
    mapping(address => uint256) public stakes;
    bool private initialized;

    event Staked(address indexed account, uint256 amount);
    event Unstaked(address indexed account, uint256 amount);
    event Upgraded(address indexed implementation);

    modifier onlyOwner() {
        require(msg.sender == owner, "not owner");
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

    function stake(uint256 amount) external {
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

    function upgradeTo(address newImplementation) external onlyOwner {
        require(newImplementation.code.length > 0, "not a contract");
        assembly {
            sstore(IMPLEMENTATION_SLOT, newImplementation)
        }
        emit Upgraded(newImplementation);
    }
}
