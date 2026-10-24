"""Lease overlap signals for Shifting Grounds (task 6.1).

This turns the per-cell warming projections (data/processed/grid_predictions.csv) into a
planning signal for every active offshore wind lease and target species. For each lease,
species and scenario it computes the area-weighted mean habitat suitability of the grid
cells the lease overlaps, the percent change from the +0 deg C baseline to the warmed
scenario, and a categorical signal (Rising / Falling / Stable / Uncertain) with a fixed
suggestion text.

Everything here is implemented EXACTLY as design.md's "## Lease overlap signals" section
specifies. The thresholds and the four suggestion-text strings are locked-in constants
(design.md tables; docs/DECISIONS.md D-006 and D-011). Per .kiro/steering/workflow.md
they must NOT be changed without logging a decision, so they live as named constants at
the top of this module.

Method (design.md "## Lease overlap signals"):

- "Load active lease areas from the BOEM shapefile. Use leases, not planning areas."
  We load the BOEM Offshore_Wind_Leases_outlines layer: one dissolved polygon per issued
  lease, carrying its lease number, company and project name (D-015). These are the issued
  (active) wind leases, as opposed to the MHK leases-and-planning-areas file, which we do
  NOT use.
- "For each lease, species and scenario, compute the mean suitability of the grid cells it
  overlaps, weighted by overlap area." Each grid cell is a 0.2 deg square built from its
  lat_cell/lon_cell lower-left corner (CELL from scenarios.py). We intersect the lease
  polygon with every cell and weight each cell's suitability by the intersection area.
- "Percent change = (scenario - baseline) / baseline, where baseline is +0 deg C."

Signal rules (design.md table; checked in this order):

| Uncertain | Species test AUC below 0.70, OR fewer than 20 tows from 2016 onward within
              25 km of the lease. Checked FIRST. A lease that overlaps no grid cells is
              also Uncertain (design.md Error Handling). |
| Rising    | Change of +10% or more |
| Falling   | Change of -10% or less |
| Stable    | Change between -10% and +10% |

Species with fewer than 50 presences are skipped entirely (design.md Error Handling,
D-011). None of the six target species hits this in the current data, but the rule is
enforced so the pipeline stays correct if the data changes.

CRS handling: grid cells and lease polygons both start in EPSG:4326 (lon/lat degrees).
Degrees are not a constant area, so for TRUE area weights we reproject both to an
equal-area projection, EPSG:5070 (NAD83 / CONUS Albers), before intersecting and before
measuring the 25 km survey-coverage distance (D-016). All geometric area and distance math
happens in that metric CRS.

Task 6.3 will EXTEND this module with join_revenue(); this file deliberately stops at the
signals and leaves a documented stub for it.

Output (written by task 6.3, not here): data/processed/lease_signals.csv. Task 6.1 only
computes the signals DataFrame and reports it.
"""

from __future__ import annotations

import json
import os

import geopandas as gpd
import pandas as pd
from shapely.geometry import box

from prepare_data import PRESENCE_PATH, PROCESSED_DIR, REPO_ROOT, TARGET_SPECIES, TOWS_PATH
from scenarios import CELL, GRID_PREDICTIONS_PATH
from train import METRICS_PATH

# --- Paths ------------------------------------------------------------------

# The BOEM "outlines" layer: one dissolved polygon per issued (active) wind lease.
# We use leases, NOT the separate MHK leases-and-planning-areas file (design.md).
LEASES_PATH = os.path.join(
    REPO_ROOT,
    "data",
    "raw",
    "boem",
    "boem-renewable-energy-shapefiles_0",
    "Offshore_Wind_Leases_outlines.shp",
)
# Written by task 6.3 (revenue join), not by this task.
LEASE_SIGNALS_PATH = os.path.join(PROCESSED_DIR, "lease_signals.csv")

# --- Locked-in constants (design.md "## Lease overlap signals" + D-006, D-011) ---
# DO NOT change these without logging a decision in docs/DECISIONS.md
# (.kiro/steering/workflow.md guardrail: never silently change signal thresholds or
# suggestion text).

# Rising: change of +10% or more. Falling: change of -10% or less. Stable: in between.
RISING_THRESHOLD = 0.10   # +10% as a fraction
FALLING_THRESHOLD = -0.10  # -10% as a fraction

# Uncertain rule: species test AUC below this, OR too few nearby recent tows.
MIN_AUC = 0.70
# ... fewer than this many tows from MIN_COVERAGE_YEAR onward within COVERAGE_RADIUS_KM.
MIN_NEARBY_TOWS = 20
COVERAGE_RADIUS_KM = 25.0
MIN_COVERAGE_YEAR = 2016

