"""Shifting Grounds -- Streamlit app (task 7).

The map, selectors, lease panel and hindcast tab. This app only READS the processed
files the offline pipeline already wrote; it does no training and calls no external
service in task 7 (the SHAP plot and the DeepSeek brief are task 8 -- see the clearly
marked seams below).

Layout (design.md "## Components and Interfaces" -> app.py):
- Sidebar: species and warming scenario (+1 / +2 C) selectors. The lease-area selector
  lives in the right panel of the Map tab (task 7.3), above the lease status it drives;
  clicking a lease outline on the map selects it too, and the two stay in sync.
- A folium map via streamlit-folium: active BOEM lease outlines plus the 0.2-degree
  grid colored by the PERCENT CHANGE in habitat suitability from the +0 C baseline to
  the selected warmed scenario, for the selected species. Diverging palette centered on
  zero, with a legend.
- A lease panel: the signal (Rising / Falling / Stable / Uncertain), the numbers
  (baseline and scenario suitability, percent change), the NOAA revenue value (or the
  literal "no data"), and the fixed suggestion text -- all from lease_signals.csv.
- Tabs: the map, and a hindcast tab for the selected species (scatter of predicted vs
  observed along-shelf shift for all six species, 1:1 line, selected species highlighted,
  its depth shift shown alongside -- point estimates only, no error bars, no verdict
  coloring, per D-020).
- A footer: the uniform-warming note, the exact line "Shows change in fishing overlap,
  not harm to fish", and the three data credits (workflow.md guardrail).

Everything that loads data or builds a figure lives in a plain importable function so the
pipeline can be smoke-tested headlessly with `python -c "..."` without starting a server.

Data read (all written by tasks 2-6):
- data/processed/lease_signals.csv  -- per (lease, species, scenario) signal + numbers
                                       + revenue + suggestion (540 rows).
- data/processed/grid_predictions.csv -- per (cell, species, scenario) suitability.
- data/processed/hindcast.csv       -- per-species predicted/observed shift (point est.).
BOEM lease outlines come from src/overlap.py's load_leases() (reprojected back to lon/lat
for folium).
"""

from __future__ import annotations

import os
import sys

import pandas as pd

# Make the sibling src/ package importable (load_leases, paths, species list).
REPO_ROOT = os.path.dirname(os.path.abspath(__file__))
SRC_DIR = os.path.join(REPO_ROOT, "src")
if SRC_DIR not in sys.path:
    sys.path.insert(0, SRC_DIR)

from overlap import (  # noqa: E402  (after sys.path tweak)
    GEOGRAPHIC_CRS,
    LEASE_SIGNALS_PATH,
    NO_REVENUE,
    load_leases,
)
from prepare_data import TARGET_SPECIES, TOWS_PATH  # noqa: E402
from scenarios import CELL, GRID_PREDICTIONS_PATH  # noqa: E402

# --- Paths ------------------------------------------------------------------

HINDCAST_PATH = os.path.join(REPO_ROOT, "data", "processed", "hindcast.csv")

# --- Display constants ------------------------------------------------------

# Human-readable species labels for the selector, in the demo order (cold-water contrast
# last). Keys are the TARGET_SPECIES keys the processed files use.
SPECIES_LABELS = {
    "longfin_squid": "Longfin squid",
    "summer_flounder": "Summer flounder",
    "black_sea_bass": "Black sea bass",
    "scup": "Scup",
    "silver_hake": "Silver hake",
    "atlantic_cod": "Atlantic cod",
}
SPECIES_ORDER = list(SPECIES_LABELS.keys())

# Warming scenarios the app lets the user pick. +0 C is the baseline (never selectable;
# it is the reference the change is measured against), so the selector offers +1 and +2.
WARMED_DELTAS = [1, 2]

# The three REAL warming frames the model produced (grid_predictions.csv has delta in
# {0, 1, 2}). The segmented map control offers exactly these -- degrees of BOTTOM-WATER
# WARMING, not a timeline. There is no time axis: the models use only bottom temperature
# and depth (D-004/D-007), so these are "+0 C / +1 C / +2 C of warming", never years or
# dates. At +0 C every cell's change is 0 by definition (the baseline it is measured
# against); it is the default segment so the viewer starts from "no change yet".
SWEEP_DELTAS = [0, 1, 2]


# Signal -> color for the lease panel badge (not the map; the map colors by numeric
# change). Neutral, not a verdict palette -- Uncertain is grey, not red.
SIGNAL_COLORS = {
    "Rising": "#d7301f",     # warm red: overlap grows
    "Falling": "#2171b5",    # cool blue: overlap shrinks
    "Stable": "#4d9221",     # green: little change
    "Uncertain": "#808080",  # grey: not confident
}

# Diverging MAP palette for ABSOLUTE change in suitability, centered on zero. Blue =
# falling (habitat shrinks), white = ~no change, red = rising (habitat grows).
#
# The MAP colors by ABSOLUTE change = (scenario_suitability - baseline_suitability), a
# value in roughly [-1, +1]. We switched the map off percent change on purpose: percent
# change = (scenario - baseline) / baseline blows up in low-baseline cells (e.g. Atlantic
# cod, baseline suitability ~0.0002) to thousands of percent, so one tiny-baseline cell
# would saturate full red next to a real -80% neighbour. Absolute change has no
# small-denominator blow-up, so the map reads honestly as a heat surface.
#
# The LEASE PANEL still shows PERCENT change and the Rising/Falling/Stable/Uncertain
# signal (those are tied to the +/-10% thresholds in src/overlap.py); only the MAP
# coloring uses absolute change.
#
# Saturation: +/-ABS_CHANGE_SCALE suitability maps to full blue/red. This is DISPLAY ONLY
# (it only sets how colors spread, never a stored value). 0.30 keeps the map readable:
# observed absolute changes span roughly [-0.70, +0.61], so +/-0.30 gives strong color to
# meaningful shifts without a handful of extreme cells washing out the rest.
ABS_CHANGE_SCALE = 0.30  # +/-0.30 suitability maps to full color saturation

# Sequential heatmap ramp for RAW habitat suitability (task 8.1). This layer colors each
# real 0.2-degree cell by its RAW predicted suitability in [0, 1] -- the probability the
# species is present -- NOT population, abundance or fish counts (the model outputs
# P(present) only, D-004/D-007). It is a separate, optional overlay from the diverging
# blue/white/red CHANGE layer, so it uses a clean SEQUENTIAL palette (light -> dark) to
# read as "low -> high suitability" and stay visually distinct from the change surface.
#
# Palette: a light-yellow -> orange -> dark-red "YlOrRd"-style sequential ramp. 0.0 maps
# to the palest stop, 1.0 to the darkest. This is DISPLAY ONLY (it only sets how colors
# spread across the real 0-1 range); it never changes a stored value, and there is one
# value per real cell (no interpolation, same honest rule as the change layer).
SUITABILITY_RAMP = [
    (0.0, (255, 255, 204)),   # #ffffcc  pale yellow  (suitability ~0: unlikely present)
    (0.25, (254, 217, 118)),  # #fed976  light orange
    (0.5, (253, 141, 60)),    # #fd8d3c  orange
    (0.75, (240, 59, 32)),    # #f03b20  red-orange
    (1.0, (189, 0, 38)),      # #bd0026  dark red     (suitability ~1: likely present)
]

