"""Shifting Grounds -- Streamlit app (task 7).

The map, selectors, lease panel and hindcast tab. This app only READS the processed
files the offline pipeline already wrote; it does no training and calls no external
service in task 7 (the SHAP plot and the DeepSeek brief are task 8 -- see the clearly
marked seams below).

Layout (design.md "## Components and Interfaces" -> app.py):
- Sidebar: species, warming scenario (+1 / +2 C) and lease selectors.
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
from prepare_data import TARGET_SPECIES  # noqa: E402
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

# Signal -> color for the lease panel badge (not the map; the map colors by numeric
# change). Neutral, not a verdict palette -- Uncertain is grey, not red.
SIGNAL_COLORS = {
    "Rising": "#d7301f",     # warm red: overlap grows
    "Falling": "#2171b5",    # cool blue: overlap shrinks
    "Stable": "#4d9221",     # green: little change
    "Uncertain": "#808080",  # grey: not confident
}

# Diverging map palette for percent change, centered on zero. Blue = falling (habitat
# shrinks), white = ~no change, red = rising (habitat grows). The scale saturates at
# +/-CHANGE_SCALE so a handful of huge percent changes don't wash out the rest.
CHANGE_SCALE = 0.30  # +/-30% maps to full color saturation

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
    """Per-cell percent change in suitability for one species, +0 C -> +delta C.

    Returns one row per grid cell with its lower-left corner (lat_cell, lon_cell), the
    baseline (+0 C) and scenario (+delta C) suitability and the percent change
    (scenario - baseline) / baseline, matching the lease-signal definition. Cells whose
    baseline is zero give an undefined change (NaN) and are carried through so the caller
    can gray them out rather than silently drop them.
    """
    sub = grid_preds.loc[grid_preds["species"] == species]
    base = sub.loc[sub["delta"] == 0, ["lat_cell", "lon_cell", "suitability"]].rename(
        columns={"suitability": "baseline"}
    )
    scen = sub.loc[sub["delta"] == delta, ["lat_cell", "lon_cell", "suitability"]].rename(
        columns={"suitability": "scenario"}
    )
    merged = base.merge(scen, on=["lat_cell", "lon_cell"], how="inner")
    # Zero baseline -> division gives inf; treat that as an undefined change (NaN) so the
    # cell is drawn grey rather than fully saturated.
    import numpy as np

    change = (merged["scenario"] - merged["baseline"]) / merged["baseline"]
    merged["change"] = change.replace([np.inf, -np.inf], np.nan)
    return merged


def _change_to_color(change: float) -> str:
    """Map a percent change (fraction) to a diverging blue-white-red hex color.

    Negative (falling) -> blue, ~0 -> white, positive (rising) -> red, saturating at
    +/-CHANGE_SCALE. NaN (undefined change, e.g. zero baseline) -> light grey.
    """
    if change is None or pd.isna(change):
        return "#cccccc"
    t = max(-1.0, min(1.0, float(change) / CHANGE_SCALE))
    if t >= 0:  # white -> red
        r, g, b = 255, int(255 * (1 - t)), int(255 * (1 - t))
    else:  # white -> blue
        s = -t
        r, g, b = int(255 * (1 - s)), int(255 * (1 - s)), 255
    return f"#{r:02x}{g:02x}{b:02x}"


# ---------------------------------------------------------------------------
# Map (folium)
# ---------------------------------------------------------------------------


def build_map(leases, grid_change: pd.DataFrame, selected_lease_id: str | None = None):
    """Build the folium map: grid cells colored by change + lease outlines.

    - Each grid cell is drawn as its 0.2-degree square (lower-left corner at
      lat_cell/lon_cell), filled by the diverging change palette.
    - Active BOEM lease outlines are drawn on top; the selected lease is highlighted.
    Returns a folium.Map. Imported lazily so the module (and its data functions) can be
    smoke-tested without folium side effects at import time.
    """
    import folium

    # Center on the survey area (roughly the Mid-Atlantic to Gulf of Maine shelf).
    fmap = folium.Map(location=[40.5, -71.0], zoom_start=6, tiles="CartoDB positron")

    # --- Grid cells colored by change ---------------------------------------
    grid_layer = folium.FeatureGroup(name="Habitat change", show=True)
    for _, row in grid_change.iterrows():
        lat, lon = float(row["lat_cell"]), float(row["lon_cell"])
        change = row["change"]
        color = _change_to_color(change)
        pct = "n/a" if pd.isna(change) else f"{change:+.0%}"
        folium.Rectangle(
            bounds=[[lat, lon], [lat + CELL, lon + CELL]],
            color=None,
            weight=0,
            fill=True,
            fill_color=color,
            fill_opacity=0.55,
            tooltip=f"Change: {pct}",
        ).add_to(grid_layer)
    grid_layer.add_to(fmap)

    # --- Lease outlines -----------------------------------------------------
    lease_layer = folium.FeatureGroup(name="Wind lease areas", show=True)
    for _, lease in leases.iterrows():
        is_selected = selected_lease_id is not None and lease["lease_id"] == selected_lease_id
        folium.GeoJson(
            lease.geometry.__geo_interface__,
            style_function=(
                (lambda _f, sel=is_selected: {
                    "color": "#111111" if sel else "#444444",
                    "weight": 3 if sel else 1,
                    "fill": False,
                })
            ),
            tooltip=f"{lease['lease_id']} \u2014 {lease['lease_name']}",
        ).add_to(lease_layer)
    lease_layer.add_to(fmap)

    folium.LayerControl(collapsed=True).add_to(fmap)
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

    # Lease options in a stable, readable order.
    lease_options = (
        signals[["lease_id", "lease_name"]]
        .drop_duplicates()
        .sort_values("lease_id")
    )
    lease_ids = lease_options["lease_id"].tolist()
    lease_label = dict(zip(lease_options["lease_id"], lease_options["lease_name"]))
    lease_id = st.sidebar.selectbox(
        "Lease area",
        options=lease_ids,
        format_func=lambda lid: f"{lid} \u2014 {lease_label.get(lid, '')}",
    )

    # --- Tabs: map + lease panel, then hindcast -----------------------------
    tab_map, tab_hindcast = st.tabs(["Map & lease", "Hindcast"])

    with tab_map:
        col_map, col_panel = st.columns([3, 2])

        with col_map:
            st.subheader(
                f"{SPECIES_LABELS[species]} \u2014 change at +{delta} \u00b0C"
            )
            grid_change = grid_change_for(grid_preds, species, delta)
            fmap = build_map(leases, grid_change, selected_lease_id=lease_id)
            st_folium(fmap, width=None, height=560, returned_objects=[])
            st.markdown(
                "Blue = habitat suitability falls, red = rises, white \u2248 little "
                "change (saturates at \u00b130%). Grey cells have an undefined change."
            )

        with col_panel:
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

                st.metric(
                    "Avg annual fishing value (NOAA, last 5 yrs)",
                    format_revenue(row["avg_value"]),
                )

                st.markdown("**Suggestion**")
                st.write(row["suggestion"])

                # --- Task 8 seam: DeepSeek brief ----------------------------
                # Task 8 will call explain.brief(row) here (DeepSeek, with the template
                # fallback) and render a 2-3 sentence plain-English note above the
                # suggestion. Left intentionally unimplemented in task 7.

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

        # --- Task 8 seam: SHAP temperature response -------------------------
        # Task 8 will add a tab (or section) with each species' SHAP bottom-temperature
        # response plot. Left intentionally unimplemented in task 7.

    # --- Footer -------------------------------------------------------------
    st.divider()
    st.markdown(f"**{FOOTER_OVERLAP_NOTE}**")
    st.caption(FOOTER_WARMING_NOTE)
    for credit in FOOTER_CREDITS:
        st.caption(credit)


if __name__ == "__main__":
    main()
