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

Task 6.3 EXTENDS this module with join_revenue(): it attaches the most-recent-5-years
average NOAA annual value to each (lease, species) signal row through the human-confirmed
data/processed/name_map.csv, showing "no data" (not 0) when nothing matches, and main()
writes the full table to data/processed/lease_signals.csv.

Output: data/processed/lease_signals.csv -- the per-(lease, species, scenario) table the
app reads: the signal + numbers + the 5-year revenue value + the fixed suggestion.
"""

from __future__ import annotations

import json
import os
import re

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

# --- Revenue inputs/outputs (tasks 6.2 / 6.3) -------------------------------
# NOAA GARFO "ALL_WEA_BY_AREA" landings-and-value export (2008-2025), one row per
# (year, lease area, species). Lives under data/raw/ and is gitignored.
REVENUE_PATH = os.path.join(
    REPO_ROOT,
    "data",
    "raw",
    "revenue",
    "Landing and Revenue Data for Wind Energy Lease Areas, 2008-2025.csv",
)
# Cleaned, numeric per-(area, species, year) revenue table (written by task 6.2).
REVENUE_CLEAN_PATH = os.path.join(PROCESSED_DIR, "revenue_clean.csv")
# DRAFT name map (written by task 6.2, confirmed by the human before task 6.3 uses it).
NAME_MAP_PATH = os.path.join(PROCESSED_DIR, "name_map.csv")

# Number of most-recent available years to average for the revenue context (D-011:
# "Revenue is the 5-year average"). The newest year in this export is 2025, so the
# 5-year window is 2021-2025.
REVENUE_AVG_YEARS = 5

# --- Target-species name map: NOAA species name -> survey species key -------
# Built in task 6.2 by matching the NOAA GARFO species names to the six TARGET_SPECIES
# keys (see data/processed/column_map.md for the survey scientific/common names). Every
# one of the six is an unambiguous 1:1 match to exactly one distinct NOAA name, so all
# six are CONFIDENT. The NOAA export also carries ~132 other species we do not model;
# they are intentionally left unmapped (dropped from the revenue context, reported, not
# silently discarded). The ambiguity guardrail: if a target species had matched two or
# more plausible NOAA names, or none, it would be left UNCERTAIN here for the human --
# none did.
SPECIES_NAME_MAP = {
    # NOAA species name         # survey key        # NOAA distinct alternatives ruled out
    "SQUID (LONGFIN)":  "longfin_squid",    # vs "SQUID (ILLEX)" (shortfin, a different squid)
    "FLOUNDER,SUMMER":  "summer_flounder",  # unique among the many FLOUNDER,* names
    "SEA BASS,BLACK":   "black_sea_bass",   # unique
    "SCUP":             "scup",             # single SCUP row; the PORGY,* names are other species
    "HAKE,SILVER":      "silver_hake",      # vs HAKE,WHITE / HAKE,RED / HAKE,OFFSHORE / HAKE,SPOTTED
    "COD":              "atlantic_cod",     # single COD row, FMP "Northeast Multispecies" = Gadus morhua
}

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
    "avg_value",       # 5-year avg NOAA annual value (task 6.3), or "no data" (D-021)
]

# The columns lease_signals() itself produces (everything except the revenue column, which
# join_revenue() appends in task 6.3). Keeping this separate from SIGNAL_COLUMNS means the
# signals table carries no empty avg_value placeholder that would collide in the merge.
_SIGNAL_ONLY_COLUMNS = [c for c in SIGNAL_COLUMNS if c != "avg_value"]


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
    MIN_PRESENCES presences are skipped entirely. Returns a DataFrame with the signal
    columns (SIGNAL_COLUMNS minus avg_value, which join_revenue() appends in task 6.3).
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

    signals = pd.DataFrame(rows, columns=_SIGNAL_ONLY_COLUMNS)
    signals = signals.sort_values(
        ["lease_id", "species", "delta"]
    ).reset_index(drop=True)
    return signals


# --- Revenue cleaning + draft name map (task 6.2) ---------------------------


def _parse_money(series: pd.Series) -> pd.Series:
    """Parse a '$1,234' / '1,234' money or count column to float.

    Strips '$', thousands commas and surrounding whitespace, then coerces to numeric.
    Blank/unparseable cells become NaN (reported by the caller, never silently zeroed).
    """
    cleaned = (
        series.astype(str)
        .str.replace(r"[\$,]", "", regex=True)
        .str.strip()
        .replace({"": None, "nan": None, "None": None})
    )
    return pd.to_numeric(cleaned, errors="coerce")


def normalize_area_code(raw: str) -> str | None:
    """Normalize a NOAA lease-area string to the BOEM ``lease_id`` spelling.

    NOAA writes areas two ways in this export -- ``OCS-A-0562`` (dashes) and
    ``OCS_A_0482`` (underscores) -- while BOEM's ``lease_id`` is ``OCS-A 0562``
    (dash then space). We parse out the region letter and the numeric lease number
    and re-emit the BOEM form, so the match is on the lease NUMBER, not on punctuation.
    Returns None for anything that does not look like an OCS lease code (reported,
    not guessed).
    """
    m = re.match(r"^OCS[-_ ]?([A-Za-z])[-_ ]?0*(\d+)\s*$", str(raw).strip())
    if not m:
        return None
    letter = m.group(1).upper()
    number = m.group(2).zfill(4)
    return f"OCS-{letter} {number}"


def clean_revenue(
    path: str = REVENUE_PATH, verbose: bool = True
) -> pd.DataFrame:
    """Load and clean the NOAA GARFO wind-area revenue CSV (task 6.2).

    Returns a tidy per-(area, species, year) table with numeric value and landings and a
    ``lease_id`` column (the BOEM spelling, or NaN when the area has no BOEM match). No
    rows are dropped silently: every filter prints a before/after count and a reason.

    Columns out:
      year, noaa_area, lease_id, noaa_species, nominal_value, value_2025, landings_lb
    """

    def log(msg: str) -> None:
        if verbose:
            print(msg)

    raw = pd.read_csv(path, dtype=str)
    n0 = len(raw)
    log(f"[revenue] loaded {n0} rows from {os.path.basename(path)}")
    log(f"[revenue] columns: {list(raw.columns)}")

    df = pd.DataFrame(
        {
            "year": pd.to_numeric(raw["Year"], errors="coerce").astype("Int64"),
            "noaa_area": raw["Lease Area"].astype(str).str.strip(),
            "noaa_species": raw["Species"].astype(str).str.strip(),
            "nominal_value": _parse_money(raw["Nominal Value ($)"]),
            "value_2025": _parse_money(raw["Value (2025 dollars)"]),
            "landings_lb": _parse_money(raw["Landings (pounds*)"]),
        }
    )

    # Report numeric-parse gaps (kept as NaN, not dropped).
    n_val_na = int(df["value_2025"].isna().sum())
    n_year_na = int(df["year"].isna().sum())
    log(
        f"[revenue] numeric parse: {n_val_na} rows have no 2025-dollar value (NaN), "
        f"{n_year_na} rows have an unparseable year (NaN). These are kept, not dropped."
    )

    # Attach the BOEM lease_id via number-based normalization.
    df["lease_id"] = df["noaa_area"].map(normalize_area_code)
    unmatched_areas = sorted(
        df.loc[df["lease_id"].isna(), "noaa_area"].unique()
    )
    log(
        f"[revenue] area match: {df['lease_id'].notna().sum()} rows carry a lease_id; "
        f"{df['lease_id'].isna().sum()} rows have no recognizable OCS code"
    )
    if unmatched_areas:
        log(f"[revenue]   un-normalizable area strings: {unmatched_areas}")

    log(
        f"[revenue] cleaned table: {len(df)} rows "
        f"(no rows dropped; row count unchanged from {n0})"
    )
    return df


def build_name_map(
    revenue: pd.DataFrame,
    leases: gpd.GeoDataFrame,
    verbose: bool = True,
) -> pd.DataFrame:
    """Build the DRAFT data/processed/name_map.csv (task 6.2).

    Two kinds of rows, one table (design.md "### Revenue join" -- a mapping table the
    human confirms before the revenue join in task 6.3):

      kind="species": NOAA species name -> survey species key (one row per distinct NOAA
                       species; the six target species are mapped, the rest left blank).
      kind="area":    NOAA lease area   -> BOEM lease_id (one row per distinct NOAA area).

    Every row carries ``confidence`` ("confident" / "UNCERTAIN") and a ``notes`` column.
    AMBIGUOUS matches are never guessed: they are emitted as UNCERTAIN with a note so the
    human decides. This draft is explicitly unconfirmed -- the ``status`` column is
    "DRAFT" on every row until the human confirms.
    """

    def log(msg: str) -> None:
        if verbose:
            print(msg)

    rows: list[dict] = []

    # --- Species rows --------------------------------------------------------
    noaa_species = sorted(revenue["noaa_species"].dropna().unique())
    mapped_species = 0
    for name in noaa_species:
        survey_key = SPECIES_NAME_MAP.get(name)
        if survey_key is not None:
            mapped_species += 1
            rows.append(
                {
                    "kind": "species",
                    "noaa_name": name,
                    "maps_to": survey_key,
                    "confidence": "confident",
                    "status": "DRAFT",
                    "notes": "Exact 1:1 match to one target species; see column_map.md.",
                }
            )
        else:
            # Not one of the six modelled species -> intentionally unmapped. Not an
            # ambiguity; just outside scope. Recorded so nothing is dropped silently.
            rows.append(
                {
                    "kind": "species",
                    "noaa_name": name,
                    "maps_to": "",
                    "confidence": "not_target",
                    "status": "DRAFT",
                    "notes": "Not one of the 6 target species; no revenue context used.",
                }
            )

    # --- Area rows -----------------------------------------------------------
    boem_ids = set(leases["lease_id"].unique())
    noaa_areas = sorted(revenue["noaa_area"].dropna().unique())
    matched_areas = 0
    for area in noaa_areas:
        lease_id = normalize_area_code(area)
        if lease_id is None:
            rows.append(
                {
                    "kind": "area",
                    "noaa_name": area,
                    "maps_to": "",
                    "confidence": "UNCERTAIN",
                    "status": "DRAFT",
                    "notes": "Could not parse an OCS lease code from this area string.",
                }
            )
        elif lease_id in boem_ids:
            matched_areas += 1
            rows.append(
                {
                    "kind": "area",
                    "noaa_name": area,
                    "maps_to": lease_id,
                    "confidence": "confident",
                    "status": "DRAFT",
                    "notes": "Lease number matches a BOEM lease exactly (separators aside).",
                }
            )
        else:
            # Parsed to a valid OCS code, but BOEM's outlines layer has no such lease.
            # Confident it is NOT any of the 45 BOEM leases; left unmapped, flagged.
            rows.append(
                {
                    "kind": "area",
                    "noaa_name": area,
                    "maps_to": "",
                    "confidence": "UNCERTAIN",
                    "status": "DRAFT",
                    "notes": (
                        f"Parses to {lease_id} but no such lease in the BOEM outlines "
                        "layer (45 leases); no overlap geometry to join to."
                    ),
                }
            )

    name_map = pd.DataFrame(
        rows, columns=["kind", "noaa_name", "maps_to", "confidence", "status", "notes"]
    )

    log(
        f"[name_map] species rows: {len(noaa_species)} distinct NOAA species, "
        f"{mapped_species} mapped to a target species, "
        f"{len(noaa_species) - mapped_species} left unmapped (not targets)"
    )
    log(
        f"[name_map] area rows: {len(noaa_areas)} distinct NOAA areas, "
        f"{matched_areas} matched to a BOEM lease_id, "
        f"{len(noaa_areas) - matched_areas} UNCERTAIN (no BOEM lease)"
    )
    return name_map


def run_clean_revenue(verbose: bool = True) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Task 6.2 entry point: write the cleaned revenue table and the DRAFT name map.

    Writes data/processed/revenue_clean.csv and data/processed/name_map.csv (DRAFT),
    then STOPS. It does NOT run the revenue join (task 6.3) or mark the mapping confirmed.
    Returns (cleaned_revenue, draft_name_map) for the main-agent review / human checkpoint.
    """
    print("=== Shifting Grounds: clean NOAA revenue + DRAFT name map (task 6.2) ===")
    revenue = clean_revenue(verbose=verbose)
    leases = load_leases()
    name_map = build_name_map(revenue, leases, verbose=verbose)

    os.makedirs(PROCESSED_DIR, exist_ok=True)
    revenue.to_csv(REVENUE_CLEAN_PATH, index=False)
    name_map.to_csv(NAME_MAP_PATH, index=False)
    print(f"[revenue] wrote cleaned revenue -> {REVENUE_CLEAN_PATH}")
    print(f"[name_map] wrote DRAFT name map -> {NAME_MAP_PATH}")
    print(
        "[name_map] DRAFT and UNCONFIRMED: the revenue join (task 6.3) must wait until "
        "the human confirms this mapping."
    )
    return revenue, name_map