# The exact caption for the hindcast scatter (task 7 bullet; must not be reworded).
HINDCAST_CAPTION = (
    "Trained on 2009\u20132015 only, then compared with what the survey saw from 2019 "
    "on. Point estimates; small shifts may be noise."
)

# --- Footer text (workflow.md guardrail; design.md "Known limits" + credits) ----
# The uniform-warming note, the fixed overlap-not-harm line, and the three data credits.
# These strings are part of the spec contract and must not be reworded.
FOOTER_WARMING_NOTE = (
    "Scenarios add the same warming everywhere. That is a simplification; real warming "
    "is uneven."
)
FOOTER_OVERLAP_NOTE = "Shows change in fishing overlap, not harm to fish."
FOOTER_CREDITS = [
    "Survey data: NOAA Fisheries, Northeast Fisheries Science Center bottom trawl survey.",
    "Lease areas: Bureau of Ocean Energy Management.",
    "Fishing revenue: NOAA Fisheries, Greater Atlantic Regional Fisheries Office.",
]


# ---------------------------------------------------------------------------
# Data loading (importable, cached in the app)
# ---------------------------------------------------------------------------


def load_lease_signals(path: str = LEASE_SIGNALS_PATH) -> pd.DataFrame:
    """Load lease_signals.csv (the per-(lease, species, scenario) signal table).

    svspp is kept as a string (zero-padded code). ``avg_value`` is an object column that
    is either a float (a real 5-year average) or the literal string "no data"; we do NOT
    coerce it to numeric so the "no data" sentinel survives (D-021).
    """
    return pd.read_csv(path, dtype={"svspp": str, "avg_value": str})


def load_grid_predictions(path: str = GRID_PREDICTIONS_PATH) -> pd.DataFrame:
    """Load grid_predictions.csv (per-cell, per-species, per-scenario suitability)."""
    return pd.read_csv(path, dtype={"svspp": str})


def load_hindcast(path: str = HINDCAST_PATH) -> pd.DataFrame:
    """Load hindcast.csv (one row per species, point-estimate shifts)."""
    return pd.read_csv(path, dtype={"svspp": str})


def load_lease_outlines():
    """Load BOEM lease outlines as a lon/lat GeoDataFrame for folium.

    Reuses src/overlap.py's load_leases() (which dissolves to one polygon per lease and
    returns the equal-area CRS) and reprojects back to EPSG:4326 for the web map.
    """
    leases = load_leases()
    return leases.to_crs(GEOGRAPHIC_CRS)


# ---------------------------------------------------------------------------
# Grid-change table (map coloring)
# ---------------------------------------------------------------------------


def grid_change_for(
    grid_preds: pd.DataFrame, species: str, delta: int
) -> pd.DataFrame:
    """Per-cell change in suitability for one species, +0 C -> +delta C.

    Returns one row per grid cell with its lower-left corner (lat_cell, lon_cell), the
    baseline (+0 C) and scenario (+delta C) suitability, and BOTH change measures:

    - ``abs_change`` = scenario - baseline, in roughly [-1, +1]. This is what the MAP
      colors by (no small-denominator blow-up).
    - ``change`` = (scenario - baseline) / baseline -- the percent change (as a fraction),
      matching the lease-signal definition. Shown in the tooltip (annotated). Cells whose
      baseline is zero give an undefined percent (NaN); their absolute change is still
      defined, so they are still colored, and the tooltip flags the percent as n/a.
    """
    sub = grid_preds.loc[grid_preds["species"] == species]
    base = sub.loc[sub["delta"] == 0, ["lat_cell", "lon_cell", "suitability"]].rename(
        columns={"suitability": "baseline"}
    )
    scen = sub.loc[sub["delta"] == delta, ["lat_cell", "lon_cell", "suitability"]].rename(
        columns={"suitability": "scenario"}
    )
    merged = base.merge(scen, on=["lat_cell", "lon_cell"], how="inner")
    import numpy as np

    # Absolute change drives the map coloring (bounded, no blow-up).
    merged["abs_change"] = merged["scenario"] - merged["baseline"]
    # Percent change (fraction) for the tooltip. Zero baseline -> inf -> undefined (NaN).
    pct = (merged["scenario"] - merged["baseline"]) / merged["baseline"]
    merged["change"] = pct.replace([np.inf, -np.inf], np.nan)
    return merged


def suitability_for(
    grid_preds: pd.DataFrame, species: str, delta: int
) -> pd.DataFrame:
    """Per-cell RAW habitat suitability for one species at one warming delta.

    Selects the rows for the given species and warming segment (delta in {0, 1, 2}) and
    returns one row per real 0.2-degree cell with its lower-left corner (lat_cell,
    lon_cell) and the model's RAW predicted suitability -- the probability the species is
    present, in [0, 1]. This is read straight from grid_predictions.csv's ``suitability``
    column (task 8.1): no retraining, no derived math, one value per real cell.

    NOTE: ``suitability`` is P(present), NOT population, abundance or a fish count.
    """
    sub = grid_preds.loc[
        (grid_preds["species"] == species) & (grid_preds["delta"] == delta),
        ["lat_cell", "lon_cell", "suitability"],
    ]
    return sub.reset_index(drop=True)


def _change_to_color(abs_change: float) -> str:
    """Map an ABSOLUTE suitability change to a diverging blue-white-red hex color.

    Negative (falling) -> blue, ~0 -> white, positive (rising) -> red, saturating at
    +/-ABS_CHANGE_SCALE. NaN (undefined, shouldn't happen for absolute change) -> grey.
    """
    if abs_change is None or pd.isna(abs_change):
        return "#cccccc"
    t = max(-1.0, min(1.0, float(abs_change) / ABS_CHANGE_SCALE))
    if t >= 0:  # white -> red
        r, g, b = 255, int(255 * (1 - t)), int(255 * (1 - t))
    else:  # white -> blue
        s = -t
        r, g, b = int(255 * (1 - s)), int(255 * (1 - s)), 255
    return f"#{r:02x}{g:02x}{b:02x}"


