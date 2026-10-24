"""Prepare the NOAA NEFSC fall bottom trawl survey data for Shifting Grounds.

This module turns the raw survey CSVs into the canonical processed tables that the
rest of the pipeline builds on. It is written as small, reusable functions so that
later tasks (the presence table in task 2.4) can import and extend it.

Conventions (see .kiro/steering/workflow.md):
- Never drop rows silently. Every filter reports the row count before and after and
  why rows were removed.
- Column names and species codes are the confirmed mapping in
  data/processed/column_map.md (decisions D-005, D-013).

Processed-table schema for tows.csv (per design.md):
    ID        tow / station id        (SVSTA.ID)
    EST_YEAR  survey year             (SVSTA.EST_YEAR)
    DECDEG_BEGLAT  latitude  (deg)    (SVSTA.DECDEG_BEGLAT)
    DECDEG_BEGLON  longitude (deg)    (SVSTA.DECDEG_BEGLON)
    AVGDEPTH  depth (m)               (SVSTA.AVGDEPTH)
    BOTTEMP   bottom temperature (C)  (SVSTA.BOTTEMP)
"""

from __future__ import annotations

import os

import pandas as pd

# --- Paths ------------------------------------------------------------------

# Resolve paths relative to the repo root (one level up from this file's src/).
REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

SURVEY_DIR = os.path.join(
    REPO_ROOT,
    "data",
    "raw",
    "survey",
    "22560_NEFSCFallFisheriesIndependentBottomTrawlData",
)
SVSTA_PATH = os.path.join(SURVEY_DIR, "22560_UNION_FSCS_SVSTA.csv")
SVCAT_PATH = os.path.join(SURVEY_DIR, "22560_UNION_FSCS_SVCAT.csv")
CRUISES_PATH = os.path.join(SURVEY_DIR, "22560_SVDBS_CRUISES.csv")

PROCESSED_DIR = os.path.join(REPO_ROOT, "data", "processed")
TOWS_PATH = os.path.join(PROCESSED_DIR, "tows.csv")

# --- Constants (confirmed mapping, column_map.md / decisions D-005, D-013) ---

# Target species -> zero-padded 3-char SVSPP code. Used by task 2.4.
TARGET_SPECIES = {
    "longfin_squid": "503",
    "summer_flounder": "103",
    "black_sea_bass": "141",
    "scup": "143",
    "silver_hake": "072",
    "atlantic_cod": "073",
}

# Season to keep (FALL survey only), joined from CRUISES on CRUISE6.
SEASON = "FALL"
# First survey year to keep (vessel change in 2009; decision D-005).
MIN_YEAR = 2009

# Canonical tows.csv columns, in order.
TOW_COLUMNS = [
    "ID",
    "EST_YEAR",
    "DECDEG_BEGLAT",
    "DECDEG_BEGLON",
    "AVGDEPTH",
    "BOTTEMP",
]
# Fields a usable tow must have (year + lat + lon + depth + bottom temp).
REQUIRED_FIELDS = [
    "EST_YEAR",
    "DECDEG_BEGLAT",
    "DECDEG_BEGLON",
    "AVGDEPTH",
    "BOTTEMP",
]


# --- Loaders ----------------------------------------------------------------


def load_survey(survey_dir: str = SURVEY_DIR):
    """Load the station (SVSTA) and catch (SVCAT) tables.

    Returns (stations, catch) as DataFrames. SVSPP in catch is read as a string so
    zero-padded codes like "072" survive (column_map.md FLAG 4).
    """
    # The survey CSVs carry free-text comment columns with non-UTF-8 (latin-1) bytes,
    # so read them as latin-1 to avoid decode errors on those fields.
    stations = pd.read_csv(
        SVSTA_PATH,
        dtype={"ID": str, "CRUISE6": str},
        encoding="latin-1",
        low_memory=False,
    )
    catch = pd.read_csv(
        SVCAT_PATH,
        dtype={"ID": str, "SVSPP": str},
        encoding="latin-1",
        low_memory=False,
    )
    return stations, catch


def load_cruises(cruises_path: str = CRUISES_PATH) -> pd.DataFrame:
    """Load the CRUISES table (CRUISE6 -> SEASON, YEAR). CRUISE6 read as string."""
    return pd.read_csv(cruises_path, dtype={"CRUISE6": str}, encoding="latin-1")