# Species with fewer than this many presences are skipped (design.md Error Handling).
MIN_PRESENCES = 50

# Signal labels.
RISING = "Rising"
FALLING = "Falling"
STABLE = "Stable"
UNCERTAIN = "Uncertain"

# Fixed suggestion text, one per signal. Quoted VERBATIM from design.md's suggestion
# table. These strings are part of the spec contract and must never be reworded here.
SUGGESTIONS = {
    RISING: (
        "Fishing interest here is likely to grow over the project's life. Options to "
        "plan for: wider turbine spacing or transit lanes for mobile gear, compensation "
        "that accounts for future as well as past catch, construction timed around key "
        "seasons, and ongoing monitoring."
    ),
    FALLING: (
        "Past catch data likely overstates future overlap here. Options: weigh projected "
        "as well as historical data in planning, and keep monitoring."
    ),
    STABLE: "Today's exposure data is a fair guide to future overlap here.",
    UNCERTAIN: (
        "The model isn't confident enough here to say. Rely on historical data and local "
        "fishermen's knowledge, and gather more survey data."
    ),
}

# Equal-area CRS used for all area and distance math (NAD83 / CONUS Albers, metres).
EQUAL_AREA_CRS = "EPSG:5070"
# The BOEM shapefile and the grid are both lon/lat degrees.
GEOGRAPHIC_CRS = "EPSG:4326"
KM_PER_M = 1.0 / 1000.0

# Canonical lease_signals columns produced here (task 6.3 adds the revenue column).
# Baseline suitability, scenario suitability and change are the raw numbers the app and
# the DeepSeek brief read.
SIGNAL_COLUMNS = [
    "lease_id",        # BOEM lease number (e.g. "OCS-A 0501")
    "lease_name",      # project / company name for display
    "species",         # target-species key from TARGET_SPECIES
    "svspp",           # zero-padded 3-char species code
    "delta",           # warming scenario in deg C (1 or 2; +0 is the baseline)
    "baseline",        # area-weighted mean suitability at +0 deg C
    "scenario",        # area-weighted mean suitability at +delta deg C
    "change",          # (scenario - baseline) / baseline
    "signal",          # Rising / Falling / Stable / Uncertain
    "suggestion",      # fixed suggestion text paired with the signal
    "auc",             # species test AUC (for the brief + Uncertain rule)
    "n_cells",         # grid cells the lease overlaps
    "n_nearby_tows",   # 2016+ tows within 25 km (for the Uncertain rule)
]


# --- Loaders ----------------------------------------------------------------


def load_leases(path: str = LEASES_PATH) -> gpd.GeoDataFrame:
    """Load the active BOEM wind lease polygons (the outlines layer).

    Returns a GeoDataFrame in the equal-area CRS with ONE row per lease number and two
    display columns, ``lease_id`` (BOEM lease number) and ``lease_name`` (project name,
    falling back to company then lease number). A few lease numbers appear as several
    polygon rows in the shapefile (a main area plus export-cable or sub-block pieces);
    we DISSOLVE those into one multipolygon per lease so the area-weighted suitability
    spans the whole lease and downstream tables carry one row per (lease, species,
    scenario). Invalid geometries are repaired with a zero-width buffer first.
    """
    leases = gpd.read_file(path)
    if leases.crs is None:
        leases = leases.set_crs(GEOGRAPHIC_CRS)

    # Stable id + human-readable name for the app and the brief.
    leases["lease_id"] = leases["LEASE_NUMB"].astype(str).str.strip()
    name = leases.get("PROJECT_NA")
    company = leases.get("COMPANY")
    leases["lease_name"] = (
        name.fillna("").astype(str).str.strip()
        if name is not None
        else ""
    )
    # Fall back to company, then the lease number, when the project name is blank.
    blank = leases["lease_name"].eq("") | leases["lease_name"].str.lower().eq("none")
    if company is not None:
        leases.loc[blank, "lease_name"] = (
            company.astype(str).str.replace(r"\s+", " ", regex=True).str.strip()
        )
    still_blank = leases["lease_name"].eq("")
    leases.loc[still_blank, "lease_name"] = leases.loc[still_blank, "lease_id"]

    # Repair any invalid rings before we dissolve/intersect (buffer(0) is the fix).
    leases["geometry"] = leases.geometry.buffer(0)

    # One geometry per lease number: merge the multiple polygon rows some leases have
    # (a lease can carry a main area plus export-cable/sub-block pieces). Keep the first
    # display name seen for each lease id.
    dissolved = leases.dissolve(by="lease_id", aggfunc={"lease_name": "first"})
    dissolved = dissolved.reset_index()

    return dissolved.to_crs(EQUAL_AREA_CRS)