# Percent-change display cap for the MAP TOOLTIP only. Tiny-baseline cells produce raw
# percents in the thousands (e.g. +6809% when baseline suitability is near zero), which
# is honest but unreadable as a headline. We cap the HEADER at "250%+" and, only when
# capped, add a small-font footer explaining the near-zero baseline is why the percent is
# so large. The body still shows the exact baseline -> scenario values and absolute
# change, so the real numbers are always right there. This caps DISPLAY only; it never
# touches the map's absolute-change coloring, the lease panel's percent/signal, or the
# +/-10% signal thresholds in src/overlap.py. Suitability is bounded [0, 1], so the most
# negative percent is about -100%; negatives are shown in full (no negative cap).
TOOLTIP_PCT_CAP = 2.5  # 250%


def format_tooltip_change(baseline, scenario, abs_change, pct_change) -> str:
    """Build the annotated per-cell map tooltip (folium accepts HTML).

    Layout:
    - HEADER (bold, larger): the PERCENT change, the most prominent line. Capped at
      "250%+" when the real percent exceeds +TOOLTIP_PCT_CAP (e.g. a near-zero baseline
      cell whose real percent is +6809% shows "250%+"). At or below the cap the real
      signed percent is shown (e.g. "-20%", "+140%"). Undefined percent (zero baseline)
      shows "n/a".
    - BODY: the baseline -> scenario suitability and the absolute change (Δ) -- the
      context, with the real numbers so the viewer sees where the percent comes from.
    - FOOTER (small, grey): ONLY present when the header was capped; a short note that
      the baseline suitability is near zero, so a small absolute rise is a huge percent.

    Examples:
    - normal:  header "-20%",  body "Suitability 0.500 -> 0.400 (Δ -0.100)", no footer.
    - capped:  header "250%+", body "Suitability 0.000 -> 0.052 (Δ +0.052)", footer
      "Large % -- baseline suitability is near zero".
    """
    b = "n/a" if pd.isna(baseline) else f"{float(baseline):.3f}"
    s = "n/a" if pd.isna(scenario) else f"{float(scenario):.3f}"
    d = "n/a" if pd.isna(abs_change) else f"{float(abs_change):+.3f}"

    capped = False
    if pct_change is None or pd.isna(pct_change):
        header = "n/a"
    else:
        p = float(pct_change)
        if p > TOOLTIP_PCT_CAP:
            # Cap the headline magnitude; the real numbers live in the body + footer.
            header = f"{TOOLTIP_PCT_CAP:.0%}+"
            capped = True
        else:
            header = f"{p:+.0%}"

    header_html = (
        f"<span style='font-weight:700;font-size:1.15em'>{header}</span>"
    )
    body_html = (
        f"<span>Suitability {b} \u2192 {s} (\u0394 {d})</span>"
    )
    parts = [header_html, body_html]
    if capped:
        parts.append(
            "<span style='font-size:0.8em;color:#666'>"
            "Large % \u2014 baseline suitability is near zero</span>"
        )
    return "<br>".join(parts)


def _suitability_to_color(suitability: float) -> str:
    """Map a RAW suitability in [0, 1] to a sequential light->dark hex color.

    Interpolates along SUITABILITY_RAMP (pale yellow at 0 -> dark red at 1). This is a
    DISPLAY-ONLY mapping of the stored probability to a color; it never changes a value.
    NaN / missing -> grey. Values are clamped to [0, 1] (suitability is a probability).
    """
    if suitability is None or pd.isna(suitability):
        return "#cccccc"
    t = max(0.0, min(1.0, float(suitability)))
    stops = SUITABILITY_RAMP
    for i in range(len(stops) - 1):
        t0, c0 = stops[i]
        t1, c1 = stops[i + 1]
        if t <= t1:
            # Linear interpolation within this segment.
            f = 0.0 if t1 == t0 else (t - t0) / (t1 - t0)
            r = int(round(c0[0] + (c1[0] - c0[0]) * f))
            g = int(round(c0[1] + (c1[1] - c0[1]) * f))
            b = int(round(c0[2] + (c1[2] - c0[2]) * f))
            return f"#{r:02x}{g:02x}{b:02x}"
    r, g, b = stops[-1][1]
    return f"#{r:02x}{g:02x}{b:02x}"


def format_tooltip_suitability(suitability) -> str:
    """Build the per-cell tooltip for the RAW habitat-suitability layer (HTML).

    Honest labeling (task 8.1): the number is the model's predicted PROBABILITY OF
    PRESENCE in [0, 1], NOT population, abundance or a fish count. Example output:
    "Habitat suitability: 0.42 (probability of presence)".
    """
    if suitability is None or pd.isna(suitability):
        val = "n/a"
    else:
        val = f"{float(suitability):.2f}"
    return (
        f"<span style='font-weight:700'>Habitat suitability: {val}</span>"
        "<br><span style='font-size:0.85em;color:#555'>"
        "probability of presence (0\u20131), not a population estimate</span>"
    )


# ---------------------------------------------------------------------------
# Map (folium)
# ---------------------------------------------------------------------------


