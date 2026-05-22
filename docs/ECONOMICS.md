# DeAI — Economics (Mapped Direction)

> Status: direction doc. The token model is **decided** (see First Principle
> and §1). Recommended mechanics with honest tradeoffs; empirical parameters
> explicitly deferred to non-transferable testnet. Nothing here is implemented
> yet.

---

## First Principle — The Redemption Invariant

**DEAI is always redeemable for real inference, at a rate that is
transparently and verifiably determined — never set at anyone's discretion.**

This is the top of the document, above every other choice, because it is what
separates a real economic system from a Ponzi. The distinction is not how many
tokens exist or how they are marketed — it is whether the token can be
extinguished for something with inherent worth at a rate nobody can move at
will. The rate must *evolve* (hardware and models get cheaper); the iron
property is that it evolves by an open, verifiable rule, never by discretion.

A speculative coin is worth only what the next buyer will pay. A real one has a
floor: cheap tokens get redeemed for real work, which pulls value back up. That
redemption pressure is the anti-Ponzi mechanism, built into the protocol rather
than hoped for.

Hold this invariant and almost every other parameter can flex and be tested.
Break it — make the token non-redeemable, or let the network be unable to honor
redemption — and DeAI is indistinguishable from the coins that died for the
wrong reasons, regardless of intent.

---

## 0. The failure mode this design exists to prevent

**The mercenary-mining / unanchored-token death spiral.** A volatile token is
made the mandatory unit and demand is merely hoped for. Holders and miners sell
into no real buyers; price falls; miners leave; the network shrinks; demand
falls further. Most dead coins died exactly here. "Crypto forked a million
times and here we are" is survivorship bias — the graveyard of tokens that did
this is enormous and invisible.

The redemption invariant is the structural defense against this. §0 is the
disease; the First Principle is the vaccine.

---

## 1. The model (decided): redemption-anchored work token, stable-edged

DEAI **is** the network's economic medium — the founding thesis is preserved,
not sidelined. It earns the "real, not Ponzi" position through the invariant,
not through marketing. Two consequences follow:

1. **Inference is priced in compute units, not dollars-of-token.** The token
   *is* the compute unit. A given amount of DEAI always redeems for a
   corresponding unit of inference work at the transparently-determined rate
   (see the rate-mechanism subsection below). The token may trade *above* this
   floor (scarcity, growth, speculation); it structurally cannot collapse
   while the network can do work and honor redemption.
2. **Stablecoin / fiat on-ramps are a necessity, not an option.** Volatility is
   not eliminated — it is pushed to the on/off-ramp, the way a card tap hides
   interbank settlement. Users and miners interact through a stable edge; the
   internal economy is one thing (compute units carried by the token) with
   pluggable on-ramps (fiat, stablecoin, native token). This is the
   *responsible* version of "do both and see" — one anchored economy with
   multiple entry points whose real-world usage is observed empirically — not
   two competing rails or an unanchored token hoping for value.

### The honest miner-side caveat

The invariant cleanly anchors the *user* side. It does **not** fully solve the
*miner* side: miners pay electricity in fiat, so cost recovery still depends on
a liquid path from earned tokens to real money. This value-leak is inherent to
*every* token model — anyone claiming otherwise is selling something. Partial
mitigations, stated without overselling:

- **Renewable/own-generation power** lowers miners' real fiat cost and is the
  most durable structural answer.
- **Framing:** miners are taking *cashback on compute the world is already
  spending.* People already run AI constantly in daily life; DeAI lets that
  existing behavior pay some of it back. If adopted, some participants monetize
  what others simply pay for. That is the adoption story, and it is honest —
  it is a rebate on real activity, not a promise of free money.

(Hardware-entropy/degradation cost is deliberately out of scope — not a
material factor worth documenting.)

### The rate mechanism & the immutable self-check (the deepest problem)

The invariant is bedrock; the **rate** is not a number anyone sets — it is the
output of a transparent rule. The enemy is *discretion*, not *change*: the rate
must evolve as hardware and models get cheaper, but no party — the core team
included — may move it at will. A team that merely *promises* not to is not
*credibly* honest, because users can verify rules, not intentions.

**How the rate is determined (recommended direction).** The network measures
its own delivered compute — standardized benchmark / sampled work run across
many nodes, the *same useful-work measurement the verification layer produces*
— and the rate is a deterministic, open function of that on-network
measurement and observed supply/demand, market-discovered within guardrails
(bounded change per epoch, so it tracks reality without being whipsawed or
yanked). No external oracle (that only relocates the trust problem to the
oracle); no team pronouncement; no naive vote (the rate is an *adversarial*
parameter — miners and users want it in opposite directions — so it cannot be
a simple governance knob).

