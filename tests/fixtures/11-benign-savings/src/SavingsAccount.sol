// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;

import {SafeTransfer} from "./SafeTransfer.sol";

/// @notice Holds deposits of one ERC-20 per account with no yield and no fees. The owner can pause new
///         deposits; withdrawals are always available.
contract SavingsAccount {
    using SafeTransfer for address;

    address public immutable token;
    address public owner;
    address public pendingOwner;
    bool public depositsPaused;
    mapping(address => uint256) public balanceOf;
    uint256 public totalDeposits;
    uint256 private locked = 1;

    event Deposited(address indexed account, uint256 amount);
    event Withdrawn(address indexed account, address indexed to, uint256 amount);
    event DepositsPaused(bool paused);
    event OwnershipTransferStarted(address indexed previousOwner, address indexed newOwner);
    event OwnershipTransferred(address indexed previousOwner, address indexed newOwner);

    modifier onlyOwner() {
        require(msg.sender == owner, "not owner");
        _;
    }

    /// @dev Tokens with transfer hooks could otherwise re-enter deposit between the two balance reads.
    modifier nonReentrant() {
        require(locked == 1, "reentrant call");
        locked = 2;
        _;
        locked = 1;
    }

    constructor(address token_) {
        require(token_.code.length > 0, "token has no code");
        token = token_;
        owner = msg.sender;
    }

    /// @dev Credits the amount actually received, so fee-charging tokens cannot over-credit.
    function deposit(uint256 amount) external nonReentrant {
        require(!depositsPaused, "deposits paused");
        require(amount > 0, "zero amount");
        uint256 before = _balance();
        token.safeTransferFrom(msg.sender, address(this), amount);
        uint256 received = _balance() - before;
        balanceOf[msg.sender] += received;
        totalDeposits += received;
        emit Deposited(msg.sender, received);
    }

    function withdraw(uint256 amount, address to) external nonReentrant {
        require(to != address(0), "zero recipient");
        uint256 balance = balanceOf[msg.sender];
        require(balance >= amount, "insufficient balance");
        balanceOf[msg.sender] = balance - amount;
        totalDeposits -= amount;
        token.safeTransfer(to, amount);
        emit Withdrawn(msg.sender, to, amount);
    }

    function setDepositsPaused(bool paused) external onlyOwner {
        depositsPaused = paused;
        emit DepositsPaused(paused);
    }

    function transferOwnership(address newOwner) external onlyOwner {
        pendingOwner = newOwner;
        emit OwnershipTransferStarted(owner, newOwner);
    }

    function acceptOwnership() external {
        require(msg.sender == pendingOwner, "not pending owner");
        emit OwnershipTransferred(owner, msg.sender);
        owner = msg.sender;
        pendingOwner = address(0);
    }

    function _balance() private view returns (uint256) {
        (bool ok, bytes memory data) = token.staticcall(abi.encodeWithSignature("balanceOf(address)", address(this)));
        require(ok && data.length >= 32, "balance query failed");
        return abi.decode(data, (uint256));
    }
}
