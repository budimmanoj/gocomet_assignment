# Worked example: Conflict: two authorised sources disagree

Two sources with authority give different rates for the same shipment, and the contract refuses to rank them. The skill: raise it with both sources and the money at stake, and leave it out of the totals.

## The documents

Everything is in `docs/`, laid out like the scenario mailbox (one folder per batch, attachments inside the emails). The report date is `2032-11-30`.

| File | What it is | Received |
|---|---|---|
| `batch_01/0002.eml` | email from Farid Underhill: `Executed agreement TBX-US-EXP-E90` | `2032-02-07` |
| `batch_01/0002.eml#MSA-TBX-US-EXP-E90.pdf` | Master Services Agreement (Express Air) TBX-US-EXP-E90 | `2032-02-07` |
| `batch_01/0003.eml` | email from Farid Underhill: `Signed amendment 1 to TBX-US-EXP-E90` | `2032-03-16` |
| `batch_01/0003.eml#TBX-US-EXP-E90-AMD-1.pdf` | Amendment No. 1 to TBX-US-EXP-E90 | `2032-03-16` |
| `batch_02/0001.eml` | email from Isolde Zeller: `Rate notice USW1-USC3` | `2032-06-02` |
| `batch_02/0002.eml` | email from Tarrowby Billing: `Invoice TX-US-2032-5166` | `2032-06-26` |
| `batch_02/0002.eml#TX-US-2032-5166.pdf` | Invoice TX-US-2032-5166 | `2032-06-26` |

## The deciding clause

MSA §13.3, `batch_01/0002.eml#MSA-TBX-US-EXP-E90.pdf` p. 4:

> `13.3 Unranked instruments. Where a rate notice under clause 3.5 and an amendment state different rates for the same lane and period, the parties shall resolve the difference jointly; neither prevails automatically.`

## The email line

Email `batch_02/0001.eml`, sent `2032-06-02` by Isolde Zeller, subject `Rate notice USW1-USC3`. The line that matters:

> `USW1-USC3 100-299.5 kg: 3.03 USD`

## Step by step

1. Invoice `TX-US-2032-5166` (`batch_02/0002.eml#TX-US-2032-5166.pdf` p. 1) bills AWB `TE92942629`, picked up `2032-06-17`: `113` kg at `3.03`, freight `342.39`, fuel `79.23`. Billed: `342.39 + 79.23 = 421.62`.
2. The signed amendment (`batch_01/0003.eml#TBX-US-EXP-E90-AMD-1.pdf` p. 1) sets the lane rate: `USW1-USC3 100-299.5 kg 2.88 USD`.
3. The rate notice from Isolde Zeller, the Schedule 1 rates contact (`batch_02/0001.eml` p. 1), sets a different rate for the same lane and dates: `USW1-USC3 100-299.5 kg: 3.03 USD`.
4. Both are in force on the pickup date, both come from people with authority, and clause 13.3 (`batch_01/0002.eml#MSA-TBX-US-EXP-E90.pdf` p. 4) says neither prevails.
5. Correct under the amendment: `2.88 × 113 = 325.44`, fuel `23.14% × 325.44 = 75.31`, total `325.44 + 75.31 = 400.75`.
6. Correct under the notice: `3.03 × 113 = 342.39`, fuel `23.14% × 342.39 = 79.23`, total `342.39 + 79.23 = 421.62`.
7. Range: low `max(0, 421.62 − 421.62) = 0.00`, high `421.62 − 400.75 = 20.87`.
8. Report `verdict: conflict` with the range `[0.00, 20.87]`, cite both sources and escalate. It stays out of the totals; picking either rate is marked wrong.

## Why the paired decoy is not a finding

Change one detail: the rate notice comes from someone who is missing from Schedule 1 for rates. Such a notice carries no authority, the signed amendment alone governs, and the answer is decided: `421.62 − 400.75 = 20.87` USD, a plain overcharge. The conflict exists only because both sources have authority and the contract refuses to rank them.

## The finding

This goes in `findings` of the report for `--as-of 2032-11-30`. The same item is in `expected_finding.json`, which is a complete report.json.

```json
{
  "id": "overcharge:TX-US-2032-5166",
  "class": "overcharge",
  "variant": "XC-01",
  "invoice_id": "TX-US-2032-5166",
  "verdict": "conflict",
  "amount_usd": null,
  "amount_range": [
    "0.00",
    "20.87"
  ],
  "deadline": null,
  "action": "escalate",
  "confidence": 0.9,
  "evidence": [
    {
      "doc": "batch_01/0003.eml#TBX-US-EXP-E90-AMD-1.pdf",
      "page": 1,
      "quote": "USW1-USC3 100-299.5 kg 2.88 USD"
    },
    {
      "doc": "batch_02/0001.eml",
      "page": 1,
      "quote": "USW1-USC3 100-299.5 kg: 3.03 USD"
    },
    {
      "doc": "batch_01/0002.eml#MSA-TBX-US-EXP-E90.pdf",
      "page": 4,
      "quote": "13.3 Unranked instruments. Where a rate notice under clause 3.5 and an amendment state different rates for the same lane and period, the parties shall resolve the difference jointly; neither prevails automatically."
    }
  ],
  "missing_doc": null,
  "supersedes": [],
  "learned_at": null
}
```

The action is `escalate` in both modes.

Check it against the documents:

```
python grader/validate.py --report data/examples/conflict/expected_finding.json \
    --mailbox data/examples/conflict/docs
```
