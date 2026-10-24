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

### D-019 · 12:13 · Revise the hindcast: like-for-like presence rates, along-shelf axis, bootstrap intervals and verdicts
- Decided by: human (brief docs/HINDCAST_BRIEF.md) + agent (task 4.1)
- Context: The old hindcast (D-011 method) compared unlike things. Predicted shift was a suitability-weighted latitude over shared cells, but observed shift was the mean latitude of every present tow anywhere, so it moved with the survey footprint (no 2020 tows, partial 2017; D-014), not the fish. Cell latitude used the mean tow latitude inside each cell, leaking tow placement into the predicted shift. Raw north-south latitude is the wrong axis for a shelf that runs SW-NE, and there was no uncertainty estimate, so shifts of 1-3 km were labelled "opposite" on noise.
- Decision: Rebuild the hindcast so predicted and observed are measured the same way, add an along-shelf axis and depth, and add bootstrap intervals and explicit verdicts. Locked BEFORE rerunning:
  1. Shared cells = 0.2 deg cells with >= 2 tows in EACH period (early 2009-2015, late 2019 onward), matching the scenario grid's 2-tow minimum. Observed presence rate per cell = present tows / total tows. Predicted presence rate per cell = mean of the early model's predicted probability over that cell's tows, each tow keeping its own BOTTEMP/AVGDEPTH. Habitat center = presence-rate-weighted mean position of the shared cells; shift = late center - early center.
  2. Each cell's position is its fixed geometric center (lower-left corner + 0.1 deg in both directions), identical in both periods; only presence rates move a center. Each cell's depth is the mean AVGDEPTH of all its tows from both periods pooled, also identical across periods.
  3. Along-shelf axis = first principal component of all 2009-onward tow positions reprojected to EPSG:5070 (D-016), oriented so positive points northeast; its bearing is printed. Along-shelf shift (km) = change in the center's position along that axis. Depth shift (m) = change in the presence-weighted mean cell depth (positive = deeper). The north-south latitude shift is kept as a secondary column for comparison with the old numbers.
  4. Bootstrap: 200 replicates, fixed seed reusing RANDOM_STATE from src/train.py. Each replicate resamples tows with replacement within each period stratified by year, refits the early model, rebuilds the shared-cell set and recomputes all shifts. Report the 5th and 95th percentiles (90% interval) for every predicted and observed shift. Replicates that leave no shared cells are dropped and counted.
  5. Verdict per species on the along-shelf shift: "No clear shift" if the observed interval includes 0; "Agrees" if observed and predicted intervals both exclude 0 with the same sign; "Model misses" if the observed interval excludes 0 but the predicted interval includes 0; "Opposite" if both exclude 0 with opposite signs.
  6. Extrapolation diagnostic (report only, no fix): per species, the share of late-period tows in shared cells whose BOTTEMP is outside the early training tows' min-max range; and separately the share of grid cells in data/processed/grid_predictions.csv at +1C and +2C above the 2009-2018 models' max training temperature. src/scenarios.py is left unchanged.
