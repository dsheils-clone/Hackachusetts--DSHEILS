"""Grid and warming scenarios for Shifting Grounds (task 5).

This is the forward projection. It builds a recent-conditions grid of the survey area,
then re-predicts each species' habitat suitability under uniform warming of +0, +1 and
+2 degrees C. The result feeds the map and the lease signals.

Algorithm, implemented EXACTLY as design.md's "### Grid and scenarios" section
specifies:

- "Cell size 0.2 deg latitude by 0.2 deg longitude. Keep cells with at least 2 tows
  from 2016 onward."
- "Each cell gets its mean bottom temperature and mean depth from those tows."
- "Scenarios add 0, 1 or 2 deg C to every cell's bottom temperature before predicting.
  This uniform warming is a simplification; real warming is uneven."
- "Output: data/processed/grid_predictions.csv with cell geometry, species, scenario
  and suitability."

Models: this uses the task-3 full-data models (models/<species>.joblib), NOT the
hindcast's early-only models. design.md's architecture diagram wires models/*.joblib
into scenarios.py, and the hindcast trains its own throwaway models in-process. So the
forward projection is made with the models trained on all of 2009-2018.

Warming mechanic (design.md, quoted above): the ONLY thing a scenario changes is the
cell's bottom temperature, which gets the scenario delta added. Depth is left untouched.
The model (BOTTEMP + AVGDEPTH, never lat/lon/year) is then asked for P(present). This is
the uniform-warming simplification stated as a limit in design.md and in app.py's footer.

Grid convention is shared with the hindcast (src/hindcast.py): the same 0.2-degree cell
snapping (_cell_index / CELL) so the scenario grid lines up with the hindcast grid.

Output: data/processed/grid_predictions.csv, one row per (cell, species, scenario) with
the cell geometry, the cell's baseline + scenario bottom temperature, depth, the species,
the scenario delta and the predicted suitability.
"""

from __future__ import annotations

import os

import joblib
import pandas as pd

from hindcast import CELL, _cell_index
from prepare_data import (
    PROCESSED_DIR,
    REPO_ROOT,
    TARGET_SPECIES,
    TOWS_PATH,
)
from train import FEATURES, MODELS_DIR, _assert_features_allowed

# --- Paths ------------------------------------------------------------------

GRID_PREDICTIONS_PATH = os.path.join(PROCESSED_DIR, "grid_predictions.csv")

# --- Grid and scenario config (design.md "### Grid and scenarios" + D-011) --

# First survey year the scenario grid is built from (D-011: 2016 onward).
GRID_START_YEAR = 2016
# A cell is kept only if at least this many tows from GRID_START_YEAR fall in it.
MIN_TOWS_PER_CELL = 2
# Uniform warming scenarios, in degrees C added to every cell's bottom temperature.
DELTAS = (0, 1, 2)

# Canonical grid_predictions.csv columns, in order.
GRID_PREDICTION_COLUMNS = [
    "lat_cell",       # lower-left corner latitude of the 0.2 deg cell
    "lon_cell",       # lower-left corner longitude of the 0.2 deg cell
    "cell_lat",       # mean tow latitude in the cell (for mapping / weighting)
    "cell_lon",       # mean tow longitude in the cell
    "n_tows",         # number of 2016+ tows that built the cell
    "baseline_bottemp",  # cell mean bottom temperature (the +0 deg C value)
    "AVGDEPTH",       # cell mean depth (unchanged across scenarios)
    "species",        # target-species key from TARGET_SPECIES
    "svspp",          # zero-padded 3-char species code
    "delta",          # warming applied to bottom temperature, deg C (0, 1 or 2)
    "BOTTEMP",        # bottom temperature used for prediction = baseline + delta
    "suitability",    # predicted P(present) for the cell under this scenario
]


# --- Grid -------------------------------------------------------------------


