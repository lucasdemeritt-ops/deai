# DeAI — Verification Approach (Decision + Direction)

> Status: decision doc. The verification approach is the keystone the
> economics, roadmap ordering, and chain choice all hang off of. Replaces the
> open "ZK-Proof vs. TEE" roadmap line with a concrete direction.

---

## Why this is the keystone

A node claims: "I ran model M on prompt P and got output O." The network must
know O is genuinely M(P) — not garbage, and not output from a smaller, cheaper
model the miner swapped in. Until this is real:

- `mock_verify` accepts any non-empty string → the slashing economics cannot
  meaningfully trigger.
- Every downstream economic guarantee is hollow.
- Mainnet (real token value) would be a money printer on day one.

## Why LLM verification is specifically hard

1. **Inference is non-deterministic in practice.** Different GPUs, drivers,
   batch sizes, and backends yield different token sequences for the *same*
   model and prompt — even at temperature 0. "Run it twice, compare exactly"
   does not work across heterogeneous consumer hardware.
2. **Models are huge and outputs are semantic.** Re-verifying a 70B forward
   pass is expensive, and "is this answer correct" is itself AI-hard.

Consequence: "the same model" must be *defined*. Each supported model needs a
**reference inference stack** — a pinned runtime + quantization + decoding
params (temperature 0, fixed seed) — so that "two nodes disagree" is a
well-defined statement. This is a near-term spec task.

## Decision: optimistic-first, tiered toward TEE, zk as research

Verification is a property of a **tier**, mapping onto the existing
Local-small / Local-large / Cloud-bridge model. Users choose trust level and
pay accordingly.

| Tier | Mechanism | Status |
|---|---|---|
| Standard | Optimistic redundant execution + economic slashing | Build now |
| Attested (premium) | TEE attestation (also gives prompt privacy) | When capable miners exist |
| Proven (research) | zkML | When practical; small models first |

Rationale:
- **Optimistic** is the only mechanism deployable today, is model-agnostic,
  runs on consumer GPUs, and makes slashing real.
- **TEE** (NVIDIA H100/H200 Confidential Computing, Intel TDX, AMD SEV-SNP) is
  near-native performance and *also* solves prompt confidentiality (the
  SECURITY.md Rule 3 gap). But it needs datacenter-class GPUs — it cannot be
  the only path without abandoning the consumer-hardware ethos. So: premium
  lane, not mandatory. It becomes especially valuable at sharded-inference
  Stage 2 (see VISION.md) by attesting each shard's enclave.
- **zkML** is the true long-term trustless answer but, as of early 2026,
  proving a full large-LLM forward pass is orders of magnitude slower than the
  inference itself. Track it, prototype on small models, do not gate the
  roadmap on it.

## Optimistic protocol sketch (Stage 0–1)

> Fully specified in **[VERIFICATION_PROTOCOL.md](VERIFICATION_PROTOCOL.md)**
> (state machine, parameter register, threat model, and a live code⇄spec
> conformance ledger). The sketch below is the summary.

1. Accept output O from node A by default; reward accrues but is not finalized.
2. With probability *p*, silently re-dispatch (P, pinned model, fixed decoding)
   to a different randomly chosen node B (optionally a trusted reference node).
3. Compare with **tolerance**, not exact match:
   - exact, if the reference stack guarantees determinism, else
   - semantic similarity (embedding cosine ≥ threshold T), or
   - a judge-model verdict.
4. On disagreement → escalate to a larger committee; majority rules; slash the
   dishonest minority's stake; reverse their accrued reward.
5. Security is economic, not cryptographic: the attacker does not know *which*
   tasks are checked, so cheating is deterred when
   `stake_at_risk × p > gain_per_cheat`.

Hard sub-problems to spec: false-positive risk (slashing an *honest* node
destroys provider trust — providers are the scarce side, this is existential),
collusion/sybil (attacker runs both the cheating node and the checker — ties
verification to the economics workstream), and choice of comparison method.

## What we can build now (no live-test budget required)

All design / local-mock work, none blocked on testing:

1. ✅ **Done.** Optimistic protocol fully specced (p, comparison method,
   escalation/slash flow, reference-inference-stack requirement) in
   [VERIFICATION_PROTOCOL.md](VERIFICATION_PROTOCOL.md).
2. ✅ **Done (seam).** `mock_verify` replaced with a real `Verifier` interface;
   redundant-execution verifier behind it; tested locally with two mock nodes.
   Remaining sub-work (committee, reference stack, final comparator, settlement)
   tracked in VERIFICATION_PROTOCOL.md §8.
3. ✅ **Done (the verifiable half).** GPU bonus removed from pay (`ledger.py`
   + `chain_ledger.py`) and from routing score (`orchestrator.score_node`) —
   self-reported hardware no longer earns or prioritizes; unit-tested.
   **Deferred:** folding hardware into a *measured* benchmark/tier system —
   it depends on the per-model reference stack
   ([VERIFICATION_PROTOCOL.md](VERIFICATION_PROTOCOL.md) §1) and is the
   substrate for difficulty/load-aware scheduling (README Phase 4).
4. Switch rewards to off-chain accrual + claimable batch settlement (Merkle
   distributor pattern) — removes per-task on-chain mint, decouples from chain
   choice, kills a whole exploit/gas class. Buildable in mock mode.
5. Make identity cost something (mandatory minimum stake or proof-of-burn) so
   the optimistic economics are sound. (Overlaps the economics workstream.)

## Deferred / open

- Comparison-method choice (semantic threshold vs. judge model vs. logprob
  agreement) — needs empirical testing.
- Chain architecture: downstream of this decision. If verification stays
  off-chain (optimistic/TEE), a cheap EVM L2 / app-rollup suffices and a
  sovereign chain is a *want*, not a need. A sovereign chain is only
  *technically* justified if verification becomes consensus (validators
  re-verify inference). Revisit only then.
- zkML maturity — research-track, re-evaluate periodically.
