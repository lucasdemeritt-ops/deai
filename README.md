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

> **Status:** steps 3–4 describe the *target* design. Today inference runs in a normal process. Verification now goes through a pluggable `Verifier` seam: the default is still a non-empty-content check, with an *optimistic redundant-execution* verifier available behind `--verify-sample-rate` (off by default). Committee escalation, the empirical comparison method, TEE/zkML tiers, and on-chain escrow payment are not yet implemented — see [Verification & economics (current state)](#verification--economics-current-state) below.

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

### Verification & economics (current state)

The sections above describe the target system. Several core pieces are deliberately still placeholders, and we'd rather state that than imply protections that aren't there yet:

- **Verification is early.** The old `mock_verify` is gone — replaced by a pluggable `Verifier` seam (`protocol/verification.py`). The default `ContentVerifier` still only checks for non-empty content (legacy behaviour, so nothing changes unless opted in). An optimistic `RedundantExecutionVerifier` exists and is unit-tested: with a sampling rate it silently re-runs a task on a second node and compares. It is **off by default** and still incomplete — committee escalation is not built (a two-sample mismatch is rejected but no node is auto-slashed, deliberately, to avoid false-positive slashing of honest providers), the comparison method is a labelled placeholder pending empirical work, and the per-model reference inference stack does not exist yet. So real Proof-of-Useful-Inference is in progress, not done.
- **No escrow in the live path.** `PaymentContract` (user deposit → escrow → release to miner) is written and unit-tested, but it is *not* wired into the running orchestrator. The live reward path mints DEAI directly to the miner on task completion — there is no user payment or escrow today.
- **DEAI has no monetary value.** The contracts are deployed only on the Ethereum Sepolia *testnet*. Sepolia DEAI is a valueless test token used to prove the mechanics. Nothing here is real money.
- **The chain is an open question.** Sepolia is for testing only. Whether DeAI ultimately runs on an existing chain or its own sovereign chain is an explicitly undecided, deferred decision — not committed in either direction.

Closing the verification gap is the single highest priority before any of the token economics can be trusted.

---

## Direction & Design

The current-state notes above are deliberately honest about what is *not* yet built. The design direction that closes those gaps is decided and documented:

- **[docs/VISION.md](docs/VISION.md)** — the actual goal: many nodes *contribute to* an inference, not one node per task. The honest staircase to get there (single-node → job-parallel swarms → model-sharded inference → distributed training) and why each step is independently testable.
- **[docs/VERIFICATION.md](docs/VERIFICATION.md)** — the keystone decision: verification is *optimistic-first* (redundant execution + economic slashing), *tiered* toward TEE attestation, with zkML as a research track. Real verification comes **before** mainnet, not after. Full Stage 0–1 protocol spec (state machine, parameters, threat model, code⇄spec conformance ledger) in **[docs/VERIFICATION_PROTOCOL.md](docs/VERIFICATION_PROTOCOL.md)**.
- **[docs/ECONOMICS.md](docs/ECONOMICS.md)** — the token model: DEAI is redeemable for real inference at a rate that is *transparently and verifiably determined, never set at anyone's discretion* (the redemption invariant + the immutable self-check). Stable on-ramps absorb volatility; the token is non-transferable and valueless until an explicit graduation checklist is met.

One-line summary of the sequencing: **trustworthy work-measurement is the keystone — honest pay and an honest redemption rate both depend on it — so verification and economic hardening come first, and mainnet is a graduation exam gated behind them, not a milestone to rush.**

---

## Roadmap

### Phase 1 — Feasibility ✓
- [x] Task orchestration — request routing from API to nodes over WebSocket
- [x] Multi-node routing — scored dispatch (model match, GPU, round-robin fairness)
- [x] Earnings ledger — nodes earn tokens per completed task (in-memory placeholder)
- [x] Real inference — Ollama integration, local models serving actual responses
- [x] Security principles — documented non-negotiable rules for privacy and safety

### Phase 2 — Chain & Infrastructure ✓
**Blockchain strategy:** Smart contracts are deployed to a free testnet (Ethereum Sepolia) with a valueless test token. The token stays non-transferable until verification and economics are proven. Mainnet, and the existing-chain-vs-sovereign-chain decision, are deliberately deferred and gated — see [docs/ECONOMICS.md](docs/ECONOMICS.md), [docs/VERIFICATION.md](docs/VERIFICATION.md), and the re-ordered roadmap below.

- [x] **DeAI token contract** — ERC-20 token with mint/burn roles; written, tested (24/24 passing)
- [x] **Payment contract** — escrow: user deposits tokens, released to miner on verified task completion; written, tested — **not yet integrated into the live orchestrator path** (see *Verification & economics (current state)* above)
- [x] **Slashing contract** — miners who return bad results lose a portion of their staked tokens; written, tested
- [x] **Testnet deployment** — all three contracts live on Ethereum Sepolia
  - DeAIToken: [`0xE513DAb60018fc63bDB240605CE0816dE7751B27`](https://sepolia.etherscan.io/address/0xE513DAb60018fc63bDB240605CE0816dE7751B27)
  - PaymentContract: [`0x49F2ed162B5DEba2b768BFD79313FADdF3c075C8`](https://sepolia.etherscan.io/address/0x49F2ed162B5DEba2b768BFD79313FADdF3c075C8)
  - SlashingContract: [`0xDFea0F4436E3B30D2861D7b7Acf6c252Da28633c`](https://sepolia.etherscan.io/address/0xDFea0F4436E3B30D2861D7b7Acf6c252Da28633c)
- [x] **On-chain rewards** — orchestrator mints DEAI test tokens to miner wallets on task completion (Sepolia testnet — no monetary value)
- [x] **Node Client installer** — one-click setup scripts for Windows (`install_node.ps1`) and Linux/macOS (`install_node.sh`)
- [x] **Marketplace API** — OpenAI-compatible endpoint with optional API key auth (`--api-key`)
- [x] **Persistent Agent Runner** — `application/agent_runner.py`; runs on a token budget, pauses when exhausted, resumes on top-up

> **Re-ordered:** verification and economic hardening now precede mainnet, and the original "Phase 5 — Distributed Training" moonshot is honestly sequenced last as the actual destination. See *Direction & Design* above.

### Phase 3 — Verification & Economic Foundations (the keystone)

Nothing below ships with real value until this phase is proven. All of it runs on the non-transferable testnet. See [docs/VERIFICATION.md](docs/VERIFICATION.md) and [docs/ECONOMICS.md](docs/ECONOMICS.md).

- [~] **Real verification** — *in progress.* `Verifier` seam landed (`protocol/verification.py`) with an optimistic redundant-execution verifier (sampled silent re-dispatch + tolerance comparison), unit-tested, off by default. Remaining: committee escalation + blame attribution, the empirically-chosen comparison method, per-model reference inference stack, then turn sampling on. This is what makes slashing meaningful.
- [ ] **Trustworthy work-measurement** — the shared substrate that both honest pay *and* the honest redemption rate depend on.
- [ ] **Tiered verification** — Standard (optimistic) now; Attested (TEE, also prompt privacy) as a premium lane; zkML as a research track.
- [ ] **Vesting-bond sybil resistance** — no upfront stake; unvested earnings act as a slashable bond. Preserves no-barrier-to-entry.
- [ ] **Redemption-anchored economics** — DEAI redeemable for inference at a transparently determined rate; stablecoin/fiat on-ramps; burn sinks.
- [ ] **The immutable self-check** — open on-chain rule, tamper-evident inputs, publicly recomputable, rule changes only via a pre-announced timelocked path. (Expected to take more than one iteration — see ECONOMICS.md.)
- [ ] **Decentralize the orchestrator** — remove the single-trusted-node and `MINTER_ROLE` centralization.

### Phase 4 — Collaborative Compute & Scale

The contribution staircase begins (VISION.md Stage 1) alongside openness work.

- [ ] **Job parallelism / agent swarms** — large jobs decomposed into independent sub-tasks across many nodes, results aggregated by a coordinator.
- [ ] **Reward pooling & dedicated mining** — supporters point nodes at a specific project; pooled rewards. Task sponsorship; shareable project pages.
- [ ] **Provider-passthrough auth** — authenticate with an existing AI provider (Anthropic, OpenAI, etc.); DeAI never touches billing or credentials.
- [ ] **Cloud bridge nodes** — contribute existing provider subscription capacity; the provider bills the miner directly.
- [ ] **Relay layer** — hide node IPs from the orchestrator (SECURITY.md Rule 6); turns Rules 1 & 3 from policy into architecture.
- [ ] **Model marketplace** — community-published model registry; any model, any hardware tier.

### Phase 5 — Mainnet Graduation

Mainnet is a graduation exam, not a deadline. Entered only when the checklist in [docs/ECONOMICS.md](docs/ECONOMICS.md) is met: verification false-positive rate measured low, sybil resistance demonstrated, redemption-rate rule reproducible and stable, contracts audited, legal review complete.

- [ ] **Graduation checklist cleared** on testnet.
- [ ] **Mainnet deployment** — the token becomes transferable / value-bearing only here.
- [ ] **Chain decision** — a cheap existing EVM L2 by default; a sovereign chain (Cosmos SDK / Substrate / app-rollup) only if verification becomes consensus. Explicitly downstream of the verification architecture.
- [ ] **Key & rate-rule authority sunset** — multisig + timelock before any value; broader governance later.

### Phase 6 — Model-Sharded Inference & Distributed Training (the goal)

The actual destination (VISION.md Stages 2–3): no node needs to run a whole large model alone.

- [ ] **Model-sharded inference** — a single inference split across many nodes (Petals-class); the literal "one node contributes part of the work."
- [ ] **Per-shard verification** — TEE attestation per shard becomes especially valuable here.
- [ ] **Training job orchestration** — coordinate multi-node training runs; handle node dropout and job resumption gracefully.
- [ ] **Gradient aggregation** — secure aggregation of model updates across contributing nodes.
- [ ] **Training verification** — cryptographic or statistical confirmation that nodes contributed honest compute to a training run.
- [ ] **Long-job economics** — token model for hours/days-long jobs; partial payouts, checkpointing, slashing for early dropout.
- [ ] **Open model registry** — community-trained models published; anyone contributes compute, anyone uses the result.

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
