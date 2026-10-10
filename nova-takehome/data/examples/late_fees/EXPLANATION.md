# Worked example: Late fee not owed: fee billed despite an extension

A late fee billed on an invoice paid inside an extended due date. The skill: find the extension, check who granted it, and count days from the new date.

## The documents

Everything is in `docs/`, laid out like the scenario mailbox (one folder per batch, attachments inside the emails). The report date is `2033-02-28`.

| File | What it is | Received |
|---|---|---|
| `batch_01/0002.eml` | email from Joaquin Whitlock: `Executed agreement TBX-US-EXP-E42` | `2032-05-01` |
| `batch_01/0002.eml#MSA-TBX-US-EXP-E42.pdf` | Master Services Agreement (Express Air) TBX-US-EXP-E42 | `2032-05-01` |
| `batch_01/0005.eml` | email from Ulrich Ellwood: `Due date extension TX-US-2032-5494` | `2032-08-07` |
| `batch_01/0006.eml` | email from Tarrowby Billing: `Invoice TX-US-2032-5496` | `2032-08-22` |
| `batch_01/0006.eml#TX-US-2032-5496.pdf` | Invoice TX-US-2032-5496 | `2032-08-22` |
| `batch_01/0008.eml` | email from Signe Hartigan: `AP register 2032-08-31` | `2032-08-31` |
| `batch_01/0008.eml#ap-register-2032-08-31.xlsx` | AP register as of 2032-08-31 | `2032-08-31` |
| `batch_02/0002.eml` | email from Ulrich Ellwood: `Due date extension TX-US-2032-5498` | `2032-11-07` |
| `batch_02/0003.eml` | email from Tarrowby Billing: `Invoice TX-US-2033-5582` | `2033-01-18` |
| `batch_02/0003.eml#TX-US-2033-5582.pdf` | Invoice TX-US-2033-5582 | `2033-01-18` |
| `batch_02/0003.eml#DGD-TE54004399.pdf` | Shipper's declaration TE54004399 | `2033-01-18` |
| `batch_02/0006.eml` | email from Signe Hartigan: `AP register 2033-02-28` | `2033-02-28` |
| `batch_02/0006.eml#ap-register-2033-02-28.xlsx` | AP register as of 2033-02-28 | `2033-02-28` |

## The deciding clause

MSA §10.5, `batch_01/0002.eml#MSA-TBX-US-EXP-E42.pdf` p. 4:

> `10.5 Extension of due date. A due date may be extended by written notice from the Carrier's Authorised Person (payment terms); the extended date replaces the due date for clause 10.2.`

## The email line

Email `batch_01/0005.eml`, sent `2032-08-07` by Ulrich Ellwood, subject `Due date extension TX-US-2032-5494`. The line that matters:

> `We extend the due date of invoice TX-US-2032-5494 to 2032-08-25.`

## Step by step

1. Invoice `TX-US-2032-5494` was due on `2032-08-10` (AP register, `batch_01/0008.eml#ap-register-2032-08-31.xlsx` p. 1).
2. On `2032-08-07`, Ulrich Ellwood, the Schedule 1 contact for payment terms, writes: `We extend the due date of invoice TX-US-2032-5494 to 2032-08-25.` Clause 10.5 makes the extended date the due date.
3. The AP register shows it paid on `2032-08-17`.
4. Days late against the extended date: `2032-08-17 − 2032-08-25 = -8`. Zero or fewer days late means no late fee (the grace period is `5` days on top).
5. Invoice `TX-US-2032-5496` still bills a late fee (`batch_01/0006.eml#TX-US-2032-5496.pdf` p. 1): `13 - - Late fee on TX-US-2032-5494: USD 680.12 overdue, month 1 @ 1.86% - 1 month 1.86% 12.65`.
6. Late fee not owed: `12.65 − 0.00 = 12.65` USD.

## Why the paired decoy is not a finding

Invoice `TX-US-2033-5582` also bills a late fee on an invoice whose due date was extended to `2032-12-12` (`batch_02/0003.eml#TX-US-2033-5582.pdf` p. 1): `11 - - Late fee on TX-US-2032-5498: USD 4200.07 overdue, month 1 @ 1.86% - 1 month 1.86% 78.12`.

This time the payment came late: `2033-01-01 − 2032-12-12 = 20` days, past the `5`-day grace. One month's fee under clause 10.2 is `1.86% × 4200.07 = 78.12`, exactly what was billed. The fee is owed, so there is no finding.

## The finding

This goes in `findings` of the report for `--as-of 2033-02-28`. The same item is in `expected_finding.json`, which is a complete report.json. It also lists the decoy as `verdict: no_finding`, the way a harness may report a key it checked and cleared; leaving the decoy out of a report is just as right.

```json
{
  "id": "late_fee_not_owed:TX-US-2032-5496",
  "class": "late_fee_not_owed",
  "variant": "LF-01",
  "invoice_id": "TX-US-2032-5496",
  "verdict": "finding",
  "amount_usd": "12.65",
  "amount_range": null,
  "deadline": null,
  "action": "draft:dispute",
  "confidence": 0.95,
  "evidence": [
    {
      "doc": "batch_01/0005.eml",
      "page": 1,
      "quote": "We extend the due date of invoice TX-US-2032-5494 to 2032-08-25."
    },
    {
      "doc": "batch_01/0008.eml#ap-register-2032-08-31.xlsx",
      "page": 1,
      "quote": "TX-US-2032-5494 | 2032-06-26 | due 2032-08-10 | USD 680.12 | paid | 2032-08-17"
    },
    {
      "doc": "batch_01/0006.eml#TX-US-2032-5496.pdf",
      "page": 1,
      "quote": "13 - - Late fee on TX-US-2032-5494: USD 680.12 overdue, month 1 @ 1.86% - 1 month 1.86% 12.65"
    },
    {
      "doc": "batch_01/0002.eml#MSA-TBX-US-EXP-E42.pdf",
      "page": 4,
      "quote": "10.5 Extension of due date. A due date may be extended by written notice from the Carrier's Authorised Person (payment terms); the extended date replaces the due date for clause 10.2."
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
python grader/validate.py --report data/examples/late_fees/expected_finding.json \
    --mailbox data/examples/late_fees/docs
```
