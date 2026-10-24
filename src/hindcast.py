"""Hindcast check for Shifting Grounds (task 4).

The hindcast is the credibility moment in the demo: it asks whether a model trained on
*older* survey years would have predicted the north-south habitat shift that the survey
later observed. If the predicted and observed shifts point the same way and track in
rough size, the forward projections earn some trust.

Algorithm, implemented EXACTLY as design.md's "### Hindcast" section specifies:

1. Train each species' model on 2009-2015 tows only. Same model and features as task 3
   (HistGradientBoostingClassifier on BOTTEMP + AVGDEPTH; never lat/lon/year).
2. Build a grid of mean bottom temperature and depth for 2009-2015 and another for
   2019 onward. Use ONLY grid cells sampled in BOTH periods.
3. Predicted shift: change in the suitability-weighted mean latitude of the grid
   between the two periods, converted to km (1 deg latitude ~= 111 km). Each period's
   grid uses that period's OWN observed temperatures, so the only thing that moves the
   predicted centre is how the model maps changing temperature/depth to suitability.
4. Observed shift: change in the mean latitude of tows where the species was present
   between the two periods.
5. Save both shifts per species to data/processed/hindcast.csv.

Sign convention: a POSITIVE shift (km) means the habitat centre moved NORTH (to higher
latitude) from the early period to the late period.

Grid convention matches design.md's grid-and-scenarios section: 0.2 deg x 0.2 deg cells,
each cell carrying its mean bottom temperature and mean depth from the tows that fall in
it during the period. (The scenario grid in task 5 additionally requires >= 2 tows from
2016 onward; here the "sampled in both periods" rule plays the equivalent role.)

Output: data/processed/hindcast.csv, one row per species with the predicted and observed
shift in km plus the underlying early/late mean latitudes and supporting counts.
"""

from __future__ import annotations

import os

import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingClassifier

from prepare_data import (
    PRESENCE_PATH,
    PROCESSED_DIR,
    REPO_ROOT,
    TARGET_SPECIES,
    TOWS_PATH,
)
from train import FEATURES, LABEL, RANDOM_STATE, _assert_features_allowed

# --- Paths ------------------------------------------------------------------

HINDCAST_PATH = os.path.join(PROCESSED_DIR, "hindcast.csv")

# --- Hindcast config (design.md "### Hindcast" + D-011) ---------------------

# Period 1: train the model and build the early grid on these years only.
EARLY_YEARS = (2009, 2015)  # inclusive
# Period 2: the "later" years the model never saw.
LATE_MIN_YEAR = 2019

# Grid cell size in degrees (design.md grid-and-scenarios section).
CELL = 0.2
# 1 degree of latitude is about 111 km (design.md step 3).
KM_PER_DEG_LAT = 111.0

# Canonical hindcast.csv columns, in order.
HINDCAST_COLUMNS = [
    "species",
    "svspp",
    "predicted_shift_km",
    "observed_shift_km",
    "predicted_lat_early",
    "predicted_lat_late",
    "observed_lat_early",
    "observed_lat_late",
    "n_grid_cells",
    "n_present_early",
    "n_present_late",
]


# --- Period slicing ---------------------------------------------------------


def _year(frame: pd.DataFrame) -> pd.Series:
    return pd.to_numeric(frame["EST_YEAR"], errors="coerce")


def early_mask(frame: pd.DataFrame) -> pd.Series:
    y = _year(frame)
    return (y >= EARLY_YEARS[0]) & (y <= EARLY_YEARS[1])


def late_mask(frame: pd.DataFrame) -> pd.Series:
    return _year(frame) >= LATE_MIN_YEAR


# --- Data -------------------------------------------------------------------


def load_hindcast_frame(
    tows_path: str = TOWS_PATH, presence_path: str = PRESENCE_PATH
) -> pd.DataFrame:
    """Join presence to tows on ID so each (tow, species) row carries the features,
    the label, the year and the latitude. Latitude is kept only for the observed/grid
    centres, never as a model feature.
    """
    tows = pd.read_csv(tows_path, dtype={"ID": str})
    presence = pd.read_csv(presence_path, dtype={"ID": str})

    cols = ["ID", "EST_YEAR", "DECDEG_BEGLAT", "DECDEG_BEGLON", *FEATURES]
    merged = presence.merge(
        tows[cols], on="ID", how="left", validate="many_to_one"
    )
    missing = merged[FEATURES + ["DECDEG_BEGLAT"]].isna().any(axis=1).sum()
    assert missing == 0, (
        f"{missing} (tow, species) rows did not join to a tow with valid "
        f"{FEATURES} + latitude; the presence/tows join is broken."
    )
    return merged


