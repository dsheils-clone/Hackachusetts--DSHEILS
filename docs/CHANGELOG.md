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
### 10:48 · data(prepare): build tows table
- What changed: added src/prepare_data.py with reusable loaders (load_survey, load_cruises) and build_tows(); built data/processed/tows.csv — fall tows (SEASON='FALL' via CRUISES join on CRUISE6) with EST_YEAR >= 2009, columns ID, EST_YEAR, DECDEG_BEGLAT, DECDEG_BEGLON, AVGDEPTH, BOTTEMP. Every filter reports row counts and per-field drops. Survey CSVs read as latin-1 (non-UTF-8 comment fields).
- How to check it: `python3 src/prepare_data.py` prints 22432 all -> 22432 fall -> 5667 year>=2009 -> 4878 after dropping missing (dropped by field: BOTTEMP 787, AVGDEPTH 13, lat 2, lon 2), then tows per year. Output tows.csv has 4878 unique-ID rows, no NaN in required fields.
- Known issues: the CRUISES table in this download is fall-only, so the SEASON filter removes 0 rows here (kept as a correct guard). 2017 is partial (117 tows); 2020 is absent (survey gap, as design.md anticipated).
### 10:51 · data(prepare): build presence table
- What changed: added build_presence()/save_presence() to src/prepare_data.py and wired them into main() so the script now regenerates both tows.csv and presence.csv. Built data/processed/presence.csv in long form (one row per tow+species): columns ID, species, SVSPP, present. Every tow is zero-filled across all 6 target species; present=1 when an SVCAT row exists for that ID with the matching SVSPP (collapsed across CATCHSEX). Longfin squid counts SVSPP 503 only and excludes 520 (egg mops, D-013).
- How to check it: `python3 src/prepare_data.py` prints per-species presence counts and rates and asserts the invariant (29268 rows = 4878 tows x 6 species, every tow a row per species). presence.csv has 29268 data rows; rates: longfin squid 76.2%, silver hake 69.6%, summer flounder 27.1%, scup 25.3%, black sea bass 22.2%, Atlantic cod 12.4%. Cross-check: raw SVCAT has 3716 kept tows with 503 and 0 with 520.
- Known issues: none. Cod's low rate (12.4%) is the intended cold-water contrast.

### 11:03 · model(train): train habitat models for 6 species
- What changed: Added src/train.py — one HistGradientBoostingClassifier per species on BOTTEMP + AVGDEPTH only (lat/lon/year asserted out), trained on EST_YEAR 2009–2018 and tested on 2019 onward. Wrote models/<species>.joblib and models/metrics.json (test AUC + train/test positive rate per species).
- How to check it: `python3 src/train.py` then `cat models/metrics.json`; test AUCs range 0.78 (atlantic_cod) to 0.93 (longfin_squid), all well above 0.5.
- Known issues: atlantic_cod has the weakest class balance (train pos 14.4%, test pos 8.3%) and the lowest AUC (0.784), as expected for the cold-water contrast species.
