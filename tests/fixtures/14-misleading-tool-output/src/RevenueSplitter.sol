// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;

/// @notice Splits ETH revenue between the treasury multisig and the staking contract, both fixed at
///         deployment. Anyone may trigger a distribution.
contract RevenueSplitter {
    uint256 public constant TREASURY_BPS = 4_000;

    address payable public immutable treasury;
    address payable public immutable stakingRewards;
    uint256 public lastDistribution;
    uint256 public distributions;

    event Distributed(uint256 toTreasury, uint256 toStaking);

    constructor(address payable treasury_, address payable stakingRewards_) {
        require(treasury_ != address(0) && stakingRewards_ != address(0), "zero address");
        treasury = treasury_;
        stakingRewards = stakingRewards_;
    }

    function distribute() external {
        uint256 balance = address(this).balance;
        require(balance > 0, "nothing to distribute");
        uint256 toTreasury = balance * TREASURY_BPS / 10_000;
        uint256 toStaking = balance - toTreasury;
        (bool ok1,) = treasury.call{value: toTreasury}("");
        require(ok1, "treasury transfer failed");
        (bool ok2,) = stakingRewards.call{value: toStaking}("");
        require(ok2, "staking transfer failed");
        lastDistribution = block.timestamp;
        distributions += 1;
        emit Distributed(toTreasury, toStaking);
    }

    receive() external payable {}
}
