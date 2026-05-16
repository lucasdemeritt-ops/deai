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
├──────────────────────────────────────────┤
│           Protocol Layer                 │
│   Task Orchestration · Smart Contracts   │
│   ZK-Proof / TEE Verification            │
├──────────────────────────────────────────┤
│           Compute Layer                  │
│   Distributed GPUs · CPUs · Node Client  │
└──────────────────────────────────────────┘
```

---

## Roadmap

### Phase 1 — Feasibility (Months 1–6)
- [ ] Compare ZK-Proofs vs. TEE for verifiable inference
- [ ] Design the Orchestration Layer (task routing protocol)
- [ ] Build a centralized-to-decentralized bridge prototype (1 server → 3–5 nodes)

### Phase 2 — Infrastructure (Months 6–12)
- [ ] Node Client — one-click installer (Windows/Linux) to join the network
- [ ] Incentive Layer — smart contracts for payments, slashing, and rewards
- [ ] Marketplace API — drop-in OpenAI-compatible endpoint for developers

### Phase 3 — Scaling (Months 12–24)
- [ ] Testnet launch — open to community; adversarial testing
- [ ] Sharding — split large tasks across multiple nodes in parallel

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

## Growth Strategy

1. **"Earn While You Sleep"** — Target crypto-mining and home-server communities. One-click installer, start earning immediately.
2. **Developer-First** — OpenAI-compatible API so any existing app can switch in minutes.
3. **Compute Subsidy** — Free compute credits for developers for 6 months to seed demand and attract node operators.

---

## Project Structure

```
deai/
├── compute/        # Node client software
├── protocol/       # Orchestration, smart contracts, verification
├── application/    # API server, SDK, dashboard
└── docs/           # Specifications and research
```

---

## Contributing

This project is in the early research and design phase. Contributions, ideas, and critiques are welcome — open an issue to start a discussion.

## License

[MIT](LICENSE)
