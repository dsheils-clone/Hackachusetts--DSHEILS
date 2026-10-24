---
inclusion: always
---

# Workflow rules

## After every completed task or fix
1. Run the app (or tests, if they exist) and confirm nothing broke. Fix breakages before moving on.
2. If a decision was made during the change, by you or by the human in chat, append an entry to docs/DECISIONS.md. Skip this step if no decision was made.
3. Append a short entry to docs/CHANGELOG.md.
4. Mark the task done in tasks.md.
5. Commit everything in one commit with the message `type(scope): summary`. Types: feat, fix, data, model, docs, chore.
6. Push.

## Subagents and APIs
- Delegate data-cleaning work (task 2 and task 6.2) to the `data-cleaner` subagent, which runs on Claude Haiku.
- Review the subagent's output before building on it: row counts before and after each filter, tows per year, presence rate per species.
- Read `DEEPSEEK_API_KEY` and `DEEPSEEK_MODEL` from .env for the briefs. Never hard-code keys.

## Decision log entry (docs/DECISIONS.md)
Number decisions in order, continuing from the last entry. Get the time from `date`.

### D-012 · 14:32 · Raise the Uncertain AUC threshold to 0.75
- Decided by: human or agent
- Context: one line on the situation
- Decision: what was chosen
- Why: the reason, and the alternatives rejected
- Affects: files or components touched

## Changelog entry (docs/CHANGELOG.md)
### 14:40 · model(train): train habitat models for 6 species
- What changed: one or two lines
- How to check it: a command or click path
- Known issues: or "none"

## Writeup (docs/WRITEUP.md)
Update it only when the human asks, using DECISIONS.md and CHANGELOG.md. Keep these headings, which match Devpost: Inspiration, What it does, How we built it, Challenges we ran into, Accomplishments, What we learned, What's next.

## Guardrails
- Ask the human before changing the target species, model features, year range, signal thresholds or suggestion text; before adding a dependency; before deleting files; and before force-pushing.
- Never use latitude, longitude or year as model features.
- Only pass computed numbers and the fixed suggestion text to the LLM. Never let it add reasons, facts or advice of its own.
- Never describe results as harm to fish, or as build or don't-build verdicts. The tool shows change in fishing overlap.
- Never commit secrets. Keep keys in .env and make sure .env is in .gitignore.
- Keep data/raw/ in .gitignore. Document the download steps in README.md instead of committing data files.
- Keep main demo-ready. If a change breaks the demo, fix or revert it before starting anything new.
- Credit the data in README.md and the app footer: NOAA Fisheries Northeast Fisheries Science Center bottom trawl survey; Bureau of Ocean Energy Management lease areas; NOAA Fisheries Greater Atlantic Regional Fisheries Office fishing revenue.