def load_grid_predictions(path: str = GRID_PREDICTIONS_PATH) -> pd.DataFrame:
    """Load the per-cell, per-species, per-scenario suitability table (svspp as str)."""
    return pd.read_csv(path, dtype={"svspp": str})


def load_metrics(path: str = METRICS_PATH) -> dict:
    """Load models/metrics.json (per-species test AUC and class balance)."""
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)


def load_tows(path: str = TOWS_PATH) -> pd.DataFrame:
    """Load the tows table (one row per real tow). ID kept as string."""
    return pd.read_csv(path, dtype={"ID": str})


def load_presence(path: str = PRESENCE_PATH) -> pd.DataFrame:
    """Load the long presence table (ID, species, SVSPP, present)."""
    return pd.read_csv(path, dtype={"ID": str, "SVSPP": str})


# --- Grid geometry ----------------------------------------------------------


def grid_cells_to_gdf(
    grid_preds: pd.DataFrame, cell: float = CELL
) -> gpd.GeoDataFrame:
    """Build a GeoDataFrame of unique grid-cell squares in the equal-area CRS.

    Each cell is the ``cell`` x ``cell`` degree square whose lower-left corner is
    (lon_cell, lat_cell) -- the same snapping scenarios.py / hindcast.py use. We take the
    DISTINCT cells (grid_predictions repeats each cell once per species x scenario), build
    the square polygons in lon/lat, then reproject to the equal-area CRS so intersection
    areas are true areas. ``cell_key`` joins back to the suitability rows.
    """
    cells = (
        grid_preds[["lat_cell", "lon_cell"]]
        .drop_duplicates()
        .reset_index(drop=True)
        .copy()
    )
    # Lower-left corner at (lon_cell, lat_cell); square of side `cell` degrees.
    geometry = [
        box(lon, lat, lon + cell, lat + cell)
        for lat, lon in zip(cells["lat_cell"], cells["lon_cell"])
    ]
    cells["cell_key"] = list(zip(cells["lat_cell"], cells["lon_cell"]))
    gdf = gpd.GeoDataFrame(cells, geometry=geometry, crs=GEOGRAPHIC_CRS)
    return gdf.to_crs(EQUAL_AREA_CRS)


def tows_to_gdf(tows: pd.DataFrame) -> gpd.GeoDataFrame:
    """Build a GeoDataFrame of tow points in the equal-area CRS (for the 25 km test)."""
    gdf = gpd.GeoDataFrame(
        tows.copy(),
        geometry=gpd.points_from_xy(tows["DECDEG_BEGLON"], tows["DECDEG_BEGLAT"]),
        crs=GEOGRAPHIC_CRS,
    )
    return gdf.to_crs(EQUAL_AREA_CRS)


# --- Overlap weights --------------------------------------------------------


def cell_overlap_weights(
    lease_geom, cells_gdf: gpd.GeoDataFrame
) -> pd.DataFrame:
    """Return the grid cells a single lease overlaps and their intersection areas.

    Intersects the lease polygon (equal-area CRS) with every candidate cell and keeps
    those with positive overlap area. Returns a DataFrame with cell_key and area_weight
    (the intersection area in m^2). Empty if the lease overlaps no cells.
    """
    # Only test cells whose bounding box touches the lease (cheap spatial prefilter).
    candidates = cells_gdf.loc[cells_gdf.geometry.intersects(lease_geom)]
    if candidates.empty:
        return pd.DataFrame(columns=["cell_key", "area_weight"])

    inter = candidates.geometry.intersection(lease_geom)
    weights = inter.area
    out = pd.DataFrame(
        {"cell_key": candidates["cell_key"].to_numpy(), "area_weight": weights.to_numpy()}
    )
    return out.loc[out["area_weight"] > 0].reset_index(drop=True)


def nearby_tow_count(
    lease_geom, tow_points: gpd.GeoDataFrame, radius_km: float = COVERAGE_RADIUS_KM
) -> int:
    """Count tow points within ``radius_km`` of the lease polygon (equal-area CRS).

    Distance is point-to-polygon in metres, so a tow inside the lease has distance 0.
    ``tow_points`` should already be filtered to the coverage years (2016 onward).
    """
    if tow_points.empty:
        return 0
    dist_m = tow_points.geometry.distance(lease_geom)
    return int((dist_m <= radius_km / KM_PER_M).sum())


