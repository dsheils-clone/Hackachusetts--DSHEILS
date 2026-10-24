"""Hindcast check for Shifting Grounds (task 4.1, revised per docs/HINDCAST_BRIEF.md,
D-019; scope reduced to point estimates by D-020).

The hindcast is the credibility moment in the demo: it asks whether a model trained on
*older* survey years (2009-2015) would have anticipated the habitat shift the survey later
observed (2019 onward). To be a fair test, the predicted and observed shifts must be
measured the SAME way over the SAME cells. The old method (D-011) compared a
suitability-weighted latitude over shared cells against the mean latitude of every present
tow anywhere, so the observed shift moved with the survey footprint rather than the fish.
This revision fixes that and adds an along-shelf axis and a depth shift.

Scope note (D-020): D-019 also specified a 200-replicate bootstrap (90% intervals) and
sign-aware verdicts built on those intervals. Those were dropped for runtime. The bootstrap
refit every species' early model 200 times, which the demo time budget can't absorb. The
fixes that actually make predicted and observed comparable are all single-pass and are kept.
So this script fits each species' early model exactly ONCE and reports POINT ESTIMATES with
NO uncertainty. With no interval there is no basis for a verdict and no way to separate a
small shift from noise, so results are framed as "predicted vs observed along-shelf (and
depth) shift on a comparable metric", never as agree/disagree.

Method (locked BEFORE running; see docs/HINDCAST_BRIEF.md "## Changes" 1-3 + 6, and
D-019/D-020):

1. Shared cells. Snap tows to 0.2 deg cells. Keep only cells with >= 2 tows in EACH
   period (early 2009-2015, late 2019 onward), matching the scenario grid's 2-tow minimum.
2. Presence rate per cell, per period:
     - observed  = present tows / total tows in the cell.
     - predicted = mean of the early model's predicted P(present) over the cell's tows,
       each tow keeping its OWN BOTTEMP and AVGDEPTH (not the cell-mean temperature).
3. Fixed cell geometry. A cell's position is its geometric center (lower-left corner +
   0.1 deg in each direction), identical in both periods. A cell's depth is the mean
   AVGDEPTH of all its tows from both periods pooled, also identical across periods.
   Only presence rates can move a habitat center.
4. Habitat center (predicted or observed) = presence-rate-weighted mean position of the
   shared cells. Shift = late center - early center.
5. Along-shelf axis = first principal component of ALL 2009-onward tow positions in
   EPSG:5070 (D-016), oriented so positive points northeast; its bearing is printed.
   Along-shelf shift (km) = change in the center's position along that axis.
   Depth shift (m)        = change in the presence-weighted mean cell depth (+ = deeper).
   The north-south latitude shift (km, 1 deg ~= 111 km) is kept as a secondary column.
6. Extrapolation diagnostic (report only, no fix): per species, the share of late-period
   tows in shared cells with BOTTEMP outside the early training tows' min-max range (the
   frac_late_outside_train_temp column); and separately, printed to the console, the share
   of grid cells in data/processed/grid_predictions.csv at +1C and +2C above the 2009-2018
   models' max training temperature. src/scenarios.py is untouched.

Output: data/processed/hindcast.csv, one row per species, columns listed in HINDCAST_COLUMNS.
A readable table is printed when the script runs.
"""

from __future__ import annotations

import os

import numpy as np
import pandas as pd
from pyproj import Transformer
from sklearn.ensemble import HistGradientBoostingClassifier

from prepare_data import (
    PRESENCE_PATH,
    PROCESSED_DIR,
    TARGET_SPECIES,
    TOWS_PATH,
)
from train import FEATURES, LABEL, RANDOM_STATE, _assert_features_allowed

# --- Paths ------------------------------------------------------------------

HINDCAST_PATH = os.path.join(PROCESSED_DIR, "hindcast.csv")
GRID_PREDICTIONS_PATH = os.path.join(PROCESSED_DIR, "grid_predictions.csv")

# --- Hindcast config (brief "## Changes" + D-019/D-020; locked before running) ----