def build_map(
    leases,
    grid_change: pd.DataFrame,
    selected_lease_id: str | None = None,
    grid_suitability: pd.DataFrame | None = None,
):
    """Build the folium map: a smoother habitat-change surface under bold lease areas.

    Layering (bottom to top): OpenStreetMap basemap, then the habitat-change grid, then
    an OPTIONAL raw habitat-suitability grid (off by default), then the wind lease areas
    drawn as the bold foreground. A LayerControl lets the user hide the change grid or
    opt into the suitability grid independently while the leases stay visible.

    Raw habitat-suitability layer (task 8.1, optional overlay -- OFF by default):
    - When ``grid_suitability`` is provided (one row per real 0.2-degree cell with
      lat_cell/lon_cell/suitability for the selected species + warming segment), an
      ADDITIONAL FeatureGroup "Habitat suitability (toggle)" is added, created with
      show=False so it is UNCHECKED by default. The viewer opts in from the layer
      control; the change layer stays the default-visible one.
    - Each cell is colored by its RAW suitability in [0, 1] (probability of presence)
      with a SEQUENTIAL light->dark ramp (SUITABILITY_RAMP), distinct from the diverging
      change ramp. Honest labeling: the tooltip states it is predicted suitability
      (probability of presence), NOT population, abundance or fish counts. Same honest
      no-interpolation rule as the change layer: one value per real cell; the display-only
      blur pane and fill pad are reused for a consistent smooth look.

    Habitat grid (honest, no interpolation):
    - Each real 0.2-degree cell (lower-left corner at lat_cell/lon_cell) is still drawn as
      exactly ONE rectangle carrying ONE computed value from grid_predictions.csv. We do
      NOT interpolate or invent sub-cell values. The cell is colored by its ABSOLUTE
      change in suitability (bounded ~[-1, +1]); its tooltip shows baseline, scenario,
      absolute change and the (annotated) percent change.
    - The "smoother heat surface" look is purely a DISPLAY effect: the grid sits in a
      dedicated map pane with a stronger CSS blur so the hard spreadsheet edges feather
      and adjacent cells blend at their shared edges, reading as one smooth surface. Each
      rectangle is also drawn slightly LARGER than its real cell (a visual-only halo) and
      with a soft matching-hue stroke, so neighbouring fills overlap just at the edges and
      the seam between them dissolves. This overlaps only the VISUAL FILL, never the data:
      every rectangle's tooltip and its real 0.2-degree bounds are unchanged, no value is
      moved into a neighbour's cell, and nothing is spatially interpolated.

    Wind lease areas (bold foreground):
    - Drawn ABOVE the grid with a strong dark outline and a soft halo (a wide, faint
      under-stroke) so they read as the focus against both the basemap and the colored
      grid. The selected lease is thicker, filled and highlighted.

    Returns a folium.Map. folium is imported lazily so the module (and its data
    functions) can be smoke-tested without folium side effects at import time.
    """
    import folium
    from folium.map import CustomPane

    # Center on the survey area (roughly the Mid-Atlantic to Gulf of Maine shelf).
    fmap = folium.Map(location=[40.5, -71.0], zoom_start=6, tiles="OpenStreetMap")

    # A dedicated pane for the grid, sitting just above the basemap tiles (overlayPane is
    # z-index 400) but below the lease shapes, with a CSS blur so the cell edges feather.
    # The blur is a DISPLAY-ONLY softening of how the fixed-size cells LOOK; it does not
    # interpolate, resample or shift any cell's value (each cell is still one rectangle).
    grid_pane = CustomPane(
        name="grid_pane",
        z_index=410,
        pointer_events=True,
    )
    grid_pane.add_to(fmap)
    # Apply a STRONGER feathering blur to just this pane (not the basemap or the leases),
    # so adjacent cells blend smoothly at their shared edges and the grid reads as one
    # heat surface rather than hard tiles. This is DISPLAY-ONLY softening of how the
    # fixed-size cells LOOK; it does not interpolate, resample or shift any cell's value
    # (each cell is still one rectangle anchored to its real 0.2-degree bounds).
    blur_css = folium.Element(
        "<style>.leaflet-grid_pane-pane{filter:blur(11px);opacity:0.95;}</style>"
    )
    fmap.get_root().header.add_child(blur_css)
    # Visual-only edge overlap: draw each fill rectangle slightly larger than its real
    # cell so neighbouring fills meet and the seam dissolves under the blur. The data
    # bounds are the real cell; this pad only widens the drawn fill, never the value.
    FILL_PAD = CELL * 0.18  # ~0.036 deg of visual overlap on each side

    # --- Habitat-change grid (smoother look, one value per real cell) --------
    grid_layer = folium.FeatureGroup(name="Habitat change (toggle)", show=True)
    for _, row in grid_change.iterrows():
        lat, lon = float(row["lat_cell"]), float(row["lon_cell"])
        abs_change = row["abs_change"]
        color = _change_to_color(abs_change)  # MAP colors by absolute change
        tip = format_tooltip_change(
            row["baseline"], row["scenario"], abs_change, row["change"]
        )
        folium.Rectangle(
            # The drawn FILL is padded slightly beyond the real cell so neighbouring
            # fills overlap at their edges and blend under the blur. This is visual only:
            # the value, the tooltip and the real 0.2-degree cell it describes are
            # unchanged, and no value is resampled or interpolated into another cell.
            bounds=[
                [lat - FILL_PAD, lon - FILL_PAD],
                [lat + CELL + FILL_PAD, lon + CELL + FILL_PAD],
            ],
            color=color,       # soft edge the same hue as the fill (no hard black border)
            weight=1,
            opacity=0.0,       # the stroke itself is invisible; the pane blur feathers it
            fill=True,
            fill_color=color,
            fill_opacity=0.42,  # lower than before so OSM labels + lease outlines show
            pane="grid_pane",
            tooltip=tip,
        ).add_to(grid_layer)
    grid_layer.add_to(fmap)

    # --- Raw habitat-suitability grid (task 8.1, OPTIONAL overlay, OFF by default) ---
    # An ADDITIONAL toggleable layer that colors each real cell by its RAW predicted
    # suitability (probability of presence, 0-1) for the selected species + warming
    # segment, with a SEQUENTIAL ramp distinct from the diverging change ramp above. It
    # is created with show=False so it is UNCHECKED by default: the viewer opts in, and
    # the change layer stays the default-visible one. One value per real cell (no
    # interpolation); it reuses the same blur pane + fill pad for a consistent look.
    if grid_suitability is not None and not grid_suitability.empty:
        suit_layer = folium.FeatureGroup(
            name="Habitat suitability (toggle)", show=False
        )
        for _, row in grid_suitability.iterrows():
            lat, lon = float(row["lat_cell"]), float(row["lon_cell"])
            suit = row["suitability"]
            color = _suitability_to_color(suit)
            folium.Rectangle(
                bounds=[
                    [lat - FILL_PAD, lon - FILL_PAD],
                    [lat + CELL + FILL_PAD, lon + CELL + FILL_PAD],
                ],
                color=color,
                weight=1,
                opacity=0.0,
                fill=True,
                fill_color=color,
                fill_opacity=0.55,
                pane="grid_pane",
                tooltip=format_tooltip_suitability(suit),
            ).add_to(suit_layer)
        suit_layer.add_to(fmap)

    # --- Wind lease areas: the bold foreground layer -------------------------
    lease_layer = folium.FeatureGroup(name="Wind lease areas", show=True)
    for _, lease in leases.iterrows():
        is_selected = (
            selected_lease_id is not None and lease["lease_id"] == selected_lease_id
        )
        geom = lease.geometry.__geo_interface__
        tip = f"{lease['lease_id']} \u2014 {lease['lease_name']}"

        # Soft halo: a wide, faint under-stroke so each lease stands off the colored grid
        # and the OSM basemap before the crisp outline is drawn over it.
        folium.GeoJson(
            geom,
            style_function=(
                lambda _f, sel=is_selected: {
                    "color": "#ffffff" if sel else "#f2f2f2",
                    "weight": 9 if sel else 6,
                    "opacity": 0.85 if sel else 0.6,
                    "fill": False,
                }
            ),
        ).add_to(lease_layer)

        # Crisp bold outline on top. The selected lease is thicker, filled and highlighted.
        folium.GeoJson(
            geom,
            style_function=(
                lambda _f, sel=is_selected: {
                    "color": "#b30000" if sel else "#111111",
                    "weight": 4 if sel else 2.5,
                    "opacity": 1.0,
                    "fill": True,
                    "fillColor": "#ff6d3a" if sel else "#111111",
                    "fillOpacity": 0.28 if sel else 0.06,
                }
            ),
            tooltip=tip,
        ).add_to(lease_layer)
    lease_layer.add_to(fmap)

    # Toggle: the grid can be hidden independently; the leases stay visible.
    folium.LayerControl(collapsed=False).add_to(fmap)
    return fmap


