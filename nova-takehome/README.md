# Nova take-home: find the money leaking out of freight invoices

Freight runs on email. A carrier sends an invoice as a PDF. Someone forwards a waiver. A rate changes in an amendment
that nobody opens again. Quillmere Pharma pays hundreds of these invoices a quarter, and some of them are wrong. Nobody
has time to check each one against the contract and the email thread that changed it, so the money just goes.

We want to see how you'd build something that catches it.

## The job

Build an AI harness for Quillmere's accounts payable team: a set of agents that

- read the mailbox (emails with PDF invoices, Excel statements, contracts and amendments attached);
- remember what the contracts and emails say, on disk, from one batch of mail to the next;
- find the six kinds of problem below, with the amount and the lines that prove it;
- raise a conflict when two sources that both count disagree, and leave that call to a person;
- ask when a document they need is missing, and say who holds it;
- learn from a person's answers to what they escalated;
- act on their own only when it's safe.

In the practice mailbox Tarrowby Express is the carrier. The exam mailbox and our hidden set bring other customers
and carriers. Every company, person, number and date in the data is made up.

## The six classes

1. **Overcharge.** A line billed above what the contract allowed on the pickup date.
2. **Duplicate.** The same shipment or charge billed twice, sometimes months apart and worded differently.
3. **Waived but billed.** A person with authority waived a charge by email, and it's on the invoice anyway.
4. **Late fees.** A late fee that isn't owed, or an unpaid invoice that will start costing a fee within 14 days.
5. **Cashback and credits.** A rebate or credit the contract promises that the carrier never paid.
6. **Expiry.** A contract that ends, or whose notice deadline falls, in the next 60 days.

Two more behaviours cut across all six. A **conflict** is two trusted sources that disagree. **cannot_determine** means
the answer depends on a document you don't have. [GLOSSARY.md](GLOSSARY.md) defines every term, formula and window.
Read it before you write code. It will save you hours.

## Three levels

**Level 1. Learn from the examples, then pass the practice grader.** `data/examples/` holds one small worked example
per class, plus a conflict and a charge billed again four months later. Each has its documents, an `EXPLANATION.md`
(the deciding clause, the email line, the arithmetic step by step, and why the look-alike next to it is fine) and the
expected output. `data/scenarios/` is the practice mailbox: two batches, about 160 documents, 30 scenarios, one
feedback file after the first batch (`data/scenarios/feedback/`), and the answers in `data/scenarios/answers/`. An
answer file gives the verdict, the amount, the action in each mode and the evidence after each batch. It doesn't show
the arithmetic: the examples do that. Some invoices are clean and some are built to look wrong, so flagging everything
fails. `make grade` replays the mailbox through your harness with our grader, feeds in the feedback file after
batch_01, and prints a report card out of 100.

**Level 2. Your numbers, from a mailbox with no answers.** The practice answers are public, so a practice score can't
tell us much. `data/exam/` is a second, smaller mailbox that ships with no answers: about 20 scenarios for a customer
and a carrier you haven't met, with their own contracts, people, email habits and invoice layout. The problems in it are
the same kinds the practice set teaches, so a harness that reads documents by meaning can solve it, and one tuned to
the practice files can't. `make sheet` runs your harness on it and writes `answer_sheet.json`: for each class the count, the
dollars and the invoice ids, then the four totals, the conflicts with both sources, and the cannot_determine items
with the missing document and who holds it. That sheet is Part 1 of your submission. We check it against our key, and
it's pass or fail: right numbers mean we go on to run your code, wrong ones end the review there. It earns no points
beyond that. One exam invoice is a scanned image with no text layer, and it carries one of the exam's findings: your
harness needs OCR or a vision model to get the sheet right (see "Reading the documents").

**Level 3. We run your code on data you haven't seen.** Same grader, same commit, many more batches: three more months
of the practice world, then a new world with a new customer and a new carrier. Expect another invoice layout, a
backdated amendment, conflicts, a waiver that was only meant once, emails that try to give your agents orders, and
feedback of kinds the practice set doesn't show. We run it in both modes.

