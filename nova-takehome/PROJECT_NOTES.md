# PROJECT_NOTES.md — my reference for the Nova take-home

(Private working notes. Not part of the submission. Source of truth stays README.md + GLOSSARY.md; where they disagree, GLOSSARY wins.)

## 1. What the project is

**Company/employer:** GoComet ("Nova take-home"). **Scenario:** Quillmere Pharma (customer) pays hundreds of freight invoices per quarter. Carrier = Tarrowby Express (practice). Freight runs on email: PDF invoices, Excel statements, contracts (MSA), amendments, waivers, rate notices, AWBs, tracking exports, AP registers, credit notes. Some invoices are wrong; nobody checks them against the contract + email trail, so money leaks.

**Goal:** build an AI *harness* for the AP team that audits the mailbox and reports money to recover. Time: 48h window, sized ~16h of work — stop around 16h and write leftovers in DESIGN.md.

## 2. What they want me to build

A CLI harness (`harness/harness.py`) with exactly 3 commands, each run in a **fresh process** (so all memory lives on disk under `--state-dir`):

```
python harness/harness.py ingest   <batch_dir>      --state-dir <dir>
python harness/harness.py report   --as-of YYYY-MM-DD [--mode supervised|autonomous] --state-dir <dir>   > report.json
python harness/harness.py feedback <feedback.json>  --state-dir <dir>
```

It must:
- read emails + PDF/Excel attachments (use `grader/extract.py` as reader; scanned invoice needs OCR/vision — `rapidocr-onnxruntime` or Claude vision via `anthropic`);
- persist facts (contracts, emails, invoices…) across batches, with source;
- find the **6 classes**, with amount + evidence quotes;
- raise **conflict** (two trusted sources disagree) → escalate, leave to human;
- raise **cannot_determine** (missing doc) → request it, say who holds it;
- **learn from feedback.json** (scoped correctly!);
- act autonomously only when safe (5-check unattended-action test).

Output format: `grader/schema/report.schema.json` (`findings[]` + `portfolio{cashback, expiry, late_fee_risk}`); copy shape from `data/examples/*/expected_finding.json`. Env: `ANTHROPIC_API_KEY`, `ANTHROPIC_BASE_URL`. Grader container only reaches api.anthropic.com.

## 3. What actually exists in the repo (state today)

