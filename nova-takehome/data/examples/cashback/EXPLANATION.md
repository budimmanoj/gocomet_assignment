# Worked example: Cashback: quarterly rebate earned and not credited

A quarterly volume rebate that was earned and never credited. The skill: add up Qualifying Spend exactly as the contract defines it before reading the tier table.

## The documents

Everything is in `docs/`, laid out like the scenario mailbox (one folder per batch, attachments inside the emails). The report date is `2033-11-30`.

| File | What it is | Received |
|---|---|---|
| `batch_01/0002.eml` | email from Fintan Quigley: `Executed agreement TBX-US-EXP-E58` | `2033-01-30` |
| `batch_01/0002.eml#MSA-TBX-US-EXP-E58.pdf` | Master Services Agreement (Express Air) TBX-US-EXP-E58 | `2033-01-30` |
| `batch_01/0003.eml` | email from Tarrowby Billing: `Invoice TX-US-2033-5462` | `2033-04-13` |
| `batch_01/0003.eml#TX-US-2033-5462.pdf` | Invoice TX-US-2033-5462 | `2033-04-13` |
| `batch_01/0004.eml` | email from Tarrowby Billing: `Invoice TX-US-2033-5464` | `2033-05-28` |
| `batch_01/0004.eml#TX-US-2033-5464.pdf` | Invoice TX-US-2033-5464 | `2033-05-28` |
| `batch_01/0004.eml#AWB-TE14764227.pdf` | Air waybill TE14764227 | `2033-05-28` |
| `batch_01/0004.eml#AWB-TE51172724.pdf` | Air waybill TE51172724 | `2033-05-28` |
| `batch_02/0001.eml` | email from Tarrowby Billing: `Invoice TX-US-2033-5468` | `2033-07-31` |
| `batch_02/0001.eml#TX-US-2033-5468.pdf` | Invoice TX-US-2033-5468 | `2033-07-31` |
| `batch_02/0002.eml` | email from Tarrowby Billing: `Invoice TX-US-2033-5472` | `2033-09-11` |
| `batch_02/0002.eml#TX-US-2033-5472.pdf` | Invoice TX-US-2033-5472 | `2033-09-11` |

## The deciding clause

MSA §7.1, `batch_01/0002.eml#MSA-TBX-US-EXP-E58.pdf` p. 4:

> `7.1 Volume rebate. The Carrier shall credit a rebate on each Quarter's Qualifying Spend (QS) at the tier reached: QS >= USD 55,000.00: 5%; QS >= USD 91,000.00: 7.5%; QS >= USD 150,000.00: 10%. The tier rate applies to all QS in the Quarter.`

## The email line

No email decides this one. The deciding text is clause 7.1 of the MSA, `batch_01/0002.eml#MSA-TBX-US-EXP-E58.pdf` p. 4:

> `7.1 Volume rebate. The Carrier shall credit a rebate on each Quarter's Qualifying Spend (QS) at the tier reached: QS >= USD 55,000.00: 5%; QS >= USD 91,000.00: 7.5%; QS >= USD 150,000.00: 10%. The tier rate applies to all QS in the Quarter.`

## Step by step

1. Clause 1.1 (`batch_01/0002.eml#MSA-TBX-US-EXP-E58.pdf` p. 3) defines Qualifying Spend: freight, fuel, security and Annex D charges on invoices dated in the quarter, net of credit notes, without tax, duty or late fees.
2. The invoices on `TBX-US-EXP-E58` dated in `2033-Q2`, and what each adds to Qualifying Spend:

   | Invoice | Date | Invoice total | Qualifying |
   |---|---|---|---|
   | `TX-US-2033-5462` | `2033-04-12` | `21517.17` | `21517.17` |
   | `TX-US-2033-5464` | `2033-05-28` | `44049.82` | `44049.82` |

3. No credit note is dated in the quarter.
4. Qualifying Spend: `21517.17 + 44049.82 = 65566.99`.
5. Clause 7.1 (`batch_01/0002.eml#MSA-TBX-US-EXP-E58.pdf` p. 4): `65566.99` is at least `55,000.00` and below `91,000.00`, so the rate is `5.00%`, applied to all of it.
6. Rebate earned: `5.00% × 65566.99 = 3278.35`, rounded half up to the cent.
7. No rebate credit note for `2033-Q2` is in the mailbox by `2033-11-30`, so `3278.35` USD is owed. The credit is past its due date, so the action is a claim.

## Why the paired decoy is not a finding

The next quarter, `2033-Q3`, looks like it earns a rebate too: its invoice totals add up to `60271.89` USD, above the `55,000.00` threshold. Its invoices are in `docs/` as well:

| Invoice | Date | Invoice total | Left out (duty, tax, late fees) | Qualifying |
|---|---|---|---|---|
| `TX-US-2033-5468` | `2033-07-31` | `58247.20` | `8703.54` | `49543.66` |
| `TX-US-2033-5472` | `2033-09-11` | `2024.69` | `186.96` | `1837.73` |

Gross: `58247.20 + 2024.69 = 60271.89`. Qualifying Spend: `49543.66 + 1837.73 = 51381.39`.

The duty lines are paid on the shipper's behalf, and clause 1.1 leaves them out. `51381.39` is below `55,000.00`, so no rebate is earned and there is no finding.

## The finding

This goes in `portfolio.cashback` of the report for `--as-of 2033-11-30`. The same item is in `expected_finding.json`, which is a complete report.json. It also lists the decoy as `verdict: no_finding`, the way a harness may report a key it checked and cleared; leaving the decoy out of a report is just as right.

```json
{
  "id": "cashback:TBX-US-EXP-E58/2033-Q2/rebate",
  "class": "cashback",
  "variant": "CB-01",
  "contract_id": "TBX-US-EXP-E58",
  "period": "2033-Q2",
  "credit_type": "rebate",
  "verdict": "finding",
  "amount_usd": "3278.35",
  "amount_range": null,
  "deadline": null,
  "action": "draft:claim_credit",
  "confidence": 0.95,
  "evidence": [
    {
      "doc": "batch_01/0002.eml#MSA-TBX-US-EXP-E58.pdf",
      "page": 4,
      "quote": "7.1 Volume rebate. The Carrier shall credit a rebate on each Quarter's Qualifying Spend (QS) at the tier reached: QS >= USD 55,000.00: 5%; QS >= USD 91,000.00: 7.5%; QS >= USD 150,000.00: 10%. The tier rate applies to all QS in the Quarter."
    },
    {
      "doc": "batch_01/0002.eml#MSA-TBX-US-EXP-E58.pdf",
      "page": 3,
      "quote": "1.1 Qualifying Spend. Qualifying Spend means freight charges (base freight, fuel, security surcharge and Annex D accessorials) on invoices dated in the period, net of all credit notes dated in the period whatever invoice they reference (rebate and improvement credits excepted). It excludes taxes (sales tax, GST), duties and disbursements, late fees, and rebate or improvement credits. INR amounts are converted per invoice at the Annex F rate for the month of the invoice date."
    }
  ],
  "missing_doc": null,
  "supersedes": [],
  "learned_at": null
}
```

The action is `draft:claim_credit` in `supervised` mode and `execute:claim_credit` in `autonomous` mode, because this case passes every unattended-action check.

Check it against the documents:

```
python grader/validate.py --report data/examples/cashback/expected_finding.json \
    --mailbox data/examples/cashback/docs
```
