# Worked example: Duplicate: the same charge re-billed four months later

The same charge billed again four months later under a different name. The skill: map every billed label to its Annex E code and compare by AWB and code.

## The documents

Everything is in `docs/`, laid out like the scenario mailbox (one folder per batch, attachments inside the emails). The report date is `2032-08-31`.

| File | What it is | Received |
|---|---|---|
| `batch_01/0002.eml` | email from Anselm Castellan: `Executed agreement TBX-US-EXP-E61` | `2031-12-01` |
| `batch_01/0002.eml#MSA-TBX-US-EXP-E61.pdf` | Master Services Agreement (Express Air) TBX-US-EXP-E61 | `2031-12-01` |
| `batch_01/0003.eml` | email from Tarrowby Billing: `Invoice TX-US-2032-5436` | `2032-01-30` |
| `batch_01/0003.eml#TX-US-2032-5436.pdf` | Invoice TX-US-2032-5436 | `2032-01-30` |
| `batch_02/0002.eml` | email from Tarrowby Billing: `Invoice TX-US-2032-5441` | `2032-05-30` |
| `batch_02/0002.eml#TX-US-2032-5441.pdf` | Invoice TX-US-2032-5441 | `2032-05-30` |

## The deciding clause

Annex E, `batch_01/0002.eml#MSA-TBX-US-EXP-E61.pdf` p. 10:

> `Code SEC: Security surcharge; also billed as: Screening fee, Screening fee (adj.), Security screening`

## The email line

No email decides this one. Both invoices came by email; the later one is `batch_02/0002.eml#TX-US-2032-5441.pdf`, sent `2032-05-30` with the subject `Invoice TX-US-2032-5441`. The line that matters:

> `5 TE16812897 - Screening fee (adj.) (ref TE16812897) USC3-USE2 263 kg 0.16 42.08`

## Step by step

1. Invoice `TX-US-2032-5436`, dated `2032-01-30`, bills the security surcharge on AWB `TE16812897` (`batch_01/0003.eml#TX-US-2032-5436.pdf` p. 1): `3 TE16812897 2032-01-22 Security surcharge USC3-USE2 263 kg 0.16 42.08`.
2. Invoice `TX-US-2032-5441`, dated `2032-05-30`, four months later, has a line under a new name (`batch_02/0002.eml#TX-US-2032-5441.pdf` p. 1): `5 TE16812897 - Screening fee (adj.) (ref TE16812897) USC3-USE2 263 kg 0.16 42.08`.
3. Annex E (`batch_01/0002.eml#MSA-TBX-US-EXP-E61.pdf` p. 10) maps that name back to the same charge code: `Code SEC: Security surcharge; also billed as: Screening fee, Screening fee (adj.), Security screening`.
4. Same AWB, same charge code, same amount: the charge is billed twice. The later invoice carries the finding, for the duplicated line only: `42.08` USD.

## Why the paired decoy is not a finding

Change one detail and it is a new charge: a line for a different AWB, or a label that Annex E maps to a different code. Matching on the printed label alone misses this duplicate; matching on the AWB alone flags legitimate new charges. The check is AWB plus Annex E code plus amount.

## The finding

This goes in `findings` of the report for `--as-of 2032-08-31`. The same item is in `expected_finding.json`, which is a complete report.json.

```json
{
  "id": "duplicate:TX-US-2032-5441",
  "class": "duplicate",
  "variant": "DU-03",
  "invoice_id": "TX-US-2032-5441",
  "verdict": "finding",
  "amount_usd": "42.08",
  "amount_range": null,
  "deadline": null,
  "action": "draft:dispute",
  "confidence": 0.95,
  "evidence": [
    {
      "doc": "batch_01/0003.eml#TX-US-2032-5436.pdf",
      "page": 1,
      "quote": "3 TE16812897 2032-01-22 Security surcharge USC3-USE2 263 kg 0.16 42.08"
    },
    {
      "doc": "batch_02/0002.eml#TX-US-2032-5441.pdf",
      "page": 1,
      "quote": "5 TE16812897 - Screening fee (adj.) (ref TE16812897) USC3-USE2 263 kg 0.16 42.08"
    },
    {
      "doc": "batch_01/0002.eml#MSA-TBX-US-EXP-E61.pdf",
      "page": 10,
      "quote": "Code SEC: Security surcharge; also billed as: Screening fee, Screening fee (adj.), Security screening"
    }
  ],
  "missing_doc": null,
  "supersedes": [],
  "learned_at": null
}
```

The action is `draft:dispute` in `supervised` mode and `execute:dispute` in `autonomous` mode, because this case passes every unattended-action check.

Check it against the documents:

```
python grader/validate.py --report data/examples/duplicate_rebilled_4_months/expected_finding.json \
    --mailbox data/examples/duplicate_rebilled_4_months/docs
```