# --- Grid helpers -----------------------------------------------------------


def _cell_index(values: pd.Series, cell: float = CELL) -> pd.Series:
    """Snap coordinates to the lower-left corner of their 0.2-degree cell.

    Rounding to a fixed grid origin (0) makes the early- and late-period grids share the
    same cell boundaries, so a cell can be matched across periods.
    """
    return np.floor(values / cell) * cell


def build_period_grid(period_tows: pd.DataFrame, cell: float = CELL) -> pd.DataFrame:
    """Aggregate one period's *unique tows* into 0.2-degree cells.

    Each cell carries its mean bottom temperature, mean depth and mean latitude from the
    tows that fall in it. Returns one row per cell: lat_cell, lon_cell, BOTTEMP,
    AVGDEPTH, cell_lat (mean tow latitude in the cell), n_tows.
    """
    # The joined frame repeats each tow once per species; dedupe to real tows first so
    # cell means are not weighted by the number of target species.
    tows = period_tows.drop_duplicates(subset=["ID"]).copy()
    tows["lat_cell"] = _cell_index(tows["DECDEG_BEGLAT"], cell)
    tows["lon_cell"] = _cell_index(tows["DECDEG_BEGLON"], cell)

    grid = (
        tows.groupby(["lat_cell", "lon_cell"], as_index=False)
        .agg(
            BOTTEMP=("BOTTEMP", "mean"),
            AVGDEPTH=("AVGDEPTH", "mean"),
            cell_lat=("DECDEG_BEGLAT", "mean"),
            n_tows=("ID", "size"),
        )
    )
    return grid


# --- Model ------------------------------------------------------------------


def train_early_model(species_frame: pd.DataFrame):
    """Train one HistGradientBoostingClassifier for a species on EARLY_YEARS tows only.

    Mirrors train.train_species but with the hindcast's early-only window. Features are
    strictly BOTTEMP + AVGDEPTH; lat/lon/year can never reach the model.
    """
    _assert_features_allowed(FEATURES)
    early = species_frame.loc[early_mask(species_frame)]

    X = early[FEATURES].copy()
    y = early[LABEL].astype(int)
    _assert_features_allowed(list(X.columns))

    model = HistGradientBoostingClassifier(random_state=RANDOM_STATE)
    model.fit(X, y)
    return model


# --- Shifts -----------------------------------------------------------------


def suitability_weighted_lat(model, grid: pd.DataFrame) -> float:
    """Suitability-weighted mean latitude of the grid for one model.

    Predict P(present) for each cell from that cell's (period-specific) temperature and
    depth, then take the mean of the cells' latitudes weighted by suitability.
    """
    proba = model.predict_proba(grid[FEATURES])[:, 1]
    weight = proba.sum()
    if weight <= 0:
        # Degenerate: model predicts ~0 everywhere. Fall back to the unweighted centre
        # so the shift is still defined rather than NaN.
        return float(grid["cell_lat"].mean())
    return float(np.average(grid["cell_lat"], weights=proba))


