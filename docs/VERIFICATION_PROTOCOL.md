# DeAI — Optimistic Verification Protocol (Spec)

> Status: spec doc. This is build-now item #1 from
> [VERIFICATION.md](VERIFICATION.md) — the full specification of the **Standard
> tier** (optimistic redundant execution + economic slashing) for VISION.md
> **Stage 0–1 only**. It is the design the `Verifier` seam shipped in
> `protocol/verification.py` must converge to. Consistent with VERIFICATION.md
> (the decision) and ECONOMICS.md §4–§6 (sybil bond, slash magnitude, the
> shared work-measurement). Empirical parameters are explicitly deferred to the
> non-transferable testnet — this doc specs the *framework and invariants*, not
> the numbers. §8 is a live conformance ledger so code and spec cannot drift.

---

## 0. Scope

**Specified here:** the Standard verification tier for Stage 0 (one node / one
task) and Stage 1 (job-parallel sub-tasks): roles, the task lifecycle state
machine, the sampling rule, the comparison framework, the escalation/slash
flow, the threat model, and a parameter register.

**Not specified here (deferred, by design):**
- Attested (TEE) and Proven (zkML) tiers — future tiers, not stubs
  (VERIFICATION.md).
- Stage 2 model-sharded reward attribution — explicitly deferred, do not
  over-design (ECONOMICS.md §3).
- The numeric value of every empirical parameter — testnet-tuned
  (ECONOMICS.md §5, "Deferred / open").

**One-sentence why:** a node claims "I ran model M on prompt P and got O"; the
network must make that claim economically unprofitable to fake, because the
redemption rate (ECONOMICS.md §1) is computed from this *same* verified
work-measurement — rate honesty is downstream of verification honesty, one
problem not two.

---

## 1. Roles & definitions

- **Requester** — submits an inference task via the HTTP API.
- **Orchestrator** — owns the node registry, dispatch, sampling decision,
  re-dispatch, and (today) settlement. Currently a single trusted node
  (disclosed; decentralizing it is a separate roadmap item).
- **Primary** — the node that produced the result returned to the requester.
- **Checker** — a *different* node the same task is silently re-dispatched to.
- **Committee** — N independent nodes consulted when primary and checker
  disagree. (Not yet implemented — see §5, §8.)
- **Reference inference stack (per model)** — the pinned definition of "the
  same model": runtime + version, quantization, decode params (temperature 0,
  fixed seed), max tokens. Without this, "two nodes disagree" is not a
  well-defined statement (VERIFICATION.md, "Why LLM verification is hard").
  **A model is not eligible for the Standard tier until its reference stack is
  registered.** No model registry exists yet — this is the single largest
  unbuilt prerequisite.

A result is **honest** iff it is what the model's registered reference stack
produces for P, within the tier's comparison tolerance. Everything below
defines how the network decides that economically rather than cryptographically.

---

## 2. Task lifecycle (state machine)

```
SUBMITTED
  └─> DISPATCHED (primary)            orchestrator: find_best_node, send
        └─> RESULT_IN                  primary returns task_complete
              └─> WELL_FORMED?         cheap local gate (non-empty etc.)
                    ├─ no  ─> REJECTED_MALFORMED   (slash path, §5.1)
                    └─ yes ─> SAMPLED?  with probability p (§3)
                              ├─ no  ─> FINALIZED            (optimistic accept)
                              └─ yes ─> RECHECK_DISPATCHED (checker ≠ primary)
                                          └─> COMPARED (§4)
                                                ├─ agree    ─> FINALIZED
                                                ├─ no checker free ─> FINALIZED*
                                                └─ disagree ─> DISPUTED
                                                                  └─> ESCALATED (§5)
                                                                        ├─ primary upheld ─> FINALIZED
                                                                        └─ primary dishonest ─> SLASHED
```