# ---------------------------------------------------------------------------
# Hindcast scatter (matplotlib)
# ---------------------------------------------------------------------------


def build_hindcast_figure(hindcast: pd.DataFrame, selected_species: str):
    """Scatter of predicted vs observed along-shelf shift for all six species.

    A 1:1 line (predicted == observed) is drawn; each species is a point; the selected
    species is highlighted. POINT ESTIMATES ONLY -- no error bars, no verdict coloring
    (D-020). Returns a matplotlib Figure. matplotlib is imported lazily (Agg-safe) so the
    data functions can be tested without a display.
    """
    import matplotlib

    matplotlib.use("Agg")  # headless-safe; Streamlit renders the figure object
    import matplotlib.pyplot as plt

    fig, ax = plt.subplots(figsize=(5.2, 5.0))

    pred = hindcast["pred_shelf_km"].astype(float)
    obs = hindcast["obs_shelf_km"].astype(float)

    # 1:1 reference line across the data range (predicted == observed).
    lo = float(min(pred.min(), obs.min())) - 10
    hi = float(max(pred.max(), obs.max())) + 10
    ax.plot([lo, hi], [lo, hi], color="#888888", linestyle="--", linewidth=1, zorder=1,
            label="1:1 (predicted = observed)")

    # All species as neutral points (no verdict coloring).
    ax.scatter(pred, obs, s=45, color="#888888", zorder=2)

    # Highlight the selected species and label every point.
    for _, r in hindcast.iterrows():
        sp = r["species"]
        label = SPECIES_LABELS.get(sp, sp)
        x, y = float(r["pred_shelf_km"]), float(r["obs_shelf_km"])
        if sp == selected_species:
            ax.scatter([x], [y], s=140, color="#d7301f", edgecolor="#000000",
                       linewidth=1.2, zorder=3)
            ax.annotate(label, (x, y), textcoords="offset points", xytext=(8, 6),
                        fontsize=10, fontweight="bold")
        else:
            ax.annotate(label, (x, y), textcoords="offset points", xytext=(6, 4),
                        fontsize=8, color="#555555")

    ax.axhline(0, color="#dddddd", linewidth=0.8, zorder=0)
    ax.axvline(0, color="#dddddd", linewidth=0.8, zorder=0)
    ax.set_xlabel("Predicted along-shelf shift (km, + = northeast)")
    ax.set_ylabel("Observed along-shelf shift (km, + = northeast)")
    ax.set_title("Hindcast: predicted vs observed along-shelf shift")
    ax.set_aspect("equal", adjustable="datalim")
    ax.legend(loc="lower right", fontsize=8, frameon=False)
    fig.tight_layout()
    return fig


# ---------------------------------------------------------------------------
# Lease panel helpers
# ---------------------------------------------------------------------------


def lease_panel_row(
    signals: pd.DataFrame, lease_id: str, species: str, delta: int
) -> pd.Series | None:
    """The single lease_signals row for (lease, species, warmed scenario), or None."""
    hit = signals.loc[
        (signals["lease_id"] == lease_id)
        & (signals["species"] == species)
        & (signals["delta"] == delta)
    ]
    if hit.empty:
        return None
    return hit.iloc[0]


def lease_id_from_tooltip(tooltip: str | None, valid_ids) -> str | None:
    """Resolve a clicked lease's id from the folium tooltip text, or None.

    Each lease GeoJson carries the tooltip ``"<lease_id> \u2014 <lease_name>"`` (see
    build_map). When st_folium reports a clicked object's tooltip, we split on the em
    dash, take the leading id, and only accept it if it is a known lease id. Returns
    None for a missing/blank tooltip or an id we do not recognise (so a stray click on
    the grid or basemap never selects a lease). ``valid_ids`` is the set/list of real
    lease ids.
    """
    if not tooltip:
        return None
    text = str(tooltip).strip()
    # The tooltip is "<id> \u2014 <name>"; the id is everything before the em dash.
    head = text.split("\u2014", 1)[0].strip()
    if head in set(valid_ids):
        return head
    # Some st_folium builds return only the visible text without the separator; fall
    # back to matching the first whitespace token against the known ids.
    token = text.split()[0] if text.split() else ""
    return token if token in set(valid_ids) else None


def lease_id_at_point(leases, lat, lng) -> str | None:
    """Point-in-polygon fallback: which lon/lat lease polygon contains (lat, lng)?

    ``leases`` is the lon/lat (EPSG:4326) GeoDataFrame from load_lease_outlines, so the
    folium click's lat/lng can be tested directly. Returns the first containing lease's
    id, or None when the click is outside every lease (e.g. on the grid or open water).
    """
    if lat is None or lng is None:
        return None
    try:
        from shapely.geometry import Point
    except ImportError:  # pragma: no cover - shapely is a hard dependency
        return None
    pt = Point(float(lng), float(lat))  # shapely is (x=lon, y=lat)
    hit = leases.loc[leases.geometry.contains(pt)]
    if not hit.empty:
        return str(hit.iloc[0]["lease_id"])
    # A click can land microscopically outside a border; take the nearest lease within a
    # small tolerance (in degrees; these are lon/lat polygons) so edge clicks still
    # select. The distance-in-a-geographic-CRS warning is expected and harmless here --
    # we only need a tiny relative tolerance, not an accurate metric distance.
    import warnings

    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        dist = leases.geometry.distance(pt)
    nearest = dist.idxmin()
    if float(dist.loc[nearest]) <= 0.02:  # ~2 km at this latitude
        return str(leases.loc[nearest, "lease_id"])
    return None


def resolve_clicked_lease(st_folium_return, leases, valid_ids) -> str | None:
    """Map an st_folium return dict to a clicked lease id (tooltip first, then PIP).

    Reads ``last_object_clicked_tooltip`` for the fast, reliable path (the lease GeoJson
    tooltips carry the id). If that does not resolve to a known lease, falls back to a
    point-in-polygon hit test on ``last_object_clicked`` (or ``last_clicked``) lat/lng.
    Returns None when nothing was clicked or the click was not on a lease.
    """
    if not st_folium_return:
        return None
    tip = st_folium_return.get("last_object_clicked_tooltip")
    by_tip = lease_id_from_tooltip(tip, valid_ids)
    if by_tip is not None:
        return by_tip
    click = (
        st_folium_return.get("last_object_clicked")
        or st_folium_return.get("last_clicked")
    )
    if isinstance(click, dict):
        return lease_id_at_point(leases, click.get("lat"), click.get("lng"))
    return None


