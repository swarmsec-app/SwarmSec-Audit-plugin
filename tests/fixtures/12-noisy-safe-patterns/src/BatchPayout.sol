// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;

interface IERC20 {
    function transferFrom(address from, address to, uint256 amount) external returns (bool);
}

/// @notice Payroll helper. A payer sets a spending cap, approves this contract, then pays many
///         recipients from their own wallet in one transaction. Several calls can be bundled with
///         multicall. The contract never holds tokens or ETH.
contract BatchPayout {
    struct Budget {
        address token;
        uint256 remaining;
    }

    mapping(address => Budget) public budgets;

    event BudgetSet(address indexed payer, address indexed token, uint256 amount);
    event Paid(address indexed payer, address indexed recipient, uint256 amount);

    function setBudget(address token, uint256 amount) external {
        budgets[msg.sender] = Budget(token, amount);
        emit BudgetSet(msg.sender, token, amount);
    }

    function payMany(address[] calldata recipients, uint256[] calldata amounts) external {
        uint256 n = recipients.length;
        require(n == amounts.length, "length mismatch");
        Budget storage budget = budgets[msg.sender];
        uint256 remaining = budget.remaining;
        for (uint256 i = 0; i < n;) {
            uint256 amount = amounts[i];
            require(remaining >= amount, "over budget");
            unchecked {
                remaining -= amount;
            }
            require(IERC20(budget.token).transferFrom(msg.sender, recipients[i], amount), "transfer failed");
            emit Paid(msg.sender, recipients[i], amount);
            unchecked {
                ++i;
            }
        }
        budget.remaining = remaining;
    }

    /// @notice Executes several calls to this contract in order, with the caller's own msg.sender.
    function multicall(bytes[] calldata calls) external returns (bytes[] memory results) {
        results = new bytes[](calls.length);
        for (uint256 i = 0; i < calls.length; i++) {
            (bool ok, bytes memory result) = address(this).delegatecall(calls[i]);
            if (!ok) {
                assembly {
                    revert(add(result, 32), mload(result))
                }
            }
            results[i] = result;
        }
    }

    function selectorOf(bytes calldata data) external pure returns (bytes4 selector) {
        require(data.length >= 4, "short calldata");
        assembly {
            selector := calldataload(data.offset)
        }
    }
}