Rate honesty is therefore *downstream of verification honesty*: the rate can be
no more trustworthy than the work-measurement beneath it. One problem, not two
— solve trustworthy measurement once (the keystone), and both honest pay and
honest pricing follow from it.

**What "immutable self-check" must mean.** Not "can never change" — the rule
must be able to evolve, so naive immutability is the wrong target. It means the
rule and its measurement *cannot be changed silently, instantly, or at
discretion*, and its output is independently reproducible. Concretely, all
four:

1. The rule and measurement are open, on-chain logic — the same code everyone
   runs, not a number in a team database.
2. Every input is published and timestamped on a tamper-evident log as it
   occurs, signed by the measuring nodes — the input set cannot be edited
   after the fact.
3. Anyone can recompute the rate from the public inputs and the open rule and
   get the *identical* result. Any divergence between the published rate and
   the reproducible one is instantly detectable by anyone.
4. The rule itself can change only via a pre-announced, on-chain, timelocked
   path (the same sunset/governance mechanism as the admin key, §6) — never
   sprung, never silent, never instant. A coming change is visible far enough
   ahead that anyone who disagrees can exit before it takes effect.

If all four hold, "manipulating the ledger when we see fit" is not merely
promised against — it is *impossible and publicly detectable*. That is the
mission, applied to monetary policy.

**Honest open problems (this will take more than one attempt).**

- Trustworthy self-measurement, when the measurers are the same potentially
  adversarial nodes, is gated on the verification keystone — unsolved until
  that matures.
- Guardrail and epoch parameters (max move per epoch, measurement cadence) are
  empirical — testnet-tuned, not derivable on paper.
- The timelocked change path is still a *governance* surface for an
  adversarial parameter; making it capture-resistant is an open design
  problem, not a solved one.

These are written into the plan as scoped problems with a direction — not as
solved claims.

---

## 2. Supply policy & emission

Interacts with the anchor: redemption sets the *floor*; emission and sinks
manage the *premium above the floor*. Over-emission can depress the premium but
cannot break the floor while redemption holds and capacity exists.

- **Finite, transparent bootstrap pool** subsidising early miners — capped and
  public, not infinite mint.
- **Emission decays as real (paid) demand grows** — usage/milestone-based, not
  purely time-based.
- **Mined rewards vest** linearly (see §4 — vesting doubles as the sybil bond).
- **Sinks:** protocol fee from real revenue → buyback-and-burn (or staker
  dividend); slashed tokens burned. Sink pressure scales with real usage,
  tying the premium to genuine demand.
- **No pre-mine to team/founders** (already true — preserve; it is a trust and
  a regulatory asset).
- **Reward is per output token — guard against verbosity-farming.** Token count
  is a *work/billing* unit, never a quality signal, and it is node-self-reported.
  Paying per token means padding output is a direct incentive; the reward design
  must cap or discount degenerate length so nodes can't inflate pay with filler.
  Quality is a property of the chosen model, not the protocol's to grade
  (VERIFICATION_PROTOCOL.md §10).

---

## 3. Reward attribution under pooling / sharding

Gated on the VISION.md staircase and per-shard verification:

- **Stage 0 (one node / one task):** that node earns it minus a verification
  reserve. Spec fully now.
- **Stage 1 (job parallel):** pay per *verified* sub-task. Spec now.
- **Stage 2 (model-sharded):** splitting one inference's value across shards
  depends on per-shard verification choices not yet made (VERIFICATION.md).
  **Explicitly deferred** — do not over-design now.

---

## 4. Sybil cost & the bootstrap squared-circle

Tension: "no barrier to entry" (mission) vs. "cheating must cost something"
(security). Resolution:

**New miners stake nothing upfront. Early earnings vest; the unvested portion
is a slashable bond ("earned-reputation escrow").**

- Zero starting capital → mission preserved.
- A sybil returning garbage forfeits accrued unvested earnings, nets nothing.
- Vesting also blocks farm-and-dump → reinforces §0 defense.

One mechanism fixes sybil resistance, dump pressure, and no-barrier-to-entry.

---

## 5. Stake / slashing magnitude

Condition: `expected_penalty > expected_gain_from_cheating`. Levers (jointly
optimised): check-probability `p`, slash size, comparison tolerance
(VERIFICATION.md). A false positive from inference non-determinism slashes an
*honest* node — existential, since providers are the scarce side. Spec the
framework now; numbers are empirical, tuned on testnet.

