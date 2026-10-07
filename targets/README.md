# Target list: finance employers in Germany

`germany-finance.csv` lists 173 employers. It is **not "all companies"**. Germany has over a
thousand licensed credit institutions alone (mostly Sparkassen and Volksbanken), plus thousands of
Mittelstand firms with finance departments. A list of all of them would be useless to you. This one
covers the employers that hire the most finance people, across every segment, so you can pick from it.

## Columns
| Column | Meaning |
|---|---|
| `segment` | Kind of employer (universal bank, Landesbank, asset management, insurance, fintech, Big 4, DAX corporate...) |
| `german_finance_locations` | Where their finance jobs actually sit in Germany |
| `size` | large / mid / small (headcount in Germany, roughly) |
| `work_language` | `english`: you can work in English · `mixed`: some teams English, many need German · `german`: expect C1 German |
| `typical_finance_roles` | Where they hire most finance people |
| `notes` | Things to check before you apply |
| `priority` | **You fill this in:** A (apply now), B (later), C (skip) |
| `status` | Mirror of `pipeline.md` once you engage |

## The language reality
Of the 173 employers, 55 are tagged `english` and most of those are in Frankfurt (international
banks, EU bodies, Deutsche Börse) or Berlin/Munich (fintechs, PE/VC, a few DAX firms like SAP,
Zalando, adidas, Infineon). If your German is below B2, those 55 plus the English-speaking teams
inside the `mixed` ones are your real market. Set `priority` accordingly.

## How the list was built and what to verify
- It was compiled from Claude's general knowledge, not from live job boards. Company names,
  headquarters and segments are reliable. Ownership, restructurings and language tags can change, so
  check the `notes` column and each careers page before you apply.
- Websites are main domains. Find the careers page from there.

## Finding the long tail (when you need more)
- **Job boards:** eFinancialCareers (banking/markets), StepStone, LinkedIn, Indeed, Xing. Filter for "English" if relevant.
- **Bank register:** BaFin's company database lists every licensed institution in Germany.
- **Sparkassen / Volksbanken:** each regional bank hires on its own. Search `<city> Sparkasse Karriere`.
- **Mittelstand finance (controlling, accounting):** StepStone searches for *Controller*, *Finanzbuchhalter*, *Treasury Manager* by city.
- **EU institutions:** EPSO and each agency's own vacancies page (ECB, EIOPA, AMLA).

Ask Claude: "Add the 20 largest asset managers in Frankfurt to the CSV" or "Find English-speaking
FP&A employers in Munich". It will append rows in the same format.