- Why: Measuring predicted and observed the same way over the same cells makes the two shifts comparable, which is the whole point of the hindcast as the demo's credibility moment. Bootstrap intervals and sign-aware verdicts stop noise being read as disagreement. The along-shelf axis respects the shelf's real geometry and lets eastward/deeper responses show up. The method is locked before the run so results can't be tuned to look good. Rejected: keeping the footprint-sensitive observed metric; keeping raw latitude as the only axis; reporting point estimates with no uncertainty.
- Affects: src/hindcast.py, data/processed/hindcast.csv (new columns), .kiro/specs/shifting-grounds/design.md (### Hindcast), tasks.md (task 7 hindcast plot). src/scenarios.py unchanged.

### D-020 · 12:20 · Skip the hindcast bootstrap CIs and verdicts for runtime; ship point estimates only
- Decided by: human (scope override on docs/HINDCAST_BRIEF.md) + agent (task 4.1)
- Context: D-019 locked the revised hindcast including a 200-replicate bootstrap (refitting the early model in every replicate) and sign-aware verdicts built on the resulting 90% intervals. In practice the bootstrap refits every species' early model 200 times, which is too slow for the demo time budget. The "cheap" parts of the revision (the like-for-like shared-cell presence-rate metric, the fixed geometric cell centers and pooled-depth, the along-shelf PCA axis plus depth, and the two extrapolation diagnostics) each cost only a single pass and are kept.
- Decision: Implement only the single-pass fixes from D-019 (changes 1, 2, 3 and 6). Drop the bootstrap (change 4) and the verdicts (change 5) entirely. The hindcast now fits each species' early model exactly once and reports point estimates with no uncertainty. hindcast.csv columns are reduced to: species, svspp, axis_bearing_deg, pred_shelf_km, obs_shelf_km, pred_depth_m, obs_depth_m, pred_lat_km, obs_lat_km, n_cells, n_present_early, n_present_late, frac_late_outside_train_temp (the *_lo/*_hi interval columns, the verdict column and n_boot_dropped are removed). Results are framed as "predicted vs observed along-shelf (and depth) shift on a comparable metric", never as agree/disagree.
- Why: The bootstrap was the only expensive step (200 refits per species) and the time budget can't absorb it; the method fixes that actually make predicted and observed comparable are all single-pass and stay. Explicit tradeoff: with no bootstrap there is no uncertainty estimate, so there is no basis for a verdict and no way to tell a small shift from noise. Small along-shelf or depth shifts (a few km / a few m) must therefore be read as point estimates that may well be noise, not as evidence of agreement or disagreement. The guardrails from D-019 are otherwise unchanged (same species, same BOTTEMP+AVGDEPTH features, same HistGradientBoostingClassifier, same 2009-2015 training window and 2019-onward comparison window, lat/lon/year never features, method locked before the run). Rejected: keeping the bootstrap (too slow for the budget); keeping the verdict column off point estimates alone (a verdict with no interval would imply a confidence the method no longer has).
- Affects: src/hindcast.py (bootstrap and verdict code removed), data/processed/hindcast.csv (columns reduced), .kiro/specs/shifting-grounds/design.md (### Hindcast), tasks.md (task 7 hindcast plot: no error bars, no verdict coloring). Supersedes the bootstrap/verdict parts of D-019; the rest of D-019 stands.
### D-021 · 13:11 · Revenue join: average inflation-adjusted value over 2021–2025; encode misses as the string "no data"
- Decided by: agent (task 6.3)
- Context: design.md "### Revenue join" asks for the value per lease area, species and year, averaged over the most recent 5 years available, with "no data" shown when nothing matches (requirement 6.3: "no data" rather than zero). revenue_clean.csv carries two money columns — nominal dollars of each year and value_2025 (the same dollars inflation-adjusted to 2025) — and the newest year in the NOAA export is 2025, so the 5-year window is 2021–2025 (the window D-011 anticipated).
- Decision: (1) Window = the 5 most recent DISTINCT years present in the joined revenue, which is 2021–2025 (no imputation for a missing year; a year with no landing for a (lease, species) simply contributes no row). (2) Average value_2025 (inflation-adjusted), not nominal, since the mean spans several years and mixing unadjusted dollars across years is not comparable. (3) Encode every miss as the literal string "no data" (constant NO_REVENUE) in the avg_value column, never 0 or NaN — this makes avg_value an object column where the app prints the number when present and "no data" otherwise. A miss means the species was never landed/reported in that lease area (incl. NOAA's confidentiality-suppressed "ALL OTHERS" fleets), or the lease has no confirmed NOAA revenue area (12 of 45 leases, plus the 4 UNCERTAIN NOAA areas that have no BOEM lease). (4) Join only through the human-confirmed name_map rows whose confidence is "confident" (6 target species, 33 areas); not_target / UNCERTAIN rows never contribute a value.
- Why: Averaging the inflation-adjusted column keeps the five years on one scale. The "no data" string (vs 0) is required so planners never read a confidentiality-suppressed or never-landed combination as "$0 at stake"; it also keeps leases outside the NOAA export honestly blank rather than falsely zero. Using only confirmed mappings respects the 6.2 human checkpoint. Rejected: averaging nominal dollars (not comparable across years); filling misses with 0 (violates requirement 6.3 and misleads); inventing a window with imputation for the absent year.
- Affects: src/overlap.py (join_revenue, new average_recent_value, NO_REVENUE / REVENUE_VALUE_COLUMN constants, SIGNAL_COLUMNS gains avg_value, main() now writes the output), data/processed/lease_signals.csv (new, 540 rows × 14 columns).
### D-022 · 13:21 · Install streamlit-folium into the conda env; map colors change on a diverging blue-white-red scale saturating at ±30%
- Decided by: agent (task 7)
- Context: app.py renders the map with a folium map embedded via streamlit-folium (design.md "## Components and Interfaces" → app.py). streamlit-folium is in requirements.txt but was not present in the `shifting-grounds` conda env (ModuleNotFoundError). The map must color the 0.2° grid by the percent CHANGE in suitability from the +0 °C baseline to the selected warmed scenario, which needs a numeric→color rule.
- Decision: (1) `conda run -n shifting-grounds pip install streamlit-folium` (installed 0.27.4); it is already declared in requirements.txt so no dependency list changed. (2) Color each grid cell by percent change on a diverging palette centered on zero — blue = falling (habitat shrinks), white ≈ no change, red = rising (habitat grows) — linearly interpolated and SATURATING at ±30% (`CHANGE_SCALE = 0.30`), so a few very large percent changes don't wash out the rest. (3) A cell whose +0 °C baseline is zero has an undefined change (division by zero → inf → NaN) and is drawn light grey rather than dropped. The signal-badge colors in the lease panel are a separate, non-map palette (Uncertain is grey, not red, so it never reads as a verdict).
- Why: streamlit-folium is the design's chosen map component and was already a declared dependency; installing it is setup, not a new dependency choice. A zero-centered diverging scale is the natural way to show a signed change and matches design.md's "diverging palette centered on zero, with a legend". The ±30% saturation is a display choice (not a signal threshold — the Rising/Falling ±10% thresholds in overlap.py are untouched) and is a named constant so it's easy to find and change. Rejected: a sequential palette (hides the sign of the change); dropping zero-baseline cells (silent data loss); reusing the signal colors on the map (would conflate the per-lease signal with the per-cell numeric change).
- Affects: the `shifting-grounds` conda env (streamlit-folium 0.27.4 added); app.py (CHANGE_SCALE, _change_to_color, build_map, grid_change_for). No change to requirements.txt, the signal thresholds, or any processed file.
### D-023 · 13:40 · Map revamp: OSM basemap, bold foreground leases + grid toggle, honest display-only cell smoothing
- Decided by: human (feedback: map cluttered, leases hard to see) + agent (task 7.1)
- Context: The task-7 map read as a hard spreadsheet of squares with thin grey lease outlines that got lost against both the grid and the basemap. Two problems: (a) the "CartoDB positron" basemap now renders "API KEY REQUIRED" watermark tiles (CARTO moved its default tiles behind an API key), and (b) the wind leases — the actual subject of the tool — were visually subordinate to the habitat grid. Human asked for leases to be the bold foreground, a way to hide the grid, and a smoother (less spreadsheet-like) heat surface, WITHOUT inventing precision the 0.2° data doesn't have.
- Decision: (1) Basemap = tiles="OpenStreetMap" (no API key), replacing "CartoDB positron"; OSM place labels stay legible under the grid. (2) Draw order basemap → habitat grid → wind leases, so leases are the top layer. Leases get a soft white halo under-stroke plus a crisp dark outline (#111, weight 2.5); the selected lease is thicker (weight 4), red (#b30000) outlined and lightly filled (#ff6d3a, 0.28) to stand out. (3) Add a folium LayerControl (expanded) that registers the grid and the lease layer as independent overlays, so the user can hide "Habitat change (toggle)" while the leases stay visible. (4) Smoother LOOK via display-only CSS: the grid lives in its own Leaflet pane (z-index 410, above tiles, below leases) with filter:blur(6px) and fill_opacity lowered 0.55→0.42. Each real 0.2° cell is still exactly one rectangle at its true bounds carrying its own computed change value — no interpolation, no resampling, no overlap, no sub-cell values. A map caption states each patch is one real 0.2° cell and the softened edges are display smoothing, not interpolation.
- Why: OSM needs no key and renders cleanly, unlike the now-gated CARTO default. Putting leases on top with a halo+bold outline makes the planning subject the visual focus the human asked for; the grid toggle lets them declutter on demand. The blur is applied to the grid PANE only (not the basemap or leases) so it softens how the fixed-size cells look without touching the data — the honest constraint is kept because the blur is a pure CSS visual effect over rectangles whose geometry and values are unchanged, and the caption discloses it so the softened edges can't be misread as sub-cell precision. The ±30% saturation and the diverging blue-white-red semantics are unchanged; the ±10% signal thresholds in src/overlap.py are untouched (the blur/opacity are display-only). Rejected: enlarging/overlapping cells or value interpolation to smooth (would imply sub-cell precision the 0.2° survey grid doesn't have — fails the honesty guardrail); keeping CARTO (watermarked, needs a key); leaving leases under the grid (the clutter the human flagged).
- Affects: app.py (build_map: CustomPane + blur CSS, lowered grid opacity, halo+bold lease outlines, selected-lease highlight, LayerControl; map caption in main()). The pre-existing uncommitted OSM basemap fix is folded into this commit. No change to signal thresholds, suggestion text, the honest framing, requirements.txt, or any processed file.

### D-024 · 14:40 · Warming map: 3-segment control, absolute-change coloring, capped-% tooltip
- Decided by: human + agent (task 7.2)
- Context: The warming slider + Play/Pause autoplay was fragile (caused a StreamlitWidgetAlreadyInstantiatedError) and the human preferred a simpler control; percent-change map coloring blew up to thousands of percent in near-zero-baseline cells.
- Decision: Replace the slider/autoplay with a 3-segment control (+0/+1/+2 °C, active segment pressed/inset). Color the MAP by absolute change in suitability (±0.30 saturation); keep the LEASE PANEL on percent + the Rising/Falling/Stable/Uncertain signal (±10% thresholds, unchanged). Tooltip shows percent as a header capped at "250%+" with a small-font footer explaining low-baseline cells only when capped.
- Why: Simpler, crash-free control; absolute change is an honest, bounded map metric; the cap keeps tooltips readable while the body keeps the real baseline→scenario numbers. Rejected: the slider/autoplay (fragile), and percent-change map coloring (small-denominator blow-up). Display-only — does not touch src/overlap.py thresholds or suggestion text.
- Affects: app.py, tests/test_app_sweep_tooltip.py

### D-025 · 14:55 · Lease selection: right-panel selector + map click-to-select; explain map-vs-signal mismatch rather than change the signal
- Decided by: human + agent (task 7.3)
- Context: The lease-area selector was in the sidebar; the human wanted it in the right panel and wanted clicking a lease on the map to select it. Separately, the map (absolute-change coloring) and the lease badge (percent-change signal) can appear to disagree because near-zero-baseline cells yield huge percents.
- Decision: Move the selector to the right panel above the status; make map lease-clicks select the lease (tooltip id, point-in-polygon fallback), kept in sync with the dropdown via one non-widget state key. For the map-vs-signal mismatch, add explanatory captions only (Option A) — do NOT change the signal thresholds or logic.
- Why: Better UX and the click interaction the human asked for; explaining the mismatch keeps the honest ±10% signal definition (D-006/D-011) intact rather than re-tuning guardrail-protected thresholds. Rejected: Option B (change the signal to ignore low-baseline cells) for now — it would re-generate lease_signals.csv and alter the spec's signal meaning.
- Affects: app.py, tests/test_app_lease_selection.py