def format_revenue(avg_value) -> str:
    """Format the avg_value cell for display: '$N/yr' for a number, else 'no data'.

    avg_value is either a float-like string (a real 5-year average) or the literal
    "no data" sentinel (D-021). We never turn a missing value into $0.
    """
    if avg_value is None:
        return NO_REVENUE
    text = str(avg_value).strip()
    if text == "" or text.lower() == NO_REVENUE:
        return NO_REVENUE
    try:
        return f"${float(text):,.0f}/yr"
    except (TypeError, ValueError):
        return NO_REVENUE


def format_suitability(value) -> str:
    """Format a suitability (0-1 probability) for display, or 'n/a' when missing."""
    if value is None or pd.isna(value):
        return "n/a"
    return f"{float(value):.3f}"


def format_change(value) -> str:
    """Format a percent change (fraction) as a signed percent, or 'n/a' when missing."""
    if value is None or pd.isna(value):
        return "n/a"
    return f"{float(value):+.1%}"


# ===========================================================================
# Streamlit UI (only runs when launched via `streamlit run app.py`)
# ===========================================================================


def main() -> None:
    import streamlit as st
    from streamlit_folium import st_folium

    st.set_page_config(page_title="Shifting Grounds", layout="wide")

    # Cache the processed files so reruns on selector changes are cheap.
    @st.cache_data(show_spinner=False)
    def _signals():
        return load_lease_signals()

    @st.cache_data(show_spinner=False)
    def _grid():
        return load_grid_predictions()

    @st.cache_data(show_spinner=False)
    def _hindcast():
        return load_hindcast()

    @st.cache_resource(show_spinner=False)
    def _leases():
        # GeoDataFrame: cached as a resource (not a copyable data frame).
        return load_lease_outlines()

    # --- Task 8 cached builders (SHAP figure + DeepSeek brief) --------------
    import explain  # local to main(): keeps module import side-effect-free for tests

    @st.cache_resource(show_spinner=False)
    def _temp_response_cached(species_key: str):
        """Build (and cache) the SHAP temperature-response figure for one species.

        Loads the trained model and a sample of tow features once per species. Returns
        None if the model or sample is unavailable, so the tab degrades gracefully.
        """
        import joblib

        model_path = os.path.join(REPO_ROOT, "models", f"{species_key}.joblib")
        if not os.path.exists(model_path):
            return None
        try:
            model = joblib.load(model_path)
            tows = pd.read_csv(TOWS_PATH)
            sample = tows[["BOTTEMP", "AVGDEPTH"]].dropna()
            # Sample for speed; the explainer caps its background too.
            if len(sample) > 600:
                sample = sample.sample(600, random_state=42)
            return explain.temperature_response(model, sample)
        except Exception:
            return None

    @st.cache_data(show_spinner=False)
    def _brief_cached(lease_id_: str, species_: str, delta_: int) -> str:
        """Build (and cache) the DeepSeek brief for one (lease, species, scenario).

        Cached so re-selecting the same combination does not re-call DeepSeek. The call
        itself falls back to the deterministic template on any failure, so this never
        crashes or hangs the app.
        """
        r = lease_panel_row(signals, lease_id_, species_, delta_)
        if r is None:
            return ""
        return explain.brief(r)

    signals = _signals()
    grid_preds = _grid()
    hindcast = _hindcast()
    leases = _leases()

    st.title("Shifting Grounds")
    st.caption(
        "How warming shifts commercial fish habitat, and how that changes overlap with "
        "offshore wind lease areas. A planning signal, not a verdict."
    )

    # --- Sidebar selectors --------------------------------------------------
    st.sidebar.header("Explore")

    species = st.sidebar.selectbox(
        "Species",
        options=SPECIES_ORDER,
        format_func=lambda s: SPECIES_LABELS.get(s, s),
    )
    delta = st.sidebar.selectbox(
        "Warming scenario",
        options=WARMED_DELTAS,
        format_func=lambda d: f"+{d} \u00b0C bottom temperature",
    )

    # Lease options in a stable, readable order. The lease-area SELECTOR itself lives in
    # the right panel of the Map tab (not the sidebar) as of task 7.3; here we only build
    # the option list and labels that both the dropdown and the map click resolve against.
    lease_options = (
        signals[["lease_id", "lease_name"]]
        .drop_duplicates()
        .sort_values("lease_id")
    )
    lease_ids = lease_options["lease_id"].tolist()
    lease_label = dict(zip(lease_options["lease_id"], lease_options["lease_name"]))

    # --- Selected lease: the SINGLE SOURCE OF TRUTH -------------------------
    # Both the right-panel dropdown and a map-polygon click WRITE this one non-widget
    # session_state key. Keeping it off the selectbox's own widget key is what avoids the
    # StreamlitWidgetAlreadyInstantiatedError (we never assign a widget key after the
    # widget is built): the dropdown reads it via index=, the map click reconciles it
    # BEFORE the dropdown is instantiated, and a dropdown change writes it back via
    # on_change. Default to the first lease on first load.
    if "selected_lease_id" not in st.session_state or (
        st.session_state["selected_lease_id"] not in lease_ids
    ):
        st.session_state["selected_lease_id"] = lease_ids[0]

    # --- Reconcile a map click from the PRIOR run ---------------------------
    # st_folium reports a click on the run AFTER it happened, stored under its widget key
    # (MAP_KEY). We read that stored return here, at the TOP of the map tab -- before the
    # map is rebuilt and before the dropdown is instantiated -- so the clicked lease can
    # drive both the highlight and the dropdown index on this run. We only mutate state +
    # rerun when the clicked lease actually DIFFERS from the current selection, so a click
    # (or a reselect of the already-selected lease) can never spin an infinite rerun loop.
    MAP_KEY = "lease_map"
    clicked_id = resolve_clicked_lease(
        st.session_state.get(MAP_KEY), leases, lease_ids
    )
    if clicked_id is not None and clicked_id != st.session_state["selected_lease_id"]:
        st.session_state["selected_lease_id"] = clicked_id
        # Also push the value onto the dropdown's widget key so the selectbox shows the
        # clicked lease. This is SAFE because we are still BEFORE the selectbox is
        # instantiated this run (the forbidden case -- and the earlier crash -- is
        # writing a widget key AFTER its widget exists). index= alone would not move the
        # dropdown here: once the widget key holds a value, Streamlit keeps it and
        # ignores index=, so we must set the key directly.
        st.session_state["lease_select_widget"] = clicked_id
        st.rerun()

    # The selection drives the map highlight and the panel for the rest of this run.
    lease_id = st.session_state["selected_lease_id"]

    def _on_lease_dropdown_change() -> None:
        # The dropdown writes the SINGLE SOURCE OF TRUTH from its own (separate) widget
        # key. Writing selected_lease_id here (a non-widget key) in an on_change callback
        # is safe; we never write the widget's key after it is instantiated.
        st.session_state["selected_lease_id"] = st.session_state["lease_select_widget"]

    # --- Tabs: map + lease panel, hindcast, then temperature response -------
    tab_map, tab_hindcast, tab_temp = st.tabs(
        ["Map & lease", "Hindcast", "Temperature response"]
    )

    with tab_map:
        col_map, col_panel = st.columns([3, 2])

        with col_map:
            # --- Warming control: a three-segment button bar (+0 / +1 / +2 C) --
            # A simple segmented control drives ONLY the map, so the viewer can jump
            # between the three REAL model frames and watch the habitat change. It is
            # framed as DEGREES OF WARMING, never as years or a timeline: the model has
            # no time axis (bottom temperature + depth only, D-004/D-007). The three
            # segments are the three real model outputs (SWEEP_DELTAS) -- no interpolation
            # across the warming axis, and (unchanged from 7.1) no spatial interpolation
            # between cells. There is NO autoplay and NO slider: clicking a segment jumps
            # the map straight to that frame. The sidebar "+1 / +2 C" selector still
            # drives the lease panel on the right, independently of this control.
            #
            # CSS (scoped to this control's wrapper) makes the three options read as one
            # connected button bar with the ACTIVE segment visibly PRESSED/inset: filled
            # background, inset shadow and a 1px downward nudge so it looks recessed.
            st.markdown(
                """
                <style>
                /* Scope: the segmented/radio control inside .warming-seg only. */
                .warming-seg div[role="radiogroup"],
                .warming-seg div[data-baseweb="button-group"] {
                    display: inline-flex;
                    gap: 0;
                    border: 1px solid #b9c2cc;
                    border-radius: 8px;
                    overflow: hidden;
                }
                /* Each segment: connected (shared 1px divider), flat by default. */
                .warming-seg div[role="radiogroup"] > label,
                .warming-seg button[kind],
                .warming-seg div[data-baseweb="button-group"] button {
                    margin: 0 !important;
                    border: 0 !important;
                    border-right: 1px solid #b9c2cc !important;
                    border-radius: 0 !important;
                    background: #f4f6f8 !important;
                    color: #2b3138 !important;
                    padding: 6px 18px !important;
                    box-shadow: none !important;
                    transition: background .1s ease;
                }
                .warming-seg div[role="radiogroup"] > label:last-child,
                .warming-seg div[data-baseweb="button-group"] button:last-child {
                    border-right: 0 !important;
                }
                /* ACTIVE segment: pressed/inset look (filled, recessed, nudged down). */
                .warming-seg button[aria-checked="true"],
                .warming-seg button[aria-pressed="true"],
                .warming-seg div[role="radiogroup"] > label[data-checked="true"],
                .warming-seg div[role="radiogroup"] input:checked + div {
                    background: #1f6feb !important;
                    color: #ffffff !important;
                    box-shadow: inset 0 2px 4px rgba(0,0,0,0.35) !important;
                    transform: translateY(1px);
                    font-weight: 600 !important;
                }
                </style>
                """,
                unsafe_allow_html=True,
            )

            st.markdown('<div class="warming-seg">', unsafe_allow_html=True)
            if hasattr(st, "segmented_control"):
                # Native segmented control (Streamlit >= 1.66). Default +0 C.
                sweep_delta = st.segmented_control(
                    "Warming scenario (map)",
                    options=SWEEP_DELTAS,
                    format_func=lambda d: f"+{d} \u00b0C",
                    default=SWEEP_DELTAS[0],
                    key="warming_segment",
                    help=(
                        "Degrees of bottom-water warming, not a timeline. These are the "
                        "three scenarios the model produced (+0, +1, +2 \u00b0C); there "
                        "is no year axis. +0 \u00b0C is the baseline (no change yet)."
                    ),
                )
                # A deselected segmented_control returns None; fall back to the baseline.
                if sweep_delta is None:
                    sweep_delta = SWEEP_DELTAS[0]
            else:
                # Fallback for older Streamlit: a horizontal radio styled as the bar.
                sweep_delta = st.radio(
                    "Warming scenario (map)",
                    options=SWEEP_DELTAS,
                    format_func=lambda d: f"+{d} \u00b0C",
                    index=0,
                    horizontal=True,
                    key="warming_segment",
                    help=(
                        "Degrees of bottom-water warming, not a timeline. These are the "
                        "three scenarios the model produced (+0, +1, +2 \u00b0C); there "
                        "is no year axis. +0 \u00b0C is the baseline (no change yet)."
                    ),
                )
            st.markdown("</div>", unsafe_allow_html=True)
            sweep_delta = int(sweep_delta)

            if sweep_delta == 0:
                st.subheader(
                    f"{SPECIES_LABELS[species]} \u2014 baseline (+0.0 \u00b0C, no change yet)"
                )
            else:
                st.subheader(
                    f"{SPECIES_LABELS[species]} \u2014 change at +{float(sweep_delta):.1f} \u00b0C warming"
                )

            # At +0 C the change is 0 everywhere by definition (baseline vs itself);
            # grid_change_for handles delta == 0 cleanly (scenario == baseline -> 0%).
            grid_change = grid_change_for(grid_preds, species, sweep_delta)
            # Raw habitat suitability for the SAME species + warming segment (task 8.1):
            # the optional, off-by-default overlay in the layer control. One value per
            # real cell, read straight from grid_predictions.csv (no retraining).
            grid_suitability = suitability_for(grid_preds, species, sweep_delta)
            fmap = build_map(
                leases,
                grid_change,
                selected_lease_id=lease_id,
                grid_suitability=grid_suitability,
            )
            # Capture lease clicks: st_folium returns the clicked object's tooltip (which
            # carries the lease id) and the click lat/lng. We stash the return under
            # MAP_KEY so the reconciliation at the top of the tab can read it on the NEXT
            # run and sync selected_lease_id. returned_objects is no longer [] (which
            # returned nothing) -- it now lists exactly the click fields we consume.
            st_folium(
                fmap,
                width=None,
                height=560,
                key=MAP_KEY,
                returned_objects=[
                    "last_object_clicked",
                    "last_object_clicked_tooltip",
                    "last_clicked",
                ],
            )

            st.caption(
                "Warming scenario, not a timeline \u2014 degrees of bottom-water warming "
                "(+0 / +1 / +2 \u00b0C). The model has no year axis; these are the three "
                "scenarios it produced. +0 \u00b0C is the baseline (no change yet); pick "
                "a segment to jump the map to that warming frame."
            )
            st.markdown(
                "Map color = **absolute change** in habitat suitability (scenario "
                "\u2212 baseline). Blue = suitability falls, red = rises, white \u2248 "
                "little change (saturates at \u00b10.30). Hover any cell for its "
                "baseline \u2192 scenario values and both the absolute and percent "
                "change. Wind lease areas are outlined in bold on top; the selected "
                "lease is highlighted. Use the layer control (top right) to hide the "
                "habitat grid and read the map."
            )
            st.caption(
                "Each colored patch is one real 0.2\u00b0 survey grid cell with its own "
                "computed value. The smooth blended look is display smoothing only "
                "(edge feathering); values are never interpolated or shared between "
                "cells. The lease panel on the right still reports percent change and "
                "the Rising/Falling/Stable/Uncertain signal."
            )
            st.caption(
                "Map shades by absolute change in suitability; the lease signal at "
                "right uses percent change, so a near-zero-suitability area can read "
                "'Rising' on a tiny absolute move."
            )
            st.caption(
                "Optional layer **Habitat suitability (toggle)** (off by default; turn "
                "it on from the layer control) shades each cell by the model's RAW "
                "predicted suitability for this species and warming segment on a "
                "sequential scale (pale yellow \u2248 0 \u2192 dark red \u2248 1). This "
                "is the probability the species is present (0\u20131) \u2014 **not** a "
                "population, abundance or fish-count estimate."
            )

        with col_panel:
            # --- Lease-area selector (moved here from the sidebar, task 7.3) -----
            # Sits ABOVE the lease status it controls. index= is derived from the single
            # source of truth (selected_lease_id); the dropdown writes that key back via
            # on_change (a SEPARATE widget key, lease_select_widget), so dropdown and map
            # click stay in sync without ever writing the widget key after instantiation.
            st.selectbox(
                "Lease area",
                options=lease_ids,
                index=lease_ids.index(st.session_state["selected_lease_id"]),
                format_func=lambda lid: f"{lid} \u2014 {lease_label.get(lid, '')}",
                key="lease_select_widget",
                on_change=_on_lease_dropdown_change,
                help="Pick a lease, or click its outline on the map \u2014 they stay in sync.",
            )
            # The dropdown's on_change may have updated the selection; re-read it so the
            # panel below (and this run's heading) reflect the current choice.
            lease_id = st.session_state["selected_lease_id"]

            st.subheader(f"{lease_label.get(lease_id, lease_id)}")
            st.caption(f"Lease {lease_id}")
            row = lease_panel_row(signals, lease_id, species, delta)
            if row is None:
                st.info("No signal computed for this combination.")
            else:
                signal = row["signal"]
                color = SIGNAL_COLORS.get(signal, "#808080")
                st.markdown(
                    f"<div style='display:inline-block;padding:4px 14px;border-radius:14px;"
                    f"background:{color};color:white;font-weight:600;font-size:1.05rem'>"
                    f"{signal}</div>",
                    unsafe_allow_html=True,
                )
                st.write("")

                c1, c2, c3 = st.columns(3)
                c1.metric("Baseline (+0 \u00b0C)", format_suitability(row["baseline"]))
                c2.metric(
                    f"Scenario (+{delta} \u00b0C)", format_suitability(row["scenario"])
                )
                c3.metric("Change", format_change(row["change"]))

                st.caption(
                    "Signal uses percent change (Stable within \u00b110%); the map "
                    "shades by absolute change \u2014 the two can differ where baseline "
                    "suitability is near zero."
                )

                st.metric(
                    "Avg annual fishing value (NOAA, last 5 yrs)",
                    format_revenue(row["avg_value"]),
                )

                # --- Task 8: DeepSeek brief (with template fallback) --------
                # A 2-3 sentence plain-English note built ONLY from the numbers above and
                # the fixed suggestion text (explain.brief). If the DeepSeek call fails
                # for any reason it returns the deterministic template sentence, so this
                # never crashes or hangs the app. We render it ABOVE the fixed suggestion;
                # the suggestion text is still shown in full below (the brief supplements,
                # it does not replace it).
                st.markdown("**Plain-English brief**")
                with st.spinner("Writing a short brief..."):
                    brief_text = _brief_cached(
                        lease_id, species, int(delta)
                    )
                st.write(brief_text)

                st.markdown("**Suggestion**")
                st.write(row["suggestion"])

    with tab_hindcast:
        st.subheader(f"Hindcast \u2014 {SPECIES_LABELS[species]}")
        col_fig, col_num = st.columns([3, 2])

        with col_fig:
            fig = build_hindcast_figure(hindcast, species)
            st.pyplot(fig)
            st.caption(HINDCAST_CAPTION)

        with col_num:
            hc = hindcast.loc[hindcast["species"] == species]
            if hc.empty:
                st.info("No hindcast result for this species.")
            else:
                r = hc.iloc[0]
                st.metric(
                    "Predicted along-shelf shift",
                    f"{float(r['pred_shelf_km']):+.1f} km",
                )
                st.metric(
                    "Observed along-shelf shift",
                    f"{float(r['obs_shelf_km']):+.1f} km",
                )
                st.metric(
                    "Depth shift (predicted)",
                    f"{float(r['pred_depth_m']):+.1f} m",
                    help="Positive = deeper.",
                )
                st.metric(
                    "Depth shift (observed)",
                    f"{float(r['obs_depth_m']):+.1f} m",
                    help="Positive = deeper.",
                )
                st.caption(
                    "Along-shelf axis bearing "
                    f"{float(r['axis_bearing_deg']):.1f}\u00b0 (northeast-positive). "
                    "Point estimates only."
                )

    # --- Task 8: SHAP temperature response tab ------------------------------
    with tab_temp:
        st.subheader(f"Temperature response \u2014 {SPECIES_LABELS[species]}")
        st.caption(
            "How this species' predicted habitat suitability responds across bottom "
            "temperature, holding depth at the sample median. The blue points are the "
            "SHAP contribution of bottom temperature per tow (how much it pushes "
            "suitability up or down). Shows the model's learned temperature response, "
            "not harm to fish."
        )
        fig_temp = _temp_response_cached(species)
        if fig_temp is None:
            st.info(
                "Could not build the temperature-response plot for this species "
                "(missing model or sample data)."
            )
        else:
            st.pyplot(fig_temp)

    # --- Footer -------------------------------------------------------------
    st.divider()
    st.markdown(f"**{FOOTER_OVERLAP_NOTE}**")
    st.caption(FOOTER_WARMING_NOTE)
    for credit in FOOTER_CREDITS:
        st.caption(credit)


if __name__ == "__main__":
    main()