# --- Signal classification --------------------------------------------------


def classify_signal(change: float) -> str:
    """Map a percent change (fraction) to Rising / Falling / Stable.

    Rising at +10% or more; Falling at -10% or less; Stable strictly in between. The
    Uncertain case is decided BEFORE this is called (AUC / coverage / no-overlap), per
    design.md, so this function never returns Uncertain.
    """
    if change >= RISING_THRESHOLD:
        return RISING
    if change <= FALLING_THRESHOLD:
        return FALLING
    return STABLE


# --- Core: lease signals ----------------------------------------------------


def lease_signals(
    grid_preds: pd.DataFrame,
    leases: gpd.GeoDataFrame,
    tows: pd.DataFrame,
    metrics: dict,
    presence: pd.DataFrame | None = None,
    verbose: bool = True,
) -> pd.DataFrame:
    """Compute the overlap signal for every (active lease, species, warmed scenario).

    For each lease, intersect it with the grid to get area weights, then for each species
    and each warmed scenario (delta > 0) compute the area-weighted mean suitability at the
    baseline (+0) and at the scenario, the percent change, and the signal + suggestion.

    Uncertain is decided first (low AUC, fewer than 20 nearby 2016+ tows, or no overlap);
    otherwise the signal comes from the percent-change thresholds. Species with fewer than
    MIN_PRESENCES presences are skipped entirely. Returns a DataFrame with SIGNAL_COLUMNS.
    """

    def log(msg: str) -> None:
        if verbose:
            print(msg)

    # --- <50-presence skip (design.md Error Handling / D-011) ----------------
    skip_species: set[str] = set()
    if presence is not None:
        counts = presence.groupby("species")["present"].sum()
        for species in TARGET_SPECIES:
            n_present = int(counts.get(species, 0))
            if n_present < MIN_PRESENCES:
                skip_species.add(species)
                log(
                    f"[overlap] skipping {species}: only {n_present} presences "
                    f"(< {MIN_PRESENCES}); too rare to model (design.md)."
                )
    active_species = [s for s in TARGET_SPECIES if s not in skip_species]

    # Per-species test AUC for the Uncertain rule and the brief.
    auc = {s: (metrics.get(s, {}) or {}).get("test_auc") for s in TARGET_SPECIES}

    # Geometry: cell squares and 2016+ tow points, both in the equal-area CRS.
    cells_gdf = grid_cells_to_gdf(grid_preds)
    recent_year = pd.to_numeric(tows["EST_YEAR"], errors="coerce")
    recent_tows = tows.loc[recent_year >= MIN_COVERAGE_YEAR]
    tow_points = tows_to_gdf(recent_tows)
    log(
        f"[overlap] {len(leases)} active leases, {len(cells_gdf)} grid cells, "
        f"{len(tow_points)} tows from {MIN_COVERAGE_YEAR} onward for coverage test"
    )

    # Suitability lookup: (species, delta) -> {cell_key: suitability}.
    grid_preds = grid_preds.copy()
    grid_preds["cell_key"] = list(zip(grid_preds["lat_cell"], grid_preds["lon_cell"]))
    deltas = sorted(grid_preds["delta"].unique())
    baseline_delta = min(deltas)            # +0 deg C
    warmed_deltas = [d for d in deltas if d != baseline_delta]  # +1, +2

    # Fast lookup of suitability by (species, delta, cell_key).
    suit = {
        (sp, d): dict(zip(g["cell_key"], g["suitability"]))
        for (sp, d), g in grid_preds.groupby(["species", "delta"])
    }

    rows: list[dict] = []
    for _, lease in leases.iterrows():
        geom = lease.geometry
        lease_id = lease["lease_id"]
        lease_name = lease["lease_name"]

        weights = cell_overlap_weights(geom, cells_gdf)
        n_cells = len(weights)
        n_nearby = nearby_tow_count(geom, tow_points)

        for species in active_species:
            code = TARGET_SPECIES[species]
            species_auc = auc.get(species)

            # --- Uncertain, checked FIRST (design.md table) ------------------
            uncertain = (
                n_cells == 0
                or species_auc is None
                or species_auc < MIN_AUC
                or n_nearby < MIN_NEARBY_TOWS
            )

            # Area-weighted baseline suitability (needed for both the number display and
            # the change). If the lease overlaps no cells, suitability is undefined ->
            # NaN, and the signal is Uncertain anyway.
            def weighted_mean(delta: int) -> float:
                if n_cells == 0:
                    return float("nan")
                table = suit.get((species, delta), {})
                vals = weights["cell_key"].map(table)
                w = weights["area_weight"]
                total = w.sum()
                if total <= 0 or vals.isna().all():
                    return float("nan")
                return float((vals * w).sum() / total)

            baseline = weighted_mean(baseline_delta)

            for delta in warmed_deltas:
                scenario = weighted_mean(delta)
                if n_cells == 0 or baseline != baseline or baseline == 0:
                    # NaN baseline (no overlap) or zero baseline -> change undefined.
                    change = float("nan")
                else:
                    change = (scenario - baseline) / baseline

                if uncertain:
                    signal = UNCERTAIN
                else:
                    signal = classify_signal(change)

                rows.append(
                    {
                        "lease_id": lease_id,
                        "lease_name": lease_name,
                        "species": species,
                        "svspp": code,
                        "delta": int(delta),
                        "baseline": baseline,
                        "scenario": scenario,
                        "change": change,
                        "signal": signal,
                        "suggestion": SUGGESTIONS[signal],
                        "auc": species_auc,
                        "n_cells": n_cells,
                        "n_nearby_tows": n_nearby,
                    }
                )

    signals = pd.DataFrame(rows, columns=SIGNAL_COLUMNS)
    signals = signals.sort_values(
        ["lease_id", "species", "delta"]
    ).reset_index(drop=True)
    return signals


