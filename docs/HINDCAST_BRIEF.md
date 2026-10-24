# Brief: revise the hindcast (task 4)

## Why

The current hindcast doesn't compare like with like, so the predicted and observed shifts in data/processed/hindcast.csv can't be compared fairly:

- **Predicted** is the suitability-weighted latitude over the cells sampled in both periods.
- **Observed** is the mean latitude of every tow where the species was present, anywhere. It moves whenever the survey's footprint moves (no 2020 tows, partial 2017; see D-014), even if the fish don't.
- `cell_lat` is the mean tow latitude within a cell for each period, so where tows happened to land inside a cell leaks into the predicted shift.
- Raw latitude is the wrong axis. The Northeast shelf runs southwest to northeast, and species can respond to warming by moving east (cod toward Georges Bank) or deeper rather than north.
- There's no uncertainty estimate. Shifts of 1–3 km (longfin squid, black sea bass) are probably noise, but the script labels them "opposite."

Current results, kept for comparison:

| Species | Predicted (km) | Observed (km) |
|---|---|---|
| silver_hake | +8.12 | +14.95 |
| summer_flounder | +6.01 | +37.65 |
| scup | −6.17 | +59.86 |
| atlantic_cod | +1.90 | −19.65 |
| longfin_squid | +1.45 | −2.73 |
| black_sea_bass | −0.46 | +1.86 |

## Ground rules

- **Fix every method choice below before you rerun.** Don't adjust the axis, cell minimum, bootstrap settings or verdict rules after seeing results to make the numbers look better. If the results are weak, report them as they are. The hindcast exists to earn trust, and tuning it to look good defeats that.
- Don't change the target species, features (BOTTEMP, AVGDEPTH), model type, the 2009–2015 training window or the 2019-onward comparison window. Changing any of these needs the human's approval (workflow.md guardrails).
- No new dependencies. numpy, pandas, pyproj and matplotlib are enough.
- Latitude, longitude and year stay out of the model. They're used only to compute the habitat centers.

## Changes

### 1. Same cells, same metric for predicted and observed

- Keep only cells with **at least 2 tows in each period** (matches the scenario grid's 2-tow minimum).
- **Observed presence rate per cell** = present tows ÷ total tows in that cell, per period.
- **Predicted presence rate per cell** = the mean of the early model's predicted probability over that cell's tows, per period, with each tow keeping its own BOTTEMP and AVGDEPTH. This replaces predicting from the cell-mean temperature, so both rates are averages over the same tows.
- **Habitat center** (predicted or observed) = the weighted mean position of the shared cells, weighted by that period's presence rate.
- **Shift** = late center − early center.

### 2. Fixed cell positions

- Each cell's position is its **geometric center** (lower-left corner + 0.1° in both directions) and is the same in both periods. Only presence rates can move a center.
- Each cell's depth for the depth-center calculation is the mean AVGDEPTH of all its tows from both periods pooled. It is likewise the same in both periods.

### 3. Along-shelf axis plus depth

- Reproject cell centers to EPSG:5070 (already used in src/overlap.py, D-016).
- Define the along-shelf axis as the **first principal component of all tow positions** (2009 onward) in EPSG:5070. It comes from the survey footprint, not from any species' result. Orient it so positive points northeast, and print its bearing.
- **Along-shelf shift (km)** = change in the habitat center's position along that axis.
- **Depth shift (m)** = change in the presence-weighted mean cell depth. Positive means deeper.
- Keep the north-south latitude shift as a secondary column so the old numbers can still be compared.

### 4. Bootstrap confidence intervals

- 200 replicates with a fixed seed (reuse `RANDOM_STATE` from src/train.py).
- In each replicate:
  1. Resample tows with replacement within each period, stratified by year.
  2. Refit the early model on the resampled early tows.
  3. Rebuild the shared-cell set and recompute all shifts.
- Report the 5th and 95th percentiles (a 90% interval) for every predicted and observed shift.
- If a replicate leaves no shared cells, drop it and print a count of how many were dropped.

### 5. Verdict per species (along-shelf shift)

| Verdict | Rule |
|---|---|
| No clear shift | Observed interval includes 0 |
| Agrees | Observed and predicted intervals both exclude 0, same sign |
| Model misses | Observed interval excludes 0; predicted interval includes 0 |
| Opposite | Observed and predicted intervals both exclude 0, opposite signs |

### 6. Extrapolation diagnostic (report only, no fix)

Gradient-boosted trees go flat outside the temperatures they were trained on.

- For each species, report the share of late-period tows in shared cells with BOTTEMP outside the min–max range of the early training tows.
- Separately, report the share of grid cells in data/processed/grid_predictions.csv at +1°C and +2°C whose temperature is above the maximum training temperature of the 2009–2018 models. This is context for the scenarios, so don't change src/scenarios.py.

## Output

Replace data/processed/hindcast.csv with one row per species. Columns:

`species, svspp, axis_bearing_deg, pred_shelf_km, pred_shelf_lo, pred_shelf_hi, obs_shelf_km, obs_shelf_lo, obs_shelf_hi, pred_depth_m, pred_depth_lo, pred_depth_hi, obs_depth_m, obs_depth_lo, obs_depth_hi, pred_lat_km, obs_lat_km, verdict, n_cells, n_present_early, n_present_late, n_boot_dropped, frac_late_outside_train_temp`

Print a readable table of the same results when the script runs.

## For the app (task 7, not built yet)

Add to the hindcast tab bullet in tasks.md:

- One scatter plot of all six species: predicted vs observed along-shelf shift, with 90% error bars on both axes, a 1:1 line, and points colored by verdict.
- Highlight the selected species and show its depth shift next to the plot.
- Caption: "Trained on 2009–2015 only, then compared with what the survey saw from 2019 on. Bars show 90% intervals."

## Steps

1. Append a decision entry to docs/DECISIONS.md, continuing from the last number (D-018 if nothing has been added since D-017), **before** rerunning. Record the method above and the four verdict rules.
2. Update the "### Hindcast" section of .kiro/specs/shifting-grounds/design.md to match.
3. Add a task 4.1 "Revise hindcast per docs/HINDCAST_BRIEF.md" to tasks.md, and add the plot to task 7's hindcast bullet.
4. Implement in src/hindcast.py. Run it with `conda run -n shifting-grounds python src/hindcast.py` (D-017).
5. **Checkpoint:** show the human the new table next to the old one, plus the extrapolation numbers. Don't change the method in response to the results without the human's approval.
6. After approval, follow workflow.md: changelog entry (include the old and new tables), mark 4.1 done, commit as `model(hindcast): ...`, push.