# --- Revenue join (task 6.3) ------------------------------------------------

# How the revenue column shows "no revenue matched" (design.md "### Revenue join":
# 'Show "no data" when nothing matches'; requirement 6.3: show "no data" rather than
# zero). A literal string, NOT 0 or NaN, so the app never displays a misleading $0 for a
# species NOAA never reported in that area (e.g. confidentiality-suppressed "ALL OTHERS"
# fleets, a species not landed there, or a lease with no NOAA revenue area at all).
NO_REVENUE = "no data"

# Which money column to average. revenue_clean.csv carries both the nominal dollars of
# each year and value_2025 (the same dollars inflation-adjusted to 2025). Averaging across
# a multi-year window mixes dollars from different years, so we average the inflation-
# adjusted column to keep the five years comparable (D-021). Column name from clean_revenue().
REVENUE_VALUE_COLUMN = "value_2025"


def average_recent_value(
    revenue: pd.DataFrame,
    name_map: pd.DataFrame,
    years: int = REVENUE_AVG_YEARS,
    value_column: str = REVENUE_VALUE_COLUMN,
    verbose: bool = True,
) -> tuple[pd.DataFrame, list[int]]:
    """Average each (lease_id, survey species) value over the most recent ``years``.

    design.md "### Revenue join": "take value by lease area, species and year. Average the
    most recent 5 years available." We translate the NOAA names to our own keys through the
    CONFIRMED name_map (NOAA species name -> survey species key; NOAA area -> BOEM lease_id),
    keep only rows that carry both a target species and a real BOEM lease, restrict to the
    most recent ``years`` distinct years PRESENT in the data, and take the mean annual value
    per (lease_id, species).

    Returns (per-(lease_id, species) mean-value table, the list of years averaged).
    """

    def log(msg: str) -> None:
        if verbose:
            print(msg)

    # --- Confirmed lookups from the (human-confirmed) name_map ---------------
    species_rows = name_map.loc[
        (name_map["kind"] == "species")
        & (name_map["confidence"] == "confident")
        & name_map["maps_to"].astype(str).str.len().gt(0)
    ]
    species_lookup = dict(zip(species_rows["noaa_name"], species_rows["maps_to"]))

    area_rows = name_map.loc[
        (name_map["kind"] == "area")
        & (name_map["confidence"] == "confident")
        & name_map["maps_to"].astype(str).str.len().gt(0)
    ]
    area_lookup = dict(zip(area_rows["noaa_name"], area_rows["maps_to"]))
    log(
        f"[revenue-join] confirmed name_map: {len(species_lookup)} target species, "
        f"{len(area_lookup)} NOAA areas -> BOEM lease_id"
    )

    df = revenue.copy()
    # Map NOAA names to our keys. Rows without a target species or a BOEM lease fall out of
    # the join (they become "no data" downstream) -- never silently counted as zero.
    df["species"] = df["noaa_species"].map(species_lookup)
    df["join_lease_id"] = df["noaa_area"].map(area_lookup)
    joined = df.loc[df["species"].notna() & df["join_lease_id"].notna()].copy()
    log(
        f"[revenue-join] {len(joined)} of {len(df)} revenue rows carry both a target "
        f"species and a BOEM lease (rest are non-target species / unmatched areas)"
    )

    # --- Most recent N years PRESENT in the joined revenue -------------------
    present_years = sorted(int(y) for y in joined["year"].dropna().unique())
    window_years = present_years[-years:] if present_years else []
    log(
        f"[revenue-join] most recent {years} years available: {window_years} "
        f"(of {present_years[0] if present_years else '-'}..{present_years[-1] if present_years else '-'})"
    )
    in_window = joined.loc[joined["year"].isin(window_years)].copy()

    # --- Mean annual value per (lease_id, species) ---------------------------
    # Mean over the window's rows == mean annual value per (lease, species): the NOAA export
    # has at most one row per (lease, species, year), so this averages across the years that
    # actually have a value (a year with no landing simply does not contribute a row).
    grouped = (
        in_window.groupby(["join_lease_id", "species"], as_index=False)[value_column]
        .mean()
        .rename(columns={"join_lease_id": "lease_id", value_column: "avg_value"})
    )
    log(
        f"[revenue-join] {len(grouped)} (lease, species) pairs have a {years}-year "
        f"average value from {window_years}"
    )
    return grouped, window_years