# --- Revenue join (task 6.3) ------------------------------------------------


def join_revenue(signals, revenue, name_map):  # noqa: ANN001
    """Join the 5-year average NOAA value to each lease and species (TASK 6.3).

    Intentionally not implemented in task 6.1. Task 6.3 will add the revenue column and
    the "no data" handling, then write data/processed/lease_signals.csv. See design.md
    "### Revenue join".
    """
    raise NotImplementedError(
        "join_revenue is implemented in task 6.3, not task 6.1."
    )


# --- Script entry point -----------------------------------------------------


def main() -> None:
    print("=== Shifting Grounds: lease overlap signals (task 6.1) ===")
    print(
        f"[overlap] thresholds: Rising >= +{RISING_THRESHOLD:.0%}, "
        f"Falling <= {FALLING_THRESHOLD:.0%}, Stable in between; "
        f"Uncertain if AUC < {MIN_AUC} or < {MIN_NEARBY_TOWS} tows "
        f"({MIN_COVERAGE_YEAR}+) within {COVERAGE_RADIUS_KM:.0f} km"
    )
    print(f"[overlap] equal-area CRS for area/distance math: {EQUAL_AREA_CRS}")

    leases = load_leases()
    grid_preds = load_grid_predictions()
    tows = load_tows()
    metrics = load_metrics()
    presence = load_presence()

    print(f"[overlap] loaded {len(leases)} active lease polygons from {LEASES_PATH}")

    signals = lease_signals(grid_preds, leases, tows, metrics, presence=presence)

    # --- Report -------------------------------------------------------------
    n_leases = signals["lease_id"].nunique()
    n_species = signals["species"].nunique()
    overlapping = signals.loc[signals["n_cells"] > 0, "lease_id"].nunique()
    print(
        f"[overlap] computed {len(signals)} signal rows "
        f"({n_leases} leases x {n_species} species x warmed scenarios); "
        f"{overlapping} leases overlap at least one grid cell"
    )

    print("[overlap] signal counts (all leases x species x scenarios):")
    for sig, n in signals["signal"].value_counts().items():
        print(f"         {sig:>10}: {n}")

    # A few concrete examples from leases that actually overlap the grid, +2 deg C.
    print("[overlap] example lease/species signals at +2 deg C (overlapping leases):")
    examples = signals.loc[(signals["delta"] == 2) & (signals["n_cells"] > 0)]
    for _, r in examples.head(12).iterrows():
        base = "nan" if pd.isna(r["baseline"]) else f"{r['baseline']:.3f}"
        scen = "nan" if pd.isna(r["scenario"]) else f"{r['scenario']:.3f}"
        chg = "nan" if pd.isna(r["change"]) else f"{r['change']:+.1%}"
        print(
            f"         {r['lease_id']:>11} {r['lease_name'][:28]:<28} "
            f"{r['species']:>16}: {base} -> {scen} ({chg}) [{r['signal']}]"
        )

    print(
        "[overlap] NOTE: data/processed/lease_signals.csv is written by task 6.3 "
        "(revenue join); task 6.1 computes the signals only."
    )


if __name__ == "__main__":
    main()
