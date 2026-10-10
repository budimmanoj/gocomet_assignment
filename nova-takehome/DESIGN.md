# Design

## Fact model

`ingest` saves each email under `--state-dir/docs/`: headers, body, and every attachment as text pages from `grader/extract.py` (the grader's own text layer). Scans go through local OCR (rapidocr), with Claude vision as a fallback. `report` re-parses those pages every time, so a report is a pure function of (documents received by `as_of`, feedback decided by `as_of`, mode). Documents are classified by what they say, not by file name. Contract terms are read with patterns. When one is missing and a key is set, Claude quotes the clause, and the value is kept only if that quote is on the page. Invoice lines are read by token type: waybill, lane, four date formats, quantity with unit, percent, money. The arithmetic (rate × qty = amount, base × % = amount) then decides which number is which, so a new column order still reads. Every fact keeps its citation (doc, page, printed line), its received date and its source's authority level.

## Conflicts

A shipment is priced on its pickup date: tracking, then a carrier "picked up" email, then the AWB, then the invoice. The rate is the MSA period's, replaced lane by lane by signed amendments in force, and by rate notices only when the sender's address is the carrier's Schedule 1 `rates` contact (or someone feedback confirmed). Quoted text and text addressed to an AI are ignored. A conflict is raised only when an amendment and an authorised notice both apply, give different amounts, and the contract says neither prevails. Otherwise precedence decides. The range spans the two correct totals. A table an amendment names but we don't hold, or an INR month without an Annex F row, makes the key `cannot_determine`, with the holder taken from Schedule 1.

## Confidence

Each class starts from a prior (0.95 for expiry, 0.75 for cannot_determine). It is lowered when the pickup date isn't from tracking or a carrier email, when numbers came from OCR, when INR conversion was needed, when feedback changed the item, or when the amount is under $1. Checked on practice (Brier 0.011; every item right, so AUROC isn't measurable) and on 22 eval cases. It is hand-set, not fitted.

## People in the loop

Internal actions (alert, payment reminder, track credit) always run. Outbound actions are `draft:*` in supervised mode and never `execute:*`. At $5,000.00 or more per invoice or cashback key, summed over outbound findings, the action is `human_review` in both modes. In autonomous mode `execute:*` needs all five unattended checks: no missing document, a tracking or carrier-email pickup date for pricing findings, no conflict on the contract and lane, under $5,000, and a Schedule 1 recipient. Otherwise it is `human_review`, with `held_because` naming the failed check. Conflicts are always `escalate`. Recipients come only from Schedule 1. An email that addresses an AI or automated reader contributes no facts.

## Feedback

Items decided by `as_of` apply to later reports:
- `close`, `reject`: remove exactly that key.
- `override_amount`: replaces its amount.
- `one_off_approval`: makes a finding for the named months on that one invoice.
- Standing facts (`sender_authority`, `rate_accepted`, `precedence`): used inside the detectors only when every `applies_to` filter (contract, lane, person, category) matches and the date is in scope. A later signed amendment still beats a precedence decision.

Every item computed with a feedback fact carries `learned_at`. Sibling lanes, other people and other months are untouched.

## New documents

Only documents are stored, so an amendment, credit note, extension or waiver changes every later report. The printed report is kept per mode. A key whose verdict or amount changes gets a new id and `supersedes: [old id]`. A key that exists only because a backdated instrument arrived for an invoice already held gets `retro: true`. Lapsed alerts drop out. If an invoice's lines don't add up to its printed total, Claude lists its charge lines. Each line must exist verbatim on the page, and we parse and price it ourselves.

## Cost

Measured locally, the practice mailbox (163 documents) ingests in 8.3 s, 6 s of it OCR on one scan, and a report takes 0.6 s. That is about 1 minute per 1,000 documents. Model cost is zero when the built-in readers succeed, as they did on every practice, exam and eval document. The fallbacks cost about 2k input / 0.6k output tokens per scanned page, and 3k / 1.5k per invoice that won't reconcile. At a 5% fallback rate that is about 0.25M tokens per 1,000 documents. Answers are cached by content hash.

## What I'd do next

- Contract clauses in unseen wording are the biggest risk: a missed clause is silently absent. A page-verified model fallback now covers the main terms. I'd extend it to rebate tiers, annex tables and Schedule 1.
- Margin step-down is built from the glossary alone and is the least tested class.
- Confidence should be fitted on a larger eval set that includes wrong answers.
- Conditional waivers are only evaluated for "paid by <date>".
