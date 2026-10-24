"""Unit tests for task 8.1: the raw habitat-suitability heatmap layer.

Covers the pure helpers in app.py (no Streamlit, no server needed):
- suitability_for: selects the right rows for a species + warming delta, one row per
  real cell, with values in [0, 1] read straight from grid_predictions.csv.
- _suitability_to_color: the sequential light->dark ramp (endpoints + monotonic).
- format_tooltip_suitability: honest "probability of presence, not a population" label.
- build_map: the "Habitat suitability (toggle)" layer is present in the rendered HTML
  and its FeatureGroup is created with show=False (unchecked by default), coexisting
  with the default-visible change layer and the wind lease layer.
"""

import os
import sys

import numpy as np
import pandas as pd
import pytest

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)

import app  # noqa: E402


@pytest.fixture(scope="module")
def grid_preds():
    return app.load_grid_predictions()


@pytest.fixture(scope="module")
def leases():
    return app.load_lease_outlines()


# --- suitability_for --------------------------------------------------------


def test_suitability_for_returns_expected_columns(grid_preds):
    out = app.suitability_for(grid_preds, "summer_flounder", 1)
    assert list(out.columns) == ["lat_cell", "lon_cell", "suitability"]
    assert len(out) > 0


def test_suitability_values_in_unit_interval(grid_preds):
    for species in app.SPECIES_ORDER:
        for delta in app.SWEEP_DELTAS:
            out = app.suitability_for(grid_preds, species, delta)
            vals = out["suitability"].astype(float)
            assert ((vals >= 0.0) & (vals <= 1.0)).all(), (species, delta)


def test_suitability_for_selects_correct_species_and_delta(grid_preds):
    species, delta = "black_sea_bass", 2
    out = app.suitability_for(grid_preds, species, delta)
    # Cross-check against a direct filter of the raw frame.
    expected = grid_preds.loc[
        (grid_preds["species"] == species) & (grid_preds["delta"] == delta)
    ]
    assert len(out) == len(expected)
    # One row per real cell: no duplicate cell corners.
    assert not out.duplicated(subset=["lat_cell", "lon_cell"]).any()


def test_suitability_for_matches_raw_values(grid_preds):
    species, delta = "scup", 0
    out = app.suitability_for(grid_preds, species, delta)
    raw = grid_preds.loc[
        (grid_preds["species"] == species) & (grid_preds["delta"] == delta)
    ]
    merged = out.merge(
        raw[["lat_cell", "lon_cell", "suitability"]],
        on=["lat_cell", "lon_cell"],
        suffixes=("_got", "_raw"),
    )
    assert len(merged) == len(out)
    assert np.allclose(
        merged["suitability_got"].astype(float),
        merged["suitability_raw"].astype(float),
    )


def test_suitability_for_empty_for_unknown_species(grid_preds):
    out = app.suitability_for(grid_preds, "not_a_species", 1)
    assert out.empty


# --- _suitability_to_color --------------------------------------------------


def test_color_endpoints_are_ramp_stops():
    assert app._suitability_to_color(0.0) == "#ffffcc"
    assert app._suitability_to_color(1.0) == "#bd0026"


def test_color_clamps_and_handles_nan():
    assert app._suitability_to_color(-0.5) == "#ffffcc"  # clamped to 0
    assert app._suitability_to_color(2.0) == "#bd0026"   # clamped to 1
    assert app._suitability_to_color(np.nan) == "#cccccc"
    assert app._suitability_to_color(None) == "#cccccc"


def test_color_is_a_valid_hex_across_range():
    for s in np.linspace(0, 1, 21):
        c = app._suitability_to_color(float(s))
        assert len(c) == 7 and c.startswith("#")
        int(c[1:], 16)  # parses as hex


def test_color_darkens_with_suitability():
    # Perceived darkness (sum of channels falls) should drop from low to high suitability.
    def brightness(hexc):
        return sum(int(hexc[i : i + 2], 16) for i in (1, 3, 5))

    assert brightness(app._suitability_to_color(0.1)) > brightness(
        app._suitability_to_color(0.9)
    )


# --- format_tooltip_suitability ---------------------------------------------


def test_tooltip_is_honest_probability_not_population():
    html = app.format_tooltip_suitability(0.42)
    assert "Habitat suitability: 0.42" in html
    assert "probability of presence" in html
    assert "not a population estimate" in html


def test_tooltip_handles_missing():
    html = app.format_tooltip_suitability(np.nan)
    assert "n/a" in html


# --- build_map: layer present, off by default, coexists ---------------------


def test_build_map_includes_suitability_layer_off_by_default(grid_preds, leases):
    species, delta = "summer_flounder", 1
    grid_change = app.grid_change_for(grid_preds, species, delta)
    grid_suit = app.suitability_for(grid_preds, species, delta)
    fmap = app.build_map(
        leases, grid_change, selected_lease_id=None, grid_suitability=grid_suit
    )
    html = fmap.get_root().render()

    # The new suitability layer name is in the rendered LayerControl/overlay HTML.
    assert "Habitat suitability (toggle)" in html
    # The existing change layer and the lease layer still coexist.
    assert "Habitat change (toggle)" in html
    assert "Wind lease areas" in html

    # The suitability FeatureGroup must be created with show=False (unchecked default),
    # while the change layer stays show=True. Inspect the folium object tree.
    import folium

    feature_groups = {
        child.layer_name: child
        for child in fmap._children.values()
        if isinstance(child, folium.FeatureGroup)
    }
    assert "Habitat suitability (toggle)" in feature_groups
    assert feature_groups["Habitat suitability (toggle)"].show is False
    assert feature_groups["Habitat change (toggle)"].show is True


def test_build_map_without_suitability_is_backward_compatible(grid_preds, leases):
    # Omitting grid_suitability keeps the original two-layer map (no new layer, no crash).
    species, delta = "scup", 2
    grid_change = app.grid_change_for(grid_preds, species, delta)
    fmap = app.build_map(leases, grid_change, selected_lease_id=None)
    html = fmap.get_root().render()
    assert "Habitat suitability (toggle)" not in html
    assert "Habitat change (toggle)" in html


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))