# --- Tows table -------------------------------------------------------------


def build_tows(
    stations: pd.DataFrame,
    cruises: pd.DataFrame,
    season: str = SEASON,
    min_year: int = MIN_YEAR,
    verbose: bool = True,
) -> pd.DataFrame:
    """Build the tows table: fall tows from `min_year` onward with the six canonical
    columns, dropping any tow missing year, lat, lon, depth or bottom temperature.

    Reports the row count before and after every filter, and how many rows were
    dropped for each required field. Returns a DataFrame with TOW_COLUMNS.
    """

    def log(msg: str) -> None:
        if verbose:
            print(msg)

    n_all = len(stations)
    log(f"[tows] all SVSTA station rows: {n_all}")

    # --- Filter 1: FALL tows, via CRUISES.SEASON joined on CRUISE6 (D-013) ---
    # SVSTA has no SEASON column and spans all seasons/years back to 1963, so we must
    # restrict to fall cruises explicitly.
    fall_cruise6 = set(
        cruises.loc[cruises["SEASON"] == season, "CRUISE6"].astype(str)
    )
    is_fall = stations["CRUISE6"].astype(str).isin(fall_cruise6)
    fall = stations.loc[is_fall].copy()
    n_fall = len(fall)
    log(
        f"[tows] after SEASON == '{season}' (join on CRUISE6): {n_fall} "
        f"(removed {n_all - n_fall} non-fall rows)"
    )

    # --- Filter 2: year >= min_year (D-005) ---
    year = pd.to_numeric(fall["EST_YEAR"], errors="coerce")
    year_ok = year >= min_year
    recent = fall.loc[year_ok].copy()
    n_recent = len(recent)
    log(
        f"[tows] after EST_YEAR >= {min_year}: {n_recent} "
        f"(removed {n_fall - n_recent} rows earlier than {min_year} "
        f"or with unparseable year)"
    )

    # --- Keep only the canonical columns ---
    tows = recent[TOW_COLUMNS].copy()

    # Coerce the numeric fields so blanks/bad values become NaN and are caught below.
    tows["EST_YEAR"] = pd.to_numeric(tows["EST_YEAR"], errors="coerce").astype("Int64")
    for col in ["DECDEG_BEGLAT", "DECDEG_BEGLON", "AVGDEPTH", "BOTTEMP"]:
        tows[col] = pd.to_numeric(tows[col], errors="coerce")

    # --- Filter 3: drop tows missing any required field; report per field ---
    n_before_drop = len(tows)
    missing_counts = {f: int(tows[f].isna().sum()) for f in REQUIRED_FIELDS}
    log("[tows] rows missing each required field (before dropping):")
    for field, count in missing_counts.items():
        log(f"         {field:>14}: {count}")

    complete = tows.dropna(subset=REQUIRED_FIELDS).copy()
    n_after_drop = len(complete)
    log(
        f"[tows] after dropping tows missing any required field: {n_after_drop} "
        f"(removed {n_before_drop - n_after_drop} rows)"
    )

    # Final tidy: year back to plain int, stable sort by year then ID.
    complete["EST_YEAR"] = complete["EST_YEAR"].astype(int)
    complete = complete.sort_values(["EST_YEAR", "ID"]).reset_index(drop=True)

    return complete


def tows_per_year(tows: pd.DataFrame) -> pd.Series:
    """Return a Series of tow counts per EST_YEAR, sorted by year."""
    return tows["EST_YEAR"].value_counts().sort_index()


def save_tows(tows: pd.DataFrame, path: str = TOWS_PATH) -> None:
    """Write the tows table to CSV (no index)."""
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tows.to_csv(path, index=False)


# --- Script entry point -----------------------------------------------------


def main() -> None:
    print("=== Shifting Grounds: build tows table (task 2.3) ===")
    stations, _catch = load_survey()
    cruises = load_cruises()

    tows = build_tows(stations, cruises)

    save_tows(tows)
    print(f"[tows] saved {len(tows)} rows to {TOWS_PATH}")
    print(f"[tows] columns: {list(tows.columns)}")

    print("[tows] tows per year:")
    for year, count in tows_per_year(tows).items():
        print(f"         {year}: {count}")


if __name__ == "__main__":
    main()
