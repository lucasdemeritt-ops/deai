# DAI — The Actual Goal and the Path There

> Status: direction doc. Records the intended end-state and the staged path to
> it. This is *target*, deliberately separated from current state (see README
> "Verification & economics (current state)" for what exists today).

---

## The goal, stated plainly

The goal is **not** "one node does one whole inference and we verify it." That is
only the starting point.

The goal is that **a single node contributes part of the work** — so that no
node needs to be powerful enough to run a whole large model alone, and many
small contributors collectively run models none of them could run individually.
That collective, permissionless capacity is the mission.

## The crypto analogy — what's true, what's a false friend

The mental model came from Bitcoin mining. It's worth being precise, because it
cuts the opposite way from intuition:

- In Bitcoin, **every miner does the same whole work, redundantly, in a race.**
  All of it is discarded except the single winner's. The work is *deliberately
  wasteful and non-reusable.*
- A mining **pool** does not split a block's work into parts. It splits the
  **reward** — members submit "shares" proving they did some guessing and are
  paid proportionally.

So the faithful mapping of the analogy is **reward sharing among many
contributors**, not "split one unit of work." Splitting the work itself is a
real and separate thing — and it is much harder. DAI's pitch (useful,
non-wasted compute) is the *opposite* of Bitcoin's intentional redundancy.

## Three real architectures for "many nodes contribute"

**A. Reward pooling.** Each node still does a *whole* inference; earnings are
pooled and split across a project's supporters. The faithful mining-pool
mapping. Difficulty: low — an accounting/economics design, not a compute one.
Already implied by roadmap "Mining pools / Dedicated Mining."

**B. Job parallelism (agent swarms).** A large *job* is decomposed into many
independent sub-tasks, each a whole inference on a different node, results
aggregated by a coordinator. "Many nodes contribute to one goal" with no
per-token coupling. Difficulty: moderate — mostly orchestration. Buildable and
testable now. Already on the roadmap as "agent swarms."

**C. Model-sharded inference — the literal version of the goal.** One large
model split across many nodes; each holds only some layers; one answer is
produced by streaming activations node→node. A low-VRAM node can hold a slice
of a model it could never run alone.

Honest reality on C (this is not science fiction — Hugging Face's *Petals* ran
176B-parameter models over volunteer internet nodes):
- **Network-latency bound.** Activations cross the internet for every token.
  Good for batch/async/agent workloads; weak for low-latency chat. Pursue
  latency-tolerant use cases first.
- **Fragile.** A node dropping mid-generation stalls the request unless every
  shard has a hot standby — a real redundancy cost.
- **Verification gets harder, not easier.** Each shard's partial computation
  must be attributable and checkable, not just one final output. It compounds
  the keystone problem.
- It is the same problem family as distributed training (below).

**D. Distributed training (moonshot / Phase 5).** Coordinated state across many
nodes, gradient sync, straggler/Byzantine tolerance, and proof of honest
contribution — an open research problem at scale over untrusted networks.

## The staircase — not moonshot *or* pragmatic, one progression

Each step is independently useful, shippable, and provable before the next is
built. This is the "take steps to get there so we can prove it works" path.

| Stage | What it is | Difficulty | Verification (see VERIFICATION.md) |
|---|---|---|---|
| 0 — now | One node, whole inference | Built | Optimistic + economic slashing |
| 1 | Job parallelism (swarms) + reward pooling | Moderate, buildable now | Optimistic per sub-task |
| 2 | Model-sharded inference (the literal goal) | Hard (Petals-class) | Per-shard checks; TEE attestation shines here |
| 3 — moonshot | Distributed training at scale | Research-grade | zkML / open research |

The tiered verification plan is the connective tissue. At Stage 2, TEE
attestation becomes especially attractive because attesting each shard's
enclave sidesteps the brutal per-shard verification problem (and is the prompt
privacy story too). The vision and the verification plan are the same plan.

## A note on verification and waste — share, don't multiply

A fair worry once you see redundant verification at work: if many nodes re-run
the same inference and only one result counts, isn't that multiplying compute,
the opposite of the mission? The answer is that redundancy is a *sampled
economic tax*, not the operating mode. The network's job is to **share** work —
different requests to different nodes, and ultimately one inference split across
nodes (the staircase above). The only repeated work is a small random *check*,
and even that shrinks over time as cheaper verification layers (node
qualification, canary tasks, reputation, TEE attestation) take over. Running
everything in parallel would defeat the purpose; the design specifically avoids
it. (Details: VERIFICATION_PROTOCOL.md §9.)

There is also a constructive role here for the most powerful machines. Rather
than only competing to serve plain inference, high-end nodes can opt into a
**verification pool** — staked, larger-model judges that adjudicate disputes and
sell a premium "judge-verified" assurance lane. That turns expensive hardware
into a source of network *health* (better dispute resolution, deeper capacity)
instead of leaving it idle or priced out. It is a research direction, with real
cost and centralization tradeoffs, specified in VERIFICATION_PROTOCOL.md §11.

## Next workstream: economics & valuation (not yet started)

Captured here so it is not lost. This is the next to-do list, deliberately
unanswered until we work it deliberately:

1. **Supply policy.** What mints DAI? Capped or uncapped? Emission tied to
   verified useful work *and* real demand, not unbounded.
2. **Source of value.** What makes DAI worth anything — is it required to pay
   for inference, or optional? Native token vs. stablecoin settlement for
   price-stable compute pricing.
3. **Sybil cost.** A fresh wallet must not be a free identity. Mandatory
   minimum stake or proof-of-burn so optimistic verification's economics hold.
4. **Stake economics.** Slashing magnitude vs. per-task reward; the condition
   `stake_at_risk × check_probability > gain_per_cheat` must hold.
5. **Reward attribution under pooling/sharding.** How one task's reward is
   split fairly *and verifiably* across N contributing nodes.
6. **Admin-key sunset.** Concrete plan to renounce / timelock / govern the
   token `DEFAULT_ADMIN_ROLE` before any valued token exists.
7. **Non-transferable until graduation.** Keep DAI non-transferable (no DEX,
   no bridge) until verification + economics are proven, decoupling
   "persistent chain" from "real money."
8. **Regulatory surface.** A token with market value carries legal/regulatory
   exposure — flag for real advice, do not self-advise.

## Roadmap note

The staged sequencing above (verification before mainnet; mainnet behind
proven economics) is the *intended* order. The public README roadmap has not
been re-ordered yet — that is a deliberate, visible strategy change to confirm
before promoting it from this doc into the README.