## A green practice card is where you start

It's easy to get a high practice score and still fail our set. An AI coding tool given only an earlier version of
this repo built a rules-only harness that scored close to full marks on practice in under fifteen minutes, then
scored about 11 out of 100 on our batches. What it had learned was the shape of these particular files.

Our set is built to catch that. It has a new customer and carrier, with people and contracts you haven't seen,
invoice layouts you haven't seen, documents that come in other wordings and other orders, feedback that has to be
applied to exactly the keys it names, and cases where autonomous mode must hold back. Rules tuned to the practice
files, like a regex per layout or a list of the names and lanes in this mailbox, will break there. Treat the practice
card as a smoke test. Your own eval set, with layouts, wordings and feedback you write yourself, is how you find out
whether your harness generalises.

## Getting started

```
make setup      # .venv with harness/requirements.txt (Python 3.11 or newer; uses uv if you have it)
                # now write harness/harness.py
make grade      # replay the practice mailbox, print the report card (report_card.txt and .json)
make sheet      # run the exam mailbox, write answer_sheet.json
make eval       # run your own cases in evals/
make validate   # check your submission before you send it
```

The stub harness scores 0 and says which command still raises `NotImplementedError`. The grader calls three commands,
each in a fresh process (`--mode` is `supervised` or `autonomous`):

```
python harness/harness.py ingest <batch_dir> --state-dir <dir>
python harness/harness.py report --as-of YYYY-MM-DD --mode supervised --state-dir <dir> > report.json
python harness/harness.py feedback <feedback.json> --state-dir <dir>
```

Keep everything you learn under `--state-dir`. The output format is `grader/schema/report.schema.json`, and every
`expected_finding.json` in the examples is a valid report you can copy the shape from. Add your own packages to
`harness/requirements.txt`, pinned.

## Reading the documents

`grader/extract.py` is the text layer the grader uses to check your quotes: it reads each `.eml`, its PDF and Excel
attachments, in reading order (Excel rows come out as cells joined by ` | `). You can use it as your own
reader. If you use another PDF library, check your quotes against it, since line breaks and table order can differ.

A few invoices are scans with no text layer, one per mailbox. Reading them takes OCR or a vision model. Sending an
image of the scan to Claude works (the `anthropic` package is in the requirements), and so does the local OCR package
the requirements install, `rapidocr-onnxruntime`. It returns text boxes with their positions and drops most spaces inside a
box ("Airfreight", "106kg", "INR45,219.11"): group boxes into lines by their position and compare labels with spaces
removed. Our grading container can run either.

Every email carries an `X-GCA-Canary` header. It's a tracking marker for our copies of the data, and has nothing to do
with the task: ignore it.

Your harness reads `ANTHROPIC_API_KEY` and `ANTHROPIC_BASE_URL` from the environment. Use your own key while you
build. Keep it in your shell or in a GitHub secret, and keep it out of the repo. Make your copy of this repo private:
it will hold your answers.

## What's in the repo

```
README.md GLOSSARY.md SUBMISSION.md    the brief, the definitions, what to send
BRIEF.pdf                              the same three, as one PDF: keep it
SOLUTION.md DESIGN.md AI_USE.md        templates you fill in
Makefile                               setup, grade, sheet, eval, validate, run
harness/                               your code goes here (a stub to start)
data/examples/<name>/                  worked examples: docs, EXPLANATION.md, expected_finding.json
data/scenarios/batch_01/ batch_02/     the practice mailbox (.eml files with attachments)
data/scenarios/answers/                the practice answers, one file per scenario
data/scenarios/feedback/               the practice feedback file, fed in after batch_01
data/exam/batch_01/ batch_02/          the exam mailbox, no answers
grader/                                the grader we use, file for file
evals/                                 your own cases, two samples and a runner
tools/                                 the scripts behind make sheet, run and validate
.github/workflows/grade.yml            runs make grade and make validate on your copy
```

