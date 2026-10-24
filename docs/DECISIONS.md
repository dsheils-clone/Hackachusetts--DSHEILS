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

### D-015 · 11:59 · Active leases = the BOEM Offshore_Wind_Leases_outlines layer
- Decided by: agent (task 6.1)
- Context: design.md says "Load active lease areas from the BOEM shapefile. Use leases, not planning areas." The download has two lease layers: Offshore_Wind_Leases (4891 rows, one per sub-block, nationwide incl. CA/Pacific) and Offshore_Wind_Leases_outlines (51 rows, one dissolved polygon per issued lease with LEASE_NUMB, COMPANY, PROJECT_NA, ACRES). Neither has an explicit active/status field; the issued-lease dataset IS the set of active leases. A separate BOEM_MHKLeasesandPlanningAreas file holds planning areas and is not used.
- Decision: Use the outlines layer as the active leases. Dissolve its polygons by LEASE_NUMB (a few leases — OCS-A 0498, 0501, 0497, 0517 — appear as several rows for main area plus export-cable/sub-block pieces) to get 45 unique leases, one geometry each. A lease that overlaps no grid cell is labelled Uncertain (design.md Error Handling); 9 leases (Gulf of Maine, Carolinas, Pacific) fall outside the survey footprint and come out Uncertain for that reason.
- Why: The outlines layer gives one clean polygon and a project name per lease, matches design.md's app requirement for "lease outlines", and avoids the sub-block layer's nationwide 4891-row sprawl. Rejected: the full Offshore_Wind_Leases sub-block layer (would need its own dissolve and carries no project name), and the MHK planning-areas file (explicitly excluded by design.md).
- Affects: src/overlap.py, app.py (task 7 lease outlines)

### D-016 · 11:59 · Equal-area CRS (EPSG:5070) for area weights and the 25 km coverage test
- Decided by: agent (task 6.1)
- Context: design.md requires the lease suitability to be "weighted by overlap area" and the Uncertain rule to count tows "within 25 km". Both the BOEM shapefile and the grid are EPSG:4326 (lon/lat degrees), where a degree is not a constant area and cannot measure kilometres directly.
- Decision: Reproject lease polygons and the 0.2° grid-cell squares to EPSG:5070 (NAD83 / CONUS Albers Equal Area, metres) before intersecting; do all intersection-area weighting and the point-to-polygon 25 km distance test in that metric CRS.
- Why: CONUS Albers is the standard US equal-area projection and gives true areas and metric distances over the Atlantic shelf. Rejected: computing areas/distances in raw degrees (area varies with latitude; 25 km would be mis-measured) and a global projection like Web Mercator (badly area-distorted at these latitudes).
- Affects: src/overlap.py

### D-017 · 11:59 · Run the offline pipeline via the `shifting-grounds` conda env
- Decided by: human + agent (task 6.1)
- Context: geopandas 1.2 and its geospatial stack (shapely, pyproj, fiona) plus the ML/app libraries are installed in a dedicated conda env named `shifting-grounds`, not in the base interpreter.
- Decision: Run all pipeline modules with `conda run -n shifting-grounds python src/<module>.py` (e.g. `conda run -n shifting-grounds python src/overlap.py`). Earlier changelog entries say `python3 src/...`; the conda-env form is the current, correct invocation.
- Why: The base interpreter lacks geopandas/shapely, so plain `python3` would fail on src/overlap.py. Keeps the geospatial deps isolated. Affects how every script in the pipeline is launched.
- Affects: src/overlap.py and all other src/*.py scripts; README.md (run steps, when next updated)

### D-018 · 12:08 · NOAA revenue name-map method: number-based area match, exact species names, unmatched reported not dropped (DRAFT)
- Decided by: agent (data-cleaner, task 6.2)
- Context: The NOAA GARFO revenue export names species and lease areas differently from the survey species keys and the BOEM lease_ids. design.md "### Revenue join" asks for a data/processed/name_map.csv confirmed by the human. NOAA writes areas two ways (`OCS-A-0562`, `OCS_A_0482`) while BOEM uses `OCS-A 0562`; the species list has close neighbours (SQUID LONGFIN vs ILLEX; five HAKE,* variants; one plain COD).
- Decision: (1) Match areas on the parsed OCS lease NUMBER (`normalize_area_code()` re-emits the BOEM spelling), not on punctuation — 33/37 areas match a BOEM lease. (2) Map each of the six target species to its single exact NOAA name: SQUID (LONGFIN)→longfin_squid, FLOUNDER,SUMMER→summer_flounder, SEA BASS,BLACK→black_sea_bass, SCUP→scup, HAKE,SILVER→silver_hake, COD→atlantic_cod. (3) Keep the mapping as a DRAFT (status=DRAFT on every row) pending human confirmation, and never drop unmatched rows silently — the 132 non-target species and the 4 areas with no BOEM lease (OCS-A 0563/0565/0566/0569) are written with confidence not_target / UNCERTAIN and a note.
- Why: Each target species has exactly one unambiguous NOAA name and each NOAA area a unique lease number, so these are confident 1:1 matches rather than guesses; punctuation-insensitive matching avoids a false mismatch on separators. Rejected: name-only/fuzzy species matching (would risk collapsing SILVER into WHITE/RED hake or LONGFIN into ILLEX squid), and dropping unmatched NOAA areas/species (hides data; the workflow forbids silent drops). The 4 unmatched areas are flagged UNCERTAIN rather than guessed because the BOEM outlines layer genuinely has no such lease.
- Affects: src/overlap.py (clean_revenue, normalize_area_code, build_name_map, run_clean_revenue; SPECIES_NAME_MAP), data/processed/revenue_clean.csv, data/processed/name_map.csv (DRAFT); task 6.3 (revenue join) is blocked until the human confirms the map.
