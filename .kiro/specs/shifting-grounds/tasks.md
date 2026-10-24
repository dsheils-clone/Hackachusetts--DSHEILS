# Implementation Plan

Work through the tasks in order. After each task, follow .kiro/steering/workflow.md. Get tasks 1–9 working end to end before starting task 10. If the build falls behind, skip in this order: task 10, the SHAP plot in task 8, the revenue join in task 6. Keep the hindcast; it's the credibility moment in the demo.

Data-cleaning tasks (task 2 and task 6.2) go to the `data-cleaner` subagent, which runs on Claude Haiku (see design.md, Implementation notes). The main agent reviews its output before building on it. Briefs in task 8 use the DeepSeek API key in .env.

The human does these steps outside Kiro:

- Before task 1: check the Haiku model ID with `/model` and update .kiro/agents/data-cleaner.json if needed.
- Before task 2: download the NOAA fall survey zip and support tables (links in design.md) and unzip them into data/raw/survey/.
- Before task 6: download BOEM's lease area shapefile into data/raw/boem/, and the NOAA wind area landings and value CSV (species view, all areas) into data/raw/revenue/.
- Before task 8: add `DEEPSEEK_API_KEY` to .env.

- [x] 1. Set up the project (20 min)
  - Create the folder structure in design.md
  - Create requirements.txt: pandas, numpy, scikit-learn, shap, matplotlib, joblib, geopandas, shapely, pyproj, folium, streamlit, streamlit-folium, openai, python-dotenv
  - Create .gitignore covering data/raw/, .env and Python caches
  - Create .env.example with `DEEPSEEK_API_KEY=` and `DEEPSEEK_MODEL=deepseek-flash`
  - Write README.md with the data download steps and the data credits
  - _Requirements: 8.5_

- [x] 2. Clean and prepare the survey data (data-cleaner subagent) (1.5 h)
  - [x] 2.1 Inspect the SVSTA and SVCAT headers; map the real column names and species codes to design.md; write the mapping to data/processed/column_map.md
    - _Requirements: 1.1_
  - [x] 2.2 Checkpoint: stop and show the human the column mapping and species codes; continue only after they confirm
    - _Requirements: 1.1_
  - [x] 2.3 Build the tows table: fall tows from 2009 onward with year, latitude, longitude, depth and bottom temperature; drop tows missing any of these and report how many; save data/processed/tows.csv
    - _Requirements: 1.1, 1.3_
  - [x] 2.4 Build the presence table: one row per tow and target species, zero-filled; save data/processed/presence.csv
    - _Requirements: 1.2_
  - [x] 2.5 Main agent review: report tows per year and presence rate per species; check every tow has a row for every species; flag anything odd to the human
    - _Requirements: 1.4_

- [x] 3. Train the habitat models (1 h)
  - Train one HistGradientBoostingClassifier per species on bottom temperature and depth
  - Train on 2009–2018, test on 2019 onward; save test AUC and class balance to models/metrics.json
  - Save each model to models/<species>.joblib
  - Assert that latitude, longitude and year are not features
  - _Requirements: 2.1, 2.2, 2.3, 2.4_

- [x] 4. Run the hindcast (45 min)
  - Implement run_hindcast() as described in design.md
  - Save predicted and observed shifts per species to data/processed/hindcast.csv
  - _Requirements: 3.1, 3.2, 3.3, 3.4_
  - [x] 4.1 Revise hindcast per docs/HINDCAST_BRIEF.md
    - Same shared cells and presence-rate metric for predicted and observed; along-shelf axis plus depth; 200-replicate bootstrap 90% intervals; per-species verdicts; extrapolation diagnostic
    - _Requirements: 3.1, 3.2, 3.3, 3.4_

- [x] 5. Build the grid and warming scenarios (1 h)
  - Build the 0.2° grid from 2016-onward tows, keeping cells with at least 2 tows
  - Predict suitability for every cell, species and scenario (+0, +1, +2°C)
  - Save data/processed/grid_predictions.csv
  - _Requirements: 4.1, 4.2_

- [ ] 6. Compute lease signals and revenue context (1 h)
  - [x] 6.1 Load active leases; compute area-weighted suitability, percent change and signal with the thresholds and suggestion text in design.md
    - _Requirements: 5.1, 5.2, 5.3, 5.4, 5.5_
  - [x] 6.2 (data-cleaner subagent) Clean the NOAA revenue CSV and draft data/processed/name_map.csv matching NOAA species and area names to the survey species and BOEM leases; stop and ask the human to confirm the mapping
    - _Requirements: 6.1_
  - [x] 6.3 Join the 5-year average value to each lease and species, showing "no data" when nothing matches; save data/processed/lease_signals.csv
    - _Requirements: 6.1, 6.3_

- [x] 7. Build the app: map, selectors and lease panel (2 h)
  - Map with lease outlines and the grid colored by change for the selected species and scenario, using streamlit-folium
  - Species, scenario and lease selectors in the sidebar
  - Lease panel with signal, numbers, revenue and suggestion
  - Hindcast tab for the selected species, including a scatter plot of all six species: predicted vs observed along-shelf shift, with a 1:1 line and the selected species highlighted plus its depth shift shown next to the plot (point estimates only — no error bars and no verdict coloring, per D-020); caption "Trained on 2009–2015 only, then compared with what the survey saw from 2019 on. Point estimates; small shifts may be noise."
  - Uniform-warming note, "Shows change in fishing overlap, not harm to fish", and data credits in the footer
  - _Requirements: 4.3, 6.2, 8.1, 8.2, 8.3, 8.4, 8.5_

  - [x] 7.1 Map revamp: leases as a bold foreground layer with a grid on/off toggle; smoother, semi-transparent/blurred habitat cells anchored to the real 0.2° cells (no interpolation of values); keep OpenStreetMap basemap (no API key)
    - _Requirements: 4.3, 8.1, 8.2_
  - [x] 7.2 Warming slider/animation: sweep +0 → +2°C showing the habitat change build up, framed as DEGREES OF WARMING not years (honest; only the +0/+1/+2°C scenarios the model produced, or clearly-labelled interpolation); its own human checkpoint
    - _Requirements: 4.2, 4.3, 8.1_

- [ ] 8. Add explanations (1 h)
  - SHAP temperature response plot per species in a tab
  - Implement brief() with the DeepSeek prompt in design.md, reading DEEPSEEK_API_KEY and DEEPSEEK_MODEL from .env
  - Fall back to the template sentence if the call fails
  - _Requirements: 7.1, 7.2, 7.3, 7.4_

- [ ] 9. Checkpoint: demo readiness (1 h)
  - Ask the human to click through the app and pick 2–3 showcase lease and species pairs; fix anything broken
  - Write docs/DEMO.md with the demo flow from design.md and the chosen pairs
  - Update docs/WRITEUP.md from DECISIONS.md and CHANGELOG.md
  - The human makes 3 slides
  - _Requirements: 3.4, 5.5, 7.2, 8.3_

- [ ] 10. Stretch (optional; start only after task 9)
  - [ ] 10.1 Add an all-species view weighted by each species' share of NOAA revenue
    - _Requirements: 6.1, 8.1_
  - [ ] 10.2 Add the spring survey as a second season and compare signals
    - _Requirements: 2.1_
