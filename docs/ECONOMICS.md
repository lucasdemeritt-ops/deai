# DeAI — Economics (Mapped Direction)

> Status: direction doc. Maps the token economics before implementation.
> Answers the eight open questions seeded in VISION.md. Recommended model with
> tradeoffs stated honestly; empirical parameters explicitly deferred to
> non-transferable testnet. Nothing here is implemented yet.

---

## 0. The failure mode this design exists to prevent

**The mercenary-mining death spiral.** Tokens are minted to attract miners
before paying users exist. Miners farm and immediately sell (their costs are in
real money). With no external buyers, price falls; miners earn less in real
terms and leave; the network shrinks; demand falls further. Spiral down.

Root cause, always: the token's value came from *more emission*, not from
anyone outside the system paying real money for useful work. **Design rule: the
token's value must trace to external revenue. If you cannot draw a line from
"an external person paid money for inference" to "the token is worth
something," the structure is a Ponzi regardless of intent.**

---

## 1. Source of value — the load-bearing decision

Two philosophies:

- **Token-as-money.** Users must buy DEAI to pay for inference. Crypto-native,
  but forces every developer to acquire/manage a volatile token before their
  first API call and puts FX risk on every customer's bill. Kills the
  "two-line migration from OpenAI" pitch. Most serious infra does not do this.
- **Dual-asset (recommended).** Users pay in a **stablecoin / fiat on-ramp**;
  compute pricing is stable and the migration UX survives. **DEAI is the
  incentive + security + governance token**: staked/bonded to mine, slashed for
  cheating, governs the protocol, and **captures a fee from real stablecoin
  revenue** (buyback-and-burn, or paid to honest stakers).

Recommendation: **dual-asset.** Only model with a non-circular value source and
a product usable by normal developers.

> **DECISION REQUIRED FROM OWNER.** Token-as-money vs. dual-asset is partly a
> values call. The rest of this doc assumes dual-asset; confirm or push back
> before it is locked.

---

## 2. Supply policy & emission

- Not a fixed time-based cap (emission unrelated to usefulness) nor unbounded
  per-task mint (inflation → decay).
- **Finite, transparent bootstrap pool** subsidising early miners — explicitly
  capped and public, not infinite mint.
- **Emission decays as real (paid) demand grows** — milestone/usage-based, not
  purely time-based.
- **Mined rewards vest** linearly over time (see §4 — vesting doubles as the
  sybil bond).
- **Sinks:** protocol fee from stablecoin revenue → buyback-and-burn (or
  staker dividend); slashed tokens burned. As usage grows, sink pressure
  offsets emission and ties token value to real demand.

No pre-mine to team/founders (already true — preserve this; it is both a trust
and a regulatory asset).

---

## 3. Reward attribution under pooling / sharding

Gated on the VISION.md staircase and on per-shard verification:

- **Stage 0 (one node / one task):** that node earns it, minus a verification
  reserve. Trivial. Spec this fully now.
- **Stage 1 (job parallel):** each sub-task is a unit; pay per *verified*
  sub-task. Clean. Spec now.
- **Stage 2 (model-sharded):** splitting one inference's value across shards is
  genuinely hard and depends on per-shard verification choices not yet made
  (VERIFICATION.md). Candidate bases: shard-token-seconds of contributed
  compute, equal split, or layer-weighted — all require verified contribution.
  **Explicitly deferred.** Do not over-design Stage 2 economics now.

---

## 4. Sybil cost & the bootstrap squared-circle

Tension on record: "no barrier to entry" (mission) vs. "stake at risk or
cheating is free" (security). Resolution:

**New miners stake nothing upfront. Early earnings vest over time; the unvested
portion is a slashable bond ("earned-reputation escrow").**

- Zero starting capital → mission preserved.
- A sybil returning garbage forfeits accrued unvested earnings, nets nothing →
  cheating is costly without an entry fee.
- Vesting also blocks farm-and-dump → directly fights the §0 spiral.

One mechanism (vesting-with-bond) fixes sybil resistance, dump pressure, and
the no-barrier requirement together. This is the centerpiece.

---

## 5. Stake / slashing magnitude

Security condition: `expected_penalty > expected_gain_from_cheating`, where
gain ≈ compute cost saved by faking, penalty ≈ slash × check-probability `p`.

Levers (jointly optimised, not set in isolation):
- higher `p` → more redundant-compute cost
- higher slash → deters cheating but a false positive (from inference
  non-determinism) slashes an *honest* node — existential, providers are the
  scarce side
- comparison tolerance method (see VERIFICATION.md)

Conclusion: spec the *framework and inequality* now; final numbers are
empirical. Tune on non-transferable testnet.

---

## 6. Admin-key sunset & governance

- **Testnet:** admin key held (acceptable, disclosed in SECURITY.md).
- **Before any valued/transferable token:** mint authority → multisig +
  timelock. No valued token launches with a unilateral mint key.
- **Later:** on-chain governance. Note token-weighted governance trends to
  plutocracy; reputation-weighted (by verified work) is more mission-aligned
  but more complex. Do not over-build governance now — commit only to the
  sunset milestone.

---

## 7. Non-transferable until graduation

DEAI is non-transferable (no DEX, no bridge) through all of testnet. The full
loop — emission, vesting, bonding, slashing, attribution — runs with valueless
tokens and zero attack incentive while parameters are tuned.

**Graduation is a checklist, never a date:**
1. Verification false-positive rate measured and low.
2. Sybil resistance demonstrated under adversarial testing.
3. Supply/price dynamics observed stable in simulation + testnet.
4. Contracts audited.
5. Legal review complete (see §8).

---

## 8. Regulatory surface

A transferable token with market value, earned by the public, with team-held
keys, sits in securities/regulatory territory in many jurisdictions.
**Engineering guidance only — not legal advice:**

- Non-transferable test token avoids most of this during development.
- Real legal counsel in relevant jurisdictions is a **hard gate** before
  graduation, not a formality.
- Surface-reducing choices already aligned: no team pre-mine, utility-first,
  decentralised issuance, key sunset. Keep them.

---

## Recommended shape (one-paragraph summary)

Two assets: stablecoin/fiat for inference payment (stable pricing, preserves
the OpenAI-migration UX); DEAI as incentive/security/governance token whose
value traces to a protocol fee on real revenue via buyback-burn. Finite
transparent bootstrap emission that decays with paid demand. No upfront stake;
unvested earnings act as a slashable bond, simultaneously solving sybil
resistance, dump pressure, and no-barrier-to-entry. Slashed and fee tokens
burned as demand sinks. Mint authority sunset to multisig+timelock before any
value; governance later. Non-transferable through testnet; graduation is an
explicit checklist gated on measured verification quality and legal review.

## Decided vs. deferred

- **Decided (pending owner confirm on §1):** dual-asset; vesting-bond sybil
  model; finite decaying bootstrap pool; burn sinks; key sunset; non-
  transferable-until-graduation; checklist graduation.
- **Deferred to empirical testnet tuning:** slash magnitude, check-probability
  `p`, comparison tolerance, exact emission/decay/vesting curves.
- **Deferred to later stages:** Stage 2 sharded reward attribution; governance
  mechanism design; legal counsel engagement.
