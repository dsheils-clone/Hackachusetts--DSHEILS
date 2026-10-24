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
