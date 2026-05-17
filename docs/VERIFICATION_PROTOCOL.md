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
| Semantic similarity (embedding cosine ≥ T) | general default for free-form output | low | leading candidate, **not chosen** |
| Judge-model verdict | high-value or structured tasks | medium (an inference itself) | candidate; recursion risk noted |
| Logprob agreement | when both nodes can return token logprobs | low | candidate; needs protocol support |

**Decided:** comparison is tolerant, pluggable behind the `Verifier` seam, and
selected per tier/model — *not* one global hardcoded rule. A model's
registered reference stack determines which methods are even admissible.

**Deferred (empirical):** the actual method and threshold `T`. This is called
out as open in VERIFICATION.md ("Deferred / open") and ECONOMICS.md
("comparison tolerance").

**Today:** `default_comparator` is a whitespace/case-normalized sequence ratio.
It is an explicitly labelled **placeholder** — sufficient to (a) prove the seam
end-to-end and (b) catch garbage or a swapped smaller model, **not** the final
comparator and **must not** gate mainnet economics. Replacing it requires no
orchestrator change (that is the point of the seam).

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
| comparison method | how two outputs are compared | **deferred** (empirical) | `Verifier` seam (pluggable) |
| reference stack / model | pinned runtime+quant+decode+seed | **deferred** (no registry yet) | future model registry |
| committee size `N`, quorum | adjudication panel | **deferred** | unbuilt |
| appeal window | delay before slash is final | **deferred** | unbuilt |
| `slash_fraction` | portion of unvested bond burned | **deferred** (ECONOMICS.md §5) | unbuilt |
| checker selection policy | how the checker/committee is chosen | **deferred** (collusion-sensitive) | unbuilt |

"Bootstrap default" = a safe placeholder that changes no existing behaviour,
not the intended production value.

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
  today. Solidity contract verified by the hardhat suite in CI, not locally
  (sandbox solc download blocked).
- ❌ Conditioned/adaptive `p`; final comparison method.
- ✅ Self-reported hardware (GPU/VRAM) removed from pay and routing score
  (build-now #3, the verifiable half). The *measured* benchmark/tier
  replacement (§1, §7) remains ❌ deferred.

Any change to those files must update this section in the same commit.

---

## 9. Decided vs. deferred

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