- `FINALIZED` = result returned, reward **accrues off-chain** to the primary.
  Build-now #4 is **done**: there is no per-task mint; cumulative accrual is
  settled once per epoch as a Merkle root via `MerkleDistributor`, and miners
  claim themselves. Under the target economics this accrual is still meant to
  be **unvested/bonded** until a vesting period elapses (ECONOMICS.md §4) —
  that vesting layer, and slash-reduces-accrual, are the documented next step
  (the accrual seam is built to accept them without rework).
- `FINALIZED*` (no checker available) = accept optimistically rather than
  punish a provider for a thin network; the task is recorded as *unverified*.
  This is a deliberate availability-over-strictness choice for the bootstrap
  phase and must be revisited before mainnet (an attacker could DoS the checker
  pool to force this branch).
- `DISPUTED → ESCALATED` is currently a **stub**: the implementation rejects
  the result to the requester and flags `escalation_required`; it does **not**
  convene a committee and does **not** auto-slash. This is intentional (§5.2).

---

## 3. Sampling probability `p`

**Invariant (decided).** Cheating must be -EV:

```
expected_penalty(slashable_bond, p)  >  expected_gain_per_cheat
```

(ECONOMICS.md §5.) The attacker must not be able to tell which tasks are
checked — sampling is **silent** (the checker dispatch is an ordinary task; the
node is never told it is a recheck). Security is economic, not cryptographic.

**Decided:**
- `p` is a protocol parameter, applied per task, silent.
- Recheck always lands on a node *other than* the primary (`exclude` set).
- `p` may be **conditioned** (higher for: new/low-reputation nodes, high-value
  tasks, models whose recent dispute rate is elevated). The conditioning
  inputs must themselves be tamper-evident (they feed economics).

**Deferred (empirical, testnet):** the baseline numeric `p`, the conditioning
schedule, and how `p` trades off against `slash_fraction` and the comparison
threshold (jointly optimised — ECONOMICS.md §5).

**Today:** `p` is a single static knob (`--verify-sample-rate`, default `0.0`).
Default-off is the *bootstrap* setting (legacy behaviour, no behaviour change
on merge), **not** the target — the target is `p > 0`, conditioned, once
reference stacks and committee escalation exist.

---

## 4. Comparison

The hard part. Re-running M(P) on a second node does **not** yield byte-equal
output across heterogeneous consumer hardware even at temperature 0
(VERIFICATION.md). So comparison is **tolerant**, and the tolerance method is a
*pluggable policy*, decided empirically.

**Decision framework (which method, when):**

| Method | Use when | Cost | Status |
|---|---|---|---|
| Exact / normalized-exact | reference stack provably deterministic for that model+hardware class | trivial | only with a strong reference stack |
| Semantic similarity (embedding cosine ≥ T) | general default for free-form output | low | **chosen — see below** |
| Judge-model verdict | high-value or structured tasks | medium (an inference itself) | ruled out as default: recursion risk, latency, cost |
| Logprob agreement | when both nodes can return token logprobs | low | ruled out as default: not universally supported by Ollama |

**Decided:** comparison is tolerant, pluggable behind the `Verifier` seam, and
selected per tier/model — *not* one global hardcoded rule. A model's
registered reference stack determines which methods are even admissible.

**Decided (comparator choice):** semantic embedding cosine similarity is the
chosen direction for the Standard-tier default comparator. Rationale:

- *Logprob agreement* ruled out: logprob support is model- and runtime-dependent
  and is not universally available in Ollama; it also requires protocol changes
  to surface per-token probabilities through the task result schema.
- *Judge model* ruled out as default: adds a full inference round-trip per
  verification check (latency + cost), introduces a recursive trust question
  (who watches the judge?), and creates a single point of failure. May be
  considered for high-value tasks in a future tier.
