# Your eval set

Put your own golden cases in `cases/`, one YAML file each. We ship two samples, built from the worked examples, so
you can see the shape. Add at least ten of your own that go beyond ours: other layouts, other wordings, edge dates,
other ways the sources can disagree, feedback that should change an answer and feedback that shouldn't.

Each case names a mailbox folder, the date to report on, the mode, and what the report must say about one finding
key:

```yaml
name: short description
mailbox: data/examples/overcharge/docs      # a folder holding batch_01/, batch_02/ ...
as_of: "YYYY-MM-DD"
mode: supervised                            # or autonomous
feedback: {batch_01: evals/feedback/my_case.json}   # optional: fed in after that batch
expect:
  key: {invoice_id: "...", class: overcharge}
  verdict: finding                           # finding | no_finding | conflict | cannot_determine
  amount_usd: "0.00"                         # or amount_range for a conflict
  action: draft:dispute
  missing_doc: "Annex A rev 2"               # optional, for cannot_determine
why: one line on what decides it
```

Build your own mailboxes under `evals/` (copy an example's `docs/` and edit it, or write new `.eml` files). Then run:

```
make eval                 # every case; writes evals/results.json
make eval K=conflict      # only cases whose file name contains "conflict"
```

`evals/run_evals.py` starts each case from an empty state folder, ingests every batch in order, runs one report and
compares the item for your key using the grader's own matching (amounts within $0.01). It prints PASS or FAIL per
case with what differs. Put the score in your submission, and show that the set catches a regression: break
something on purpose and watch a case fail.

The runner prints how many cases are yours: every file in `cases/` whose name doesn't start with `sample_` counts,
and `make validate` wants at least ten. Cases that only point at `data/scenarios` or `data/examples` re-test what we
gave you, so build some mailboxes of your own.