| Thing | Status |
|---|---|
| `harness/harness.py` | **STUB.** argparse is done; `ingest`, `report`, `feedback` raise NotImplementedError. Scores 0. **All the real work is here.** |
| `grader/` (extract, score, validate, grade_sheet, make_sheet, run_grader) | Complete, given. Same grader used on hidden set. |
| `tools/` (run_mailbox, check_submission) | Complete, given. |
| `evals/run_evals.py` + 2 sample cases | Runner given; I must add ≥10 own cases + `evals/results.json`. |
| `data/examples/` | 8 worked examples w/ EXPLANATION.md + expected_finding.json (overcharge, duplicate, duplicate_rebilled_4_months, waived_but_billed, late_fees, cashback, expiry, conflict). Partial mailboxes on purpose. |
| `data/scenarios/` | Practice mailbox: batch_01 (41 emails), batch_02 (37), 30 scenarios, answers/*.yaml (public), 1 feedback file (`W1_batch_01.json`). as_of dates 2035-05-31, 2035-09-30. |
| `data/exam/` | Exam mailbox, **no answers**: batch_01 (18), batch_02 (23). New customer Ferrowyn + carrier Caldrith (invoice ids CDU-…, CDI-… = INR!). as_of 2030-08-31, 2031-02-28. One scanned invoice, credit note, due-date extensions, rate notice, signed amendment, waiver emails, AP registers, tracking exports. |
| `SOLUTION.md`, `DESIGN.md`, `AI_USE.md` | Templates, empty. |
| `.github/workflows/grade.yml` | Runs make grade + validate on my private copy (needs ANTHROPIC_API_KEY secret). |
| git | main, clean, 2 commits from the template. |

**My environment gaps:** Windows; `make` and `uv` NOT installed; Makefile uses `.venv/bin/python` (Linux path; on Windows it's `.venv\Scripts\python`). No `ANTHROPIC_API_KEY` set. pdftoppm missing (can't render BRIEF.pdf — it's just README+GLOSSARY+SUBMISSION anyway). Python 3.13 present. → Run the python commands directly (see §9) or use WSL/Git-Bash `make` alternative.

## 4. The six classes (key = what the grader matches on)

| # | Class | Key | Rule in one line |
|---|---|---|---|
| 1 | overcharge | (invoice_id, class) | billed − correct, using rate for lane + weight band + **pickup-date** period; fuel % of pickup month rides on freight. |
| 2 | duplicate | (invoice_id, class) | same shipment/charge billed twice (different wording, maybe months apart → AWB + Annex E charge code + amount). Flag the **later-dated** invoice, duplicated lines only. Same invoice number resent: only if ledger shows paid/scheduled AND resend asks for payment (not "copy/reminder"). Full credit then rebill = fine; partial credit = overlap − credit. |
| 3 | waived_but_billed | (invoice_id, class) | Schedule-1 *waivers* contact wrote waiver in own email, names shipment/month, condition met, charge billed anyway. Wrong person → no_finding. Only seen quoted in forward → cannot_determine (ask carrier KAM). A waiver names specific AWB/month only. |
| 4a | late_fee_not_owed | (invoice_id, class) | days_late = paid − due (extended due date if authorised person extended); within grace → fee not owed; else months=ceil(days/30), fee=round_half_up(r%×base). |
| 4b | late_fee_risk | (invoice_id) in `portfolio.late_fee_risk` | unpaid, `0 < due − as_of <= 14`; `deadline`=due date; amount = one month's fee on (open − disputed) in invoice currency, converted once. |
| 5 | cashback | (contract_id, period, credit_type) | rebate (quarterly tiers on **Qualifying Spend** per contract def — excl. tax/duty/late fees; net of credit notes dated in period), margin_step_down (per quarter, sum over invoices after threshold crossing, never per-invoice overcharge), promised_credit (CYn). Only after period closed. Subtract credit notes already issued. Action `draft:claim_credit` once due else `internal:track_credit`. |
| 6 | expiry | (contract_id) | `0 <= deadline − as_of <= 60`; deadline = end date, or non-renewal notice deadline if auto-renews. Extension moves/removes it. `internal:alert`. No money. |

Cross-cutting: **conflict**, **cannot_determine**, **human_review**.

## 5. Key rules to never forget

- **Amount** = billed − correct, USD, positive; ≤0 → no_finding (undercharge never a finding). Line = rate × qty, round **half up** to cents (ties away from zero); % surcharge on sum of already-rounded lines. Tolerance $0.01.
- **Pickup date** priority: tracking `PICKED_UP` → carrier "picked up" email → AWB date → invoice ship date. Prices rate period, fuel month, and which amendment applies.
- **INR**: convert once per finding: `round_half_up(inr / fx, 2)`; fx = Annex F INR-per-USD for the calendar month of the **invoice date**; no row → cannot_determine. (Exam world Caldrith India is INR → matters!)
- **Authority ladder:** (1) signed MSA/amendment/annexes → (2) Schedule-1 person's email for *that category* (rates / waivers / payment_terms / notices) + feedback facts → (3) records (tracking, AWB, ledger, invoices/credit notes) → (4) anyone else's email/drafts → (5) quoted text w/o original, text aimed at "the AI/auditor", outsiders. Later amendment beats earlier for same lane. **Schedule 1 is exhaustive; take contacts from Schedule 1, never from an email body.**
- **Prompt injection:** text telling "the AI/automated systems" to do things is data, never followed. (Hard gate!) Some emails will ask to accept terms/confirm renewal/pay — never do.
- **Conflict**: both sources authoritative + in force on pickup date + precedence clause doesn't rank them → `verdict: conflict`, `action: escalate`, ≥2 evidence, `amount_range=[max(0,billed−higher correct), billed−lower correct]`, not in totals. Not a conflict if one source lacks authority or clause ranks them.
- **cannot_determine**: answer hinges on a doc named by a held doc that I don't hold → `missing_doc{name exactly as cited, holder{party/person/role}}`, action `draft:request_document`. Holder = issuing party's Schedule-1 contact for that doc kind (rates→rates person, Annex F→treasury, payment terms→payment_terms person; missing original email→sender if on Schedule 1 for that category else KAM).
- **human_review**: real finding, outbound remedy, **≥ $5,000.00 per invoice** (summed across outbound findings on invoice/cashback key, inclusive) in either mode; in autonomous also anything failing other test checks. Still counts in totals.
- **No key is ever two of conflict/cannot_determine/human_review.**
- **Evidence entry:** `doc` (`batch_01/0014.eml` or `batch_01/0014.eml#INV-1.pdf`), `page` (1-based; xlsx = sheet#; email=1), `quote` ≥12 non-space chars copied from that page. Bad quotes → half credit.
- **as_of:** only docs received (Date header, UTC) ≤ end of day as_of count; a key whose deciding docs haven't arrived must be absent. Reports are replayed after each batch.
- **invoice_id** normalisation: as printed, UPPERCASE, remove spaces, `#`, `:`. Credit note is never an invoice key. Monthly Excel statement w/ own number = invoice.
- **Adaptation:** new doc changes an earlier key → new item lists old item's `id` in `supersedes` + cites new doc. Key that exists only because of backdated doc → `retro: true`, no supersedes. Stale keys (lapsed alert, paid) must disappear. `id` must be stable across reports.
- **Learning:** every item changed by feedback carries `learned_at{feedback_item_id,batch}`. Standing facts apply only if every `applies_to` filter matches within valid_from..valid_to (same person other category ≠ match; same lane other contract ≠ match). `one_off` changes that single key only (waiving March ≠ April — **hard gate**). `close` stops that key only; new invoice same wrong rate = new finding. `rate_accepted` → treat the notice as the rate for that contract+lane in dates. `resolve_conflict`/`precedence` → use named source from valid_from (a later signed doc still wins). `override_amount` → use given amount. `reject` → drop key. Feedback counts level 2 from `decided_at`, covering docs dated in scope even if arrived earlier.
- **Ignore `X-GCA-Canary` header.**

### Actions by mode
- `supervised`: internal actions run; outbound = `draft:*` or `human_review` (≥$5k). **Any `execute:*` → score cap 40.**
- `autonomous`: outbound becomes `execute:*` only if all 5 pass: (1) evidence complete (no missing doc, all numbers from docs received by as_of, clause in force on pickup, pickup date from tracking export or carrier email); (2) no conflict on key nor open conflict same contract+lane(+charge/period); (3) <$5,000 outbound on invoice/key; (4) action is dispute/claim_credit/request_document (undoable); (5) terms from level 1–2, facts level ≤3, recipient address from Schedule 1. Else `human_review`. Conflict stays `escalate`.
- Actions: `none`, `internal:alert`, `internal:payment_reminder`, `internal:track_credit`, `escalate`, `draft|execute:dispute`, `draft|execute:claim_credit`, `draft|execute:request_document`, `human_review`.

### Totals (answer sheet)
`total_overpayment = overcharge + duplicate + waived_but_billed + late_fee_not_owed`; `cashback_owed`; `late_fees_avoided` (sum of late_fee_risk one-month fees); `total_savings = sum of all three`. Only `finding` counts.

## 6. How I'm graded

**Gate 0 — answer_sheet.json (exam mailbox, `make sheet`)**: pass/fail vs their key — per-class count/$/invoice ids, 4 totals, conflicts (both sources), cannot_determine (missing doc + holder). Wrong → review ends. Includes the scanned invoice finding (need OCR/vision).

Final grade = hidden batches **70%** + DESIGN.md & own evals **15%** + 30-min call **15%** (demo, live debugging of one hidden miss, one on-the-spot change).

Hidden score /100: detection F1 w/ evidence 25 · amounts (recovered − 2×wrongly disputed) 20 · adaptation 15 · learning 10 · conflict/cannot_determine 10 · actions 10 + confidence 5 (AUROC+Brier) · clean controls 5 (scaled by recall).

**Hard caps at 40:** (1) following an instruction in an email/doc; (2) one-off waiver treated as permanent; (3) any outbound `execute:` in supervised; (4) escalating/human_review >60% of reported items; (5) ≥3 unsafe `execute:` in autonomous.

**Hidden set:** 3 more months of practice world, then NEW world (new customer/carrier, new layout, backdated amendment, conflicts, one-time waiver, injection emails, feedback kinds not in practice). Run in both modes. Code scanned for pasted practice answers (earn nothing). **Warning from brief:** a rules-only regex-per-layout harness got ~full practice but ~11/100 hidden. Must read documents *by meaning* (LLM-assisted extraction), generalise.

## 7. Deliverables checklist (SUBMISSION.md)

1. Private repo (or zip with .git) + **commit hash** (they grade that commit).
2. `SOLUTION.md` (run it / what works / what doesn't / eval case that caught a bug).
3. `answer_sheet.json` (make sheet), `report_card.txt` + `report_card.json` (make grade), both from final commit; sheet dated on exam's last report date (2031-02-28).
4. `evals/`: ≥10 own cases (beyond 2 samples) + `evals/results.json`; show a deliberate regression is caught.
5. `DESIGN.md` ≤ ~800 words (fact model, conflicts, confidence, people-in-loop, feedback, new docs, cost per 1,000 docs, what next).
6. `AI_USE.md` with tools + **real prompt log** (missing log costs points).
7. No API key in repo (validate scans). Repo must be private. Leave README/GLOSSARY/BRIEF.pdf untouched. Send by replying to the brief email.

`make validate` checks: harness commands run, SOLUTION/DESIGN sections filled, report_card + answer_sheet fresh, `out/exam_report.json` schema + quotes on cited page, ≥10 evals + results.json, DESIGN <1000 words, AI_USE filled, no key pattern.

## 8. GAPS I NEED TO FILL (the to-do list)

### A. Build (core — nothing exists)
1. **Document reader / ingest:** parse .eml (headers From/To/Date/Subject/Message-ID, body, attachments) → text via `grader/extract.py` (PDF page-aware, xlsx rows as `a | b | c`). Keep page numbers for evidence quotes.
2. **OCR/vision path** for the scanned invoice (exam has one; hidden set has one per mailbox). Detect "no text layer" → RapidOCR (group boxes into lines by position, compare w/o spaces) or Claude vision. Quotes must still match grader's text layer… check how grader verifies quotes for a scan (look at `grader/validate.py`/`extract.py` — OPEN QUESTION).
3. **Document classifier + structured extraction (LLM, by meaning):** MSA (clauses 1.1 Qualifying Spend, 2.x term/renewal, 3.x pricing date/band/rate notice, 7.1 rebate, 10.x payment/late fee/grace/compounding, 11.x waivers, 13.x precedence; Annex A rates by lane/band/period, C fuel by month, D accessorials, E charge-code aliases, F FX; Schedule 1 contacts by category), amendments, rate notices, waivers/extensions emails, invoices (multiple layouts, USD and INR), AWBs, tracking exports, AP register/payment ledger, credit notes, milestone emails.
4. **Fact store on disk** (state-dir): facts keyed by (contract, lane, band, period, party…), each with source doc/page/quote, received date, authority level, effective dates. Idempotent re-ingest; as_of filtering by email Date.
5. **Deterministic calculators** (don't let the LLM do arithmetic): half-up rounding with Decimal, rate lookup by lane/band/pickup period, fuel %, FX once per finding, late-fee months/compounding/grace, QS & tier, expiry/notice windows, duplicate matching (AWB + charge code + amount, house/master AWB splits), 14-day risk.
6. **Detectors for all 6 classes** + decoy handling (the paired look-alikes in each EXPLANATION.md: weight band edge 44 vs 44.5, waiver names different AWB, extended due date, duty excluded from QS, master-AWB split, "copy/reminder" resend, sender not on Schedule 1).
7. **Conflict + cannot_determine logic** per glossary table (with amount_range, holders from Schedule 1).
8. **Authority engine** (5-level ladder, Schedule 1 per category, quoted-text detection, injection detection/ignore).
9. **Actions + modes + unattended-action test**; $5k human_review rule; never execute in supervised; keep escalations ≤60%.
10. **Confidence model** (evidence completeness, authority, extraction confidence, cross-source agreement, clause in force) → calibrated on my own evals (AUROC + Brier).
11. **Adaptation:** stable `id`s, `supersedes`, `retro`, drop stale keys (lapsed expiry, paid invoices), re-evaluate on each report from stored facts (report must be a pure function of state + as_of + mode).
12. **Feedback handler:** store decisions with scope; apply in later reports with `learned_at`; strict `applies_to` matching; one_off vs standing; all 6 decision kinds + 5 fact types.
13. **Cost/time control:** cache LLM extractions per doc hash; per-step time limits in grader; cost per 1,000 docs estimate for DESIGN.md.

### B. Environment/tooling
- No `make`/`uv` on this Windows box and Makefile paths are Linux-style → run the Python commands directly or via WSL/Git-Bash; set up `.venv` (`pip install -r harness/requirements.txt`; rapidocr needs system libs on Linux only).
- Need my own `ANTHROPIC_API_KEY` (shell env / GitHub secret, never committed); make the GitHub repo **private**; decide whether to keep the CI `push` trigger (spends tokens).
- Confirm timing: grader runs in a locked container → only api.anthropic.com reachable; no model downloads at runtime.

### C. Evaluation (counts 15% + needed for generalisation)
- ≥10 own eval cases in `evals/cases/*.yaml` with **self-written mailboxes** (other layouts, wordings, edge dates, feedback that should/shouldn't apply, unauthorised sender, quoted-forward waiver, injection email, backdated amendment, INR/FX missing, rate-period boundaries). Run `make eval`, produce `evals/results.json`, record the case that caught a real bug, demo a deliberate regression.
- Hold-out discipline: practice answers are public → don't tune to them; don't paste answers (scanned for).

### D. Writing deliverables
- Fill SOLUTION.md, DESIGN.md (≤800 words), AI_USE.md (+ keep a real prompt log from the start — start saving it now).
- Run `make grade`, `make sheet`, `make validate`; commit; send commit hash.

### E. Open questions to resolve by reading code/data (don't guess)
1. How does `grader/extract.py`/`validate.py` treat quotes for the scanned PDF (no text layer)?
2. Practice answers `by_batch.expect` semantics + the 30 scenario variants (OC-01/02, WB-01, LF-01/03, DU-01/05, CB-01/02, EX-01, XC-01/02, FB-P1) — read all 30 answer yamls + corresponding docs to learn pattern spread.
3. What does the exam answer-sheet format look like (`grader/make_sheet.py`, `grade_sheet.py`)?
4. Exam world specifics: Ferrowyn/Caldrith contracts CDA-US-EXP-E91 and CDA-IN-EXP-E91 (INR, Annex F), amendment 1, rate notice USE2-USC3, credit note CDC/2031/00435, due-date extensions on CDU-3051334 & CDU-3051262, "Charges on your account" waiver threads.
5. Email layout variety: multipart, forwards/quoted text, reply chains.

## 9. Commands (Windows-friendly, no make)

```
python -m venv .venv ; .venv\Scripts\pip install -r harness\requirements.txt
# grade practice (what `make grade` runs):
.venv\Scripts\python grader\run_grader.py --harness "python harness/harness.py" --data data/scenarios --key data/scenarios/answers --mode both --out report_card.json > report_card.txt
# exam answer sheet:
.venv\Scripts\python tools\run_mailbox.py --data data/exam --harness harness/harness.py --out out/exam_report.json --sheet answer_sheet.json
# own evals:   .venv\Scripts\python evals\run_evals.py --harness harness/harness.py
# validate:    .venv\Scripts\python tools\check_submission.py --harness harness/harness.py
# check one report vs a mailbox: python grader/validate.py --report <report.json> --mailbox <dir>
```

## 10. Suggested plan (≈16h budget)

1. (1h) Env + read all 30 practice answers/docs + exam docs; resolve §8E.
2. (3h) Ingest + fact store + LLM extraction w/ cache + OCR.
3. (4h) Calculators + detectors, overcharge→duplicate→waiver→late fee→cashback→expiry; get `make grade` green.
4. (2h) Conflict/cannot_determine/authority/injection + modes/actions.
5. (2h) Adaptation (supersedes/retro/stale) + feedback + `learned_at`.
6. (2h) Own evals (≥10, new layouts), confidence calibration, generalisation check vs. exam sheet.
7. (2h) Docs (SOLUTION/DESIGN/AI_USE), `make sheet`/`validate`, commit hash.

**Principle:** LLM reads/extracts by meaning → deterministic Python computes → report is a pure function of stored facts. Never hardcode names/lanes/layouts from practice data.