- *Semantic embedding cosine*: small embedding models (nomic-embed-text,
  all-MiniLM-L6) run locally, have ~50ms latency against Ollama, require no new
  Python dependencies (just an HTTP call the orchestrator already makes), and
  handle paraphrase equivalence — the main failure mode of the SequenceMatcher
  placeholder (two honest nodes saying the same thing in different words).

**Deferred (still empirical):** the threshold `T` and the specific embedding
model. These must be calibrated on testnet data across a representative sample
of prompt types. Starting point: `T = 0.85`, `nomic-embed-text`.

**Today:** `EmbeddingComparator` is implemented and wired to
`--embedding-url`. When `--embedding-url` is not set, `default_comparator`
(whitespace/case-normalized sequence ratio) is still used as the fallback so
CI and no-Ollama deployments are unchanged. Operators opt into semantic
comparison by pointing at their Ollama instance:

```bash
python protocol/orchestrator.py \
  --verify-sample-rate 1.0 \
  --embedding-url http://localhost:11434
# requires: ollama pull nomic-embed-text
```

Replacing it in the future requires no orchestrator change — that is the point
of the `Verifier` seam.

---

## 5. Escalation & slashing

### 5.1 Malformed result (unambiguous)

Empty / non-well-formed output has no attribution ambiguity. Current behaviour
(preserved from before the seam): reject to the requester, and on-chain slash
the producing node when running in chain mode. This stays.

### 5.2 Verified disagreement (the dangerous case)

A primary/checker disagreement does **not** by itself identify the liar — with
two samples either node could be the dishonest one, or the comparison could be
a false positive from inference non-determinism. **Slashing an honest provider
is existential** (providers are the scarce side — VERIFICATION.md,
ECONOMICS.md §5). Therefore:

**Decided:**
1. A two-sample disagreement **never** auto-slashes. It transitions to
   `DISPUTED`, the requester gets an error (not a possibly-wrong answer), and
   no reward is finalized for that task.
2. Slashing requires **committee adjudication**: re-dispatch to N independent
   nodes; the majority output (under the same tolerance) defines ground truth;
   the dissenting minority is judged dishonest.
3. The penalty is taken from the dishonest node's **unvested earned bond**
   (ECONOMICS.md §4) — never from capital it never had to post (no-barrier-to-
   entry is preserved) — its accrued-unfinalized reward is reversed, and
   slashed tokens are **burned** (ECONOMICS.md §2 sinks).
4. False-positive defenses: never slash on a single checker; conservative
   agreement threshold; an **appeal window** before a slash is irreversible;
   elevated `p` on a node's *subsequent* tasks rather than an immediate
   high-severity penalty on a first lone disagreement.

**Deferred (empirical / open):** committee size N and quorum, appeal-window
mechanics, the slash fraction of bond, and collusion-resistant committee
selection (§6). Magnitudes are testnet-tuned (ECONOMICS.md §5).

**Today:** steps 2–4 are **not built**. The implementation stops at step 1
(`DISPUTED`, reject, `escalation_required`, no slash). This is the correct
*safe* partial state — it withholds payment from a possibly-cheating node
without risking an honest-node slash — but it is *incomplete*, not done.

## 6. Threat model

| Attack | Mechanism | Mitigation | Status |
|---|---|---|---|
| Garbage / model-swap | return junk or a cheaper smaller model's output | tolerant comparison vs reference stack catches it | comparator placeholder; reference stack unbuilt |
| Lazy/copying checker | checker returns junk or echoes primary instead of re-executing | independent re-execution; sometimes route to a trusted reference node; committee | committee/reference-node selection unbuilt |
| Collusion / sybil | attacker runs both primary and checker | random checker selection + identity must cost (the vesting bond, ECONOMICS.md §4) + trusted reference nodes | **open** — hard when attacker controls a large share of a small network; tied to the economics/sybil workstream |
| Checker-pool DoS | starve checkers to force the `FINALIZED*` (no-checker) branch | trusted reference fallback; cap unverified throughput | open; bootstrap accepts this risk knowingly |
| Honest-node griefing | adversary tries to trigger false-positive slashes of honest providers | §5.2 defenses (committee, appeal, bond-only, conservative threshold) | escalation unbuilt → currently no slash, so not yet exploitable |

