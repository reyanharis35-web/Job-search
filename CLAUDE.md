# Job search: operating rules for Claude

This repo is a job search for **finance roles in Germany**, kept as plain markdown files.
The files are the memory. If something isn't in a file, it doesn't exist next session.

## Before answering anything
1. Read `profile.md`. Everything you write has to fit its constraints (languages, visa, target roles, salary floor).
2. If the question names a company, read `companies/<company-slug>.md` and its row in `targets/germany-finance.csv`.
3. If it names a person, read `people/<person-slug>.md`.
4. If a file you needed doesn't exist or is empty, **say so**. Never treat a missing file as "nothing to know".
5. Tag claims: [Certain] = it's in a file (cite the file), [Likely] = inference, [Guessing] = no evidence.

## When the user pastes interview notes, a call summary or a recruiter message
Run the debrief flow without being asked:
1. Copy `debriefs/_TEMPLATE.md` to `debriefs/YYYY-MM-DD-<company-slug>.md` and fill it in.
2. Update `companies/<slug>.md` (create it from `_TEMPLATE.md` if it's missing). Append dated facts. Never delete
   an old fact; if a new one contradicts it, mark the old one `(stale YYYY-MM-DD)`.
3. Update or create `people/<slug>.md` for every person mentioned by name.
4. Add every promise either side made to `followups.md` with an owner and a due date.
5. Move the company's stage in `pipeline.md`.

## When drafting (outreach, cover letters, follow-up emails)
- Read `voice.md` first and write like the user, not like an AI.
- Pull specifics from the company file. A generic draft means you didn't read it.
- Every experience claim must come from `experience.md`. Never infer duties Reyan didn't list.
- German-language roles get German drafts unless the user says otherwise.

## Rules
- Newest fact wins; older facts are marked stale, never deleted.
- Don't invent recruiters, salaries, openings or deadlines. If you don't know, say what to check.
- Slugs are lowercase-hyphenated: `deutsche-bank`, `munich-re`.
- Dates are ISO: `2026-10-07`.

## Session start
Read `followups.md` and list anything overdue or due within 3 days before doing anything else.
When asked for new jobs, run `python3 scripts/fetch_leads.py` first and work from the auto block in `leads.md`; never present a lead from web search as live.
