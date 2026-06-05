// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;

import "@openzeppelin/contracts/utils/cryptography/MerkleProof.sol";
import "@openzeppelin/contracts/access/AccessControl.sol";

interface IDAIToken {
    function mint(address to, uint256 amount) external;
}

/**
 * @title MerkleDistributor
 * @notice Claimable batch settlement of earned DAI (build-now #4).
 *
 * Instead of the orchestrator minting per task with a permanently-hot
 * MINTER_ROLE key, earnings accrue OFF-CHAIN. Once per epoch the orchestrator
 * (UPDATER_ROLE) publishes a single Merkle root of CUMULATIVE earnings per
 * wallet. Miners claim their own tokens by proving their leaf — paying their
 * own gas, on their own schedule. One on-chain write per epoch instead of
 * two per task.
 *
 * Cumulative design: each leaf is (account, totalEarnedToDate). claim() pays
 * totalEarnedToDate - alreadyClaimed, so a miner may skip epochs and claim
 * once; replaying an old proof simply pays nothing new.
 *
 * Slashing is applied OFF-CHAIN by reducing a node's accrued amount before it
 * ever enters a root — there is intentionally no on-chain clawback path.
 *
 * Leaf convention (must match protocol/merkle.py and the test):
 *   leaf = keccak256(bytes.concat(keccak256(abi.encode(account, cumulative))))
 * (OpenZeppelin-recommended double hash; MerkleProof uses sorted pairs.)
 */
contract MerkleDistributor is AccessControl {
    bytes32 public constant UPDATER_ROLE = keccak256("UPDATER_ROLE");

    IDAIToken public immutable token;
    bytes32 public merkleRoot;
    uint256 public epoch;

    /// @notice Cumulative DAI (wei) already claimed per account.
    mapping(address => uint256) public claimed;

    event RootUpdated(uint256 indexed epoch, bytes32 root);
    event Claimed(address indexed account, uint256 amount, uint256 cumulative);

    constructor(address tokenAddr, address updater) {
        token = IDAIToken(tokenAddr);
        _grantRole(DEFAULT_ADMIN_ROLE, msg.sender);
        _grantRole(UPDATER_ROLE, updater);
    }

    /// @notice Publish the next epoch's cumulative-earnings Merkle root.
    function updateRoot(bytes32 newRoot) external onlyRole(UPDATER_ROLE) {
        merkleRoot = newRoot;
        epoch += 1;
        emit RootUpdated(epoch, newRoot);
    }

    /// @notice Claim all DAI earned to date for msg.sender.
    /// @param cumulativeAmount total DAI (wei) earned by msg.sender as of the
    ///        currently-published root.
    /// @param proof Merkle proof for msg.sender's leaf.
    function claim(uint256 cumulativeAmount, bytes32[] calldata proof) external {
        bytes32 leaf = keccak256(
            bytes.concat(keccak256(abi.encode(msg.sender, cumulativeAmount)))
        );
        require(
            MerkleProof.verifyCalldata(proof, merkleRoot, leaf),
            "MerkleDistributor: bad proof"
        );

        uint256 already = claimed[msg.sender];
        require(
            cumulativeAmount > already,
            "MerkleDistributor: nothing to claim"
        );

        uint256 payout = cumulativeAmount - already;
        claimed[msg.sender] = cumulativeAmount;

        token.mint(msg.sender, payout);
        emit Claimed(msg.sender, payout, cumulativeAmount);
    }
}
