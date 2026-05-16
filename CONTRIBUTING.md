# Contributing to DeAI

Thanks for your interest. DeAI is an early-stage open source project and contributions of any kind are welcome — code, bug reports, docs, and ideas.

## Before you start

Read [docs/SECURITY.md](docs/SECURITY.md). The rules there are non-negotiable. PRs that log IPs, transmit credentials, or store prompt content on-chain will not be merged, no matter how well-written they are.

---

## Running the project locally

### Prerequisites

| Tool | Version | Required for |
|---|---|---|
| Python | 3.10+ | Orchestrator + node client |
| Node.js | 18+ | Smart contracts |
| Ollama | any | Real inference (optional — mock mode works without it) |

### 1. Clone and install

```bash
git clone https://github.com/theblankist/deai.git
cd deai
pip install -r requirements.txt
```

### 2. Start the orchestrator

```bash
python protocol/orchestrator.py
```

Runs on `http://localhost:8000`. Leave this terminal open.

### 3. Connect a node (no Ollama needed)

Open a second terminal:

```bash
# Mock mode — simulates inference, no model download required
python compute/node.py --models llama3

# Real inference — requires Ollama running with a model pulled
python compute/node.py --ollama --auto
```

### 4. Send a test request

Open a third terminal:

```bash
python test_request.py --message "Hello from DeAI"

# Check connected nodes and earnings
python test_request.py --status
```

### 5. Smart contracts (optional)

```bash
cd chain
npm install
npm test          # runs all 24 contract tests
npx hardhat run scripts/deploy.js   # deploys to local network
```

---

## How to contribute

1. **Open an issue first** for anything beyond a typo fix — describe what you want to change and why. This prevents wasted effort if the direction doesn't fit the roadmap.

2. **Fork and branch** off `main`. Name your branch something descriptive: `feat/relay-layer`, `fix/heartbeat-timeout`, etc.

3. **Keep PRs focused.** One logical change per PR. If you're fixing a bug and spotted a refactor opportunity, open two PRs.

4. **Tests.** If you're touching the smart contracts, run `npm test` in `chain/` and make sure all 24 pass. Python changes don't have a formal test suite yet — manually verify the three-terminal flow still works.

5. **No new dependencies without discussion.** Open an issue before adding a package.

6. **Commit messages.** Plain English, present tense: `Add scored routing for GPU nodes`, not `Added routing stuff`.

---

## Project structure

```
deai/
├── protocol/
│   ├── orchestrator.py   # Network brain — WebSocket hub, task dispatch, REST API
│   └── ledger.py         # In-memory token ledger (placeholder for on-chain)
├── compute/
│   └── node.py           # Miner node client — connects to orchestrator, runs inference
├── shared/
│   └── schemas.py        # Pydantic models shared across layers
├── chain/
│   ├── contracts/        # Solidity smart contracts
│   ├── test/             # Contract test suite (Mocha + Hardhat v3)
│   └── scripts/          # Deployment scripts
├── docs/
│   └── SECURITY.md       # Non-negotiable security rules
└── test_request.py       # CLI test tool
```

---

## Areas actively looking for help

- **Verification layer** — replace `mock_verify()` in orchestrator with real result verification
- **Node installer** — one-click setup script for Windows and Linux miners
- **Python tests** — formal test suite for the orchestrator and node client
- **Front-end** — simple dashboard to visualize nodes, tasks, and earnings
- **Docs** — architecture deep-dives, tutorials, model compatibility guides

---

## Questions?

Open a GitHub issue tagged `question`. We don't have a Discord yet — when there are enough people who want one, we'll set it up.