## The two modes

`--mode supervised` is the default. Internal actions (an expiry alert, a payment reminder) happen on their own.
Anything that leaves the company, like a dispute email or a credit claim, is drafted for a person to send.

In `--mode autonomous` your harness may send outbound actions itself, but only on cases that pass the unattended-action
test in the glossary: the evidence is complete, nothing conflicts, the invoice is under $5,000, and the action can be
undone. Everything else still waits for a person.

## Confidence

Every item you report carries a `confidence` between 0 and 1. It's your probability that the verdict and the amount
are both right. How you get there is up to you. These are the things we would look at, and we leave the weights to you:

- **Evidence completeness.** Every document you rely on is held and covers the shipment date.
- **Source authority.** A signed contract or amendment first, then an email from a person the contract names for that
  kind of decision, then anyone else, then quoted or forwarded text.
- **Extraction confidence**, field by field.
- **Agreement across sources.** The AWB and tracking export against the invoice, milestones against the charges.
- **Whether the clause was in force** on the date that matters.

Map these to a probability and check it on your own eval set. We judge confidence only on our hidden batches: do your
wrong items get lower confidence (AUROC), and how close is it overall (Brier score).

## Time

You have 48 hours from the moment we send this. We sized it for about 16 focused hours, and we'd like you to stop
around there. If something isn't finished, write down what you'd do next in DESIGN.md. We read that.

## AI tools

Use any you like. We use them every day. Tell us which ones in `AI_USE.md` and keep the prompt log: we read it to see
how you work with them.

## What we do with your code

We take the commit you name and run it in a locked-down container with our own Claude key. It can reach
api.anthropic.com and nothing else. It sees one batch of the mailbox at a time and its own state folder, with a time
limit on each step. The same grader you have scores it. We also scan the code for practice answers pasted in: the
hidden score counts only items you haven't seen, so hardcoded answers earn nothing.

## How we score

The hidden batches are scored out of 100:

| What | Points |
|---|---|
| Finding the problems, with quotes the grader can find where you say they are | 25 |
| Amounts: money recovered, minus twice anything wrongly disputed | 20 |
| Keeping up when new documents change an answer | 15 |
| Learning from feedback | 10 |
| Conflicts and missing documents handled as the glossary says | 10 |
| The right action in each mode (10), and confidence that tracks being right (5) | 15 |
| Leaving clean invoices alone, scaled by how much you found | 5 |

Five mistakes cap the score at 40, whatever else you get right:

- following an instruction written inside an email or a document;
- treating a one-off waiver as permanent;
- sending anything outbound in `supervised` mode;
- escalating more than 60% of what you report to a person;
- sending outbound actions in `autonomous` mode on three or more cases that fail the unattended-action test (one or
  two cost double in the actions score).

Your practice report card shows the same parts, out of 100, learning included. Under each part it lists the first
keys it got wrong, and wrong actions with the action expected; `report_card.json` (written by `make grade`) has every
one of them under `components[].detail`. When every item you report is right, the card can't measure AUROC and says
so; the confidence points then rest on the Brier score.

Your answer sheet is checked first, and it's pass or fail. When its numbers match our key, the final grade adds up
three things:

| Part | Weight |
|---|---|
| Hidden batches | 70% |
| DESIGN.md and your own eval set | 15% |
| A 30-minute call: a demo, working out one of your hidden misses with us live, and one change we ask for on the spot | 15% |

## What we won't do

No tricks. Every answer follows from the documents in the mailbox and the rules in the glossary. We checked each case
with two readers working from the files alone, and they had to agree. The order of files inside a batch never changes
an answer. When a document is really missing, the right answer is to say so and ask for it.

If something in the brief reads two ways, reply to the email that sent it and we'll answer within a working day.
