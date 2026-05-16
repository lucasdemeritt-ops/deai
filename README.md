# DeAI — Decentralized AI Network

> A permissionless, censorship-resistant compute marketplace where anyone with a GPU or CPU earns by powering AI inference.

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

---

## Roadmap

### Phase 1 — Feasibility (Months 1–6)
- [x] Task orchestration — request routing from API to nodes over WebSocket
- [x] Multi-node routing — scored dispatch (model match, GPU, round-robin fairness)
- [x] Earnings ledger — nodes earn tokens per completed task
- [ ] ZK-Proof vs. TEE research — choose the verification approach
- [ ] Mock → real inference — Ollama integration for local model execution

### Phase 2 — Infrastructure (Months 6–12)
- [ ] Node Client installer — one-click setup for Windows/Linux miners
- [ ] Smart contracts — on-chain payments, slashing for bad actors, token economy
- [ ] Persistent Agent Runner — long-running agents funded by a token budget; pause and resume as balance allows
- [ ] Multi-model support — nodes advertise what they can run; routing matches model to capable node
- [ ] Marketplace API — drop-in OpenAI-compatible endpoint for any existing app

### Phase 3 — Collaborative Compute (Months 12–18)
- [ ] **Task Sponsorship** — share a wallet address so others can donate tokens to keep your agent running
- [ ] **Dedicated Mining** — miners point their node at a specific project or agent instead of the general pool
- [ ] Project pages — shareable public page showing an agent's purpose, wallet, and live contributor list
- [ ] Mining pools — group nodes together under a shared project identity

### Phase 4 — Provider Auth & Cloud Bridge (Months 18–24)
- [ ] **Provider-passthrough auth** — users and miners authenticate with their existing AI provider (Anthropic, OpenAI, etc.) using OAuth login or API key; DeAI never touches billing or payment
- [ ] **Cloud bridge nodes** — miners run a node backed by their own provider subscription; tasks route through it, miner earns tokens, provider bills the miner directly as always
- [ ] `deai login --provider anthropic` — CLI auth flow; sign into your existing account, no DeAI account or separate billing required
- [ ] `deai node --provider openai` — node operator flow; contribute your existing subscription capacity to the network and earn tokens back
- [ ] Testnet launch — open to community; adversarial testing and security audit
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
