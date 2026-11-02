// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

// Starting point for handler-based invariant tests in projects without forge-std.
// Copy into the approved test directory and replace the protocol-specific parts marked PROTOCOL.

/// @dev Foundry cheatcodes used by handlers; the address is Foundry's fixed cheatcode address.
interface Vm {
    function prank(address sender) external;
    function startPrank(address sender) external;
    function stopPrank() external;
    function deal(address account, uint256 balance) external;
    function warp(uint256 timestamp) external;
}

abstract contract InvariantBase {
    Vm internal constant vm = Vm(address(uint160(uint256(keccak256("hevm cheat code")))));

    error InvariantViolated(uint256 left, uint256 right, string what);

    function assertEq(uint256 left, uint256 right, string memory what) internal pure {
        if (left != right) revert InvariantViolated(left, right, what);
    }

    function assertGe(uint256 left, uint256 right, string memory what) internal pure {
        if (left < right) revert InvariantViolated(left, right, what);
    }
}

/// @dev The fuzzer calls only this contract. Each function is one user action with bounded inputs.
contract Handler is InvariantBase {
    address[3] internal actors = [address(0xA1), address(0xA2), address(0xA3)];

    // PROTOCOL: store the system under test and ghost totals here, e.g. mapping(address => uint256) deposited;

    function _actor(uint256 seed) internal view returns (address) {
        return actors[seed % actors.length];
    }

    // PROTOCOL: one external function per user action, for example:
    // function deposit(uint256 seed, uint256 amount) external {
    //     address a = _actor(seed);
    //     amount = amount % 1e30 + 1;
    //     ...fund a, vm.startPrank(a), call the system, vm.stopPrank()...
    //     deposited[a] += amount;
    // }
}

contract InvariantTest is InvariantBase {
    Handler internal handler;

    function setUp() public {
        // PROTOCOL: deploy the system, then the handler that drives it.
        handler = new Handler();
    }

    /// @dev Foundry reads this to restrict fuzzing to the handler.
    function targetContracts() public view returns (address[] memory targets) {
        targets = new address[](1);
        targets[0] = address(handler);
    }

    // PROTOCOL: invariant_* functions that only read state, for example
    // function invariant_solvent() public view { assertGe(token.balanceOf(address(vault)), vault.totalDeposits(), "solvent"); }
}
