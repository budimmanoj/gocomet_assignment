# Worked example: Expiry: contract deadline inside 60 days

A contract whose end date falls inside the 60-day alert window. The skill: find the operative date and measure it from the report date.

## The documents

Everything is in `docs/`, laid out like the scenario mailbox (one folder per batch, attachments inside the emails). The report date is `2034-02-28`.

| File | What it is | Received |
|---|---|---|
| `batch_01/0002.eml` | email from Isolde Yardley: `Executed agreement TBX-US-EXP-E24` | `2033-03-10` |
| `batch_01/0002.eml#MSA-TBX-US-EXP-E24.pdf` | Master Services Agreement (Express Air) TBX-US-EXP-E24 | `2033-03-10` |

## The deciding clause

MSA §2.2, `batch_01/0002.eml#MSA-TBX-US-EXP-E24.pdf` p. 3:

> `2.2 Initial term. The initial term is 12 months, ending on 2034-03-20.`

## The email line

No email decides this one. The date is in the MSA, `batch_01/0002.eml#MSA-TBX-US-EXP-E24.pdf` p. 3:

> `2.2 Initial term. The initial term is 12 months, ending on 2034-03-20.`

## Step by step

1. Clause 2.2 (`batch_01/0002.eml#MSA-TBX-US-EXP-E24.pdf` p. 3): `2.2 Initial term. The initial term is 12 months, ending on 2034-03-20.`
2. Clause 2.3 (`batch_01/0002.eml#MSA-TBX-US-EXP-E24.pdf` p. 3): `2.3 Auto-renewal. This Agreement does not renew automatically. It ends at the end of the initial term unless extended under clause 2.4.` So the date that matters is the last day of the term, `2034-03-20`.
3. The report is as of `2034-02-28`. Days left: `2034-03-20 − 2034-02-28 = 20`.
4. `20` is between 0 and 60, so the contract goes in `portfolio.expiry` with deadline `2034-03-20`. The alert is internal; whether to renew is a business decision.

## Why the paired decoy is not a finding

The same contract, reported as of `2033-08-31` (after `batch_01`), is `2034-03-20 − 2033-08-31 = 201` days from its deadline. That is more than 60, so it must be absent from that report. The alert appears only once the date is inside the window.

## The finding

This goes in `portfolio.expiry` of the report for `--as-of 2034-02-28`. The same item is in `expected_finding.json`, which is a complete report.json.

```json
{
  "id": "expiry:TBX-US-EXP-E24",
  "class": "expiry",
  "variant": "EX-01",
  "contract_id": "TBX-US-EXP-E24",
  "verdict": "finding",
  "amount_usd": null,
  "amount_range": null,
  "deadline": "2034-03-20",
  "action": "internal:alert",
  "confidence": 0.95,
  "evidence": [
    {
      "doc": "batch_01/0002.eml#MSA-TBX-US-EXP-E24.pdf",
      "page": 3,
      "quote": "2.2 Initial term. The initial term is 12 months, ending on 2034-03-20."
    }
  ],
  "missing_doc": null,
  "supersedes": [],
  "learned_at": null
}
```

The action is `internal:alert` in both modes.

Check it against the documents:

```
python grader/validate.py --report data/examples/expiry/expected_finding.json \
    --mailbox data/examples/expiry/docs
```
