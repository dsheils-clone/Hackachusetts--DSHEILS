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
### 10:43 · data(prepare): map survey columns and species codes
- What changed: inspected SVSTA/SVCAT headers and the species list; wrote data/processed/column_map.md mapping real columns to design fields and resolving the 6 target-species SVSPP codes (all match design: squid 503, summer flounder 103, black sea bass 141, scup 143, silver hake 072, cod 073). Flagged season-via-CRUISES, the duplicate "SCUP" name (143 vs 642), and the squid egg-mop code (520) for the human.
- How to check it: open data/processed/column_map.md; `grep -i "longfin squid\|scup" data/raw/survey/SVDBS_SupportTables/SVDBS_SVSPECIES_LIST.csv` shows the codes.
- Known issues: none; flags 1-4 await human confirmation at the 2.2 checkpoint.
