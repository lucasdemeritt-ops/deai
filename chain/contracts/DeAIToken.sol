// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;

import "@openzeppelin/contracts/token/ERC20/ERC20.sol";
import "@openzeppelin/contracts/access/AccessControl.sol";

/**
 * @title DeAIToken
 * @notice The native utility token of the DeAI network.
 *
 * MINTER_ROLE  — granted to the PaymentContract so it can mint rewards
 *                to miners when tasks complete successfully.
 * BURNER_ROLE  — granted to the SlashingContract so it can burn a
 *                miner's tokens as a penalty for bad results.
 *
 * No tokens are pre-minted to any team or founder wallet.
 * Tokens enter circulation only when miners earn them by completing tasks.
 */
contract DeAIToken is ERC20, AccessControl {
    bytes32 public constant MINTER_ROLE = keccak256("MINTER_ROLE");
    bytes32 public constant BURNER_ROLE = keccak256("BURNER_ROLE");

    constructor() ERC20("DeAI", "DEAI") {
        _grantRole(DEFAULT_ADMIN_ROLE, msg.sender);
    }

    function mint(address to, uint256 amount) external onlyRole(MINTER_ROLE) {
        _mint(to, amount);
    }

    function burn(address from, uint256 amount) external onlyRole(BURNER_ROLE) {
        _burn(from, amount);
    }
}
