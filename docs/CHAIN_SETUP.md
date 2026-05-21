# On-Chain Mode — Setup Guide

By default the orchestrator runs in **mock mode**: everything works with an in-memory ledger and no blockchain is needed. This is intentional — contributors and testers can run the full network without installing anything blockchain-related.

**On-chain mode** adds real contract calls on top of mock mode:
- The SlashingContract tracks miner reputation on-chain (task completions, slashes)
- The eligibility gate checks a miner has **not been ejected** before routing tasks to them — staking is optional, **not** required
- Slashed tokens are permanently burned from circulation

The PaymentContract (user deposit → escrow → release to miner) is **not** integrated at all — neither on-chain nor in-memory. In chain mode the live path accrues rewards off-chain and settles them once per epoch as a cumulative Merkle root miners claim from `MerkleDistributor` (build-now #4 — no per-task mint, no hot mint key); in mock mode it is in-memory only. Either way there is no user payment or escrow — rewards are minted into existence, not funded by a paying user. Full escrow integration needs user wallets and signing, and is deferred (roadmap Phase 3).

---

## Prerequisites

- Node.js 22+ (for Hardhat)
- Python 3.10+ with `pip install -r requirements.txt` already done
- A funded wallet for the orchestrator (testnet or local)

---

## Step 1 — Start a local chain

For development, spin up a local Hardhat node. It gives you 20 pre-funded test accounts.

```bash
cd chain
npx hardhat node
```

Leave this running. It listens on `http://localhost:8545`.

---

## Step 2 — Deploy the contracts

In a second terminal:

```bash
cd chain
npx hardhat run scripts/deploy.js --network localhost
```

The script prints the deployed addresses:

```
DeAIToken:        0x5FbDB2315678afecb367f032d93F642f64180aa3
PaymentContract:  0xe7f1725E7734CE288F8367e1Bb143E90bb3F0512
SlashingContract: 0x9fE46736679d2D9a65F0992F2272dE9f3c7fa6e0
```

Copy these — you'll need them in the next step.

---

## Step 3 — Configure environment

Copy `.env.example` to `.env` in the project root and fill in the values:

```bash
cp .env.example .env
```

```env
DEAI_RPC_URL=http://localhost:8545
DEAI_SLASHING_CONTRACT=0x9fE46736679d2D9a65F0992F2272dE9f3c7fa6e0
DEAI_PAYMENT_CONTRACT=0xe7f1725E7734CE288F8367e1Bb143E90bb3F0512
DEAI_TOKEN_CONTRACT=0x5FbDB2315678afecb367f032d93F642f64180aa3
DEAI_DISTRIBUTOR_CONTRACT=0x<MerkleDistributor address from deploy.js output>
# Optional: seconds between reward-settlement epochs (default 3600)
# DEAI_SETTLE_INTERVAL=3600

# First Hardhat test account private key (pre-funded, safe for local dev only)
DEAI_ORCHESTRATOR_KEY=0xac0974bec39a17e36ba4a6b4d238ff944bacb478cbed5efcae784d7bf4f2ff80
```

---

## Step 4 — Start the orchestrator in chain mode

```bash
python protocol/orchestrator.py --chain
```

Or pass everything as flags instead of env vars:

```bash
python protocol/orchestrator.py --chain \
  --rpc-url http://localhost:8545 \
  --token-contract       0x5FbDB2315678afecb367f032d93F642f64180aa3 \
  --slashing-contract    0x9fE46736679d2D9a65F0992F2272dE9f3c7fa6e0 \
  --payment-contract     0xe7f1725E7734CE288F8367e1Bb143E90bb3F0512 \
  --distributor-contract 0x<MerkleDistributor address> \
  --orchestrator-key     0xac0974bec39a17e36ba4a6b4d238ff944bacb478cbed5efcae784d7bf4f2ff80
```

You should see:
```
ChainLedger ready  rpc=http://localhost:8545  orchestrator=0xf39F...  distributor=0x...
Running in ON-CHAIN mode — rewards accrue off-chain, settled every 3600s via MerkleDistributor
Reward settlement loop started  interval=3600s
```

Rewards no longer mint per task. They accrue off-chain; every epoch the
orchestrator publishes one cumulative Merkle root. A miner fetches their
proof from `GET /claim/<wallet>` and calls `MerkleDistributor.claim()`
themselves.

---

## Step 5 — Connect a node with a wallet

Staking is **optional**. Any miner that has not been ejected is eligible to receive tasks (`isEligible` returns `!ejected` — there is no minimum-stake gate). Stake acts only as a protection buffer: a miner with stake absorbs a bad result instead of being ejected on the first one. You can run a node with no stake at all.

If you specifically want to test the stake/slash path, mint yourself some DEAI and call `stake()` via the Hardhat console first; otherwise you can skip staking entirely.

Start the node with its wallet address:

```bash
python compute/node.py --models llama3 --wallet 0x<MINER_WALLET_ADDRESS>
```

Or set it in the environment:
```bash
DEAI_WALLET=0x... python compute/node.py --models llama3
```

Nodes without a wallet still work — they're just not tracked on-chain and won't appear in SlashingContract's reputation records.

---

## Sepolia testnet (live deployment)

The contracts are already deployed on Ethereum Sepolia — you can point directly at them:

| Contract | Address |
|---|---|
| DeAIToken | [`0xE513DAb60018fc63bDB240605CE0816dE7751B27`](https://sepolia.etherscan.io/address/0xE513DAb60018fc63bDB240605CE0816dE7751B27) |
| PaymentContract | [`0x49F2ed162B5DEba2b768BFD79313FADdF3c075C8`](https://sepolia.etherscan.io/address/0x49F2ed162B5DEba2b768BFD79313FADdF3c075C8) |
| SlashingContract | [`0xDFea0F4436E3B30D2861D7b7Acf6c252Da28633c`](https://sepolia.etherscan.io/address/0xDFea0F4436E3B30D2861D7b7Acf6c252Da28633c) |

To run against the live testnet deployment, use the public Sepolia RPC (no account needed):

```env
DEAI_RPC_URL=https://ethereum-sepolia.publicnode.com
DEAI_SLASHING_CONTRACT=0xDFea0F4436E3B30D2861D7b7Acf6c252Da28633c
DEAI_PAYMENT_CONTRACT=0x49F2ed162B5DEba2b768BFD79313FADdF3c075C8
DEAI_TOKEN_CONTRACT=0xE513DAb60018fc63bDB240605CE0816dE7751B27
```

To deploy your own instance (e.g. for testing contract changes):
1. Get free Sepolia ETH from `https://sepolia-faucet.pk910.de` (no account needed — mines in browser)
2. Generate a wallet: `node --input-type=module -e "import { ethers } from 'ethers'; const w = ethers.Wallet.createRandom(); console.log(w.address, w.privateKey);"`
3. Fill in `chain/.env` with your RPC URL and deployer key
4. Deploy: `npx hardhat run scripts/deploy.js --network sepolia`

---

## How mock mode and chain mode differ

| | Mock mode | Chain mode |
|---|---|---|
| Ledger | In-memory, resets on restart | SlashingContract on-chain, persistent |
| Eligibility check | All nodes eligible | Any miner not ejected is eligible — stake is optional, **not** required |
| Task completion | Increments in-memory counter | Accrues reward off-chain + calls `recordCompletion()` on-chain |
| Reward settlement | In-memory balance only | Off-chain accrual → cumulative Merkle root per epoch via `MerkleDistributor`; miners claim (`GET /claim/<wallet>` → `claim()`) |
| Bad results | Logged, no penalty | Calls `slash()` — burns up to 10 DEAI from stake; a miner with no stake is ejected on the first bad result |
| Payment / escrow | Not implemented (rewards minted, not user-funded) | Not implemented (PaymentContract not wired; deferred) |
| Requires blockchain | No | Yes |
