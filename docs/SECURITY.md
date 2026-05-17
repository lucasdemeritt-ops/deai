# DeAI Security Principles

These are non-negotiable design rules. Every contributor must read this before touching the codebase. Every feature must be evaluated against these principles before it ships.

---

## The Core Promise

A user or miner on the DeAI network should never have to trust us. They should be able to verify — by reading the open source code — that their identity, credentials, and content are safe. Trust is not a policy. It is a property of the system.

---

## Current State vs. Target

This document describes the **target** security properties of the network. Several are not yet enforced *by the system* — today they hold only because a single trusted orchestrator, run by the core team, behaves correctly and its code is open to audit.

The distinction matters and we state it plainly: the Core Promise above says trust should be a *property of the system*, not a policy. Until the relay layer (Rule 6) and a decentralized orchestrator exist, Rules 1 and 3 are enforced by policy plus code review of a single operator — not yet by the architecture. Where that gap exists it is flagged inline as **[Current state]**. See also *Known Centralization (Current State)* at the end of this document.

---

## Rule 1: IP Addresses Are Never Stored

**What this means:**
- The orchestrator sees IP addresses transiently when a node or user connects. It does not log them, write them to disk, or record them on-chain. Ever.
- No analytics, no access logs, no "debugging" databases that capture IPs.
- The chain records wallet addresses and task proofs. It never records network addresses.

**Why:**
An IP address can identify a person's physical location and ISP. In some countries, using an AI network could be dangerous. We do not create records that could be subpoenaed, hacked, or leaked to put a user at risk.

**How we enforce it:**
- The orchestrator codebase is open source and auditable.
- No third-party analytics or logging services are integrated.
- Future versions will route node connections through a relay layer so the orchestrator never sees real IPs at all — only the relay does, transiently.

**[Current state]** Enforced today by a single trusted orchestrator that sees connecting IPs transiently and is coded not to log or store them. This is a policy + auditable-code guarantee, not yet an architectural one — the relay layer (Rule 6) is what turns it into a true system property.

---

## Rule 2: API Keys and Provider Credentials Never Leave the Miner's Machine

**What this means:**
- When a miner runs a cloud bridge node (backed by Anthropic, OpenAI, or any other provider), their credentials are stored locally in an encrypted config file on their own machine.
- The orchestrator sends the task text to the miner. The miner calls the provider API directly from their machine using their own key. The result comes back to the miner. The miner returns the result to the orchestrator.
- At no point does any credential touch the network, the orchestrator, or the chain.

```
Orchestrator ──── task text ────► Miner's machine
                                       │
                                  Miner calls provider
                                  API locally with their key
                                       │
Orchestrator ◄─── result only ──── Miner's machine
```

**Why:**
A stolen API key means someone else runs up charges on your subscription. We will never put ourselves in a position where a breach of our infrastructure could compromise a miner's provider account.

**How we enforce it:**
- The node client code is open source. Anyone can verify that credentials are never serialized into outbound messages.
- Credentials are stored using the same model as SSH keys — local file, encrypted at rest, never transmitted.

---

## Rule 3: Prompt Content Never Goes On-Chain

**What this means:**
- The actual text of a user's request (the prompt) and the model's response are never written to the blockchain.
- What goes on-chain is a **cryptographic hash** of the task — a fixed-length fingerprint that proves the task happened and was completed, without revealing what it contained.
- The prompt travels only between the user, the orchestrator (transiently), and the assigned node.

**Why:**
Blockchains are permanent and public. A prompt written to a chain today could be read by anyone, forever. Users must be able to ask sensitive questions — medical, legal, personal — without those questions becoming part of a permanent public record.

**What a hash looks like:**
```
Prompt:  "What are the symptoms of depression?"
On-chain: 0x3f7a2c1b...  ← this is all anyone sees
```
The hash proves the task existed and was verified. It reveals nothing about the content.