# Period 1: train the early model and build the early rates on these years only.
EARLY_YEARS = (2009, 2015)  # inclusive
# Period 2: the "later" years the early model never saw.
LATE_MIN_YEAR = 2019

# Grid cell size in degrees (design.md grid-and-scenarios section).
CELL = 0.2
# A cell must have at least this many tows in EACH period to be "shared".
MIN_TOWS_PER_PERIOD = 2
# 1 degree of latitude is about 111 km (secondary north-south shift only).
KM_PER_DEG_LAT = 111.0

# CRS used for the along-shelf axis and along-shelf/north-south distances (D-016).
GEOGRAPHIC_CRS = "EPSG:4326"
EQUAL_AREA_CRS = "EPSG:5070"  # NAD83 / CONUS Albers, metres
KM_PER_M = 1.0 / 1000.0

# The 2009-2018 training window of the deployed scenario models (train.py TRAIN_YEARS),
# used only for the grid-cell extrapolation diagnostic.
SCENARIO_TRAIN_YEARS = (2009, 2018)
SCENARIO_DELTAS = (1, 2)  # +1C and +2C warming scenarios

# Canonical hindcast.csv columns, in order (D-020 reduced set: point estimates only, no
# bootstrap interval columns, no verdict, no n_boot_dropped).
HINDCAST_COLUMNS = [
    "species",
    "svspp",
    "axis_bearing_deg",
    "pred_shelf_km",
    "obs_shelf_km",
    "pred_depth_m",
    "obs_depth_m",
    "pred_lat_km",
    "obs_lat_km",
    "n_cells",
    "n_present_early",
    "n_present_late",
    "frac_late_outside_train_temp",
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
    the label, the year and the lat/lon. lat/lon/year are used only for the habitat
    centers and the axis, never as model features.
    """
    tows = pd.read_csv(tows_path, dtype={"ID": str})
    presence = pd.read_csv(presence_path, dtype={"ID": str})

    cols = ["ID", "EST_YEAR", "DECDEG_BEGLAT", "DECDEG_BEGLON", *FEATURES]
    merged = presence.merge(tows[cols], on="ID", how="left", validate="many_to_one")
    missing = merged[FEATURES + ["DECDEG_BEGLAT", "DECDEG_BEGLON"]].isna().any(axis=1).sum()
    assert missing == 0, (
        f"{missing} (tow, species) rows did not join to a tow with valid "
        f"{FEATURES} + lat/lon; the presence/tows join is broken."
    )
    return merged


# --- Geometry ---------------------------------------------------------------


def _cell_index(values: pd.Series, cell: float = CELL) -> pd.Series:
    """Snap coordinates to the lower-left corner of their 0.2-degree cell.

    Rounding to a fixed grid origin (0) makes the early and late grids share the same
    cell boundaries so a cell can be matched across periods.
    """
    return np.floor(values / cell) * cell


def _to_5070(lon: np.ndarray, lat: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Reproject lon/lat (EPSG:4326) arrays to EPSG:5070 metres (x east, y north)."""
    transformer = Transformer.from_crs(GEOGRAPHIC_CRS, EQUAL_AREA_CRS, always_xy=True)
    x, y = transformer.transform(np.asarray(lon), np.asarray(lat))
    return np.asarray(x), np.asarray(y)


def along_shelf_axis(tows: pd.DataFrame) -> tuple[np.ndarray, float]:
    """First principal component of ALL 2009-onward tow positions in EPSG:5070.

    Returns (unit_vector, bearing_deg). The vector is oriented so it points toward the
    northeast (positive x = east and positive y = north components), and the bearing is
    the compass bearing (degrees clockwise from north) of that direction. The axis comes
    from the survey footprint, not from any species' result.
    """
    pts = tows.drop_duplicates(subset=["ID"])
    x, y = _to_5070(pts["DECDEG_BEGLON"].to_numpy(), pts["DECDEG_BEGLAT"].to_numpy())
    coords = np.column_stack([x, y])
    centered = coords - coords.mean(axis=0)
    # First PC = eigenvector of the largest eigenvalue of the covariance matrix.
    cov = np.cov(centered, rowvar=False)
    eigvals, eigvecs = np.linalg.eigh(cov)
    axis = eigvecs[:, int(np.argmax(eigvals))]
    # Orient northeast: positive x (east) AND positive y (north). Flip if needed so the
    # vector's north component is positive; if it is near zero, use the east component.
    if axis[1] < 0 or (axis[1] == 0 and axis[0] < 0):
        axis = -axis
    axis = axis / np.linalg.norm(axis)
    # Compass bearing: 0 = north, 90 = east. atan2(east, north).
    bearing = float(np.degrees(np.arctan2(axis[0], axis[1])) % 360.0)
    return axis, bearing


# --- Shared cells and presence rates ----------------------------------------


def build_shared_cells(sp: pd.DataFrame):
    """Find the shared cells for one species.

    A shared cell has >= MIN_TOWS_PER_PERIOD tows in BOTH periods (early 2009-2015 and
    late 2019 onward). Returns a 3-tuple (cells, tows, shared_keys):
        cells       : DataFrame of the qualifying (lat_cell, lon_cell) pairs
        tows        : the per-tow frame with lat_cell/lon_cell/is_early/is_late
        shared_keys : set of (lat_cell, lon_cell) tuples that qualify
    Returns None if no cell qualifies.
    """
    tows = sp.copy()
    tows["lat_cell"] = _cell_index(tows["DECDEG_BEGLAT"])
    tows["lon_cell"] = _cell_index(tows["DECDEG_BEGLON"])
    tows["is_early"] = early_mask(tows)
    tows["is_late"] = late_mask(tows)

    # Cells with enough tows in each period.
    counts = (
        tows.groupby(["lat_cell", "lon_cell"])
        .agg(n_early=("is_early", "sum"), n_late=("is_late", "sum"))
        .reset_index()
    )
    keep = counts.loc[
        (counts["n_early"] >= MIN_TOWS_PER_PERIOD)
        & (counts["n_late"] >= MIN_TOWS_PER_PERIOD)
    ]
    if keep.empty:
        return None

    shared_keys = set(zip(keep["lat_cell"], keep["lon_cell"]))
    return keep[["lat_cell", "lon_cell"]].reset_index(drop=True), tows, shared_keys


def cell_table(sp: pd.DataFrame, model) -> pd.DataFrame | None:
    """Compute the full shared-cell table (geometry + depth + both rates) for a species.

    Returns None if there are no shared cells. Otherwise a DataFrame with columns:
        center_lat, center_lon, cell_depth,
        obs_rate_early, obs_rate_late, pred_rate_early, pred_rate_late
    """
    built = build_shared_cells(sp)
    if built is None:
        return None
    cells, tows, shared_keys = built

    # Presence label and the early model's predicted probability per tow. Each tow keeps
    # its own BOTTEMP/AVGDEPTH; predicted is the mean of P(present) over the cell's tows.
    tows = tows.copy()
    tows["proba"] = model.predict_proba(tows[FEATURES])[:, 1]

    # Restrict to shared cells only.
    key = list(zip(tows["lat_cell"], tows["lon_cell"]))
    tows = tows.loc[[k in shared_keys for k in key]].copy()

    # Pooled-both-periods mean depth per cell + fixed geometric center.
    geo = (
        tows.groupby(["lat_cell", "lon_cell"], as_index=False)
        .agg(cell_depth=("AVGDEPTH", "mean"))
    )
    geo["center_lat"] = geo["lat_cell"] + CELL / 2.0
    geo["center_lon"] = geo["lon_cell"] + CELL / 2.0

    # Per-period, per-cell observed and predicted presence rates.
    def period_rates(mask_col: str, suffix: str) -> pd.DataFrame:
        sub = tows.loc[tows[mask_col]]
        agg = (
            sub.groupby(["lat_cell", "lon_cell"], as_index=False)
            .agg(**{
                f"obs_rate_{suffix}": (LABEL, "mean"),
                f"pred_rate_{suffix}": ("proba", "mean"),
            })
        )
        return agg

    early_rates = period_rates("is_early", "early")
    late_rates = period_rates("is_late", "late")

    table = (
        geo.merge(early_rates, on=["lat_cell", "lon_cell"], how="inner")
        .merge(late_rates, on=["lat_cell", "lon_cell"], how="inner")
    )
    if table.empty:
        return None
    return table


# --- Center and shift math --------------------------------------------------


def _weighted_center(table: pd.DataFrame, rate_col: str) -> tuple[float, float, float]:
    """Presence-rate-weighted center of the shared cells for one period.

    Returns (lon_center, lat_center, depth_center) in degrees / metres. If the rate
    weights sum to zero, fall back to the unweighted mean so the center is defined.
    """
    w = table[rate_col].to_numpy(dtype=float)
    if w.sum() <= 0:
        w = np.ones_like(w)
    lon_c = float(np.average(table["center_lon"], weights=w))
    lat_c = float(np.average(table["center_lat"], weights=w))
    depth_c = float(np.average(table["cell_depth"], weights=w))
    return lon_c, lat_c, depth_c


def shifts_from_table(table: pd.DataFrame, axis: np.ndarray) -> dict:
    """All shifts for one shared-cell table and a fixed along-shelf axis.

    Returns pred/obs along-shelf shift (km), depth shift (m) and north-south shift (km).
    """
    # Predicted centers.
    plon_e, plat_e, pdep_e = _weighted_center(table, "pred_rate_early")
    plon_l, plat_l, pdep_l = _weighted_center(table, "pred_rate_late")
    # Observed centers.
    olon_e, olat_e, odep_e = _weighted_center(table, "obs_rate_early")
    olon_l, olat_l, odep_l = _weighted_center(table, "obs_rate_late")

    # Project the early/late centers to EPSG:5070 and take the along-shelf component.
    px, py = _to_5070(
        np.array([plon_e, plon_l, olon_e, olon_l]),
        np.array([plat_e, plat_l, olat_e, olat_l]),
    )
    pred_e = np.array([px[0], py[0]])
    pred_l = np.array([px[1], py[1]])
    obs_e = np.array([px[2], py[2]])
    obs_l = np.array([px[3], py[3]])

    pred_shelf_km = float((pred_l - pred_e) @ axis) * KM_PER_M
    obs_shelf_km = float((obs_l - obs_e) @ axis) * KM_PER_M

    return {
        "pred_shelf_km": pred_shelf_km,
        "obs_shelf_km": obs_shelf_km,
        "pred_depth_m": pdep_l - pdep_e,
        "obs_depth_m": odep_l - odep_e,
        "pred_lat_km": (plat_l - plat_e) * KM_PER_DEG_LAT,
        "obs_lat_km": (olat_l - olat_e) * KM_PER_DEG_LAT,
    }


# --- Model ------------------------------------------------------------------


def train_early_model(early_tows: pd.DataFrame):
    """Train one HistGradientBoostingClassifier on EARLY_YEARS tows for one species.

    `early_tows` is the per-species frame already restricted to the early period. Features
    are strictly BOTTEMP + AVGDEPTH; lat/lon/year can never reach the model.
    """
    _assert_features_allowed(FEATURES)
    X = early_tows[FEATURES].copy()
    y = early_tows[LABEL].astype(int)
    _assert_features_allowed(list(X.columns))
    model = HistGradientBoostingClassifier(random_state=RANDOM_STATE)
    model.fit(X, y)
    return model


# --- Extrapolation diagnostics ----------------------------------------------


def frac_late_outside_train_temp(sp: pd.DataFrame) -> float:
    """Share of late-period tows in shared cells with BOTTEMP outside the early tows'
    min-max range, for one species."""
    built = build_shared_cells(sp)
    if built is None:
        return float("nan")
    _cells, tows, shared_keys = built
    key = list(zip(tows["lat_cell"], tows["lon_cell"]))
    in_shared = tows.loc[[k in shared_keys for k in key]]
    early = in_shared.loc[early_mask(in_shared), "BOTTEMP"]
    late = in_shared.loc[late_mask(in_shared), "BOTTEMP"]
    if late.empty or early.empty:
        return float("nan")
    lo, hi = early.min(), early.max()
    outside = ((late < lo) | (late > hi)).sum()
    return float(outside / len(late))


def grid_extrapolation_shares() -> dict:
    """Share of grid cells in grid_predictions.csv at +1C and +2C whose temperature is
    above the 2009-2018 models' maximum training temperature.

    The grid's BOTTEMP column already holds baseline + delta per row (see
    data/processed/grid_predictions.csv), so we read it directly rather than touch
    src/scenarios.py (brief change 6). Returns {species: {delta: frac, ...}, ...} plus an
    "_overall" summary per delta averaged over species.
    """
    tows = pd.read_csv(TOWS_PATH, dtype={"ID": str})
    y = pd.to_numeric(tows["EST_YEAR"], errors="coerce")
    train = tows.loc[(y >= SCENARIO_TRAIN_YEARS[0]) & (y <= SCENARIO_TRAIN_YEARS[1])]

    grid = pd.read_csv(GRID_PREDICTIONS_PATH, dtype={"svspp": str})
    out: dict = {}
    overall: dict[int, list[float]] = {d: [] for d in SCENARIO_DELTAS}
    max_train_temp = float(train["BOTTEMP"].max())  # same tows -> one max for all species
    for species in TARGET_SPECIES:
        sp_grid = grid.loc[grid["species"] == species]
        per_delta = {}
        for d in SCENARIO_DELTAS:
            cells = sp_grid.loc[sp_grid["delta"] == d]
            if cells.empty:
                per_delta[d] = float("nan")
                continue
            frac = float((cells["BOTTEMP"] > max_train_temp).mean())
            per_delta[d] = frac
            overall[d].append(frac)
        out[species] = per_delta
    out["_overall"] = {
        d: (float(np.mean(v)) if v else float("nan")) for d, v in overall.items()
    }
    out["_max_train_temp"] = max_train_temp
    return out


# --- Per-species driver -----------------------------------------------------


def run_hindcast(frame: pd.DataFrame, species: str, axis: np.ndarray, bearing: float) -> dict:
    """Full revised hindcast for one species (point estimate only, D-020).

    Returns a dict matching HINDCAST_COLUMNS.
    """
    sp = frame.loc[frame["species"] == species].copy()

    # Point estimate: early model on the real early tows, real shared cells.
    model = train_early_model(sp.loc[early_mask(sp)])
    table = cell_table(sp, model)
    assert table is not None and not table.empty, (
        f"{species}: no cells had >= {MIN_TOWS_PER_PERIOD} tows in both periods."
    )
    point = shifts_from_table(table, axis)

    # Supporting counts (real data).
    present = sp.loc[sp[LABEL] == 1]
    n_present_early = int(early_mask(present).sum())
    n_present_late = int(late_mask(present).sum())

    return {
        "species": species,
        "svspp": TARGET_SPECIES[species],
        "axis_bearing_deg": round(bearing, 2),
        "pred_shelf_km": round(point["pred_shelf_km"], 2),
        "obs_shelf_km": round(point["obs_shelf_km"], 2),
        "pred_depth_m": round(point["pred_depth_m"], 2),
        "obs_depth_m": round(point["obs_depth_m"], 2),
        "pred_lat_km": round(point["pred_lat_km"], 2),
        "obs_lat_km": round(point["obs_lat_km"], 2),
        "n_cells": int(len(table)),
        "n_present_early": n_present_early,
        "n_present_late": n_present_late,
        "frac_late_outside_train_temp": round(frac_late_outside_train_temp(sp), 4),
    }


def run_all(frame: pd.DataFrame, axis: np.ndarray, bearing: float) -> pd.DataFrame:
    rows = []
    for species in TARGET_SPECIES:
        print(f"[hindcast] running {species} (single early-model fit, point estimate)...")
        rows.append(run_hindcast(frame, species, axis, bearing))
    return pd.DataFrame(rows, columns=HINDCAST_COLUMNS)


def save_hindcast(hindcast: pd.DataFrame, path: str = HINDCAST_PATH) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    hindcast.to_csv(path, index=False)


# --- Script entry point -----------------------------------------------------


def main() -> None:
    print("=== Shifting Grounds: hindcast check (task 4.1, revised per HINDCAST_BRIEF.md) ===")
    print(
        f"[hindcast] train years {EARLY_YEARS[0]}-{EARLY_YEARS[1]}; "
        f"compare against {LATE_MIN_YEAR} onward; "
        f"shared cells need >= {MIN_TOWS_PER_PERIOD} tows per period; "
        f"POINT ESTIMATES only (no bootstrap, no verdict -- D-020)"
    )
    print(f"[hindcast] features (and ONLY these): {FEATURES}")
    _assert_features_allowed(FEATURES)

    frame = load_hindcast_frame()
    print(
        f"[hindcast] joined frame: {len(frame)} (tow, species) rows across "
        f"{frame['species'].nunique()} species"
    )

    # Along-shelf axis from ALL 2009-onward tow positions (survey footprint).
    axis, bearing = along_shelf_axis(frame)
    print(
        f"[hindcast] along-shelf axis (first PC, EPSG:5070): bearing {bearing:.2f} deg "
        f"(0=N, 90=E); unit vector east={axis[0]:+.4f}, north={axis[1]:+.4f}"
    )

    hindcast = run_all(frame, axis, bearing)

    # --- Readable table ---
    print(
        "\n[hindcast] predicted vs observed along-shelf shift (km, + = toward NE along "
        "shelf) and depth shift (m, + = deeper). Point estimates; small shifts may be noise:"
    )
    print(
        f"{'species':>16} | {'pred km':>8} | {'obs km':>8} | "
        f"{'pred m':>8} | {'obs m':>8} | cells | pres e/l"
    )
    for _, r in hindcast.iterrows():
        print(
            f"{r['species']:>16} | "
            f"{r['pred_shelf_km']:+8.2f} | {r['obs_shelf_km']:+8.2f} | "
            f"{r['pred_depth_m']:+8.2f} | {r['obs_depth_m']:+8.2f} | "
            f"{r['n_cells']:5d} | {r['n_present_early']:4d}/{r['n_present_late']:<4d}"
        )

    print("\n[hindcast] secondary north-south latitude shift (km, + = north):")
    for _, r in hindcast.iterrows():
        print(
            f"{r['species']:>16}: predicted {r['pred_lat_km']:+7.2f} | "
            f"observed {r['obs_lat_km']:+7.2f}"
        )

    # --- Extrapolation diagnostics ---
    print("\n[hindcast] extrapolation diagnostic 1 -- share of LATE tows in shared cells")
    print("           with BOTTEMP outside the early (2009-2015) training min-max range:")
    for _, r in hindcast.iterrows():
        print(f"{r['species']:>16}: {r['frac_late_outside_train_temp']:.1%}")

    grid_ex = grid_extrapolation_shares()
    print(
        "\n[hindcast] extrapolation diagnostic 2 -- share of grid cells above the "
        f"2009-2018 models' max training temp ({grid_ex['_max_train_temp']:.2f} C):"
    )
    for species in TARGET_SPECIES:
        d = grid_ex[species]
        print(f"{species:>16}: +1C {d[1]:.1%} | +2C {d[2]:.1%}")
    ov = grid_ex["_overall"]
    print(f"{'(mean over species)':>16}: +1C {ov[1]:.1%} | +2C {ov[2]:.1%}")

    save_hindcast(hindcast)
    print(f"\n[hindcast] saved {len(hindcast)} rows to {HINDCAST_PATH}")
    print(f"[hindcast] columns: {list(hindcast.columns)}")


if __name__ == "__main__":
    main()