def run_hindcast(frame: pd.DataFrame, species: str) -> dict:
    """Run the full hindcast for one species. Returns a dict with predicted and
    observed shift in km (positive = northward) plus the supporting numbers.
    """
    sp = frame.loc[frame["species"] == species].copy()

    # --- 1. Train on 2009-2015 only -----------------------------------------
    model = train_early_model(sp)

    # --- 2. Grids for each period, kept to cells sampled in BOTH periods -----
    early_grid = build_period_grid(sp.loc[early_mask(sp)])
    late_grid = build_period_grid(sp.loc[late_mask(sp)])

    shared = early_grid.merge(
        late_grid, on=["lat_cell", "lon_cell"], suffixes=("_early", "_late")
    )
    # Early-period grid for prediction: early temperatures/depths, with each cell's
    # latitude. Late-period grid: late temperatures/depths. Same set of cells.
    early_shared = shared.rename(
        columns={
            "BOTTEMP_early": "BOTTEMP",
            "AVGDEPTH_early": "AVGDEPTH",
            "cell_lat_early": "cell_lat",
        }
    )[["lat_cell", "lon_cell", "BOTTEMP", "AVGDEPTH", "cell_lat"]]
    late_shared = shared.rename(
        columns={
            "BOTTEMP_late": "BOTTEMP",
            "AVGDEPTH_late": "AVGDEPTH",
            "cell_lat_late": "cell_lat",
        }
    )[["lat_cell", "lon_cell", "BOTTEMP", "AVGDEPTH", "cell_lat"]]

    n_cells = len(shared)
    assert n_cells > 0, (
        f"{species}: no grid cells were sampled in both the early and late periods."
    )

    # --- 3. Predicted shift: suitability-weighted mean latitude, early -> late
    pred_lat_early = suitability_weighted_lat(model, early_shared)
    pred_lat_late = suitability_weighted_lat(model, late_shared)
    predicted_shift_km = (pred_lat_late - pred_lat_early) * KM_PER_DEG_LAT

    # --- 4. Observed shift: mean latitude of present tows, early -> late ------
    present = sp.loc[sp[LABEL] == 1]
    early_present = present.loc[early_mask(present)]
    late_present = present.loc[late_mask(present)]
    obs_lat_early = float(early_present["DECDEG_BEGLAT"].mean())
    obs_lat_late = float(late_present["DECDEG_BEGLAT"].mean())
    observed_shift_km = (obs_lat_late - obs_lat_early) * KM_PER_DEG_LAT

    return {
        "species": species,
        "svspp": TARGET_SPECIES[species],
        "predicted_shift_km": round(predicted_shift_km, 2),
        "observed_shift_km": round(observed_shift_km, 2),
        "predicted_lat_early": round(pred_lat_early, 4),
        "predicted_lat_late": round(pred_lat_late, 4),
        "observed_lat_early": round(obs_lat_early, 4),
        "observed_lat_late": round(obs_lat_late, 4),
        "n_grid_cells": int(n_cells),
        "n_present_early": int(len(early_present)),
        "n_present_late": int(len(late_present)),
    }


def run_all(frame: pd.DataFrame) -> pd.DataFrame:
    """Run the hindcast for every target species; return a tidy DataFrame."""
    rows = [run_hindcast(frame, species) for species in TARGET_SPECIES]
    return pd.DataFrame(rows, columns=HINDCAST_COLUMNS)


def save_hindcast(hindcast: pd.DataFrame, path: str = HINDCAST_PATH) -> None:
    """Write the hindcast table to CSV (no index)."""
    os.makedirs(os.path.dirname(path), exist_ok=True)
    hindcast.to_csv(path, index=False)


# --- Script entry point -----------------------------------------------------


def main() -> None:
    print("=== Shifting Grounds: hindcast check (task 4) ===")
    print(
        f"[hindcast] train years {EARLY_YEARS[0]}-{EARLY_YEARS[1]}; "
        f"compare against {LATE_MIN_YEAR} onward"
    )
    print(f"[hindcast] features (and ONLY these): {FEATURES}")
    _assert_features_allowed(FEATURES)

    frame = load_hindcast_frame()
    print(
        f"[hindcast] joined frame: {len(frame)} (tow, species) rows across "
        f"{frame['species'].nunique()} species"
    )

    hindcast = run_all(frame)

    print("[hindcast] predicted vs observed north-south shift (km; + = north):")
    for _, r in hindcast.iterrows():
        agree = "same way" if (
            r["predicted_shift_km"] * r["observed_shift_km"] > 0
        ) else "opposite"
        print(
            f"         {r['species']:>16}: "
            f"predicted {r['predicted_shift_km']:+7.2f} km | "
            f"observed {r['observed_shift_km']:+7.2f} km | {agree} "
            f"(cells={r['n_grid_cells']}, "
            f"present early/late={r['n_present_early']}/{r['n_present_late']})"
        )

    save_hindcast(hindcast)
    print(f"[hindcast] saved {len(hindcast)} rows to {HINDCAST_PATH}")
    print(f"[hindcast] columns: {list(hindcast.columns)}")


if __name__ == "__main__":
    main()