**[Current state]** No prompt content is written to disk or chain anywhere in the codebase today — that part is real. The remaining gap is that the single orchestrator holds the full plaintext prompt in memory while routing each task. Nothing persists it, but that is currently a property of one trusted operator's code, not of the architecture. The relay layer and end-to-end task encryption are what close this.

---

## Rule 4: Wallet Addresses Are Pseudonymous, Not Anonymous

**What this means:**
- Wallet addresses are public by design. Anyone can see that wallet `0xABC...` earned tokens for completing tasks.
- What they cannot see is who owns that wallet, what tasks were completed, or what the prompts contained.
- Users and miners are responsible for maintaining their own wallet hygiene (not reusing wallets across contexts, not linking wallets to public identities carelessly).

**Why we are transparent about this:**
Pseudonymity is not the same as anonymity. We will not mislead users into thinking the chain is private. It is transparent by design — that transparency is what makes the token economy trustworthy. The protection is that content and identity are never linked to the wallet.

---

## Rule 5: Node Identity Is Ephemeral and Rotatable

**What this means:**
- Node IDs are randomly generated at startup. A miner can rotate their node ID at any time without losing their wallet balance.
- Nothing in the protocol permanently links a node ID to a wallet, a machine, or a person.
- Reputation (task completion history) accrues to wallet addresses, not node IDs, so rotation doesn't penalize good miners.

**Why:**
A permanent, trackable node ID is a surveillance vector. If someone can correlate a node ID over time with network traffic patterns, they can potentially locate a miner. Ephemeral IDs make this significantly harder.

---

## Rule 6: The Relay Layer (Phase 4)

In Phase 4, direct node-to-orchestrator connections will be replaced with a relay layer. This means:

- Nodes connect to a relay, not directly to the orchestrator.
- The orchestrator never sees node IP addresses — only the relay does, and only transiently.
- This is architecturally similar to how Tor separates the sender from the receiver.

Until the relay layer is built, nodes connect directly and the orchestrator sees their IP transiently (but does not store it, per Rule 1).

---

## Known Centralization (Current State)

For honesty, the centralizations that exist **today** and are **not** the intended end state:

1. **Single orchestrator.** One core-team node routes all tasks and is the sole holder of `UPDATER_ROLE` on `MerkleDistributor` (it alone publishes the cumulative reward roots). It no longer holds the token `MINTER_ROLE` — rewards accrue off-chain and the distributor mints only what a published root authorizes, so there is no permanently-hot mint key (build-now #4). Task routing and reward-root authority remain centralized for the bootstrapping phase. (Also documented in the README.) Decentralizing the orchestrator is a roadmap priority.
2. **Token admin key.** `DeAIToken` grants `DEFAULT_ADMIN_ROLE` to the deploying wallet. That wallet can grant itself `MINTER_ROLE` and mint without limit. This is a deployment convenience for the testnet phase — it is **not** the intended final design. Before any mainnet deployment this role must be renounced, time-locked, or moved to governance. The exact mechanism is an open decision, not yet made.

On the live testnet you are currently trusting the core team not to abuse these keys. The mission is to engineer that requirement away — not to pretend it doesn't exist. These are tracked as current-vs-target gaps.

---

## What This Means for Contributors

Before submitting code, ask:

1. **Does this log or store an IP address?** If yes, remove it.
2. **Does this transmit a credential over the network?** If yes, rearchitect it.
3. **Does this write prompt content anywhere persistent?** If yes, replace it with a hash.
4. **Does this introduce a third-party service that could collect user data?** If yes, it requires explicit discussion and approval before merging.

These rules are not suggestions. PRs that violate them will not be merged regardless of other merits.

---

## Reporting Security Issues

Do not open a public GitHub issue for security vulnerabilities. Contact the maintainers directly. We commit to responding within 48 hours and will credit responsible disclosure.

---

*This document is a living standard. As the protocol evolves, these principles apply to every new layer. When in doubt, default to less data, not more.*