def join_revenue(signals, revenue, name_map, verbose: bool = True):  # noqa: ANN001
    """Join the 5-year average NOAA value to each lease-signal row (TASK 6.3).

    Attaches an ``avg_value`` column to every signal row: the most-recent-5-years average
    NOAA annual value for that (lease_id, species), or the string "no data" when nothing
    matches (design.md "### Revenue join"; requirement 6.3 -- "no data" rather than zero).
    "No data" covers every miss: the species was never landed/reported in that lease area
    (incl. NOAA's confidentiality-suppressed fleets), or the lease has no NOAA revenue area
    at all (e.g. the 9 leases outside the NOAA export, or the 4 NOAA areas with no BOEM
    lease). Returns a new DataFrame with SIGNAL_COLUMNS in order (avg_value last).
    """

    def log(msg: str) -> None:
        if verbose:
            print(msg)

    grouped, window_years = average_recent_value(revenue, name_map, verbose=verbose)

    # Left-join onto the signals so every (lease, species, scenario) row is kept.
    merged = signals.merge(grouped, on=["lease_id", "species"], how="left")

    # Encode misses as "no data" (string), matched rows keep the numeric mean. Mixing a
    # string sentinel into a numeric column makes it object dtype -- intended: the app
    # prints the number when present and the literal "no data" otherwise.
    matched = merged["avg_value"].notna()
    merged["avg_value"] = merged["avg_value"].where(matched, NO_REVENUE)

    # Count matched vs no-data at the (lease, species) grain (not per scenario row).
    pair = merged[["lease_id", "species", "avg_value"]].drop_duplicates(
        ["lease_id", "species"]
    )
    n_pairs = len(pair)
    n_matched_pairs = int((pair["avg_value"] != NO_REVENUE).sum())
    log(
        f"[revenue-join] {n_matched_pairs} of {n_pairs} (lease, species) pairs got a "
        f"revenue value; {n_pairs - n_matched_pairs} are \"{NO_REVENUE}\" "
        f"(5-year window {window_years})"
    )

    return merged[SIGNAL_COLUMNS]


