# Job search: finance roles in Germany

A small, file-based job-search system for working with Claude Code. It borrows the useful patterns
from [kipi-system](https://github.com/assafkip/kipi-system) (plain markdown memory, newest fact wins,
debriefs that update the files, a follow-up ledger, a voice file) without its hooks, plugins and
scheduled jobs.

## Layout
| Path | What it holds |
|---|---|
| `CLAUDE.md` | Rules Claude follows in every session |
| `profile.md` | **Fill this in first.** Who you are, target roles, languages, visa status |
| `voice.md` | How you write, so drafts sound like you |
| `targets/germany-finance.csv` | Master list of target employers (173 employers), sortable on GitHub |
| `targets/shortlist.md` | Top 30 employers ranked against your profile |
| `targets/README.md` | How the list is organised, what it leaves out, and how to find the rest |
| `pipeline.md` | Every company you're actively working, by stage |
| `followups.md` | Every promise, with an owner and a due date |
| `companies/` | One file per company you're actually engaging with |
| `people/` | One file per recruiter, hiring manager or contact |
| `debriefs/` | One file per call or interview |

## Daily use
- **Start a session:** "What's due?" Claude reads `followups.md`.
- **After a call:** paste your notes. Claude writes the debrief and updates the company, people, follow-ups and pipeline files.
- **Before an interview:** "Prep me for Commerzbank." Claude reads the company file and debriefs.
- **Outreach:** "Draft a LinkedIn note to the FP&A lead at Siemens." Claude uses `voice.md` and the company file.
- **Prioritise:** "Filter the target list to English-friendly Frankfurt roles in risk." Then set `priority` in the CSV.

## Start here
1. Fill in `profile.md` (15 minutes). Until it's filled in, every recommendation is generic.
2. Fill in `voice.md` by pasting 3 to 5 messages you've actually written.
3. In `targets/germany-finance.csv`, mark 20 to 30 companies `priority=A`. Ignore the rest for now.
