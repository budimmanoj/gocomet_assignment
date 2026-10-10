# Worked example: Waived but billed

A charge the carrier waived in writing, billed anyway. The skill: check who waived it and exactly what the waiver covers.

## The documents

Everything is in `docs/`, laid out like the scenario mailbox (one folder per batch, attachments inside the emails). The report date is `2034-02-28`.

| File | What it is | Received |
|---|---|---|
| `batch_01/0002.eml` | email from Jarrah Brennick: `Executed agreement TBX-US-EXP-E49` | `2033-05-11` |
| `batch_01/0002.eml#MSA-TBX-US-EXP-E49.pdf` | Master Services Agreement (Express Air) TBX-US-EXP-E49 | `2033-05-11` |
| `batch_01/0004.eml` | email from Elspeth Iyengar: `Re: Charges on your account` | `2033-06-18` |
| `batch_01/0005.eml` | email from Tarrowby Billing: `Invoice TX-US-2033-5337` | `2033-06-28` |
| `batch_01/0005.eml#TX-US-2033-5337.pdf` | Invoice TX-US-2033-5337 | `2033-06-28` |
| `batch_02/0002.eml` | email from Elspeth Iyengar: `Re: charges on your account` | `2033-11-26` |
| `batch_02/0005.eml` | email from Tarrowby Billing: `Invoice TX-US-2034-5561` | `2034-01-28` |
| `batch_02/0005.eml#TX-US-2034-5561.pdf` | Invoice TX-US-2034-5561 | `2034-01-28` |

## The deciding clause

MSA §11.1, `batch_01/0002.eml#MSA-TBX-US-EXP-E49.pdf` p. 4:

> `11.1 Waiver authority. A charge may be waived only in writing by a person listed in Schedule 1 for waivers. Schedule 1 is exhaustive.`

## The email line

Email `batch_01/0004.eml`, sent `2033-06-18` by Elspeth Iyengar, subject `Re: Charges on your account`. The line that matters:

> `Following our call, we waive the Delivery fee on AWB TE97049901.`

## Step by step

1. On `2033-06-18`, Elspeth Iyengar writes: `Following our call, we waive the Delivery fee on AWB TE97049901.`
2. Schedule 1 (`batch_01/0002.eml#MSA-TBX-US-EXP-E49.pdf` p. 11) lists the sender: `Elspeth Iyengar, Customer Finance Lead, TBX-US: waivers, payment_terms <elspeth.iyengar@tarrowby.example>`. Waivers are in the list, and clause 11.1 makes Schedule 1 the only source of waiver authority, so the waiver binds.
3. Invoice `TX-US-2033-5337`, dated `2033-06-28` and so after the waiver, still bills the charge (`batch_01/0005.eml#TX-US-2033-5337.pdf` p. 1): `4 TE97049901 2033-06-18 Delivery fee USE2-INN1 1 shpt 133.44 133.44`. Same charge, same AWB `TE97049901`.
4. Waived but billed: the whole line, `133.44` USD.

## Why the paired decoy is not a finding

Invoice `TX-US-2034-5561` bills the same kind of charge (`batch_02/0005.eml#TX-US-2034-5561.pdf` p. 1): `Delivery fee TE10597216 USE2-USC1 23 Jan 2034 133.44 1 shpt 133.44`. A waiver from the same person is in the mailbox (`batch_02/0002.eml`): `Thanks for flagging this. We waive the Delivery fee on AWB TE33628218 in full.`

That waiver names AWB `TE33628218`; the billed line is AWB `TE10597216`. MSA §11.2 limits a waiver to the charges and shipments it names, so this charge is owed and there is no finding.

## The finding

This goes in `findings` of the report for `--as-of 2034-02-28`. The same item is in `expected_finding.json`, which is a complete report.json. It also lists the decoy as `verdict: no_finding`, the way a harness may report a key it checked and cleared; leaving the decoy out of a report is just as right.

```json
{
  "id": "waived_but_billed:TX-US-2033-5337",
  "class": "waived_but_billed",
  "variant": "WB-01",
  "invoice_id": "TX-US-2033-5337",
  "verdict": "finding",
  "amount_usd": "133.44",
  "amount_range": null,
  "deadline": null,
  "action": "draft:dispute",
  "confidence": 0.95,
  "evidence": [
    {
      "doc": "batch_01/0004.eml",
      "page": 1,
      "quote": "Following our call, we waive the Delivery fee on AWB TE97049901."
    },
    {
      "doc": "batch_01/0002.eml#MSA-TBX-US-EXP-E49.pdf",
      "page": 11,
      "quote": "Elspeth Iyengar, Customer Finance Lead, TBX-US: waivers, payment_terms <elspeth.iyengar@tarrowby.example>"
    },
    {
      "doc": "batch_01/0005.eml#TX-US-2033-5337.pdf",
      "page": 1,
      "quote": "4 TE97049901 2033-06-18 Delivery fee USE2-INN1 1 shpt 133.44 133.44"
    },
    {
      "doc": "batch_01/0002.eml#MSA-TBX-US-EXP-E49.pdf",
      "page": 4,
      "quote": "11.1 Waiver authority. A charge may be waived only in writing by a person listed in Schedule 1 for waivers. Schedule 1 is exhaustive."
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
python grader/validate.py --report data/examples/waived_but_billed/expected_finding.json \
    --mailbox data/examples/waived_but_billed/docs
```