# --- Script entry point -----------------------------------------------------


def main() -> None:
    print("=== Shifting Grounds: lease overlap signals + revenue join (tasks 6.1 + 6.3) ===")
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

    # --- Revenue join (task 6.3) --------------------------------------------
    print("[revenue-join] joining the 5-year average NOAA value to each signal row")
    revenue = pd.read_csv(REVENUE_CLEAN_PATH)
    name_map = pd.read_csv(NAME_MAP_PATH, keep_default_na=False)
    lease_signals_table = join_revenue(signals, revenue, name_map)

    os.makedirs(PROCESSED_DIR, exist_ok=True)
    lease_signals_table.to_csv(LEASE_SIGNALS_PATH, index=False)
    print(
        f"[revenue-join] wrote {len(lease_signals_table)} rows "
        f"({lease_signals_table.shape[1]} columns) -> {LEASE_SIGNALS_PATH}"
    )

    # A couple of concrete matched + no-data examples at +2 deg C.
    plus2 = lease_signals_table.loc[lease_signals_table["delta"] == 2]
    with_rev = plus2.loc[plus2["avg_value"] != NO_REVENUE]
    no_rev = plus2.loc[plus2["avg_value"] == NO_REVENUE]
    print("[revenue-join] example rows WITH a 5-year value (+2 deg C):")
    for _, r in with_rev.head(5).iterrows():
        print(
            f"         {r['lease_id']:>11} {r['species']:>16} "
            f"[{r['signal']:>9}]  ${float(r['avg_value']):,.0f}/yr"
        )
    print("[revenue-join] example rows with NO revenue match (+2 deg C):")
    for _, r in no_rev.head(5).iterrows():
        print(
            f"         {r['lease_id']:>11} {r['species']:>16} "
            f"[{r['signal']:>9}]  {r['avg_value']}"
        )


if __name__ == "__main__":
    main()