def load_tows(tows_path: str = TOWS_PATH) -> pd.DataFrame:
    """Load the tows table (one row per real tow). ID kept as string."""
    return pd.read_csv(tows_path, dtype={"ID": str})


def build_grid(
    tows: pd.DataFrame,
    start_year: int = GRID_START_YEAR,
    cell: float = CELL,
    min_tows: int = MIN_TOWS_PER_CELL,
    verbose: bool = True,
) -> pd.DataFrame:
    """Build the 0.2-degree recent-conditions grid (design.md "### Grid and scenarios").

    Keep tows from `start_year` onward, snap each to its 0.2-degree cell, and aggregate
    to one row per cell carrying its mean bottom temperature, mean depth and mean
    position. Keep only cells with at least `min_tows` tows. Returns a DataFrame with
    lat_cell, lon_cell, cell_lat, cell_lon, n_tows, baseline_bottemp, AVGDEPTH.
    """

    def log(msg: str) -> None:
        if verbose:
            print(msg)

    n_all = len(tows)
    year = pd.to_numeric(tows["EST_YEAR"], errors="coerce")
    recent = tows.loc[year >= start_year].copy()
    log(
        f"[grid] tows from {start_year} onward: {len(recent)} "
        f"(of {n_all} total tows)"
    )

    recent["lat_cell"] = _cell_index(recent["DECDEG_BEGLAT"], cell)
    recent["lon_cell"] = _cell_index(recent["DECDEG_BEGLON"], cell)

    grid = (
        recent.groupby(["lat_cell", "lon_cell"], as_index=False)
        .agg(
            baseline_bottemp=("BOTTEMP", "mean"),
            AVGDEPTH=("AVGDEPTH", "mean"),
            cell_lat=("DECDEG_BEGLAT", "mean"),
            cell_lon=("DECDEG_BEGLON", "mean"),
            n_tows=("ID", "size"),
        )
    )
    n_cells_all = len(grid)
    log(f"[grid] cells with >= 1 tow: {n_cells_all}")

    kept = grid.loc[grid["n_tows"] >= min_tows].copy()
    log(
        f"[grid] cells kept (>= {min_tows} tows): {len(kept)} "
        f"(dropped {n_cells_all - len(kept)} cells with a single tow)"
    )

    kept = kept.sort_values(["lat_cell", "lon_cell"]).reset_index(drop=True)
    return kept


# --- Models -----------------------------------------------------------------


def load_models(
    species_codes: dict[str, str] = TARGET_SPECIES, models_dir: str = MODELS_DIR
) -> dict:
    """Load the task-3 trained model for every target species from models/<species>.joblib.

    These are the full-data (2009-2018) models, the forward-projection models per
    design.md's architecture (NOT the hindcast's early-only models).
    """
    models: dict[str, object] = {}
    for species in species_codes:
        path = os.path.join(models_dir, f"{species}.joblib")
        if not os.path.exists(path):
            raise FileNotFoundError(
                f"Missing model for {species}: {path}. Run `python3 src/train.py` first."
            )
        models[species] = joblib.load(path)
    return models


# --- Scenario prediction ----------------------------------------------------


