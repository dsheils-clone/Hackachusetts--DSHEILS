"""Tests for the task 8.1 UX fix: Streamlit map-layer toggles backed by session state.

The folium in-map LayerControl was removed because st_folium cannot read the Leaflet
control's toggle state back, so every rerun (e.g. changing the warming segment) reset
the user's manual layer toggles to their defaults. Streamlit checkboxes keyed into
session_state now drive each FeatureGroup's ``show=`` flag, so the choices persist.

Two layers of coverage:
- build_map honors show_change / show_leases / show_suitability (pure, no Streamlit).
- Streamlit AppTest: the three toggle keys default to on/on/off, and turning the
  suitability toggle ON then changing the warming segment leaves it ON (visibility
  persists across a temperature change), crash-free (no StreamlitWidgetAlready-
  InstantiatedError), with build_map receiving the persisted flags.
"""

import os
import sys

import pytest

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)

import app  # noqa: E402


# --- Fixtures ---------------------------------------------------------------


@pytest.fixture(scope="module")
def grid_preds():
    return app.load_grid_predictions()


@pytest.fixture(scope="module")
def leases():
    return app.load_lease_outlines()


def _feature_groups(fmap):
    import folium

    return {
        child.layer_name: child
        for child in fmap._children.values()
        if isinstance(child, folium.FeatureGroup)
    }


# --- build_map honors the show_* flags --------------------------------------


def test_build_map_defaults_preserve_original_behavior(grid_preds, leases):
    species, delta = "summer_flounder", 1
    grid_change = app.grid_change_for(grid_preds, species, delta)
    grid_suit = app.suitability_for(grid_preds, species, delta)
    fmap = app.build_map(leases, grid_change, grid_suitability=grid_suit)
    fgs = _feature_groups(fmap)
    # Defaults: change ON, leases ON, suitability OFF.
    assert fgs["Habitat change"].show is True
    assert fgs["Wind lease areas"].show is True
    assert fgs["Habitat suitability"].show is False


def test_build_map_show_flags_map_onto_feature_groups(grid_preds, leases):
    species, delta = "scup", 2
    grid_change = app.grid_change_for(grid_preds, species, delta)
    grid_suit = app.suitability_for(grid_preds, species, delta)
    # Flip every flag away from its default and confirm each FeatureGroup follows.
    fmap = app.build_map(
        leases,
        grid_change,
        grid_suitability=grid_suit,
        show_change=False,
        show_leases=False,
        show_suitability=True,
    )
    fgs = _feature_groups(fmap)
    assert fgs["Habitat change"].show is False
    assert fgs["Wind lease areas"].show is False
    assert fgs["Habitat suitability"].show is True


def test_build_map_no_folium_layercontrol(grid_preds, leases):
    # The in-map Leaflet LayerControl must be gone (Streamlit drives visibility now).
    import folium

    species, delta = "black_sea_bass", 1
    grid_change = app.grid_change_for(grid_preds, species, delta)
    grid_suit = app.suitability_for(grid_preds, species, delta)
    fmap = app.build_map(leases, grid_change, grid_suitability=grid_suit)
    has_layer_control = any(
        isinstance(child, folium.LayerControl) for child in fmap._children.values()
    )
    assert not has_layer_control


# --- Streamlit AppTest: toggles persist across a warming change -------------


def _fresh_app():
    from streamlit.testing.v1 import AppTest

    return AppTest.from_file(
        os.path.join(REPO_ROOT, "app.py"), default_timeout=60
    ).run()


def _no_exception(at):
    return len(at.exception) == 0


def test_toggle_keys_default_on_on_off():
    at = _fresh_app()
    assert _no_exception(at)
    assert at.session_state["layer_show_change"] is True
    assert at.session_state["layer_show_leases"] is True
    assert at.session_state["layer_show_suitability"] is False


def test_three_layer_checkboxes_present():
    at = _fresh_app()
    assert _no_exception(at)
    labels = [c.label for c in at.checkbox]
    assert "Habitat change" in labels
    assert "Wind lease areas" in labels
    assert "Habitat suitability" in labels


def test_suitability_toggle_persists_across_warming_change():
    at = _fresh_app()
    assert _no_exception(at)

    # The user turns the (off-by-default) suitability layer ON.
    suit = next(c for c in at.checkbox if c.label == "Habitat suitability")
    suit.set_value(True).run()
    assert _no_exception(at)
    assert at.session_state["layer_show_suitability"] is True

    # Now change the warming segment (the rerun that used to reset the folium layers).
    seg = at.session_state["warming_segment"]
    other = next(d for d in app.SWEEP_DELTAS if d != seg)
    at.session_state["warming_segment"] = other
    at.run()

    assert _no_exception(at)  # no StreamlitWidgetAlreadyInstantiatedError, no crash
    # The user's layer choice survived the temperature change.
    assert at.session_state["layer_show_suitability"] is True
    suit_after = next(c for c in at.checkbox if c.label == "Habitat suitability")
    assert suit_after.value is True
    # The other toggles stayed at their (unchanged) defaults.
    assert at.session_state["layer_show_change"] is True
    assert at.session_state["layer_show_leases"] is True
    # The warming segment moved as the user left it.
    assert at.session_state["warming_segment"] == other


def test_change_toggle_off_persists_across_warming_change():
    at = _fresh_app()
    assert _no_exception(at)

    # Turn the default-on change layer OFF, then change the warming segment.
    change = next(c for c in at.checkbox if c.label == "Habitat change")
    change.set_value(False).run()
    assert _no_exception(at)
    assert at.session_state["layer_show_change"] is False

    seg = at.session_state["warming_segment"]
    other = next(d for d in app.SWEEP_DELTAS if d != seg)
    at.session_state["warming_segment"] = other
    at.run()

    assert _no_exception(at)
    assert at.session_state["layer_show_change"] is False  # still off after the rerun


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))
