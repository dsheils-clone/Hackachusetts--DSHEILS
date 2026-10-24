"""Unit tests for the task 7.2 warming map control and the redesigned map tooltip.

The warming control is now a simple three-segment button bar (+0/+1/+2 C) with no
autoplay and no slider, so the old frame-stepping helpers (next_sweep_delta /
snap_sweep_delta) were removed along with the whole Play/Pause state machine. These
tests cover what remains as pure helpers in app.py (no Streamlit, no folium needed):
- SWEEP_DELTAS: the three real warming frames the segments offer.
- format_tooltip_change: the header-capped HTML tooltip (normal / capped+footer /
  zero-baseline cases).
"""

import os
import sys

import numpy as np
import pytest

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)

import app  # noqa: E402


# --- Warming segments -------------------------------------------------------


def test_sweep_deltas_are_the_three_real_frames():
    assert app.SWEEP_DELTAS == [0, 1, 2]


# --- Tooltip redesign -------------------------------------------------------


def test_tooltip_normal_negative_shows_real_percent_no_footer():
    # baseline 0.5 -> 0.4 is a -20% change, under the cap: show it in full, no footer.
    html = app.format_tooltip_change(0.5, 0.4, -0.1, -0.2)
    assert "-20%" in html
    assert "Suitability 0.500 \u2192 0.400 (\u0394 -0.100)" in html
    assert "baseline suitability is near zero" not in html
    # Header is bold/larger; no cap marker.
    assert "font-weight:700" in html
    assert "250%+" not in html


def test_tooltip_normal_positive_under_cap_shows_real_percent():
    html = app.format_tooltip_change(0.2, 0.48, 0.28, 1.4)  # +140%, under 250%
    assert "+140%" in html
    assert "250%+" not in html
    assert "baseline suitability is near zero" not in html


def test_tooltip_capped_header_and_small_footer_when_over_cap():
    # Zero-ish baseline: a tiny absolute rise is a huge percent -> cap header, add footer.
    html = app.format_tooltip_change(0.0008, 0.052, 0.0512, 63.0)  # ~+6300%
    assert "250%+" in html  # header capped
    # Body keeps the real numbers.
    assert "Suitability 0.001 \u2192 0.052 (\u0394 +0.051)" in html
    # Footer present, in a smaller grey font.
    assert "baseline suitability is near zero" in html
    assert "font-size:0.8em" in html
    assert "color:#666" in html


def test_tooltip_exactly_at_cap_is_not_capped():
    # p == 2.5 (250%) is at the cap, not over it -> real percent, no footer.
    html = app.format_tooltip_change(0.2, 0.7, 0.5, 2.5)
    assert "+250%" in html
    assert "250%+" not in html
    assert "baseline suitability is near zero" not in html


def test_tooltip_zero_baseline_undefined_percent_shows_na_no_footer():
    # Zero baseline -> percent is undefined (NaN): header "n/a", absolute change still
    # shown, and NO footer (footer only appears when the header was capped).
    html = app.format_tooltip_change(0.0, 0.052, 0.052, np.nan)
    assert "n/a" in html
    assert "Suitability 0.000 \u2192 0.052 (\u0394 +0.052)" in html
    assert "baseline suitability is near zero" not in html
    assert "250%+" not in html


def test_tooltip_cap_constant_is_250_percent():
    assert app.TOOLTIP_PCT_CAP == 2.5


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))
