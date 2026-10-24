# Decision log

Decisions made before and during the build, oldest first. New entries follow the format in .kiro/steering/workflow.md and continue numbering from the last entry.

### D-001 · pre-event · Pivot from Queue Odds to fisheries and offshore wind
- Decided by: human
- Context: The climate track includes the sustainable blue economy, and fisheries plus offshore wind is a live Massachusetts issue.
- Decision: Drop Queue Odds (interconnection-queue predictor) and build a fisheries and offshore wind tool. Keep Queue Odds as a backup.
- Why: Stronger local angle and a clear climate link. Rejected: an economic exposure calculator without ML, and a "where to build" heat map framed as harm to fish.
- Affects: whole project

### D-002 · pre-event · Forward-looking species habitat model as the core
- Decided by: human
- Context: Wind farms run for decades while fish distributions shift; siting relies on past catch data.
- Decision: Model where key species can live under warming and show how their overlap with wind lease areas changes.
- Why: Puts ML at the center and fills a gap: prior work (Friedland et al. 2021) looked back rather than projecting forward.
- Affects: whole project

### D-003 · pre-event · Data sources
- Decided by: human
- Context: Need species occurrence with temperature, lease boundaries and revenue context.
- Decision: NOAA NEFSC fall bottom trawl survey; BOEM lease area shapefile; NOAA GARFO wind area landings and value data.
- Why: All free and public, and the survey records bottom temperature for every tow. Rejected: Global Fishing Watch vessel tracking (not needed for the core).
- Affects: src/prepare_data.py, src/overlap.py, README.md, app footer

### D-004 · pre-event · Bottom temperature and depth as the only features
- Decided by: human
- Context: The model must be re-predicted under warming.
- Decision: Use bottom temperature and depth; exclude latitude, longitude and year.
- Why: Location features would let the model memorize places instead of learning temperature response. Friedland et al. (2021) found bottom temperature and depth the strongest predictors.
- Affects: src/train.py

### D-005 · pre-event · Use survey data from 2009 onward
- Decided by: human
- Context: The survey changed vessels in 2009, and the released data isn't adjusted for gear or vessel changes.
- Decision: Train and test on 2009 onward only.
- Why: Keeps the data consistent at the cost of a shorter time span.
- Affects: src/prepare_data.py

### D-006 · pre-event · Planning signals, not verdicts
- Decided by: human
- Context: The model predicts habitat, not harm from turbines, and offshore wind is politically contested.
- Decision: Label each lease and species as Rising, Falling, Stable or Uncertain overlap, each with fixed suggestion text. Never say "don't build."
- Why: Matches what the model can support and keeps the tool neutral.
- Affects: src/overlap.py, app.py, src/explain.py

### D-007 · pre-event · Uniform warming scenarios of +1°C and +2°C
- Decided by: human
- Context: Need simple, explainable futures for a one-day build.
- Decision: Add the same warming to every grid cell.
- Why: Simple and transparent. Rejected: downscaled climate model projections (too much work for a day). Stated as a limit in the app.
- Affects: src/scenarios.py, app.py

### D-008 · pre-event · Haiku subagents for data cleaning
- Decided by: human
- Context: Data cleaning is repetitive and well specified.
- Decision: Delegate cleaning to a `data-cleaner` Kiro subagent running Claude Haiku; the main agent reviews its output.
- Why: Faster and cheaper for routine work, with a review step to catch errors.
- Affects: .kiro/agents/data-cleaner.json, tasks 2 and 6.2

### D-009 · pre-event · DeepSeek for the briefs
- Decided by: human
- Context: The app needs short plain-English briefs.
- Decision: Use the DeepSeek API, with the key in .env and the model name configurable (default deepseek-flash).
- Why: The human has a DeepSeek key.
- Affects: src/explain.py, .env.example

### D-010 · pre-event · Solo build as one Streamlit app with a lean workflow
- Decided by: human
- Context: Working alone for one day.
- Decision: One Streamlit app; a steering file that logs decisions only when made, writes a changelog entry and commits after each task, with no hooks.
- Why: Fewer moving parts and less agent overhead.
- Affects: app.py, .kiro/steering/workflow.md

### D-011 · pre-event · Details chosen while writing the spec
- Decided by: agent (Claude, while writing the spec)
- Context: The spec needed concrete starting values.
- Decision: Target species: longfin squid, summer flounder, black sea bass, scup, silver hake, Atlantic cod. Train 2009–2018, test 2019 onward; hindcast trains on 2009–2015. Grid 0.2° with at least 2 tows from 2016 onward. Signals: Stable within ±10%; Uncertain if AUC is below 0.70 or fewer than 20 tows from 2016 onward lie within 25 km of the lease. Skip species with fewer than 50 presences. Revenue is the 5-year average.
- Why: Reasonable defaults for a first pass; all are constants that can be changed and logged.
- Affects: design.md, src/train.py, src/hindcast.py, src/scenarios.py, src/overlap.py

### D-012 · 10:39 · Use deepseek-chat instead of deepseek-flash
- Decided by: human
- Context: The spec and design default `DEEPSEEK_MODEL` to `deepseek-flash`, but the live .env already uses `deepseek-chat`.
- Decision: Set `DEEPSEEK_MODEL=deepseek-chat` in .env.example and keep the real .env as-is.
- Why: `deepseek-chat` is the cheaper model the human selected and matches the working key. Rejected: `deepseek-flash` (the spec default), to avoid a model-name mismatch at runtime.
- Affects: .env.example, .env, src/explain.py (default model name)
### D-013 · 10:43 · Derive season from the CRUISES join, and pin squid/scup SVSPP codes
- Decided by: agent (data-cleaner, task 2.1)
- Context: SVSTA has no SEASON column and the file spans all years/seasons back to 1963; the species list has a duplicate "SCUP" common name and a separate "egg mops" code for longfin squid.
- Decision: Get FALL from CRUISES.SEASON joined on CRUISE6 (so task 2.3's "fall from 2009 onward" filters on season, not year alone). Use SVSPP 143 for scup (not 642, longspine porgy) and SVSPP 503 for longfin squid (excluding 520, egg mops).
- Why: SVSTA alone can't identify fall tows, and a name-only lookup is ambiguous for scup and would double-count squid egg masses. Rejected: filtering by year only; matching species by common name. These flags are recorded in data/processed/column_map.md for the human to confirm at the 2.2 checkpoint.
- Affects: data/processed/column_map.md, src/prepare_data.py (tasks 2.3/2.4)

### D-014 · 11:03 · Split habitat models by year window, tolerating the 2020 gap and partial 2017
- Decided by: agent (task 3)
- Context: Training splits on EST_YEAR (train 2009–2018, test 2019 onward), but the survey has no 2020 tows (COVID gap) and 2017 is partial (117 vs ~350 tows/year).
- Decision: Filter purely by year window and use whatever years exist in each window: train picks up 2009–2018 (including partial 2017), test picks up 2019, 2021–2024 (no 2020). No imputation or reweighting for the missing/partial years.
- Why: The windows are defined by year, so a missing or thin year just contributes fewer rows; it isn't an error. Train n=3232 and test n=1646 per species are ample. Rejected: dropping 2017 (loses real data) or synthesising 2020 (would fabricate observations).
- Affects: src/train.py
