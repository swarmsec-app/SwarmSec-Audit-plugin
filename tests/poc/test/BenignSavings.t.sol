// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;

import {TestBase, TestToken} from "./TestBase.sol";
import {SavingsAccount} from "fixtures/11-benign-savings/src/SavingsAccount.sol";

/// @dev Drives deposits and withdrawals from three accounts and tracks what each should hold.
contract SavingsHandler is TestBase {
    SavingsAccount internal immutable savings;
    TestToken internal immutable token;
    address[3] internal actors = [address(0xA1), address(0xA2), address(0xA3)];
    mapping(address => uint256) public expected;

    constructor(SavingsAccount savings_, TestToken token_) {
        savings = savings_;
        token = token_;
    }

    function deposit(uint256 seed, uint256 amount) external {
        address actor = actors[seed % 3];
        amount = amount % 1e30 + 1;
        token.mint(actor, amount);
        vm.startPrank(actor);
        token.approve(address(savings), amount);
        savings.deposit(amount);
        vm.stopPrank();
        expected[actor] += amount;
    }

    function withdraw(uint256 seed, uint256 amount) external {
        address actor = actors[seed % 3];
        uint256 balance = savings.balanceOf(actor);
        if (balance == 0) return;
        amount = amount % balance + 1;
        vm.prank(actor);
        savings.withdraw(amount, actor);
        expected[actor] -= amount;
    }

    function donate(uint256 amount) external {
        token.mint(address(savings), amount % 1e30);
    }

    function actor(uint256 i) external view returns (address) {
        return actors[i];
    }
}

contract BenignSavingsInvariantTest is TestBase {
    TestToken internal token;
    SavingsAccount internal savings;
    SavingsHandler internal handler;

    function setUp() public {
        token = new TestToken();
        savings = new SavingsAccount(address(token));
        handler = new SavingsHandler(savings, token);
    }

    function targetContracts() public view returns (address[] memory targets) {
        targets = new address[](1);
        targets[0] = address(handler);
    }

    /// Donations may raise the balance above recorded deposits, never the other way.
    function invariant_solvent() public view {
        assertTrue(token.balanceOf(address(savings)) >= savings.totalDeposits(), "token balance covers deposits");
    }

    function invariant_accountsMatchDeposits() public view {
        uint256 sum;
        for (uint256 i = 0; i < 3; i++) {
            address a = handler.actor(i);
            assertEq(savings.balanceOf(a), handler.expected(a), "account balance matches its net deposits");
            sum += savings.balanceOf(a);
        }
        assertEq(sum, savings.totalDeposits(), "totalDeposits is the sum of accounts");
    }
}