**Paying the verifiers (open).** Checkers earn nothing today — a known gap
(VERIFICATION_PROTOCOL.md §8). The funding source for verification work, and for
a proposed **verification pool** of staked larger-model judges (a premium
"judge-verified" assurance lane, VERIFICATION_PROTOCOL.md §11), is a deferred
economics decision: a fraction of the primary reward, or a separate
user-elected verification fee. It must not create perverse incentives (judges
paid to find fault, or to rubber-stamp). Empirical, testnet-tuned.

---

## 6. Admin-key sunset & governance

- **Testnet:** admin key held (disclosed in SECURITY.md).
- **Per-task hot mint key removed** (build-now #4): the orchestrator no
  longer holds token `MINTER_ROLE`. Rewards accrue off-chain and settle via
  `MerkleDistributor`, which mints only what a published cumulative root
  authorizes. This shrinks the always-hot attack surface ahead of the sunset.
- **Before any valued/transferable token:** mint authority → multisig +
  timelock. No valued token launches with a unilateral mint key.
- **Later:** on-chain governance. Token-weighted trends to plutocracy;
  reputation-weighted (by verified work) is more mission-aligned but complex.
  Commit only to the sunset milestone now.

The redemption rate (§1) is not a discretionary lever at all — only the *rule*
that computes it can change, and only via this same pre-announced, timelocked
path. No silent or instant change exists by construction (the immutable
self-check, §1).

---

## 7. Non-transferable until graduation

DEAI is non-transferable (no DEX, no bridge) through all of testnet. The full
loop — redemption-rate setting, emission, vesting, bonding, slashing,
attribution — runs with valueless tokens and zero attack incentive while
parameters are tuned.

**Graduation is a checklist, never a date:**
1. Verification false-positive rate measured and low.
2. Sybil resistance demonstrated under adversarial testing.
3. Redemption-rate rule independently reproducible from public inputs,
   observed stable across simulated cost shifts, with no discretionary or
   instant override path in steady state.
4. Supply/premium dynamics observed stable.
5. Contracts audited.
6. Legal review complete (§8).

---

## 8. Regulatory surface

A transferable token with market value, earned by the public, with team-held
keys, sits in securities/regulatory territory in many jurisdictions.
**Engineering guidance only — not legal advice:**

- Non-transferable test token avoids most of this during development.
- Real legal counsel in relevant jurisdictions is a **hard gate** before
  graduation, not a formality.
- Surface-reducing choices already aligned: no team pre-mine, utility-first
  (the redemption invariant *is* the utility), decentralised issuance, key
  sunset. Keep them.

---

## Chosen shape (one paragraph)

DEAI is the network's economic medium, made real (not Ponzi) by a
protocol-enforced invariant: it is always redeemable for inference at a rate
that is transparently and verifiably determined, never at anyone's discretion.
Inference is priced in compute units the token represents; volatility is
absorbed at stablecoin/fiat on-ramps, so normal users and miners touch a stable
edge over one anchored internal economy. Value floor = redeemable work; premium
above it is managed by finite decaying emission and burn sinks tied to real
revenue. No upfront stake — unvested earnings are a slashable bond, solving
sybil resistance, dump pressure, and no-barrier-to-entry together. The
redemption *rate* is set by no one — it is the reproducible output of an open
rule over the network's own verified work-measurement, market-discovered within
guardrails and changeable only via a pre-announced timelocked path (the
immutable self-check). Mint and rate-rule authority sunset to multisig+timelock
before any value; non-transferable through testnet; graduation is an explicit
checklist gated on measured verification quality, rate-rule reproducibility,
and legal review.

## Decided vs. deferred

- **Decided:** redemption-anchored work-token model (the invariant is
  first-principle, softened to "transparently and verifiably determined, never
  at discretion"); rate is the reproducible output of an open rule over the
  network's own verified work-measurement, market-discovered within guardrails
  (the immutable self-check: open on-chain logic, tamper-evident inputs,
  publicly recomputable, rule changes only via pre-announced timelocked path);
  stablecoin/fiat on-ramps as a necessity; vesting-bond sybil model; finite
  decaying bootstrap emission; burn sinks; key + rate-rule authority sunset;
  non-transferable-until-graduation; checklist graduation;
  cashback-on-existing-usage as the honest adoption framing.
- **Deferred / open hard problems (more than one attempt expected):**
  trustworthy self-measurement (gated on the verification keystone);
  guardrail and epoch parameters; capture-resistance of the timelocked
  rule-change path; slash magnitude; check-probability `p`; comparison
  tolerance; emission/decay/vesting curves.
- **Deferred to later stages:** Stage 2 sharded reward attribution; governance
  mechanism design; legal counsel engagement.
