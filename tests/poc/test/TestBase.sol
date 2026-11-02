// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;

/// @dev The few Foundry cheatcodes these tests use, declared locally so the suite needs no
///      forge-std checkout or network access.
interface Vm {
    function prank(address sender) external;
    function startPrank(address sender) external;
    function stopPrank() external;
    function deal(address account, uint256 balance) external;
    function warp(uint256 timestamp) external;
    function addr(uint256 privateKey) external returns (address);
    function sign(uint256 privateKey, bytes32 digest) external returns (uint8 v, bytes32 r, bytes32 s);
    function expectRevert(bytes calldata revertData) external;
    function expectRevert() external;
}

abstract contract TestBase {
    Vm internal constant vm = Vm(address(uint160(uint256(keccak256("hevm cheat code")))));

    error AssertEq(uint256 left, uint256 right, string reason);
    error AssertGt(uint256 left, uint256 right, string reason);
    error AssertTrue(string reason);

    function assertEq(uint256 left, uint256 right, string memory reason) internal pure {
        if (left != right) revert AssertEq(left, right, reason);
    }

    function assertGt(uint256 left, uint256 right, string memory reason) internal pure {
        if (left <= right) revert AssertGt(left, right, reason);
    }

    function assertTrue(bool ok, string memory reason) internal pure {
        if (!ok) revert AssertTrue(reason);
    }
}

/// @dev Plain 18-decimal ERC-20 with an open mint, for test setup only.
contract TestToken {
    uint8 public decimals = 18;
    uint256 public totalSupply;
    mapping(address => uint256) public balanceOf;
    mapping(address => mapping(address => uint256)) public allowance;

    function setDecimals(uint8 d) external {
        decimals = d;
    }

    function mint(address to, uint256 amount) external {
        balanceOf[to] += amount;
        totalSupply += amount;
    }

    function approve(address spender, uint256 amount) external returns (bool) {
        allowance[msg.sender][spender] = amount;
        return true;
    }

    function transfer(address to, uint256 amount) public virtual returns (bool) {
        balanceOf[msg.sender] -= amount;
        balanceOf[to] += amount;
        return true;
    }

    function transferFrom(address from, address to, uint256 amount) public virtual returns (bool) {
        allowance[from][msg.sender] -= amount;
        balanceOf[from] -= amount;
        balanceOf[to] += amount;
        return true;
    }
}
