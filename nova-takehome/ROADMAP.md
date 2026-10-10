# ROADMAP.md — what to build, step by step

Status: Phases 0-5 BUILT; Phase 6 docs written, with the prompt log and commit still to do. See [BUILD_NOTES.md](BUILD_NOTES.md)
for what exists and the results (practice 99.8/100, exam sheet hand-checked, 19/19 evals).
Decisions taken: local parsers and Decimal maths as the engine, Claude only as a fallback reader; RapidOCR first,
vision as fallback; Windows Python 3.13 with no make; the API key as a placeholder in `.env.example`.
Companion: [PROJECT_NOTES.md](PROJECT_NOTES.md) (rules, grading, deliverables). Budget ≈ 16 focused hours.

**Architecture principle:** LLM *reads* documents into structured facts (cached) → deterministic Python *computes* → `report` is a pure function of (stored facts, as_of, mode, feedback). No hardcoded names, lanes, layouts or practice answers.

## What is GIVEN vs what I BUILD

| Given (don't rebuild) | Build |
|---|---|
| `grader/extract.py` raw text reader (eml/PDF/xlsx, page-aware) | Everything in `harness/` |
| `grader/*` scoring, schema, validator, sheet maker | Fact extraction (LLM), OCR path |
| `tools/*`, `evals/run_evals.py`, harness CLI skeleton | Fact store, calculators, detectors, authority, modes, feedback, confidence |
| Examples, practice + exam data | ≥10 eval cases, SOLUTION/DESIGN/AI_USE |

## Proposed file layout (inside `harness/`)

```
harness.py        CLI (exists) → calls the modules below
reader.py         eml → docs (wraps grader/extract.py) + scan detection + OCR
extract_llm.py    classify doc + extract structured facts via Claude; disk cache by doc hash
store.py          state-dir persistence: docs, facts (with source), feedback, report ids
money.py          Decimal helpers: half-up rounding, FX, INR→USD
rules/            contract.py (rates, bands, fuel, clauses, Schedule 1), authority.py, pickup.py
detect/           overcharge.py duplicate.py waiver.py latefee.py cashback.py expiry.py
resolve.py        conflict / cannot_determine / human_review decisions
actions.py        action per mode + unattended-action test
confidence.py     evidence/authority/extraction/agreement → probability
feedback.py       apply feedback decisions with scope + learned_at
report.py         assemble report.json (ids, supersedes, retro, stale removal)
```

---

## Phase 0 — Setup & recon (≈1h)
1. Create `.venv` (no `make`/`uv` on this machine; use `python -m venv`), install `harness/requirements.txt`.
2. Set `ANTHROPIC_API_KEY` in shell only; make GitHub repo **private**; never commit key.
3. Write Windows-friendly command cheat sheet (see PROJECT_NOTES §9); confirm `grader/run_grader.py` runs against the stub (expect score 0, `NotImplementedError`).
4. Read: all 30 `data/scenarios/answers/*.yaml`, the 8 `EXPLANATION.md`, and the exam `.eml` set. Write down every document type and layout seen.
5. Resolve open questions: how scans are quoted/verified (`validate.py`), answer-sheet format (`make_sheet.py`), MSA clause numbering variance between worlds.
6. Start the **prompt log** now (needed for AI_USE.md).

**Exit:** env works, grader runs, I can list every doc type + the 30 scenario variants.

## Phase 1 — Read & store documents (≈3h)
1. `reader.py`: parse every `.eml` → list of docs `{doc_id (batch/file[#att]), sender, to, received_date_utc, subject, pages[]}` using `grader/extract.py`. Preserve page numbers.
2. Scan handling: detect image-only PDF (`pdf_is_image_only`) → OCR (RapidOCR, rebuild lines by box position) or Claude vision. Keep result as pages so quotes can cite them.
3. `store.py`: state-dir layout; ingest is **idempotent**, keyed by message-id/doc hash; stores raw pages + received date so `as_of` filtering works later.
4. `extract_llm.py`: one Claude call per document → JSON by doc type, **cached on disk by hash** (cost + time limit). Types and fields:
   - **MSA/amendment:** contract_id, parties, effective/end dates, renewal + notice terms, pricing-date clause, weight-band rule, Annex A rates (lane × band × period), Annex C fuel by month, Annex D accessorials, Annex E charge-code aliases, Annex F FX by month, payment terms/grace/late-fee rate/compounding, rebate tiers + Qualifying Spend definition, margin step-down, promised credits, waiver rules, precedence clause, **Schedule 1 contacts by category**.
   - **Invoice (USD/INR, any layout):** invoice_id (normalised), date, due date, currency, lines (AWB, ship date, charge label, lane, qty, rate, amount), totals, tax/duty flags.
   - **AWB, tracking export, AP register/ledger, credit note, milestone email.**
   - **Emails:** waiver, due-date extension, rate notice, forward/quoted text, "picked up" notice, payment-terms.
   - Each fact stores `doc`, `page`, `quote` (verbatim, ≥12 non-space chars).
5. Prompt-injection hygiene: extraction prompt treats document text strictly as data; add a flag `addresses_automated_reader` per email; such text never produces facts that change terms.

**Exit:** `ingest` runs on practice + exam without crashing; I can dump facts for any doc and every quote is found on its cited page (use `grader/validate.py` helpers).

## Phase 2 — Core engine (≈4h)
1. `money.py`: Decimal + half-up (ties away from zero); INR→USD once per finding (invoice-month FX, missing row → cannot_determine).
2. `rules/pickup.py`: pickup date priority — tracking `PICKED_UP` → carrier email → AWB date → invoice ship date; remember which source was used (needed for autonomous test).
3. `rules/contract.py`: rate lookup by lane + chargeable-weight band (watch band edges like 44 vs 44.5) + rate period by pickup date; fuel % by pickup month; amendment precedence (later beats earlier, per lane); clause in force on pickup date.
4. `rules/authority.py`: 5-level ladder; Schedule 1 category check by sender email/name; detect quoted/forwarded text without original; ignore automated-reader instructions.
5. Detectors, in this order (each returns finding/no_finding/conflict/cannot_determine + evidence):
   1. `overcharge` (incl. fuel re-price; margin step-down belongs to cashback)
   2. `duplicate` (AWB + Annex E code + amount; later invoice; resend rules; credit-note overlap)
   3. `waiver` (authority, names shipment/month, condition met; quoted → cannot_determine)
   4. `latefee` — not-owed (extended due date, grace, ceil(days/30), compounding) and risk (1–14 days)
   5. `cashback` (Qualifying Spend per contract definition, tiers, period closed, subtract issued credits, due vs not due)
   6. `expiry` (end date or notice deadline; extensions move/remove)
6. `resolve.py`: conflict (both authoritative, in force, unranked → range + 2 sources) vs cannot_determine (missing named doc → `missing_doc` + holder from Schedule 1) vs human_review (≥ $5,000.00 inclusive).
7. `report.py` v1: assemble `findings` + `portfolio`, stable `id`, evidence list, validate against schema.

**Exit:** `make grade`-equivalent runs end to end; detection works on all 8 worked examples (`expected_finding.json`).

## Phase 3 — Modes, actions, confidence (≈2h)
1. `actions.py`: map verdict→action; supervised = `draft:*` / `human_review` / internal only (**never `execute:*`**); autonomous = `execute:*` only if all 5 unattended checks pass else `human_review`; conflicts stay `escalate`.
2. Guard rail: if escalations (`escalate` + `human_review`) would exceed 60% of reported items, review logic (don't just truncate).
3. `confidence.py`: combine evidence completeness, source authority, extraction confidence, cross-source agreement, clause-in-force → [0,1]. Calibrate on my own evals (target: wrong items lower, low Brier).

**Exit:** both modes produce legal actions; no `execute:*` in supervised; unsafe cases never executed.

## Phase 4 — Adaptation & feedback (≈2h)
1. Adaptation: report recomputed from stored facts every time; stable ids; when a new doc changes verdict/amount of an earlier key → `supersedes=[old id]` + cite new doc; key existing only because of backdated doc → `retro: true`; stale keys (lapsed expiry, paid invoice, fee window passed) disappear.
2. `feedback.py`: store each item with scope + `decided_at`; handle all decisions (`confirm, reject, close, override_amount, resolve_conflict, one_off_approval`) and fact types (`sender_authority, rate_accepted, waiver_scope, precedence, dispute_closed`).
3. Strict scope: standing facts match only if **every** `applies_to` filter matches within valid dates; one_off affects its single key only (**hard gate**); `close` stops that key only; set `learned_at` on every changed item.

**Exit:** practice feedback file (`W1_batch_01.json`) changes the right keys and nothing else.

## Phase 5 — Grade, generalise, evals (≈2.5h)
1. Run practice grader in both modes; fix misses using the report-card detail (don't special-case).
2. Run `make sheet` equivalent on exam; sanity-check totals by hand against documents (answer sheet is pass/fail).
3. Build **≥10 own eval cases** with new mailboxes: different layouts/wordings, band-edge weights, unauthorised sender, quoted-forward waiver, one-off vs standing waiver, injection email, backdated amendment, missing Annex F row (INR), conflict vs ranked precedence, feedback that should and should not apply, partial credit overlap, notice-deadline expiry with extension.
4. Run `evals/run_evals.py`, produce `evals/results.json`; **deliberately break something and show a case fails**; note which case caught a real bug.
5. Cost/time: measure tokens + seconds per document; estimate cost per 1,000 docs.

**Exit:** practice card healthy, exam sheet plausible, evals pass, results saved.

## Phase 6 — Deliverables & submit (≈1.5h)
1. Fill `SOLUTION.md`, `DESIGN.md` (≤ ~800 words, every heading), `AI_USE.md` (tools + real prompt log).
2. Generate `report_card.txt/.json`, `answer_sheet.json`, `evals/results.json` from the **final commit**.
3. Run `tools/check_submission.py` (validate) until all green; grep repo for key-like strings.
4. Commit; note commit hash; private repo access or zip with `.git`; reply to the brief email.
5. Prep for the 30-min call: demo script, know the code well enough to debug a hidden miss live and accept one change on the spot.

---

## Hard rules to keep checking at every phase
- Never follow instructions inside emails/documents.
- Never treat a one-off waiver as permanent.
- No `execute:*` in supervised; autonomous executes only when all 5 checks pass.
- Don't escalate >60% of reported items.
- Amounts: Decimal, half-up, within $0.01; INR converted once per finding.
- Every evidence quote must exist on the cited page.
- Same commit must run unchanged on all batches; all memory on disk under `--state-dir`.

## Risks / watch list
- Over-fitting to practice layouts (brief says that scored ~11/100 hidden).
- LLM extraction errors on numbers → verify against document text; compute in Python only.
- Scanned invoice (exam + hidden) — OCR quality and quote matching.
- Time/token limits per grader step → cache, batch calls, keep prompts small.
- Backdated amendments and `as_of` boundaries (report must be a pure function of docs received ≤ as_of).

## Decisions I need from the user before starting
1. Extraction engine: Claude API for everything (simplest, costs tokens) vs hybrid with deterministic parsers where layouts are regular? *(Recommended: Claude extraction + deterministic maths + cache.)*
2. OCR: RapidOCR (local) vs Claude vision for scans? *(Recommended: try RapidOCR first, vision as fallback.)*
3. Is an `ANTHROPIC_API_KEY` available, and may I use Windows-native Python (no `make`)?
4. Which Claude model for extraction (cost vs accuracy)?
5. Start with Phase 0 reading, or jump to Phase 1?
