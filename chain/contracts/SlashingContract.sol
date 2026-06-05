// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;

import "@openzeppelin/contracts/access/AccessControl.sol";
import "@openzeppelin/contracts/utils/ReentrancyGuard.sol";
import "./DAIToken.sol";

/**
 * @title SlashingContract
 * @notice Stake and reputation management for DAI network miners.
 *
 * Anyone can join and start earning — no stake required to participate.
 * Stake is optional but acts as a protection buffer: miners with stake
 * can absorb bad results without being ejected. Miners with no stake
 * are ejected on their first verified bad result.
 *
 * This design removes the bootstrap barrier (no chicken-and-egg token
 * problem) while keeping the economic incentive to stake strong:
 * stake protects your ability to keep earning.
 *
 * MIN_STAKE  — floor kept in contract when withdrawing (voluntary buffer)
 * SLASH_AMOUNT — tokens burned per verified bad result
 *
 * Slash tiers:
 *   stake >= SLASH_AMOUNT  → burn SLASH_AMOUNT, continue
 *   0 < stake < SLASH_AMOUNT → burn remaining stake, eject
 *   stake == 0             → eject immediately (one strike, no buffer)
 */
contract SlashingContract is AccessControl, ReentrancyGuard {
    bytes32 public constant ORCHESTRATOR_ROLE = keccak256("ORCHESTRATOR_ROLE");

    DAIToken public immutable token;

    uint256 public constant MIN_STAKE    = 100 * 1e18;  // voluntary buffer floor
    uint256 public constant SLASH_AMOUNT = 10  * 1e18;  // burned per bad result

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
        token = DAIToken(tokenAddress);
        _grantRole(DEFAULT_ADMIN_ROLE, msg.sender);
        _grantRole(ORCHESTRATOR_ROLE, orchestrator);
    }

    /**
     * @notice Miner deposits stake as a protection buffer.
     *         Stake is optional — miners can earn without it, but any
     *         bad result will eject them immediately if stake is zero.
     */
    function stake(uint256 amount) external nonReentrant {
        require(!miners[msg.sender].ejected, "Ejected miners cannot rejoin");
        require(amount > 0, "Amount must be > 0");

        token.transferFrom(msg.sender, address(this), amount);
        miners[msg.sender].stake += amount;

        emit MinerStaked(msg.sender, amount, miners[msg.sender].stake);
    }

    /**
     * @notice Returns true if the miner is eligible to receive tasks.
     *         Any miner who has not been ejected is eligible — no stake required.
     */
    function isEligible(address miner) external view returns (bool) {
        return !miners[miner].ejected;
    }

    /**
     * @notice Called by orchestrator when a task is successfully verified.
     *         Increments the miner's on-chain reputation counter.
     */
    function recordCompletion(address miner) external onlyRole(ORCHESTRATOR_ROLE) {
        require(!miners[miner].ejected, "Miner is ejected");
        miners[miner].tasksCompleted += 1;
        emit MinerTaskRecorded(miner, miners[miner].tasksCompleted);
    }

    /**
     * @notice Called by orchestrator when a miner returns a bad result.
     *
     *   - If stake >= SLASH_AMOUNT: burn SLASH_AMOUNT, miner continues
     *   - If 0 < stake < SLASH_AMOUNT: burn remainder, eject
     *   - If stake == 0: eject immediately — no buffer means no second chance
     */
    function slash(address miner) external onlyRole(ORCHESTRATOR_ROLE) nonReentrant {
        MinerRecord storage r = miners[miner];
        require(!r.ejected, "Already ejected");

        r.timesSlashed += 1;

        if (r.stake == 0) {
            // No buffer — eject on first offense
            r.ejected = true;
            emit MinerSlashed(miner, 0, 0);
            emit MinerEjected(miner);
            return;
        }

        uint256 slashAmt = r.stake >= SLASH_AMOUNT ? SLASH_AMOUNT : r.stake;
        r.stake -= slashAmt;

        // Burned tokens leave circulation permanently
        token.burn(address(this), slashAmt);
        emit MinerSlashed(miner, slashAmt, r.stake);

        if (r.stake == 0) {
            r.ejected = true;
            emit MinerEjected(miner);
        }
    }

    /**
     * @notice Withdraw earned tokens above the MIN_STAKE buffer.
     *         Keeping MIN_STAKE locked protects against 10 consecutive bad
     *         results before ejection. Call exitNetwork() to withdraw everything.
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
     * @notice Full exit — withdraw all stake and leave the network.
     *         After exit the miner is ejected and cannot rejoin with this address.
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
