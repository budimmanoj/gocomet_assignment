# Worked example: Duplicate: exact resend of a paid invoice

An invoice already paid arrives again with a request to pay it. The skill: join the email to the AP register before deciding.

## The documents

Everything is in `docs/`, laid out like the scenario mailbox (one folder per batch, attachments inside the emails). The report date is `2033-08-31`.

| File | What it is | Received |
|---|---|---|
| `batch_01/0003.eml` | email from Tarrowby Billing: `Invoice TX-US-2033-5511` | `2033-02-01` |
| `batch_01/0003.eml#TX-US-2033-5511.pdf` | Invoice TX-US-2033-5511 | `2033-02-01` |
| `batch_01/0004.eml` | email from Tarrowby Billing: `Invoice TX-US-2033-5511` | `2033-02-18` |
| `batch_01/0004.eml#TX-US-2033-5511.pdf` | Invoice TX-US-2033-5511 | `2033-02-18` |
| `batch_01/0006.eml` | email from Hollis Gallacher: `AP register 2033-02-28` | `2033-02-28` |
| `batch_01/0006.eml#ap-register-2033-02-28.xlsx` | AP register as of 2033-02-28 | `2033-02-28` |
| `batch_02/0001.eml` | email from Tarrowby Billing: `Invoice TX-US-2033-5512` | `2033-05-21` |
| `batch_02/0001.eml#TX-US-2033-5512.pdf` | Invoice TX-US-2033-5512 | `2033-05-21` |
| `batch_02/0002.eml` | email from Tarrowby Billing: `Invoice TX-US-2033-5514` | `2033-05-27` |
| `batch_02/0002.eml#TX-US-2033-5514.pdf` | Invoice TX-US-2033-5514 | `2033-05-27` |
| `batch_02/0002.eml#AWB-TE19536828.pdf` | Master air waybill TE19536828 | `2033-05-27` |

## The deciding clause

AP register: the invoice is already paid, `batch_01/0006.eml#ap-register-2033-02-28.xlsx` p. 1:

> `TX-US-2033-5511 | 2033-01-31 | due 2033-03-02 | USD 1259.23 | paid | 2033-02-07`

## The email line

Email `batch_01/0004.eml`, sent `2033-02-18` by Tarrowby Billing, subject `Invoice TX-US-2033-5511`. The line that matters:

> `Please process payment at your earliest convenience.`

## Step by step

1. Invoice `TX-US-2033-5511` first arrived on `2033-02-01` (`batch_01/0003.eml`), total `1259.23` USD.
2. The AP register (`batch_01/0006.eml#ap-register-2033-02-28.xlsx` p. 1) shows it paid: `TX-US-2033-5511 | 2033-01-31 | due 2033-03-02 | USD 1259.23 | paid | 2033-02-07`. Paid on `2033-02-07`.
3. On `2033-02-18` the same invoice number arrives again (`batch_01/0004.eml`) and asks for payment. Nothing marks it as a copy or a reminder.
4. A second payment request for an invoice already paid is a duplicate. The amount is the invoice total: `1259.23` USD.

## Why the paired decoy is not a finding

Invoice `TX-US-2033-5514` looks like a second bill for the same master AWB. Line by line:

- `Air freight (MAWB TE19536828) TE19536828-H1 USW2-INE2 14 May 2033 981.60 240 kg 4.09` (`batch_02/0001.eml#TX-US-2033-5512.pdf` p. 1)
- `Air freight (MAWB TE19536828) TE19536828-H2 USW2-INE2 14 May 2033 421.27 103 kg 4.09` (`batch_02/0002.eml#TX-US-2033-5514.pdf` p. 1)
- the master AWB (`batch_02/0002.eml#AWB-TE19536828.pdf` p. 1): `Total pieces 4 | Total chargeable weight 343 kg`

The two invoices bill different house AWBs, and `240 + 103 = 343` kg is the master total. One shipment split in two and billed once per part, so there is no finding.

## The finding

This goes in `findings` of the report for `--as-of 2033-08-31`. The same item is in `expected_finding.json`, which is a complete report.json. It also lists the decoy as `verdict: no_finding`, the way a harness may report a key it checked and cleared; leaving the decoy out of a report is just as right.

```json
{
  "id": "duplicate:TX-US-2033-5511",
  "class": "duplicate",
  "variant": "DU-01",
  "invoice_id": "TX-US-2033-5511",
  "verdict": "finding",
  "amount_usd": "1259.23",
  "amount_range": null,
  "deadline": null,
  "action": "draft:dispute",
  "confidence": 0.95,
  "evidence": [
    {
      "doc": "batch_01/0006.eml#ap-register-2033-02-28.xlsx",
      "page": 1,
      "quote": "TX-US-2033-5511 | 2033-01-31 | due 2033-03-02 | USD 1259.23 | paid | 2033-02-07"
    },
    {
      "doc": "batch_01/0004.eml",
      "page": 1,
      "quote": "Please process payment at your earliest convenience."
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
python grader/validate.py --report data/examples/duplicate/expected_finding.json \
    --mailbox data/examples/duplicate/docs
```
