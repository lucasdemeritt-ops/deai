# On-Chain Mode — Setup Guide

By default the orchestrator runs in **mock mode**: everything works with an in-memory ledger and no blockchain is needed. This is intentional — contributors and testers can run the full network without installing anything blockchain-related.

**On-chain mode** adds real contract calls on top of mock mode:
- The SlashingContract tracks miner reputation on-chain (task completions, slashes)
- The eligibility gate checks a miner's stake before routing tasks to them
- Slashed tokens are permanently burned from circulation

Payment tracking (the PaymentContract) stays in-memory for now — full integration requires users to hold DEAI tokens and sign transactions, which needs a wallet UI. That's Phase 3.

---

## Prerequisites

- Node.js 18+ (for Hardhat)
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
  --slashing-contract 0x9fE46736679d2D9a65F0992F2272dE9f3c7fa6e0 \
  --payment-contract  0xe7f1725E7734CE288F8367e1Bb143E90bb3F0512 \
  --orchestrator-key  0xac0974bec39a17e36ba4a6b4d238ff944bacb478cbed5efcae784d7bf4f2ff80
```

You should see:
```
ChainLedger ready  rpc=http://localhost:8545  orchestrator=0xf39F...
Running in ON-CHAIN mode — SlashingContract wired
```

---

## Step 5 — Connect a node with a wallet

Miners need to stake DEAI tokens before they'll be considered eligible. For local dev, mint some tokens first using the Hardhat console or a script.

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

## Testnet deployment (Sepolia / Polygon Amoy)

Same steps, but:
1. Get free test tokens from a faucet (search "Sepolia faucet" or "Amoy faucet")
2. Get a free RPC endpoint from [Alchemy](https://www.alchemy.com) or [Infura](https://www.infura.io)
3. Fill in `chain/.env` (separate from root `.env`) with your testnet RPC URL and deployer key
4. Deploy: `npx hardhat run scripts/deploy.js --network sepolia`
5. Run orchestrator pointing at Sepolia: `--rpc-url https://eth-sepolia.g.alchemy.com/v2/YOUR_KEY`

See `chain/.env.example` for all chain-specific variables.

---

## How mock mode and chain mode differ

| | Mock mode | Chain mode |
|---|---|---|
| Ledger | In-memory, resets on restart | SlashingContract on-chain, persistent |
| Eligibility check | All nodes eligible | Checks stake ≥ MIN_STAKE (100 DEAI) |
| Task completion | Increments in-memory counter | Also calls `recordCompletion()` on-chain |
| Bad results | Logged, no penalty | Calls `slash()` — burns 10 DEAI from stake |
| Payment tracking | In-memory | In-memory (PaymentContract integration is Phase 3) |
| Requires blockchain | No | Yes |
