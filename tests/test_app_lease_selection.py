"""Tests for task 7.3: lease-area selector moved to the right panel, and map-click
selection kept in sync with the dropdown.

Two layers:
- Pure helpers (no Streamlit): lease_id_from_tooltip, lease_id_at_point,
  resolve_clicked_lease -- how a folium click is mapped back to a lease id.
- Streamlit AppTest: the selector lives in the MAIN area (not the sidebar), selecting a
  lease updates the panel, a simulated map click updates both the selection and the
  dropdown, and reselecting the already-selected lease is a crash-free no-op (no infinite
  rerun, no StreamlitWidgetAlreadyInstantiatedError).
"""

import os
import sys

import pytest

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)

import app  # noqa: E402

MAP_KEY = "lease_map"  # must match the st_folium widget key in app.main()


# --- Fixtures ---------------------------------------------------------------


@pytest.fixture(scope="module")
def lease_ids():
    sig = app.load_lease_signals()
    return (
        sig[["lease_id", "lease_name"]]
        .drop_duplicates()
        .sort_values("lease_id")["lease_id"]
        .tolist()
    )


@pytest.fixture(scope="module")
def leases():
    return app.load_lease_outlines()


def _no_exception(at):
    # AppTest.exception is an (empty) ElementList when the run was clean; `is None` is
    # never true for it, so assert on emptiness instead.
    return len(at.exception) == 0


# --- Pure click-resolution helpers ------------------------------------------


def test_tooltip_resolves_known_lease(lease_ids):
    lid = lease_ids[0]
    assert app.lease_id_from_tooltip(f"{lid} \u2014 Some Project", lease_ids) == lid


def test_tooltip_rejects_unknown_and_blank(lease_ids):
    assert app.lease_id_from_tooltip("not a lease at all", lease_ids) is None
    assert app.lease_id_from_tooltip("", lease_ids) is None
    assert app.lease_id_from_tooltip(None, lease_ids) is None


def test_point_in_polygon_hits_containing_lease(leases, lease_ids):
    first = leases.iloc[0]
    c = first.geometry.centroid
    assert app.lease_id_at_point(leases, c.y, c.x) == first["lease_id"]


def test_point_in_polygon_misses_open_water(leases):
    # Far out in the Atlantic -- not inside (or near) any lease.
    assert app.lease_id_at_point(leases, 10.0, 10.0) is None


def test_resolve_clicked_prefers_tooltip(leases, lease_ids):
    lid = lease_ids[3]
    ret = {"last_object_clicked_tooltip": f"{lid} \u2014 x"}
    assert app.resolve_clicked_lease(ret, leases, lease_ids) == lid


def test_resolve_clicked_falls_back_to_point(leases, lease_ids):
    first = leases.iloc[0]
    c = first.geometry.centroid
    ret = {"last_object_clicked": {"lat": c.y, "lng": c.x}}
    assert app.resolve_clicked_lease(ret, leases, lease_ids) == first["lease_id"]


def test_resolve_clicked_empty_is_none(leases, lease_ids):
    assert app.resolve_clicked_lease({}, leases, lease_ids) is None
    assert app.resolve_clicked_lease(None, leases, lease_ids) is None


# --- Streamlit AppTest ------------------------------------------------------


def _fresh_app():
    from streamlit.testing.v1 import AppTest

    return AppTest.from_file(
        os.path.join(REPO_ROOT, "app.py"), default_timeout=60
    ).run()


def test_lease_selector_in_main_area_not_sidebar():
    at = _fresh_app()
    assert _no_exception(at)
    # The lease selector is in the main body...
    main_labels = [s.label for s in at.selectbox]
    assert "Lease area" in main_labels
    # ...and NOT in the sidebar (only Species + Warming scenario remain there).
    sidebar_labels = [s.label for s in at.sidebar.selectbox]
    assert "Lease area" not in sidebar_labels
    assert "Species" in sidebar_labels
    assert "Warming scenario" in sidebar_labels


def test_dropdown_selection_updates_panel(lease_ids):
    at = _fresh_app()
    assert _no_exception(at)
    first = at.session_state["selected_lease_id"]
    other = next(lid for lid in lease_ids if lid != first)

    sb = next(s for s in at.selectbox if s.label == "Lease area")
    sb.set_value(other).run()

    assert _no_exception(at)
    assert at.session_state["selected_lease_id"] == other
    # The right-panel caption reports the selected lease id.
    assert any(other in c.value for c in at.caption)


def test_map_click_updates_selection_and_dropdown(lease_ids):
    at = _fresh_app()
    first = at.session_state["selected_lease_id"]
    other = next(lid for lid in lease_ids if lid != first)

    # Simulate st_folium returning a click on `other`'s polygon (tooltip carries the id),
    # exactly as it would appear on the run after the user clicked.
    at.session_state[MAP_KEY] = {"last_object_clicked_tooltip": f"{other} \u2014 x"}
    at.run()

    assert _no_exception(at)  # no StreamlitWidgetAlreadyInstantiatedError, no crash
    assert at.session_state["selected_lease_id"] == other
    sb = next(s for s in at.selectbox if s.label == "Lease area")
    assert sb.value == other  # dropdown reflects the clicked lease


def test_reclicking_selected_lease_is_a_crash_free_noop():
    at = _fresh_app()
    sel = at.session_state["selected_lease_id"]
    # Clicking the already-selected lease must not change state or spin a rerun loop.
    at.session_state[MAP_KEY] = {"last_object_clicked_tooltip": f"{sel} \u2014 x"}
    at.run()
    assert _no_exception(at)
    assert at.session_state["selected_lease_id"] == sel


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))
