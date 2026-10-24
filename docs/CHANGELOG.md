# Changelog

One entry per commit, oldest first. Format: see .kiro/steering/workflow.md.

### pre-event · docs: add Kiro spec, steering, subagent and planning docs
- What changed: added the spec in .kiro/specs/shifting-grounds/, the steering file, the data-cleaner subagent, and the decision log, changelog and writeup drafts in docs/.
- How to check it: open the files.
- Known issues: confirm the Haiku model ID in .kiro/agents/data-cleaner.json with `/model`.

### 10:39 · chore(setup): scaffold project structure
- What changed: created src/, data/raw/{survey,boem,revenue}/, data/processed/, models/ folders; added requirements.txt (14 packages), extended .gitignore (keeps .env, adds data/raw/ and Python caches), .env.example (deepseek-chat), and README.md with data download steps and credits.
- How to check it: `ls -la` shows the folders and files; `git check-ignore .env` confirms .env stays ignored while .env.example is tracked.
- Known issues: none.
