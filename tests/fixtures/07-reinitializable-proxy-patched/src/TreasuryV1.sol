// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;

/// @notice Protocol treasury behind an ERC-1967 proxy. Deployed with
///         `new TreasuryProxy(address(new TreasuryV1()), abi.encodeCall(TreasuryV1.initialize, (multisig)))`.
contract TreasuryV1 {
    bytes32 internal constant IMPLEMENTATION_SLOT = 0x360894a13ba1a3210667c828492db98dca3e2076cc3735a920a3ca505d382bbc;

    address public owner;
    uint256 public withdrawLimit;
    bool private initialized;

    event Initialized(address owner);
    event Upgraded(address indexed implementation);
    event Paid(address indexed to, uint256 amount);

    modifier onlyOwner() {
        require(msg.sender == owner, "not owner");
        _;
    }

    /// @dev Locks the implementation itself; only the proxy's storage can be initialised.
    constructor() {
        initialized = true;
    }

    function initialize(address owner_) external {
        require(!initialized, "already initialized");
        require(owner_ != address(0), "zero owner");
        initialized = true;
        owner = owner_;
        withdrawLimit = 100 ether;
        emit Initialized(owner_);
    }

    function pay(address payable to, uint256 amount) external onlyOwner {
        require(amount <= withdrawLimit, "over limit");
        (bool ok,) = to.call{value: amount}("");
        require(ok, "payment failed");
        emit Paid(to, amount);
    }

    function setWithdrawLimit(uint256 limit) external onlyOwner {
        withdrawLimit = limit;
    }

    function upgradeTo(address newImplementation) external onlyOwner {
        require(newImplementation.code.length > 0, "not a contract");
        assembly {
            sstore(IMPLEMENTATION_SLOT, newImplementation)
        }
        emit Upgraded(newImplementation);
    }

    receive() external payable {}
}