def predict_scenarios(
    grid: pd.DataFrame,
    models: dict,
    species_codes: dict[str, str] = TARGET_SPECIES,
    deltas: tuple[int, ...] = DELTAS,
    verbose: bool = True,
) -> pd.DataFrame:
    """Predict suitability for every (cell, species, scenario).

    For each scenario delta, add the delta to every cell's baseline bottom temperature
    (depth unchanged) and ask each species' model for P(present). Returns a tidy
    DataFrame with GRID_PREDICTION_COLUMNS: (n_cells x n_species x n_deltas) rows.
    """

    def log(msg: str) -> None:
        if verbose:
            print(msg)

    # Guard: the model is asked for exactly BOTTEMP + AVGDEPTH, never lat/lon/year.
    _assert_features_allowed(FEATURES)

    n_cells = len(grid)
    rows: list[pd.DataFrame] = []

    for delta in deltas:
        # Uniform warming: add delta to every cell's bottom temperature; depth unchanged.
        bottemp = grid["baseline_bottemp"] + delta
        # Feature matrix in the exact FEATURES order the models were trained on.
        features = pd.DataFrame(
            {"BOTTEMP": bottemp.to_numpy(), "AVGDEPTH": grid["AVGDEPTH"].to_numpy()}
        )[FEATURES]

        for species, code in species_codes.items():
            model = models[species]
            suitability = model.predict_proba(features)[:, 1]

            block = pd.DataFrame(
                {
                    "lat_cell": grid["lat_cell"].to_numpy(),
                    "lon_cell": grid["lon_cell"].to_numpy(),
                    "cell_lat": grid["cell_lat"].to_numpy(),
                    "cell_lon": grid["cell_lon"].to_numpy(),
                    "n_tows": grid["n_tows"].to_numpy(),
                    "baseline_bottemp": grid["baseline_bottemp"].to_numpy(),
                    "AVGDEPTH": grid["AVGDEPTH"].to_numpy(),
                    "species": species,
                    "svspp": code,
                    "delta": delta,
                    "BOTTEMP": bottemp.to_numpy(),
                    "suitability": suitability,
                }
            )
            rows.append(block)

    preds = pd.concat(rows, ignore_index=True)
    preds = preds[GRID_PREDICTION_COLUMNS]
    preds = preds.sort_values(
        ["species", "delta", "lat_cell", "lon_cell"]
    ).reset_index(drop=True)

    expected = n_cells * len(species_codes) * len(deltas)
    assert len(preds) == expected, (
        f"grid_predictions row count {len(preds)} != "
        f"cells x species x scenarios ({n_cells} x {len(species_codes)} x "
        f"{len(deltas)} = {expected})"
    )
    log(
        f"[grid] predictions: {len(preds)} rows = {n_cells} cells x "
        f"{len(species_codes)} species x {len(deltas)} scenarios"
    )
    return preds


def save_grid_predictions(
    preds: pd.DataFrame, path: str = GRID_PREDICTIONS_PATH
) -> None:
    """Write the grid predictions to CSV (no index)."""
    os.makedirs(os.path.dirname(path), exist_ok=True)
    preds.to_csv(path, index=False)


# --- Script entry point -----------------------------------------------------


def main() -> None:
    print("=== Shifting Grounds: grid and warming scenarios (task 5) ===")
    print(f"[grid] features (and ONLY these): {FEATURES}")
    print(
        f"[grid] grid from {GRID_START_YEAR}+ tows, 0.2 deg cells, "
        f">= {MIN_TOWS_PER_CELL} tows/cell; scenarios +{', +'.join(map(str, DELTAS))} deg C"
    )
    _assert_features_allowed(FEATURES)

    tows = load_tows()
    grid = build_grid(tows)
    assert len(grid) > 0, "no grid cells were kept; check the tows table and thresholds."

    models = load_models()
    print(f"[grid] loaded {len(models)} species models from {MODELS_DIR}")

    preds = predict_scenarios(grid, models)

    # Quick sanity report: mean suitability per species across scenarios, so a reviewer
    # can see which way warming pushes each species on average.
    print("[grid] mean suitability by species and scenario (+0 / +1 / +2 deg C):")
    pivot = (
        preds.groupby(["species", "delta"])["suitability"].mean().unstack("delta")
    )
    for species in TARGET_SPECIES:
        vals = pivot.loc[species]
        print(
            f"         {species:>16}: "
            + " | ".join(f"+{d} {vals[d]:.3f}" for d in DELTAS)
        )

    save_grid_predictions(preds)
    print(f"[grid] saved {len(preds)} rows to {GRID_PREDICTIONS_PATH}")
    print(f"[grid] columns: {list(preds.columns)}")


if __name__ == "__main__":
    main()
