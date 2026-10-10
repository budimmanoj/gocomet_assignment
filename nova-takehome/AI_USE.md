# AI use

## Tools

Claude Code (VS Code extension) running Claude Sonnet 5.5 and Claude Opus 5.5. I used it for everything:
- reading and summarising the brief, glossary, grader and data;
- writing the harness code, the eval-world generator and these documents;
- running the grader, exam sheet and evals, and debugging the results.

## How you worked with them

I had Claude read the whole pack first and write two reference notes: `PROJECT_NOTES.md` (what is asked, the rules, how it's graded, the gaps) and `ROADMAP.md` (a phased build plan). I reviewed both before any code was written.

I then told it to follow the roadmap, to build only what the brief asks, to use placeholder names for anything I have to supply (the API key goes in `.env.example`), and to keep a markdown record of what it built (`BUILD_NOTES.md`).

What was checked against the documents rather than trusted:
- every exam answer-sheet row, recomputed by hand from the invoices, contracts and tracking;
- all 8 worked examples, compared with their `expected_finding.json`;
- the practice card read line by line.

Where it went wrong and was corrected:
- an ISO-date regex that didn't match the `T` in timestamps (every report failed at first);
- a scripted edit that silently didn't apply (an assert caught it);
- an autonomous-mode rule of its own (holding scanned invoices) that the glossary doesn't ask for, which was removed;
- the duplicate example's action, found by the example check and turned into an eval case.

## Written without AI

None of the code. The decisions (scope, what to check by hand, what to drop) were mine, made while reviewing.

## Prompt log

<!-- TODO before submitting: export this Claude Code session (the .jsonl files under
     %USERPROFILE%\.claude\projects\d--projects-gocomet2-nova-takehome\) into ai_log/, or paste the conversation here.
     Remove secrets only. make validate wants either this section filled or files in ai_log/. -->
