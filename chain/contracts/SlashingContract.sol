// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;

import "@openzeppelin/contracts/access/AccessControl.sol";
import "@openzeppelin/contracts/utils/ReentrancyGuard.sol";
import "./DeAIToken.sol";

/**
 * @title SlashingContract
 * @notice Stake and reputation management for DeAI network miners.
 *
 * Miners stake tokens when they join the network. Stake acts as a
 * security deposit — if a miner returns a bad result, they lose a
 * portion of their stake (slashing). Repeated bad behavior can result
 * in full ejection from the network.
 *
 * This creates a strong economic incentive for miners to serve
 * honest, high-quality inference results.
 *
 * Slash amounts:
 *   SLASH_AMOUNT  — tokens burned per verified bad result
 *   MIN_STAKE     — minimum stake to remain in good standing
 *
 * Below MIN_STAKE, a miner is flagged as ineligible and the orchestrator
 * will not route tasks to them until they top up their stake.
 */
contract SlashingContract is AccessControl, ReentrancyGuard {
    bytes32 public constant ORCHESTRATOR_ROLE = keccak256("ORCHESTRATOR_ROLE");

    DeAIToken public immutable token;

    uint256 public constant MIN_STAKE    = 100 * 1e18;   // 100 DEAI to participate
    uint256 public constant SLASH_AMOUNT = 10  * 1e18;   // 10 DEAI burned per offense

    struct MinerRecord {
        uint256 stake;
        uint256 tasksCompleted;
        uint256 timesSlashed;
        bool    ejected;
    }

    mapping(address => MinerRecord) public miners;

    event MinerStaked(address indexed miner, uint256 amount, uint256 totalStake);
    event MinerSlashed(address indexed miner, uint256 amount, uint256 remainingStake);
    event MinerEjected(address indexed miner);
    event MinerTaskRecorded(address indexed miner, uint256 totalCompleted);
    event StakeWithdrawn(address indexed miner, uint256 amount);

    constructor(address tokenAddress, address orchestrator) {
        token = DeAIToken(tokenAddress);
        _grantRole(DEFAULT_ADMIN_ROLE, msg.sender);
        _grantRole(ORCHESTRATOR_ROLE, orchestrator);
    }

    /**
     * @notice Miner deposits stake to join the network.
     *         Must stake at least MIN_STAKE to be eligible for tasks.
     */
    function stake(uint256 amount) external nonReentrant {
        require(!miners[msg.sender].ejected, "Ejected miners cannot rejoin");
        require(amount > 0, "Amount must be > 0");

        token.transferFrom(msg.sender, address(this), amount);
        miners[msg.sender].stake += amount;

        emit MinerStaked(msg.sender, amount, miners[msg.sender].stake);
    }

    /**
     * @notice Returns true if the miner is in good standing and eligible
     *         to receive tasks from the orchestrator.
     */
    function isEligible(address miner) external view returns (bool) {
        MinerRecord storage r = miners[miner];
        return !r.ejected && r.stake >= MIN_STAKE;
    }

    /**
     * @notice Called by orchestrator when a task is successfully verified.
     *         Increments the miner's reputation score.
     */
    function recordCompletion(address miner) external onlyRole(ORCHESTRATOR_ROLE) {
        require(!miners[miner].ejected, "Miner is ejected");
        miners[miner].tasksCompleted += 1;
        emit MinerTaskRecorded(miner, miners[miner].tasksCompleted);
    }

    /**
     * @notice Called by orchestrator when a miner returns a bad result.
     *         Burns SLASH_AMOUNT from their stake. If stake falls below
     *         MIN_STAKE, miner is ejected from the network.
     */
    function slash(address miner) external onlyRole(ORCHESTRATOR_ROLE) nonReentrant {
        MinerRecord storage r = miners[miner];
        require(!r.ejected, "Already ejected");
        require(r.stake > 0, "No stake to slash");

        uint256 slashAmt = r.stake >= SLASH_AMOUNT ? SLASH_AMOUNT : r.stake;
        r.stake -= slashAmt;
        r.timesSlashed += 1;

        // Burn the slashed tokens — they leave circulation permanently
        token.burn(address(this), slashAmt);

        emit MinerSlashed(miner, slashAmt, r.stake);

        if (r.stake < MIN_STAKE) {
            r.ejected = true;
            emit MinerEjected(miner);
        }
    }

    /**
     * @notice Miner withdraws their stake when leaving the network.
     *         Only the amount above MIN_STAKE can be withdrawn while active.
     *         Full withdrawal is allowed if the miner chooses to leave entirely.
     */
    function withdrawStake(uint256 amount) external nonReentrant {
        MinerRecord storage r = miners[msg.sender];
        require(!r.ejected, "Ejected miners cannot withdraw");
        require(r.stake >= amount, "Insufficient stake");
        require(r.stake - amount >= MIN_STAKE, "Cannot drop below minimum stake while active. Call exitNetwork() to fully withdraw.");

        r.stake -= amount;
        token.transfer(msg.sender, amount);

        emit StakeWithdrawn(msg.sender, amount);
    }

    /**
     * @notice Full exit — miner leaves the network and withdraws all stake.
     */
    function exitNetwork() external nonReentrant {
        MinerRecord storage r = miners[msg.sender];
        require(!r.ejected, "Already ejected");
        require(r.stake > 0, "No stake to withdraw");

        uint256 amount = r.stake;
        r.stake = 0;
        r.ejected = true;

        token.transfer(msg.sender, amount);
        emit StakeWithdrawn(msg.sender, amount);
    }
}
