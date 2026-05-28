// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;

import "@openzeppelin/contracts/access/AccessControl.sol";
import "@openzeppelin/contracts/utils/ReentrancyGuard.sol";
import "./DAIToken.sol";

/**
 * @title PaymentContract
 * @notice Escrow and reward logic for the DAI network.
 *
 * Flow:
 *   1. User calls depositAndRequest() with a token amount and task hash.
 *      Tokens are held in escrow by this contract.
 *   2. The off-chain orchestrator dispatches the task to a miner node.
 *   3. Once the task is verified, the orchestrator calls completeTask()
 *      which releases the escrowed tokens to the miner AND mints a bonus
 *      reward on top (the miner earns more than the user paid — the bonus
 *      is newly minted, funding early network growth).
 *   4. If a task times out or fails, the user calls refund() to reclaim
 *      their escrowed tokens.
 *
 * Security notes (see docs/SECURITY.md):
 *   - Only a task hash is stored on-chain, never the prompt content.
 *   - Node IP addresses are never recorded here or anywhere on-chain.
 *   - The ORCHESTRATOR_ROLE is the only address that can call completeTask.
 */
contract PaymentContract is AccessControl, ReentrancyGuard {
    bytes32 public constant ORCHESTRATOR_ROLE = keccak256("ORCHESTRATOR_ROLE");

    DAIToken public immutable token;

    // Flat miner bonus minted on top of the user's payment (in token units, 18 decimals)
    uint256 public constant MINER_BONUS = 10 * 1e18;

    struct Task {
        address user;
        address miner;
        uint256 amount;      // tokens escrowed by user
        bytes32 taskHash;    // hash of prompt — content never stored on-chain
        uint256 deadline;    // unix timestamp after which user can refund
        bool completed;
        bool refunded;
    }

    // taskId (off-chain UUID as bytes32) → Task
    mapping(bytes32 => Task) public tasks;

    event TaskDeposited(bytes32 indexed taskId, address indexed user, uint256 amount, bytes32 taskHash);
    event TaskCompleted(bytes32 indexed taskId, address indexed miner, uint256 totalEarned);
    event TaskRefunded(bytes32 indexed taskId, address indexed user, uint256 amount);

    constructor(address tokenAddress, address orchestrator) {
        token = DAIToken(tokenAddress);
        _grantRole(DEFAULT_ADMIN_ROLE, msg.sender);
        _grantRole(ORCHESTRATOR_ROLE, orchestrator);
    }

    /**
     * @notice User deposits tokens and registers a task.
     * @param taskId    Off-chain task UUID converted to bytes32.
     * @param taskHash  keccak256 hash of the prompt — proves the task
     *                  without revealing content.
     * @param miner     Address of the node assigned to this task.
     * @param amount    Token amount to escrow (user pays the miner).
     * @param ttlSeconds How long before the user can refund if no response.
     */
    function depositAndRequest(
        bytes32 taskId,
        bytes32 taskHash,
        address miner,
        uint256 amount,
        uint256 ttlSeconds
    ) external nonReentrant {
        require(tasks[taskId].user == address(0), "Task already exists");
        require(amount > 0, "Amount must be > 0");
        require(miner != address(0), "Invalid miner address");

        token.transferFrom(msg.sender, address(this), amount);

        tasks[taskId] = Task({
            user: msg.sender,
            miner: miner,
            amount: amount,
            taskHash: taskHash,
            deadline: block.timestamp + ttlSeconds,
            completed: false,
            refunded: false
        });

        emit TaskDeposited(taskId, msg.sender, amount, taskHash);
    }

    /**
     * @notice Called by the orchestrator once a task is verified complete.
     *         Releases escrowed tokens to miner and mints a bonus reward.
     */
    function completeTask(bytes32 taskId) external onlyRole(ORCHESTRATOR_ROLE) nonReentrant {
        Task storage task = tasks[taskId];
        require(task.user != address(0), "Task not found");
        require(!task.completed, "Already completed");
        require(!task.refunded, "Already refunded");

        task.completed = true;

        // Release escrowed user payment to miner
        token.transfer(task.miner, task.amount);

        // Mint bonus reward on top — this is how new tokens enter circulation
        token.mint(task.miner, MINER_BONUS);

        emit TaskCompleted(taskId, task.miner, task.amount + MINER_BONUS);
    }

    /**
     * @notice User reclaims their tokens if the task is not completed in time.
     */
    function refund(bytes32 taskId) external nonReentrant {
        Task storage task = tasks[taskId];
        require(task.user == msg.sender, "Not your task");
        require(!task.completed, "Task already completed");
        require(!task.refunded, "Already refunded");
        require(block.timestamp > task.deadline, "Task not yet timed out");

        task.refunded = true;
        token.transfer(msg.sender, task.amount);

        emit TaskRefunded(taskId, msg.sender, task.amount);
    }
}