The collusion row is the deepest open problem and is **explicitly shared with
the economics workstream** — verification security and sybil cost are one
problem, as ECONOMICS.md §4–§5 state.

---

## 7. Parameter register

| Parameter | Meaning | Status | Set where |
|---|---|---|---|
| `p` | per-task recheck probability | bootstrap default `0.0`; target `>0` & conditioned | `--verify-sample-rate` / env |
| `agreement_threshold` | accept iff similarity ≥ this | bootstrap default `0.85`; final value empirical | `--verify-threshold` / env |
| comparison method | how two outputs are compared | **decided**: semantic embedding cosine; threshold empirical | `--embedding-url` / `DEAI_EMBEDDING_URL`; fallback: sequence ratio |
| reference stack / model | pinned runtime+quant+decode+seed | **deferred** (no registry yet) | future model registry |
| committee size `N`, quorum | adjudication panel | **deferred** | unbuilt |
| appeal window | delay before slash is final | **deferred** | unbuilt |
| `slash_fraction` | portion of unvested bond burned | **deferred** (ECONOMICS.md §5) | unbuilt |
| checker selection policy | how the checker/committee is chosen | **deferred** (collusion-sensitive) | unbuilt |
| canary rate | fraction of tasks that are interleaved known-answer traps (§9) | **research/planned** | unbuilt |
| qualification set | golden challenges gating tier admission (§9) | **research/planned** | unbuilt |
| judge / verification pool | staked large-model adjudicators (§11) | **research/proposed** | unbuilt |

"Bootstrap default" = a safe placeholder that changes no existing behaviour,
not the intended production value.

