---
inclusion: always
---

# Workflow rules

## After every completed task, addition or fix
1. Run the app (or tests, if they exist) and confirm nothing broke. Fix breakages before moving on.
2. Append an entry to docs/DECISIONS.md for every decision made during the change, including decisions the human made in chat.
3. Append a short entry to docs/CHANGELOG.md.
4. If a feature is finished, update the matching section of docs/WRITEUP.md.
5. Mark the task done in tasks.md.
6. Commit everything in one commit with the message `type(scope): summary`. Types: feat, fix, data, model, docs, chore.
7. Push.

## Decision log entry (docs/DECISIONS.md)
Number decisions in order. Get the time from `date`.

### D-007 · 14:32 · Drop interconnection agreement status from features
- Decided by: human or agent
- Context: one line on the situation
- Decision: what was chosen
- Why: the reason, and the alternatives rejected
- Affects: files or components touched

## Changelog entry (docs/CHANGELOG.md)
### 14:40 · feat(model): train baseline classifier
- What changed: one or two lines
- How to check it: a command or click path
- Known issues: or "none"

## Writeup (docs/WRITEUP.md)
Keep these headings, which match Devpost: Inspiration, What it does, How we built it, Challenges we ran into, Accomplishments, What we learned, What's next.

## Guardrails
- Ask the human before changing the model's label or features, adding a dependency, deleting files, or force-pushing.
- Never commit secrets. Keep keys in .env and make sure .env is in .gitignore.
- Keep data/raw/ in .gitignore. Document the Queued Up download step in README.md instead of committing the Excel file.
- Keep main demo-ready. If a change breaks the demo, fix or revert it before starting anything new.
- Only pass SHAP factors or quoted bylaw text to the LLM. Never let it add reasons of its own.
- Credit the data in README.md and the app footer: "Data: Lawrence Berkeley National Laboratory and GridTracker, Queued Up 2026 Edition (CC BY 4.0)."