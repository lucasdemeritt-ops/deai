# DeAI — Decentralized AI Network

[![CI](https://github.com/theblankist/deai/actions/workflows/ci.yml/badge.svg)](https://github.com/theblankist/deai/actions/workflows/ci.yml)

> A permissionless, censorship-resistant compute marketplace where anyone with a GPU or CPU earns by powering AI inference.

---

## Quick Start

**No Ollama? No problem — mock mode works out of the box.**

```bash
# 1. Clone and install
git clone https://github.com/theblankist/deai.git
cd deai
pip install -r requirements.txt

# Terminal 1 — start the orchestrator
python protocol/orchestrator.py

# Terminal 2 — connect a node (mock mode, no model download needed)
python compute/node.py --models llama3

# Terminal 3 — send a request
python test_request.py --message "What is decentralized AI?"

# Check node status and earnings
python test_request.py --status
```

**Want real inference?** Install [Ollama](https://ollama.com), pull a model (`ollama pull llama3`), then:
```bash
python compute/node.py --ollama --auto
```

**One-click node setup:**
```bash
# Windows
.\install_node.ps1

# Linux / macOS
./install_node.sh
```

**Run a persistent agent on a token budget:**
```bash
python application/agent_runner.py --prompt "Summarize today's AI news" --budget 50 --loop
```

**Want on-chain rewards?** Mock mode runs without a blockchain — when you're ready to wire up real contracts, see [docs/CHAIN_SETUP.md](docs/CHAIN_SETUP.md).

---

## The Problem

AI development is a centralized monopoly. Large-scale models require massive GPU clusters owned by a handful of corporations. This creates:

- **High costs** — developers pay premium rates to a small number of cloud providers
- **Censorship risk** — a single entity controls what can be run and for whom
- **Compute divide** — only the wealthy can innovate at scale

## The Solution

DeAI is a **Decentralized Physical Infrastructure Network (DePIN)** for AI inference. Anyone with a GPU or CPU can loan idle compute to a global marketplace. Instead of mining useless hashes, nodes perform **Proof-of-Useful-Inference** and earn tokens in return.

### How It Works

1. **Request** — A developer submits an AI task (e.g., "Summarize this PDF") via a Smart Contract
2. **Allocation** — The protocol routes the task to the most efficient available Worker Node based on hardware capability and proximity
3. **Execution** — The node runs model inference inside a secure, verifiable environment (TEE or ZK-ML)
4. **Verification & Reward** — The result is cryptographically verified; the Smart Contract pays the node operator in DeAI tokens

### Value Proposition

| Stakeholder | Benefit |
|---|---|
| **Providers (Nodes)** | Turn idle hardware into a revenue-generating asset |
| **Users (Developers)** | High-performance AI inference at a fraction of centralized API costs |
| **Everyone** | Censorship-resistant, democratized, permissionless AI infrastructure |

---

## Architecture

```
┌──────────────────────────────────────────┐
│           Application Layer              │
│   REST API · Dashboard · SDK             │
│   Collaborative Compute · Agent Runner   │
├──────────────────────────────────────────┤
│           Protocol Layer                 │
│   Task Orchestration · Smart Contracts   │
│   ZK-Proof / TEE Verification            │
│   Earnings Ledger · Token Economy        │
├──────────────────────────────────────────┤
│           Compute Layer                  │
│   Distributed GPUs · CPUs · Node Client  │
│   Local Models · Cloud Bridge Nodes      │
└──────────────────────────────────────────┘
```

### Centralization trade-off (current state)

The compute layer is fully decentralized — anyone can run a miner node and earn tokens. The orchestrator, however, is currently a single trusted node run by the core team. It holds `MINTER_ROLE` on the token contract and signs all reward transactions, meaning task routing and token issuance are centralized for now. This is a deliberate bootstrapping trade-off, not a permanent design.

Decentralizing the orchestrator is a Phase 3 priority. In the meantime, if you want to run your own independent orchestrator:

1. Deploy fresh contracts: `npx hardhat run scripts/deploy.js --network sepolia`
2. Grant your orchestrator wallet `MINTER_ROLE` on your DeAIToken deployment
3. Start with: `python protocol/orchestrator.py --chain --token-contract 0x... --slashing-contract 0x... --orchestrator-key 0x...`
4. Point your miners at your orchestrator URL instead of the default

Your orchestrator and the core team's run independently — miners choose which one to connect to.

---

## Roadmap

### Phase 1 — Feasibility ✓
- [x] Task orchestration — request routing from API to nodes over WebSocket
- [x] Multi-node routing — scored dispatch (model match, GPU, round-robin fairness)
- [x] Earnings ledger — nodes earn tokens per completed task (in-memory placeholder)
- [x] Real inference — Ollama integration, local models serving actual responses
- [x] Security principles — documented non-negotiable rules for privacy and safety

### Phase 2 — Chain & Infrastructure ✓
**Blockchain strategy:** Deploy smart contracts to a free testnet first (Ethereum Sepolia or Polygon Amoy — no real crypto needed, test tokens are free). Prove the economics work. Move to mainnet once there are real users. Evaluate a custom chain or framework (Cosmos SDK / Substrate) if volume justifies it — that decision stays open until Phase 3.

- [x] **DeAI token contract** — ERC-20 token with mint/burn roles; written, tested (24/24 passing)
- [x] **Payment contract** — escrow: user deposits tokens, released to miner on verified task completion; written, tested
- [x] **Slashing contract** — miners who return bad results lose a portion of their staked tokens; written, tested
- [x] **Testnet deployment** — all three contracts live on Ethereum Sepolia
  - DeAIToken: [`0xE513DAb60018fc63bDB240605CE0816dE7751B27`](https://sepolia.etherscan.io/address/0xE513DAb60018fc63bDB240605CE0816dE7751B27)
  - PaymentContract: [`0x49F2ed162B5DEba2b768BFD79313FADdF3c075C8`](https://sepolia.etherscan.io/address/0x49F2ed162B5DEba2b768BFD79313FADdF3c075C8)
  - SlashingContract: [`0xDFea0F4436E3B30D2861D7b7Acf6c252Da28633c`](https://sepolia.etherscan.io/address/0xDFea0F4436E3B30D2861D7b7Acf6c252Da28633c)
- [x] **On-chain rewards** — orchestrator mints real DEAI to miner wallets on task completion
- [x] **Node Client installer** — one-click setup scripts for Windows (`install_node.ps1`) and Linux/macOS (`install_node.sh`)
- [x] **Marketplace API** — OpenAI-compatible endpoint with optional API key auth (`--api-key`)
- [x] **Persistent Agent Runner** — `application/agent_runner.py`; runs on a token budget, pauses when exhausted, resumes on top-up

### Phase 3 — Mainnet & Collaborative Compute
- [ ] **Mainnet deployment** — move contracts to production chain after testnet validation
- [ ] **Custom chain evaluation** — if transaction volume warrants it, assess building a sovereign chain optimized for Proof of Useful Inference using Cosmos SDK or Substrate
- [ ] **Task Sponsorship** — share a wallet address so others can donate tokens to keep your agent running
- [ ] **Dedicated Mining** — miners point their node at a specific project or agent instead of the general pool
- [ ] Project pages — shareable public page showing an agent's purpose, wallet, and live contributor list
- [ ] Mining pools — group nodes together under a shared project identity
- [ ] ZK-Proof vs. TEE — implement real cryptographic verification to replace mock verifier

### Phase 4 — Provider Auth, Scale & Openness
- [ ] **Provider-passthrough auth** — users and miners authenticate with their existing AI provider (Anthropic, OpenAI, etc.); DeAI never touches billing or credentials
- [ ] **Cloud bridge nodes** — miners contribute their existing provider subscription capacity; earn tokens, provider bills them directly
- [ ] `deai login --provider anthropic` — CLI OAuth flow; no DeAI account required
- [ ] `deai node --provider openai` — node operator flow using existing subscription
- [ ] Relay layer — hide node IPs from orchestrator (see SECURITY.md Rule 6)
- [ ] Sharding — split large tasks across multiple nodes in parallel
- [ ] Model marketplace — community-published model registry; any model, any hardware tier

---

## Collaborative Compute

A core social feature of DeAI. A single person can launch an agent — a research crawler, a creative writing assistant, an automation task — and invite others to keep it alive:

**Token Donation** — Share your task's wallet address. Anyone can send tokens to extend its runtime. No account required, no permission needed.

**Dedicated Mining** — Share a node configuration link. Supporters run a node pointed specifically at your project. Their compute goes directly toward your agent's tasks, and they earn tokens for doing it.

This turns every DeAI agent into a potential community — funded and powered by people who believe in what it's doing.

---

## Developer API (Target Interface)

The goal is a two-line migration from centralized APIs:

```python
# Before
response = client.openai.create(model="gpt-4", ...)

# After
response = client.deai.create(model="llama-3", ...)
```

---

## Model Support

DeAI is model-agnostic by design. Miners run whatever model fits their hardware:

| Tier | Examples | Who runs it |
|---|---|---|
| **Local small** | Llama 3 8B, Mistral 7B, Phi-3 | Anyone with 8GB+ RAM |
| **Local large** | Llama 3 70B, Mixtral | GPU miners with 24GB+ VRAM |
| **Cloud bridge** | GPT-4, Claude, Gemini | Optional — clearly labeled, higher cost |

No single company controls the model layer. If a company pulls their model or restricts access, the network routes around it.

---

## Growth Strategy

1. **"Earn While You Sleep"** — Target crypto-mining and home-server communities. One-click installer, start earning immediately.
2. **Developer-First** — OpenAI-compatible API so any existing app can switch in minutes.
3. **Compute Subsidy** — Free compute credits for developers for 6 months to seed demand and attract node operators.
4. **Collaborative Compute** — Every agent is a shareable, community-fundable project. Word of mouth becomes the growth engine.

---

## Project Structure

```
deai/
├── compute/        # Node client software
├── protocol/       # Orchestration, smart contracts, verification, ledger
├── application/    # API server, SDK, dashboard
├── shared/         # Data schemas used across all layers
└── docs/           # Specifications and research
```

---

## Contributing

This project is in active early development. Contributions, ideas, and critiques are welcome — open an issue to start a discussion.

Before contributing code, read [SECURITY.md](docs/SECURITY.md). The rules there are non-negotiable: no IP logging, no credential transmission, no prompt content on-chain. PRs that violate them won't be merged.

## License

[MIT](LICENSE)