**Threshold boundary (observed, issue #10).** `T = 0.85` was a reasonable
starting point but a short factual answer was seen to score `0.831` between two
honest nodes — a false-positive boundary case. The threshold may need to be
*length-aware* (a lower floor for short responses), and mismatch lines should
log a prompt hash so boundary cases can be investigated. This is exactly the
empirical tuning §4 defers to testnet, now with a concrete data point.

---

## 8. Conformance ledger (code ⇄ spec — no drift)

What `protocol/{verification,orchestrator,ledger,chain_ledger,merkle}.py` +
`chain/contracts/MerkleDistributor.sol` implement **today**:

- ✅ `Verifier` seam; `ContentVerifier` default (legacy non-empty, no recheck);
  `RedundantExecutionVerifier` (well-formed gate, silent sampled re-dispatch to
  a *different* node, tolerant compare).
- ✅ Disagreement → reject + `escalation_required`, **no auto-slash** (§5.2
  step 1).
- ✅ No-checker-free → optimistic accept, logged unverified (§2 `FINALIZED*`).
- ✅ `p` / threshold as static knobs, default-off (§3, §7).
- ❌ Committee adjudication, appeal window, verified-dishonesty slash (§5.2
  steps 2–4).
- ❌ Per-model reference inference stack / model registry (§1).
- ✅ Off-chain accrual + claimable batch settlement (build-now #4):
  `MerkleDistributor.sol` + `protocol/merkle.py`; orchestrator accrues and
  publishes a cumulative root per epoch; `/claim/{wallet}` serves proofs;
  no per-task mint; orchestrator no longer holds token MINTER_ROLE. ❌ still
  open: the **vesting/bond** wrapper and slash-reduces-accrual (ECONOMICS.md
  §4) — accrual is built to accept them but credits without a vesting delay
  today. Verification status of the Solidity: it is **compiled** by CI
  (`npx hardhat compile`, real solc) and compiles cleanly; its behavioural
  test (`chain/test/MerkleDistributor.test.js`) runs via
  `npm run test:merkle`, **not yet in the CI gate** — wiring two Hardhat
  test files into one `npm test` run hit a multi-file mocha/network
  lifecycle issue that is a tracked follow-up. The Python side
  (`merkle.py`) is unit-tested in CI and its roots were cross-checked
  against the JS tree.
- ✅ Comparison method decided: `EmbeddingComparator` (semantic embedding cosine
  via OpenAI-compatible `/v1/embeddings` endpoint). Enabled with
  `--embedding-url`; falls back to SequenceMatcher when not configured.
  Threshold `T` is still empirical/deferred.
- ❌ Conditioned/adaptive `p`.
- ✅ Self-reported hardware (GPU/VRAM) removed from pay and routing score
  (build-now #3, the verifiable half). The *measured* benchmark/tier
  replacement (§1, §7) remains ❌ deferred.
- ✅ **Checkers earn nothing today** — this is a known gap, not an oversight.
  The economics of checker compensation (a fraction of primary reward, or a
  separate verification fee) are deferred to the economics workstream
  (ECONOMICS.md §4–§5). The routing fix ensures primary/checker slots
  alternate fairly across nodes so no single node is permanently relegated
  to unpaid checking.

**Smoke-tested (mock + real Ollama, local):** single-node round-trip,
real Ollama inference (qwen3:8b), redundant verification with two mock
nodes (agreement 1.000), redundant verification with two real Ollama nodes
(3/3 factual questions passed at threshold 0.85), three-node load
distribution (9 tasks split 3/3/3). Six routing and dispatch bugs were
found and fixed during this testing — see git log. **Not yet tested:**
two real Ollama nodes on long-form or ambiguous prompts (agreement ratio
for complex outputs is unknown); node reconnect after mid-session drop;
Sepolia chain mode end-to-end.

Any change to those files must update this section in the same commit.

---

## 9. Reducing redundancy — the network shares work, it does not multiply it

> Principle. Redundant re-execution is a *sampled economic tax*, not the
> operating mode. The product is *sharing* compute — different tasks to
> different nodes, and (VISION Stage 2) one inference split across nodes. The
> only work ever repeated is the sampled check, whose steady-state overhead is
> ≈ `p` (a few percent), not 2×. `--verify-sample-rate 1.0` is a test setting,
> never production. The layers below drive the need for *live* redundancy
> toward the exception.

**Operational vs. adversarial faults — two different "bad node" problems.**
- *Operational* (down, slow, OOM, erroring, empty/malformed, wrong language,
  truncated, degenerate repetition): caught instantly and nearly free by
  liveness/telemetry + the `well_formed` gate. This is the only failure a
  trusted datacenter ever has.
- *Adversarial-but-healthy* (a node that quietly runs a cheaper model and
  returns fluent, plausible output to pocket the difference): invisible to
  monitoring. This is the only thing verification is actually for.

**Pre-flight qualification (planned, cheap).** Before a node gets paid work for
model M, send it *golden challenges* — prompts whose reference output (or
reference embedding under the pinned reference stack, §1) is precomputed once,
offline. Pass → admitted to the M tier, and the measured latency/throughput
*sets its capability tier* — the measured-tier replacement for the deleted
self-reported GPU flag (build-now #3). Cost: one node-side inference per
challenge, no second live node. Proves the node genuinely runs M *now*; does
not prove it stays honest later — hence canaries.

**Canary / known-answer tasks (research → planned, cheap).** Interleave golden
tasks into the real workload, made *indistinguishable* from genuine requests.
Each canary's answer is precomputed, so the check is a cheap comparison with
**no second live node** — yet deterrence equals redundancy sampling, because
the node can't tell which task is a trap.
- *Open challenge:* indistinguishability/freshness. A node that fingerprints
  canaries answers them honestly and cheats the rest. Needs a large, refreshed,
  realistic golden set, ideally drawn from real traffic.
- *Coverage gap:* you can't pre-know the answer to a novel user prompt, so
  canaries *complement* — they don't replace — redundancy/TEE for genuinely
  new work.

**The layered picture (the reduction goal).** qualification (screen in, set
tier) → canaries + reputation (cheap ongoing checks; lower `p` for proven
nodes) → redundancy (fallback for novel prompts on untrusted nodes) → TEE
attestation (removes live verification where the hardware exists) → zkML
(eventual everywhere-answer). Redundancy becomes the exception and shrinks over
time. Most of this is buildable in mock mode with the existing
`EmbeddingComparator`; all of it depends on the reference inference stack (§1).

---

## 10. What verification certifies — honest execution, not answer quality

Two questions sound alike and must be kept apart:
1. **Did the node faithfully run the model it was paid for?** (Integrity.)
   Answerable — via redundancy, canaries, or TEE. *This* is the protocol's job
   and what the economics need.
2. **Is the answer genuinely good/helpful?** (Absolute quality.) AI-hard,
   subjective, task-dependent — and *not* the protocol's job. Quality is a
   property of the model the *user* chose; the node's only duty is to run it
   faithfully. Making the protocol an answer-quality judge is the wrong target,
   the same mistake as trying to "guarantee a node's specs."

**Token count is a billing unit, not a quality signal.** Reward is paid per
output token and the count is node-self-reported. Treating "more tokens =
better" would reward verbosity-farming and let nodes inflate their own pay.
Quality is non-monotonic in length anyway (truncation → too few; repetition →
too many). Use token count for *how much work*, never for *how good*.

**The cheap heuristic floor.** Format/schema validity, language detection,
repetition/degeneration and truncation detection catch *low* quality almost
free but cannot *certify high* quality (a floor, not a ceiling). Worth wiring
in as an early reject for broken output — and it directly addresses the
qwen-thinking truncation class (issue #8).

**Specs are the wrong target; verify work.** A software sandbox runs on the
operator's machine — they own the kernel and hypervisor, so it cannot attest
hardware specs to the network (you can't trust a measurement taken on hardware
the adversary controls). Only *hardware* attestation (TEE) can. And you mostly
don't need specs at all: pay for *verified delivered work* and whether a node
"really" had 80 GB is irrelevant (build-now #3). Sandboxing's legitimate role
is isolating the workload and prompt privacy (which TEE also gives) — not
proving capacity.

---

## 11. The verification pool (judge tier) — research / proposed

An opt-in tier of capable, **staked** nodes running *larger* models that act as
judges/adjudicators, rewarded for verification. It is simultaneously a concrete
implementation of the §5.2 committee, an economic role for high-end hardware,
and a premium "judge-verified" assurance lane users can choose and pay for.

**Why it could help the network:**
- Gives expensive GPUs a purpose beyond plain inference → more high-end
  capacity joins → network health and depth.
- A larger model judging a smaller model's output is a credible
  correctness/quality signal (the standard LLM-as-judge asymmetry).
- Operationalizes committee escalation (§5.2): disputes route to the pool's
  staked judges; majority rules.
- Creates a tiered trust market: cheap optimistic tier for routine work; paid
  judge/attested tiers for high-stakes work.

**Honest effects and tradeoffs (must be designed for):**
- *Cost & who pays.* A judge verdict is a whole extra (larger) inference.
  Funded by a premium verification fee the user opts into, or a protocol sink —
  not free.
- *Recursion — who verifies the verifiers?* Judges are nodes too and can be
  lazy or collude. Mitigate with canaries among the pool, staking, reputation,
  random assignment.
- *Centralization pressure.* A pool of expensive nodes is fewer, richer
  operators — tension with the consumer-hardware ethos. Keep membership
  permissionless but stake/qualification-gated; rotate; require many judges.
- *Judge fallibility / bias / prompt-injection.* An LLM judge is imperfect and
  gameable, so a verdict must feed *committee majority*, never unilateral
  slashing — the false-positive-on-an-honest-node risk (§5.2) is existential.
- *Collusion (judge + worker).* Random, anonymous assignment + stake at risk.

**Net ecosystem effect:** a healthy addition *if* cost and centralization are
managed — it monetizes large hardware, strengthens dispute resolution, and lets
users buy assurance proportional to what's at stake. Slots into the tier model
(VERIFICATION.md), §4 (judge-model comparison), §5 (the committee), and
ECONOMICS.md (reward source + premium tier). Not decided — flagged for design.

**How we'll decide if it works — staged validation (cheapest-fatal-first).**
Run the stages in order; a failed gate reworks or drops the idea before money is
spent. The detailed mechanics (committee size/quorum, judge-selection algorithm,
fee/reward split, anti-collusion specifics, orchestrator wiring) are
deliberately left unspecified until Stage A–B produce real numbers — speccing
them earlier would be guesswork.

- **Stage A — Offline judge-accuracy study (no budget; the kill switch).** Build
  a labeled set of prompts × {honest output from the real model; "cheat"
  outputs from cheaper / wrong / subtly-degraded models}. Run candidate judge
  models as classifiers and measure the cheat-catch rate (true positive) and —
  decisively — the honest-node flag rate (false positive), across prompt types
  and lengths (ties to the §7 short-prompt boundary). *Gate:* if no
  configuration keeps honest false-positives near zero while catching cheats,
  the pool fundamentally does not work — stop here. This is largely the same
  accuracy/threshold study already owed for the comparison method.
- **Stage B — Economic simulation (no budget).** Model judge inference cost vs.
  the premium fee a user would tolerate vs. cheat gain vs. sampling rate.
  *Gate:* the fee must cover judge cost *and* the expected penalty must deter
  cheating. If the economics never close, it is a non-starter or needs an
  explicit subsidy.
- **Stage C — Mock-mode mechanism prototype (no budget).** Build dispute →
  route to pool → collect multiple verdicts → majority → outcome, with fake
  judge nodes (as in the redundancy smoke test). Proves buildability and
  exercises the random-assignment anti-collusion routing.
- **Stage D — Testnet adversarial pilot (valueless tokens).** Real mixed-size
  Ollama nodes, a real pool, nodes deliberately cheating; measure real
  false/true-positive rates, latency, cost, and pool concentration over time.

*Commit only if* A shows low honest false-positives, B's economics close, C
proves buildability, and D holds under adversarial load. Fail any stage → fix
or drop, cheaply, because the fatal questions are front-loaded.

---

## 12. Decided vs. deferred

- **Decided:** optimistic redundant execution is the Standard tier for
  Stage 0–1; silent sampling; recheck on a different node; tolerant pluggable
  comparison; two-sample disagreement never auto-slashes; slashing requires
  committee majority and is taken from the unvested earned bond and burned;
  reference inference stack is a hard prerequisite for a model to enter the
  Standard tier; verification work-measurement is the same substrate the
  redemption rate consumes (one keystone).
- **Deferred (empirical, testnet — more than one attempt expected):** `p` and
  its conditioning; comparison method and threshold; committee size/quorum;
  appeal mechanics; slash magnitude; collusion-resistant checker selection.
- **Deferred to later stages:** Attested/Proven tiers; Stage 2 sharded
  attribution; replacing the single trusted orchestrator.
- **Decided (principles, §9–§10):** verification certifies *honest execution
  of the chosen model*, not absolute answer quality; token count is a billing
  unit, not a quality signal; specs are the wrong target — verify delivered
  work, and only TEE attests hardware; redundancy is a sampled tax, not the
  operating mode — the network shares work, it never multiplies it.
- **Research / planned (§9, §11):** pre-flight qualification (golden
  challenges → measured tier); canary / known-answer tasks; the cheap
  heuristic floor (truncation/repetition/format); the verification pool
  (judge tier) as the committee implementation and a premium assurance lane.
