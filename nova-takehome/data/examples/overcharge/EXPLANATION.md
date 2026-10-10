# Worked example: Overcharge: wrong rate

A freight line billed above the contract rate. The skill: find the rate that applies to this lane, this weight band and this pickup date, then reprice the line and the fuel that rides on it.

## The documents

Everything is in `docs/`, laid out like the scenario mailbox (one folder per batch, attachments inside the emails). The report date is `2032-08-31`.

| File | What it is | Received |
|---|---|---|
| `batch_01/0002.eml` | email from Nadia Iyengar: `Executed agreement TBX-US-EXP-E60` | `2031-11-25` |
| `batch_01/0002.eml#MSA-TBX-US-EXP-E60.pdf` | Master Services Agreement (Express Air) TBX-US-EXP-E60 | `2031-11-25` |
| `batch_01/0003.eml` | email from Tarrowby Billing: `Invoice TX-US-2032-5394` | `2032-01-03` |
| `batch_01/0003.eml#TX-US-2032-5394.pdf` | Invoice TX-US-2032-5394 | `2032-01-03` |
| `batch_01/0004.eml` | email from Tarrowby Billing: `Invoice TX-US-2032-5397` | `2032-01-27` |
| `batch_01/0004.eml#TX-US-2032-5397.pdf` | Invoice TX-US-2032-5397 | `2032-01-27` |
| `batch_01/0005.eml` | email from Maren Bhandari: `Tracking export 2031-07 to 2032-02` | `2032-02-29` |
| `batch_01/0005.eml#tracking-2031-07-01.xlsx` | Tracking export 2031-07-01 to 2032-02-29 | `2032-02-29` |

## The deciding clause

MSA §3.2, `batch_01/0002.eml#MSA-TBX-US-EXP-E60.pdf` p. 3:

> `3.2 Pricing date. Each shipment is priced at the rates, surcharges and fees in force on its Pickup Date.`

## The email line

The document came as an attachment to `batch_01/0003.eml`, sent `2032-01-03` by Tarrowby Billing with the subject `Invoice TX-US-2032-5394`. The line that matters, in `batch_01/0003.eml#TX-US-2032-5394.pdf`:

> `1 TE56915687 2031-12-25 Air freight USE2-INE2 241 kg 6.69 1612.29`

## Step by step

1. The invoice line (`batch_01/0003.eml#TX-US-2032-5394.pdf` p. 1) bills `241` kg on AWB `TE56915687` at `6.69` per kg: freight `1612.29`. The fuel line for the same AWB bills `325.04`. Billed for this shipment: `1612.29 + 325.04 = 1937.33`.
2. The tracking export gives the pickup date (`batch_01/0005.eml#tracking-2031-07-01.xlsx` p. 1): `TE56915687 | PICKED_UP | 2031-12-25 | USE2 | -`. Clause 3.2 prices the shipment on `2031-12-25`.
3. Annex A (`batch_01/0002.eml#MSA-TBX-US-EXP-E60.pdf` p. 8) has the row `USE2-INE2 100-299.5 kg 6.01 6.16`. The lane and band are `USE2-INE2 band 100-299.5`; the column for the period that contains `2031-12-25` gives `6.01` per kg.
4. Correct freight: `6.01 × 241 = 1448.41`.
5. Annex C gives fuel of `20.16%` for the pickup month. Correct fuel: `20.16% × 1448.41 = 292.00`, rounded half up to the cent.
6. Correct total: `1448.41 + 292.00 = 1740.41`.
7. Overcharge: `1937.33 − 1740.41 = 196.92` USD, one finding for the invoice.

## Why the paired decoy is not a finding

Invoice `TX-US-2032-5397` (`batch_01/0004.eml#TX-US-2032-5397.pdf` p. 1) bills `1 TE68271803 2032-01-18 Air freight USE2-INE2 44 kg 7.73 340.12`. The rate looks high next to the heavier band (`USE2-INE2 45-99.5 kg 6.81 6.99`), so it is tempting to call the difference an overcharge.

It is correct. The chargeable weight is `44` kg, which sits inside band `0-44.5` (`USE2-INE2 0-44.5 kg 7.73 7.93`), and MSA §3.4 rates each shipment at the band that contains its chargeable weight. The billed rate equals the Annex A rate for that band, so there is no finding.

## The finding

This goes in `findings` of the report for `--as-of 2032-08-31`. The same item is in `expected_finding.json`, which is a complete report.json. It also lists the decoy as `verdict: no_finding`, the way a harness may report a key it checked and cleared; leaving the decoy out of a report is just as right.

```json
{
  "id": "overcharge:TX-US-2032-5394",
  "class": "overcharge",
  "variant": "OC-01",
  "invoice_id": "TX-US-2032-5394",
  "verdict": "finding",
  "amount_usd": "196.92",
  "amount_range": null,
  "deadline": null,
  "action": "draft:dispute",
  "confidence": 0.95,
  "evidence": [
    {
      "doc": "batch_01/0003.eml#TX-US-2032-5394.pdf",
      "page": 1,
      "quote": "1 TE56915687 2031-12-25 Air freight USE2-INE2 241 kg 6.69 1612.29"
    },
    {
      "doc": "batch_01/0002.eml#MSA-TBX-US-EXP-E60.pdf",
      "page": 8,
      "quote": "USE2-INE2 100-299.5 kg 6.01 6.16"
    },
    {
      "doc": "batch_01/0002.eml#MSA-TBX-US-EXP-E60.pdf",
      "page": 3,
      "quote": "3.2 Pricing date. Each shipment is priced at the rates, surcharges and fees in force on its Pickup Date."
    },
    {
      "doc": "batch_01/0005.eml#tracking-2031-07-01.xlsx",
      "page": 1,
      "quote": "TE56915687 | PICKED_UP | 2031-12-25 | USE2 | -"
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
python grader/validate.py --report data/examples/overcharge/expected_finding.json \
    --mailbox data/examples/overcharge/docs
```
