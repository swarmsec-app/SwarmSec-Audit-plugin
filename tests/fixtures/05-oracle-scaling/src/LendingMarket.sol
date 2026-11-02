// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;

interface IERC20 {
    function decimals() external view returns (uint8);
    function transfer(address to, uint256 amount) external returns (bool);
    function transferFrom(address from, address to, uint256 amount) external returns (bool);
}

interface AggregatorV3Interface {
    function decimals() external view returns (uint8);
    function latestRoundData()
        external
        view
        returns (uint80 roundId, int256 answer, uint256 startedAt, uint256 updatedAt, uint80 answeredInRound);
}

/// @notice Over-collateralised borrowing of a USD stablecoin (18 decimals) against listed tokens.
contract LendingMarket {
    uint256 public constant LTV_BPS = 7_500;

    address public owner;
    IERC20 public immutable stable;

    mapping(address => AggregatorV3Interface) public feeds;
    mapping(address => mapping(address => uint256)) public collateral;
    mapping(address => uint256) public debt;
    address[] public listedTokens;

    event FeedSet(address indexed token, address feed);
    event Borrowed(address indexed account, uint256 amount);

    modifier onlyOwner() {
        require(msg.sender == owner, "not owner");
        _;
    }

    constructor(IERC20 stable_) {
        owner = msg.sender;
        stable = stable_;
    }

    function setFeed(address token, AggregatorV3Interface feed) external onlyOwner {
        if (address(feeds[token]) == address(0)) listedTokens.push(token);
        feeds[token] = feed;
        emit FeedSet(token, address(feed));
    }

    /// @return USD value of `amount` of `token`, scaled to 18 decimals.
    function usdValue(address token, uint256 amount) public view returns (uint256) {
        (, int256 answer,,,) = feeds[token].latestRoundData();
        require(answer > 0, "invalid price");
        // Chainlink USD feeds report 8 decimals; scale the price to 18.
        uint256 price = uint256(answer) * 1e10;
        return amount * price / (10 ** IERC20(token).decimals());
    }

    function depositCollateral(address token, uint256 amount) external {
        require(address(feeds[token]) != address(0), "not listed");
        require(IERC20(token).transferFrom(msg.sender, address(this), amount), "transfer failed");
        collateral[msg.sender][token] += amount;
    }

    function borrow(uint256 amount) external {
        debt[msg.sender] += amount;
        require(debt[msg.sender] <= borrowLimit(msg.sender), "undercollateralised");
        require(stable.transfer(msg.sender, amount), "transfer failed");
        emit Borrowed(msg.sender, amount);
    }

    function repay(uint256 amount) external {
        require(stable.transferFrom(msg.sender, address(this), amount), "transfer failed");
        debt[msg.sender] -= amount;
    }

    function withdrawCollateral(address token, uint256 amount) external {
        collateral[msg.sender][token] -= amount;
        require(debt[msg.sender] <= borrowLimit(msg.sender), "undercollateralised");
        require(IERC20(token).transfer(msg.sender, amount), "transfer failed");
    }

    function borrowLimit(address account) public view returns (uint256 limit) {
        for (uint256 i = 0; i < listedTokens.length; i++) {
            address token = listedTokens[i];
            uint256 amount = collateral[account][token];
            if (amount > 0) limit += usdValue(token, amount) * LTV_BPS / 10_000;
        }
    }
}
