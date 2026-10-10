# What to send us

Send it within 48 hours of getting the brief. Everything goes in your copy of this repo.

## The list

1. **Your repo**, as a private GitHub repo or a zip. Tell us the commit hash: we grade that commit and nothing after
   it.
2. **SOLUTION.md**, your own write-up: how to run it, what works, what doesn't, and anything we should know before we
   run it. The template has a heading for each. Leave README.md, GLOSSARY.md and BRIEF.pdf as they are: they're the
   brief, and you keep them.
3. **`answer_sheet.json`** from `make sheet` (the exam mailbox), plus **`report_card.txt`** and
   **`report_card.json`** from `make grade` (the practice mailbox). Both come from your final commit. The answer sheet
   is pass or fail: its numbers have to match our key before we run your code on our set.
4. **`evals/`**: at least 10 cases of your own beyond our two samples, and **`evals/results.json`** from `make eval`
   with your harness's score on them. Tell us in SOLUTION.md which case caught a real bug.
5. **`DESIGN.md`**, short enough to print on one side of A4 (about 800 words). It covers your fact model, how you
   detect conflicts, how you compute confidence, what goes to a person and what `autonomous` mode is allowed to do,
   how feedback changes later behaviour, what happens when new documents arrive, and your cost per 1,000 documents.
   The template has a heading for each.
6. **`AI_USE.md`**: the AI tools you used, what you used them for, and the prompt log.

## How to send it

Reply to the email that sent you the brief. Either invite the GitHub account named in that email to your private repo
(read access is enough), or attach a zip of the repo with its `.git` folder. Put the commit hash in the email.

Don't make the repo public. Don't include your API key anywhere in it.

## The prompt log

We want the real log, trimmed only for secrets. Paste it into `AI_USE.md`, or put the exported files in `ai_log/` and
link them from there. A chat export, your tool's session files or a plain copy and paste all work. If you wrote some
parts without AI, say which. We read the log to see how you split the work between you and the tools. A tidy log
earns nothing extra, and a missing one costs you.

## What `make validate` checks

Run it before you send. It prints one line per check, and exits 0 only when all of them pass:

- the harness answers `ingest`, `report` and `feedback` with the arguments the grader passes;
- every section of `SOLUTION.md` is filled in;
- `report_card.json` exists and came from `make grade`;
- `answer_sheet.json` exists, came from `make sheet`, and is dated on the exam mailbox's last report date;
- `out/exam_report.json` (written by `make sheet`) matches the schema, and every quote in it is on the cited `page`;
- `evals/cases/` has at least 10 cases besides the samples, and `evals/results.json` exists;
- every section of `DESIGN.md` is filled in, and it's under about 1,000 words;
- `AI_USE.md` names your tools and has a prompt log, or links to one in `ai_log/`;
- nothing in the repo looks like an Anthropic API key.

A green `make validate` means we can grade your submission. How well it scores is up to the grader and to us.
